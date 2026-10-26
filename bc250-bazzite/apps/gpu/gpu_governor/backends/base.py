# SPDX-License-Identifier: GPL-3.0-or-later
"""Data types and the protocol every governor backend implements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol


from .. import fmt

if TYPE_CHECKING:
    from .gpu_metrics import GpuMetrics

METHODS = ("busy-flag", "process", "kernel")
TEMP_READS = ("drm", "sysfs")
SET_METHODS = ("smu", "kernel")
BURST_SAMPLES_MAX = 64


@dataclass(slots=True)
class ServiceStatus:
    installed: bool
    active: bool
    enabled: bool
    sub_state: str = ""         # systemd SubState: running, dead, failed, ...
    unit_file_state: str = ""   # enabled, disabled, static, masked, ...
    raw: str = ""


@dataclass(slots=True)
class GovernorInstallStatus:
    installed: bool
    service_present: bool
    config_present: bool
    service_name: str
    config_path: str
    message: str = ""


@dataclass(slots=True)
class GovernorConfig:
    """The sections of config.toml the app manages. Defaults equal the governor's built-in defaults.

    [gpu-usage]        fix_metrics, fix_freq, method, temp_read, flush_every
    [frequency-range]  freq_min, freq_max      (MHz, 0 = no limit; the governor clamps to its safe points)
    [load-target]      load_upper, load_lower  (fractions: ramp up above upper, down below lower)
    [temperature]      temp_throttling, temp_recovery (°C; recovery 0 = not set, key left out)
    [dbus]             dbus_enabled            (needed for the performance-mode controls)
    [gpu]              set_method              (smu or kernel: how frequency/voltage are applied)
    [timing.intervals] sample_us, adjust_us    (µs: sampling period, control-loop period)
    [timing]           burst_samples, down_events (busy samples before burst mode, 0 = off; low-load events before stepping down)
    [timing.ramp-rates] ramp_normal, ramp_burst (MHz/ms)
    [frequency-thresholds] freq_adjust         (MHz: smallest non-burst change that is applied)
    """

    fix_metrics: bool = True
    fix_freq: bool = False
    method: str = "busy-flag"
    temp_read: str = "drm"
    flush_every: int = 10
    freq_min: int = 0
    freq_max: int = 0
    load_upper: float = 0.95
    load_lower: float = 0.80
    temp_throttling: int = 85
    temp_recovery: int = 0
    dbus_enabled: bool = False
    set_method: str = "smu"
    sample_us: int = 2000
    adjust_us: int = 20000
    burst_samples: int = 0
    down_events: int = 10
    ramp_normal: float = 1.0
    ramp_burst: float = 200.0
    freq_adjust: int = 10

    def validate(self) -> None:
        if self.method not in METHODS:
            raise ValueError(fmt("Unsupported GPU usage method: %1",
                                 repr(self.method)))
        if self.temp_read not in TEMP_READS:
            raise ValueError(fmt("Unsupported temperature source: %1",
                                 repr(self.temp_read)))
        if self.set_method not in SET_METHODS:
            raise ValueError(fmt("Unsupported gpu.set-method: %1",
                                 repr(self.set_method)))
        if self.flush_every < 1:
            raise ValueError("flush-every must be at least 1")
        if self.sample_us < 1 or self.adjust_us < 1:
            raise ValueError("timing.intervals must be at least 1 µs")
        if self.adjust_us < self.sample_us:
            raise ValueError(("timing.intervals.adjust must not be shorter than "
                              "sample"))
        if not 0 <= self.burst_samples <= BURST_SAMPLES_MAX:
            raise ValueError(fmt("timing.burst-samples must be 0 (off) or 1..%1",
                                 str(BURST_SAMPLES_MAX)))
        if self.down_events < 1:
            raise ValueError("timing.down-events must be at least 1")
        if self.ramp_normal <= 0:
            raise ValueError("timing.ramp-rates.normal must be positive")
        if self.ramp_burst <= self.ramp_normal:
            raise ValueError("timing.ramp-rates.burst must be greater than normal")
        if self.freq_adjust < 0:
            raise ValueError("frequency-thresholds.adjust cannot be negative")
        if self.freq_min < 0 or self.freq_max < 0:
            raise ValueError("Frequencies cannot be negative")
        if self.freq_min and self.freq_max and self.freq_min > self.freq_max:
            raise ValueError(("frequency-range.min must not exceed "
                              "frequency-range.max"))
        if not 0.0 <= self.load_lower <= self.load_upper < 1.0:
            raise ValueError("load-target needs 0 <= lower <= upper < 1")
        if not 0 <= self.temp_throttling <= 100:
            raise ValueError("temperature.throttling must be 0..100 °C")
        if self.temp_recovery and not self.temp_recovery < self.temp_throttling:
            raise ValueError(("temperature.throttling_recovery must be below "
                              "temperature.throttling (or 0)"))

    def tuning_fields(self) -> tuple:
        """The values a preset sets, for comparing a form with the presets."""
        return (self.freq_min, self.freq_max, self.load_upper, self.load_lower, self.temp_throttling,
                self.temp_recovery)


@dataclass(slots=True)
class GpuTelemetry:
    load_percent: float | None = None   # None: no usable sensor, which is not the same as 0%
    load_source: str = ""               # "gpu_metrics", "gpu_busy_percent" or "radeontop"
    clock_mhz: int | None = None
    clock_source: str = ""              # "hwmon" or "gpu_metrics"
    temp_c: float | None = None
    temp_source: str = ""               # "hwmon" or "gpu_metrics"
    metrics: "GpuMetrics | None" = None # the parsed gpu_metrics table, when readable
    metrics_patched: bool = False       # True when the governor's table is mounted over the sysfs file


@dataclass(slots=True)
class PerformanceState:
    """What the governor reports over D-Bus (com.cyanskillfish.Governor); runtime only, not persisted."""

    available: bool = False             # the name has an owner on the system bus
    error: str = ""                     # why it is unavailable, when known
    enabled: bool = False               # performance mode on
    current_min: int = 0
    current_max: int = 0
    allowed_min: int = 0                # the safe-points range the governor will never leave
    allowed_max: int = 0
    initial_min: int = 0                # [frequency-range] of config.toml, clamped, as read at start
    initial_max: int = 0
    load_min: float = 0.0
    load_max: float = 0.0
    temp_throttling: int = 0
    temp_recovery: int = 0


@dataclass(frozen=True, slots=True)
class SafePoint:
    """One [[safe-points]] entry of config.toml: a frequency/voltage pair the governor may use."""

    frequency: int                      # MHz
    voltage: int                        # mV
    line: int = 0                       # 1-based line of its header in the file


@dataclass(frozen=True, slots=True)
class ConfigBackup:
    """A config.toml.bak-YYYYMMDD-HHMMSS copy made before a write."""

    path: Path
    created: datetime
    size: int


class GovernorBackend(Protocol):
    name: str
    short_name: str
    config_path: Path
    service_name: str
    package_name: str
    features: frozenset[str]
    default_safe_points: tuple[tuple[int, int], ...]
    release_check: bool

    def supports(self, feature: str) -> bool: ...

    def installation_status(self) -> GovernorInstallStatus: ...
    def read_config(self) -> GovernorConfig: ...
    def read_config_text(self) -> str: ...
    def write_config(self, config: GovernorConfig, *, backup: bool = True) -> Path | None: ...
    def service_status(self) -> ServiceStatus: ...
    def service_action(self, action: str) -> tuple[bool, str]: ...
    def metrics_mount_active(self) -> bool: ...
    def telemetry(self) -> GpuTelemetry: ...
    def performance_state(self) -> PerformanceState: ...
    def safe_points(self, text: str | None = None) -> list[SafePoint]: ...
    def list_backups(self) -> list[ConfigBackup]: ...
    def restore_backup(self, backup: Path) -> Path | None: ...
    def write_safe_points(self, points: list[tuple[int, int]], *, backup: bool = True) -> Path | None: ...
    def gpu_devices(self) -> list[Path]: ...
