# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication and a backend pointed at a temporary config.toml. Nothing here
touches pkexec, systemd or D-Bus; the main-window tests mock the bus."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SHIPPED = """\
[gpu-usage]
fix-metrics = true
fix-freq = false
method = "busy-flag"
temp-read = "drm"
flush-every = 10

[frequency-range]
min = 1000
max = 2000

[load-target]
upper = 0.95
lower = 0.80

[temperature]
throttling = 85

[dbus]
enabled = true

[[safe-points]]
frequency = 1000
voltage = 700

[[safe-points]]
frequency = 1500
voltage = 800

[[safe-points]]
frequency = 2000
voltage = 900
"""


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(SHIPPED, encoding="utf-8")
    return path


@pytest.fixture
def backend(config_file: Path):
    from gpu_governor.backends.cyan_skillfish import CyanSkillfishBackend
    return CyanSkillfishBackend(config_file)


@pytest.fixture
def tt_backend(config_file: Path):
    from gpu_governor.backends.cyan_skillfish_tt import CyanSkillfishTtBackend
    return CyanSkillfishTtBackend(config_file)


@pytest.fixture
def snapshot():
    """Factory for a Snapshot with sensible defaults; override what the test cares about."""
    from unittest import mock
    from gpu_governor.backends.base import GovernorConfig, GpuTelemetry, PerformanceState, ServiceStatus
    from gpu_governor.pages import Snapshot

    def make(*, load=50.0, clock=1500, temp=60.0, active=True, sub_state="running", bus=True, enabled=False,
             throttling=85, saved=None):
        return Snapshot(
            install=mock.Mock(message=""),
            service=ServiceStatus(installed=True, active=active, enabled=True, sub_state=sub_state),
            mounted=True,
            telemetry=GpuTelemetry(load_percent=load, clock_mhz=clock, temp_c=temp),
            saved=saved or GovernorConfig(temp_throttling=throttling),
            perf=PerformanceState(available=bus, enabled=enabled, current_min=1000, current_max=2000,
                                  allowed_min=500, allowed_max=2000, load_min=0.8, load_max=0.95,
                                  temp_throttling=throttling if bus else 0))
    return make
