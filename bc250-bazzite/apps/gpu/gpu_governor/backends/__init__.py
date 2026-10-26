# SPDX-License-Identifier: GPL-3.0-or-later
"""Governor backends."""

from .base import (
    METHODS, SET_METHODS, TEMP_READS, ConfigBackup, GovernorBackend, GovernorConfig, GovernorInstallStatus,
    GpuTelemetry, PerformanceState, SafePoint, ServiceStatus,
)
from .cyan_skillfish import (
    ALL_FEATURES, FEATURE_DBUS, FEATURE_DOWN_EVENTS, FEATURE_FREQUENCY_RANGE, FEATURE_GPU_USAGE,
    FEATURE_SET_METHOD, SERVICE_ACTIONS, CyanSkillfishBackend,
)
from .cyan_skillfish_tt import CyanSkillfishTtBackend
from .dbus import GovernorBus
from .gpu_metrics import GpuMetrics, parse_gpu_metrics

BACKENDS: dict[str, type[CyanSkillfishBackend]] = {"smu": CyanSkillfishBackend, "tt": CyanSkillfishTtBackend}


def detect_backend(preference: str = "auto", config_path: str | None = None) -> CyanSkillfishBackend:
    """`smu` or `tt` explicitly, or `auto`: the first governor whose systemd unit is loaded, smu when none is."""
    if preference in BACKENDS:
        return BACKENDS[preference](config_path)
    for cls in BACKENDS.values():
        candidate = cls(config_path)
        if candidate.installation_status().service_present:
            return candidate
    return CyanSkillfishBackend(config_path)


__all__ = [
    "ALL_FEATURES", "BACKENDS", "FEATURE_DBUS", "FEATURE_DOWN_EVENTS", "FEATURE_FREQUENCY_RANGE",
    "FEATURE_GPU_USAGE", "FEATURE_SET_METHOD", "detect_backend",
    "CyanSkillfishTtBackend",
    "METHODS", "SET_METHODS", "TEMP_READS", "SERVICE_ACTIONS", "ConfigBackup", "CyanSkillfishBackend", "GovernorBackend",
    "GovernorBus", "GovernorConfig", "GovernorInstallStatus", "GpuMetrics", "GpuTelemetry", "PerformanceState",
    "SafePoint", "ServiceStatus", "parse_gpu_metrics",
]
