# SPDX-License-Identifier: GPL-3.0-or-later
"""Backend for cyan-skillfish-governor-smu (filippor's SMU branch) on BC-250 / Bazzite."""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


from .. import fmt
from .base import (
    BURST_SAMPLES_MAX, METHODS, SET_METHODS, TEMP_READS, ConfigBackup, GovernorConfig, GovernorInstallStatus,
    GpuTelemetry, PerformanceState, SafePoint, ServiceStatus,
)
from .dbus import GovernorBus
from .gpu_metrics import GpuMetrics, parse_gpu_metrics
from .process import run as _run

SERVICE_ACTIONS = ("start", "stop", "restart", "enable", "disable")
BACKUP_STAMP = "%Y%m%d-%H%M%S"
_SAFE_POINT_RE = re.compile(r"^\s*\[\[\s*safe[-_]points\s*\]\]\s*(#.*)?$")
_TABLE_RE = re.compile(r"^\s*\[")
# The active points of the governor's shipped default-config.toml (smu branch).
DEFAULT_SAFE_POINTS = ((500, 700), (1000, 800), (1175, 850), (1500, 900), (1600, 910), (1700, 920),
                       (1850, 930), (2000, 960))


@dataclass(frozen=True)
class _Key:
    field: str          # GovernorConfig attribute
    toml: str           # key in the file
    kind: str           # bool | int | float | str | opt_int (0 = key left out / commented)


# Allowed values of the "str" keys; anything else in the file keeps the default.
CHOICES: dict[str, tuple[str, ...]] = {"method": METHODS, "temp_read": TEMP_READS, "set_method": SET_METHODS}


@dataclass(frozen=True)
class _Section:
    name: str                       # canonical section header
    aliases: tuple[str, ...]        # spellings the governor also accepts
    keys: tuple[_Key, ...]
    comment: str = ""               # written above a newly created section

    def without(self, *fields: str) -> "_Section":
        return _Section(self.name, self.aliases, tuple(k for k in self.keys if k.field not in fields), self.comment)


SCHEMA: tuple[_Section, ...] = (
    _Section("gpu-usage", ("gpu-usage", "gpu_usage"), (
        _Key("fix_metrics", "fix-metrics", "bool"),
        _Key("fix_freq", "fix-freq", "bool"),
        _Key("method", "method", "str"),
        _Key("temp_read", "temp-read", "str"),
        _Key("flush_every", "flush-every", "int"),
    )),
    _Section("gpu", ("gpu",), (
        _Key("set_method", "set-method", "str"),
    ), '# "smu" (direct, default) or "kernel" (through amdgpu sysfs) to apply frequency/voltage.'),
    _Section("frequency-range", ("frequency-range", "frequency_range"), (
        _Key("freq_min", "min", "int"),
        _Key("freq_max", "max", "int"),
    ), "# MHz; 0 = no limit on that side. The governor clamps to its safe-points range."),
    _Section("timing.intervals", ("timing.intervals",), (
        _Key("sample_us", "sample", "int"),
        _Key("adjust_us", "adjust", "int"),
    ), "# µs: how often the load is sampled and how often the clock is adjusted."),
    _Section("timing", ("timing",), (
        _Key("burst_samples", "burst-samples", "opt_int"),
        _Key("down_events", "down-events", "int"),
    ), "# Samples in a row at full load before burst mode (0/missing = off); low-load events before stepping down."),
    _Section("timing.ramp-rates", ("timing.ramp-rates", "timing.ramp_rates"), (
        _Key("ramp_normal", "normal", "float"),
        _Key("ramp_burst", "burst", "float"),
    ), "# MHz/ms"),
    _Section("frequency-thresholds", ("frequency-thresholds", "frequency_thresholds"), (
        _Key("freq_adjust", "adjust", "int"),
    ), "# MHz: smaller non-burst changes are not applied."),
    _Section("load-target", ("load-target",), (
        _Key("load_upper", "upper", "float"),
        _Key("load_lower", "lower", "float"),
    ), "# Fraction of GPU load: ramp up above upper, ramp down below lower."),
    _Section("temperature", ("temperature",), (
        _Key("temp_throttling", "throttling", "int"),
        _Key("temp_recovery", "throttling_recovery", "opt_int"),
    ), "# °C"),
    _Section("dbus", ("dbus",), (
        _Key("dbus_enabled", "enabled", "bool"),
    )),
)
LOAD_HOLD_SECONDS = 6.0         # how long a vanished load reading is kept before the UI shows N/A

# Capabilities a backend may lack; pages and controls that need one are hidden when it is missing.
FEATURE_GPU_USAGE = "gpu-usage"             # [gpu-usage] section and the gpu_metrics override mount
FEATURE_SET_METHOD = "gpu-set-method"       # [gpu] set-method
FEATURE_FREQUENCY_RANGE = "frequency-range"  # [frequency-range] section
FEATURE_DOWN_EVENTS = "down-events"         # [timing] down-events
FEATURE_DBUS = "dbus"                       # [dbus] section and the runtime D-Bus interface
ALL_FEATURES = frozenset({FEATURE_GPU_USAGE, FEATURE_SET_METHOD, FEATURE_FREQUENCY_RANGE, FEATURE_DOWN_EVENTS,
                          FEATURE_DBUS})
# A [section] or [[array-of-tables]] header; the latter only ever marks the end of a managed section.
_SECTION_RE = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")
# key = value, with an optional trailing comment. Values never contain '#' here (bools, ints, bare words).
_KV_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+)(?P<eq>\s*=\s*)(?P<value>[^#]*?)(?P<gap>\s*)(?P<comment>#.*)?$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


class CyanSkillfishBackend:
    """Owns the managed sections of config.toml (see SCHEMA), the systemd unit and the D-Bus client.

    Everything outside the managed keys is left byte-for-byte as it is: existing lines keep their
    indentation and trailing comments, missing keys are appended to their section, missing sections are
    created at the end. The GUI never runs as root; the only privileged steps go through a single pkexec
    call each. Performance-mode changes go over D-Bus without any privilege."""

    name = "Cyan Skillfish SMU Governor"
    short_name = "smu"
    service_name = "cyan-skillfish-governor-smu.service"
    package_name = "cyan-skillfish-governor-smu"
    default_config_path = Path("/etc/cyan-skillfish-governor-smu/config.toml")
    schema: tuple[_Section, ...] = SCHEMA
    features: frozenset[str] = ALL_FEATURES
    default_safe_points: tuple[tuple[int, int], ...] = DEFAULT_SAFE_POINTS
    release_check = True        # GitHub releases of filippor/cyan-skillfish-governor are this package

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.config_path = Path(config_path) if config_path else self.default_config_path
        self.bus = GovernorBus()
        self._last_load: tuple[float, str, float] | None = None     # value, source, monotonic time
        self._key_by_toml = {(section.name, key.toml.replace("_", "-")): key
                             for section in self.schema for key in section.keys}
        self._canonical = {alias: section.name for section in self.schema for alias in section.aliases}

    def supports(self, feature: str) -> bool:
        return feature in self.features

    # ------------------------------------------------------------------ installation
    def installation_status(self) -> GovernorInstallStatus:
        result = _run(["systemctl", "show", self.service_name, "--property=LoadState", "--value"])
        service_present = result.returncode == 0 and result.stdout.strip() == "loaded"
        config_present = self.config_path.is_file()
        if not service_present:
            message = fmt("%1 was not found. The Cyan Skillfish SMU governor does not appear to be installed.",
                self.service_name)
        elif not config_present:
            message = fmt("%1 is installed, but %2 does not exist.",
                self.service_name, str(self.config_path))
        else:
            message = "Cyan Skillfish SMU governor is installed and configured."
        return GovernorInstallStatus(installed=service_present, service_present=service_present,
                                     config_present=config_present, service_name=self.service_name,
                                     config_path=str(self.config_path), message=message)

    # ------------------------------------------------------------------ config
    def read_config_text(self) -> str:
        if not self.config_path.is_file():
            return ""
        return self.config_path.read_text(encoding="utf-8", errors="replace")

    def read_config(self) -> GovernorConfig:
        config = GovernorConfig()
        section = ""
        for line in self.read_config_text().splitlines():
            header = _SECTION_RE.match(line)
            if header:
                section = self._canonical.get(header.group(1), "")
                continue
            if not section:
                continue
            kv = _KV_RE.match(line)
            if not kv:
                continue
            key = self._key_by_toml.get((section, kv.group("key").replace("_", "-")))
            if key is None:
                continue
            self._assign(config, key, _unquote(kv.group("value")))
        return config

    @staticmethod
    def _assign(config: GovernorConfig, key: _Key, value: str) -> None:
        """Set one field from its textual TOML value; unparsable values keep the default."""
        try:
            if key.kind == "bool":
                setattr(config, key.field, value.lower() == "true")
            elif key.kind in ("int", "opt_int"):
                setattr(config, key.field, max(0, int(value.replace("_", ""))))
            elif key.kind == "float":
                setattr(config, key.field, float(value.replace("_", "")))
            elif key.kind == "str" and value in CHOICES.get(key.field, ()):
                setattr(config, key.field, value)
        except ValueError:
            pass
        if key.field == "flush_every":
            config.flush_every = max(1, config.flush_every)
        elif key.field == "burst_samples" and config.burst_samples > BURST_SAMPLES_MAX:
            config.burst_samples = 0        # the governor treats out-of-range as disabled

    @staticmethod
    def _toml_value(key: _Key, config: GovernorConfig) -> str | None:
        """Rendered value, or None when an optional key should not be written."""
        value = getattr(config, key.field)
        if key.kind == "bool":
            return "true" if value else "false"
        if key.kind == "opt_int":
            return str(int(value)) if value else None
        if key.kind == "int":
            return str(int(value))
        if key.kind == "float":
            text = f"{value:.4f}".rstrip("0")
            return text + "0" if text.endswith(".") else text
        return f'"{value}"'

    def render_config(self, original: str, config: GovernorConfig) -> str:
        """The config text with every managed key set to `config`; all other lines are untouched."""
        config.validate()
        lines = original.splitlines()
        for section in self.schema:
            lines = self._render_section(lines, section, config)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _same_value(kind: str, existing: str, desired: str) -> bool:
        """Whether a line's value already means `desired` (`1` vs `1.00`, `100_000` vs `100000`, quotes)."""
        existing = existing.strip()
        if existing == desired:
            return True
        if kind in ("int", "opt_int", "float"):
            try:
                return float(existing.replace("_", "")) == float(desired)
            except ValueError:
                return False
        if kind == "str":
            return _unquote(existing) == _unquote(desired)
        return False

    def _render_section(self, lines: list[str], section: _Section, config: GovernorConfig) -> list[str]:
        desired: dict[str, str | None] = {key.toml.replace("_", "-"): self._toml_value(key, config)
                                          for key in section.keys}
        names = {key.toml.replace("_", "-"): key.toml for key in section.keys}
        kinds = {key.toml.replace("_", "-"): key.kind for key in section.keys}
        start = end = None
        for index, line in enumerate(lines):
            header = _SECTION_RE.match(line)
            if not header:
                continue
            if start is None:
                if header.group(1) in section.aliases:
                    start = index
            else:
                end = index
                break

        if start is None:
            to_write = {k: v for k, v in desired.items() if v is not None}
            if not to_write:
                return lines
            if lines and lines[-1].strip():
                lines.append("")
            if section.comment:
                lines.append(section.comment)
            lines.append(f"[{section.name}]")
            lines.extend(f"{names[k]} = {v}" for k, v in to_write.items())
            return lines

        end = len(lines) if end is None else end
        seen: set[str] = set()
        for index in range(start + 1, end):
            line = lines[index]
            kv = _KV_RE.match(line)
            commented = False
            if not kv and line.lstrip().startswith("#"):
                # A key we commented out earlier (`# throttling_recovery = 75`) can be revived in place.
                kv = _KV_RE.match(line.lstrip()[1:].lstrip())
                commented = kv is not None
            if not kv:
                continue
            key = kv.group("key").replace("_", "-")
            if key not in desired or key in seen:
                continue
            if commented and desired[key] is None:
                continue
            seen.add(key)
            if not commented and desired[key] is not None and self._same_value(kinds[key], kv.group("value"), desired[key]):
                continue
            # Keep the line's own spacing and its trailing comment.
            gap = kv.group("gap") if kv.group("comment") else ""
            comment = kv.group("comment") or ""
            indent = kv.group("indent") if not commented else ""
            if desired[key] is None:
                lines[index] = f"{indent}# {kv.group('key')}{kv.group('eq')}{kv.group('value')}{gap}{comment}"
            else:
                lines[index] = f"{indent}{kv.group('key')}{kv.group('eq')}{desired[key]}{gap}{comment}"
        # Append missing keys after the last non-blank line of the section, so the blank lines that
        # separate it from the next section stay where they are.
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        missing = [f"{names[k]} = {v}" for k, v in desired.items() if k not in seen and v is not None]
        lines[insert_at:insert_at] = missing
        return lines

    def write_config(self, config: GovernorConfig, *, backup: bool = True) -> Path | None:
        """Write the config through one pkexec call; returns the backup path when one was made."""
        config.validate()
        original = self.read_config_text()
        rendered = self.render_config(original, config)
        if rendered == original:
            return None
        return self._install_text(rendered, backup=backup)

    def _install_text(self, text: str, *, backup: bool) -> Path | None:
        """Put `text` in place as config.toml (root-owned, 0644) with one pkexec call, optionally after
        copying the current file to config.toml.bak-<stamp>. Returns the backup path when one was made."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".toml") as tmp:
            tmp.write(text)
            temp_path = Path(tmp.name)
        # pkexec reads the file as root; it is a copy of the 0644 file in /etc, so world-readable is fine.
        temp_path.chmod(0o644)

        backup_path = None
        script = 'mkdir -p "$(dirname "$2")" && '
        if backup and self.config_path.is_file():
            stamp = datetime.now().strftime(BACKUP_STAMP)
            backup_path = self.config_path.with_name(f"{self.config_path.name}.bak-{stamp}")
            script += 'install -o root -g root -m 0644 "$2" "$3" && '
        script += 'install -o root -g root -m 0644 "$1" "$2"'
        try:
            result = _run(["pkexec", "/bin/sh", "-c", script, "sh", str(temp_path), str(self.config_path),
                           str(backup_path or "")], timeout=120)
        finally:
            temp_path.unlink(missing_ok=True)
        if result.returncode != 0:
            if result.returncode == 126:
                raise RuntimeError("Authentication was canceled.")
            raise RuntimeError((result.stderr or result.stdout).strip() or fmt(
                "pkexec failed (%1)",
                str(result.returncode)))
        return backup_path

    # ------------------------------------------------------------------ safe points
    def safe_points(self, text: str | None = None) -> list[SafePoint]:
        """The active [[safe-points]] of the file, sorted by frequency. Commented-out points are skipped."""
        lines = (self.read_config_text() if text is None else text).splitlines()
        points: list[SafePoint] = []
        current: dict[str, int] | None = None
        start = 0

        def flush() -> None:
            if current is not None and "frequency" in current and "voltage" in current:
                points.append(SafePoint(current["frequency"], current["voltage"], start))

        for number, line in enumerate(lines, 1):
            if _SAFE_POINT_RE.match(line):
                flush()
                current, start = {}, number
            elif _TABLE_RE.match(line):
                flush()
                current = None
            elif current is not None:
                match = _KV_RE.match(line)
                if match and match.group("key") in ("frequency", "voltage"):
                    try:
                        current[match.group("key")] = int(float(_unquote(match.group("value").strip())))
                    except ValueError:
                        pass
        flush()
        return sorted(points, key=lambda p: p.frequency)

    def render_safe_points(self, original: str, points: list[tuple[int, int]]) -> str:
        """`original` with its active [[safe-points]] blocks replaced by `points` (frequency, voltage), sorted.
        Commented-out blocks and everything else stay where they are; the new blocks go where the first active
        block was, or at the end of the file when there was none."""
        lines = original.splitlines()
        keep: list[str] = []
        insert_at: int | None = None
        in_point = False
        for line in lines:
            if _SAFE_POINT_RE.match(line):
                in_point = True
                if insert_at is None:
                    insert_at = len(keep)
                continue
            if in_point:
                if _TABLE_RE.match(line):
                    in_point = False
                elif not line.strip() or _KV_RE.match(line):
                    continue                    # key, blank or trailing comment of the removed block
                else:
                    in_point = False
            keep.append(line)
        block: list[str] = []
        for frequency, voltage in sorted(points):
            block += ["[[safe-points]]", f"frequency = {frequency}", f"voltage = {voltage}", ""]
        if insert_at is None:
            if keep and keep[-1].strip():
                keep.append("")
            keep += block
        else:
            keep[insert_at:insert_at] = block
        text = "\n".join(keep).rstrip("\n") + "\n"
        return re.sub(r"\n{3,}", "\n\n", text)

    def write_safe_points(self, points: list[tuple[int, int]], *, backup: bool = True) -> Path | None:
        return self._install_text(self.render_safe_points(self.read_config_text(), points), backup=backup)

    # ------------------------------------------------------------------ backups
    def list_backups(self) -> list[ConfigBackup]:
        """config.toml.bak-* next to the config, newest first."""
        found = []
        for path in self.config_path.parent.glob(f"{self.config_path.name}.bak-*"):
            try:
                stat = path.stat()
            except OSError:
                continue
            try:
                created = datetime.strptime(path.name.rsplit(".bak-", 1)[1], BACKUP_STAMP)
            except ValueError:
                created = datetime.fromtimestamp(stat.st_mtime)
            found.append(ConfigBackup(path, created, stat.st_size))
        return sorted(found, key=lambda b: b.created, reverse=True)

    def read_backup(self, backup: Path) -> str:
        return backup.read_text(encoding="utf-8", errors="replace")

    def restore_backup(self, backup: Path) -> Path | None:
        """Make `backup` the config again (the current file is backed up first). Returns the new backup path."""
        text = self.read_backup(backup)
        if text == self.read_config_text():
            return None
        return self._install_text(text, backup=True)

    # ------------------------------------------------------------------ service
    def service_status(self) -> ServiceStatus:
        result = _run(["systemctl", "show", self.service_name,
                       "--property=LoadState,ActiveState,SubState,UnitFileState"])
        props = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if result.returncode != 0 or props.get("LoadState") != "loaded":
            return ServiceStatus(installed=False, active=False, enabled=False)
        raw = _run(["systemctl", "status", "--no-pager", "--plain", "--full", self.service_name]).stdout
        return ServiceStatus(installed=True,
                             active=props.get("ActiveState") == "active",
                             enabled=props.get("UnitFileState") in ("enabled", "enabled-runtime", "static"),
                             sub_state=props.get("SubState", ""),
                             unit_file_state=props.get("UnitFileState", ""),
                             raw=raw)

    def service_action(self, action: str) -> tuple[bool, str]:
        if action not in SERVICE_ACTIONS:
            raise ValueError(fmt("Unsupported service action: %1",
                                 repr(action)))
        result = _run(["pkexec", "systemctl", action, self.service_name], timeout=120)
        if result.returncode == 126:
            return False, "Authentication was canceled."
        return result.returncode == 0, (result.stderr or result.stdout).strip()

    # ------------------------------------------------------------------ sensors
    @staticmethod
    def _gpu_devices() -> list[Path]:
        """Device directories of the AMD GPUs, card0 first."""
        found = []
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            device = card / "device"
            try:
                if (device / "vendor").read_text().strip().lower() == "0x1002":
                    found.append(device)
            except OSError:
                continue
        return found

    def gpu_devices(self) -> list[Path]:
        return self._gpu_devices()

    def metrics_mount_active(self) -> bool:
        """True when something (the governor's patched table) is mounted over a gpu_metrics file."""
        if not self.supports(FEATURE_GPU_USAGE):
            return False
        return any(self._is_mount_point(device / "gpu_metrics") for device in self._gpu_devices())

    @staticmethod
    def _is_mount_point(path: Path) -> bool:
        # Without -T, findmnt only succeeds when the path itself is a mount point.
        result = _run(["findmnt", "-n", "-o", "TARGET", str(path)], timeout=4)
        return result.returncode == 0 and bool(result.stdout.strip())

    @staticmethod
    def _read_number(path: Path) -> float | None:
        try:
            return float(path.read_text().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _read_metrics(device: Path) -> GpuMetrics | None:
        try:
            return parse_gpu_metrics((device / "gpu_metrics").read_bytes())
        except OSError:
            return None

    def telemetry(self) -> GpuTelemetry:
        data = GpuTelemetry()
        for device in self._gpu_devices():
            if data.metrics is None:
                data.metrics = self._read_metrics(device)
                data.metrics_patched = self._is_mount_point(device / "gpu_metrics")
                # Only the governor's patched table has a sane average_gfx_activity on the BC-250.
                if data.metrics is not None and data.metrics_patched and data.metrics.gfx_activity_valid():
                    data.load_percent, data.load_source = data.metrics.gfx_activity_percent, "gpu_metrics"
            if data.load_percent is None:
                value = self._read_number(device / "gpu_busy_percent")
                if value is not None and 0.0 <= value <= 100.0:
                    data.load_percent, data.load_source = value, "gpu_busy_percent"
            for hwmon in sorted((device / "hwmon").glob("hwmon*")):
                if data.clock_mhz is None:
                    hz = self._read_number(hwmon / "freq1_input")
                    if hz:
                        data.clock_mhz, data.clock_source = round(hz / 1_000_000), "hwmon"
                if data.temp_c is None:
                    milli = self._read_number(hwmon / "temp1_input")
                    if milli is not None:
                        data.temp_c, data.temp_source = milli / 1000.0, "hwmon"
        m = data.metrics
        if m is not None:
            if data.clock_mhz is None and m.current_gfxclk:
                data.clock_mhz, data.clock_source = m.current_gfxclk, "gpu_metrics"
            if data.temp_c is None and m.temperature_gfx is not None:
                data.temp_c, data.temp_source = float(m.temperature_gfx), "gpu_metrics"
        if data.load_percent is None:
            value = self._radeontop_load()
            if value is not None:
                data.load_percent, data.load_source = value, "radeontop"
        # The governor replaces its patched table file every flush; a read that lands in that moment yields
        # nothing. Keep the previous reading for a few polls instead of flashing N/A.
        now = time.monotonic()
        if data.load_percent is not None:
            self._last_load = (data.load_percent, data.load_source, now)
        elif self._last_load is not None and now - self._last_load[2] <= LOAD_HOLD_SECONDS:
            data.load_percent, data.load_source = self._last_load[0], self._last_load[1]
        return data

    @staticmethod
    def _radeontop_load() -> float | None:
        """Optional fallback: BC-250 often has no gpu_busy_percent even though the governor measures load."""
        if not shutil.which("radeontop"):
            return None
        result = _run(["radeontop", "-d", "-", "-l", "1"], timeout=3)
        match = re.search(r"gpu\s+([0-9]+(?:\.[0-9]+)?)%", result.stdout, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 0.0 <= value <= 100.0:
                return value
        return None

    # ------------------------------------------------------------------ D-Bus (performance mode)
    def performance_state(self) -> PerformanceState:
        if not self.supports(FEATURE_DBUS):
            return PerformanceState(error=fmt(
                "%1 has no D-Bus interface.", self.name))
        return self.bus.state()
