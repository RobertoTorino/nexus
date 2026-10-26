# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostics report for bug reports: versions, config, service state, journal, raw gpu_metrics."""

from __future__ import annotations

import dataclasses
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

from . import APP_NAME, __version__
from .backends.gpu_metrics import parse_gpu_metrics
from .backends.process import run

JOURNAL_LINES = 300
_RULE = "=" * 78


def default_filename() -> str:
    return f"bc250-governor-manager-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.txt"


def _command(args: list[str], timeout: float = 15.0) -> str:
    result = run(args, timeout=timeout)
    text = result.stdout
    if result.returncode != 0:
        text += ("\n" if text else "") + f"[exit {result.returncode}] {result.stderr.strip()}"
    return text.strip() or "(no output)"


def _file(path: Path) -> str:
    try:
        return path.read_text().rstrip() or "(empty)"
    except OSError as exc:
        return f"(unreadable: {exc})"


def _os_release() -> str:
    try:
        return platform.freedesktop_os_release().get("PRETTY_NAME") or "unknown"
    except (OSError, AttributeError):
        return "unknown"


def _hexdump(raw: bytes) -> str:
    lines = []
    for offset in range(0, len(raw), 16):
        chunk = raw[offset:offset + 16]
        lines.append(f"{offset:04x}  {chunk.hex(' ')}")
    return "\n".join(lines)


def _gpu_sections(devices: list[Path]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if not devices:
        return [("GPU", "No AMD GPU found under /sys/class/drm.")]
    for device in devices:
        name = device.parent.name
        attrs = []
        for attr in ("vendor", "device", "revision", "power_dpm_force_performance_level",
                     "pp_dpm_sclk", "pp_od_clk_voltage", "hwmon"):
            path = device / attr
            if attr == "hwmon":
                for hw in sorted(path.glob("hwmon*")) if path.is_dir() else []:
                    for sensor in sorted(hw.glob("*_input")) + sorted(hw.glob("*_label")):
                        attrs.append(f"{sensor.relative_to(device)} = {_file(sensor)}")
                continue
            if path.exists():
                attrs.append(f"{attr} = {_file(path)}")
        sections.append((f"{name}: sysfs", "\n".join(attrs) or "(nothing readable)"))

        metrics_path = device / "gpu_metrics"
        try:
            raw = metrics_path.read_bytes()
        except OSError as exc:
            sections.append((f"{name}: gpu_metrics", f"(unreadable: {exc})"))
            continue
        mounted = run(["findmnt", "-n", "-o", "SOURCE,FSTYPE", str(metrics_path)], timeout=4).stdout.strip()
        parsed = parse_gpu_metrics(raw)
        body = [f"size: {len(raw)} bytes", f"override mount: {mounted or 'none'}"]
        if parsed is None:
            body.append("parsed: unsupported format")
        else:
            body.append(f"parsed (format {parsed.version}):")
            body.extend(f"  {f.name} = {getattr(parsed, f.name)}" for f in dataclasses.fields(parsed))
        body.append("raw:")
        body.append(_hexdump(raw))
        sections.append((f"{name}: gpu_metrics", "\n".join(body)))
    return sections


def build_report(*, config_path: Path, service_name: str, gpu_devices: list[Path],
                 package_name: str = "cyan-skillfish-governor-smu", extra: dict[str, str] | None = None) -> str:
    """Return the full plain-text report. Never raises: every part degrades to an error note."""
    sections: list[tuple[str, str]] = [
        ("Report", "\n".join((
            f"app: {APP_NAME} {__version__}",
            f"created: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"python: {sys.version.split()[0]} ({sys.executable})",
            f"os: {_os_release()}",
            f"kernel: {platform.release()}",
            f"session: {os.environ.get('XDG_CURRENT_DESKTOP', '?')} / {os.environ.get('XDG_SESSION_TYPE', '?')}",
            f"user: uid {os.getuid()}",
        ))),
        ("Versions", "\n".join((
            f"rpm -q {package_name}: " + _command(["rpm", "-q", package_name]),
            "rpm-ostree status -b:\n" + _command(["rpm-ostree", "status", "-b"], timeout=30),
        ))),
        ("Hardware", "\n".join((
            "lscpu (model/cores):\n" + _command(["lscpu", "-e=CPU,CORE,ONLINE"]),
            "lspci (VGA):\n" + _command(["sh", "-c", "lspci -nn | grep -i -E 'vga|display|3d'"]),
            "memory:\n" + _command(["free", "-m"]),
        ))),
        (f"Config: {config_path}", _file(config_path)),
        (f"Backups next to {config_path.name}", "\n".join(
            sorted(p.name for p in config_path.parent.glob(f"{config_path.name}.*")) or ["(none)"])
         if config_path.parent.is_dir() else "(directory missing)"),
        (f"systemctl status {service_name}", _command(["systemctl", "status", service_name, "--no-pager", "-l"])),
        (f"systemctl cat {service_name}", _command(["systemctl", "cat", service_name, "--no-pager"])),
        (f"journalctl -u {service_name} -n {JOURNAL_LINES}",
         _command(["journalctl", "-u", service_name, "-n", str(JOURNAL_LINES), "--no-pager", "-o", "short-iso"],
                  timeout=30)),
        ("D-Bus com.cyanskillfish.Governor",
         _command(["busctl", "--system", "introspect", "com.cyanskillfish.Governor", "/com/cyanskillfish/Governor"])),
        ("Kernel command line", _file(Path("/proc/cmdline"))),
        ("amdgpu kernel messages",
         _command(["sh", "-c", "journalctl -k -b --no-pager -o short-iso | grep -i -E 'amdgpu|smu|cyan' | tail -n 200"],
                  timeout=30)),
    ]
    sections.extend(_gpu_sections(gpu_devices))
    for title, text in (extra or {}).items():
        sections.append((title, text))

    out = [f"{APP_NAME} diagnostics", _RULE,
           "Read this file before attaching it to a bug report and remove anything you do not want to share.", ""]
    for title, text in sections:
        out += [_RULE, title, _RULE, text, ""]
    return "\n".join(out)
