# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, and a fake /sys of a BC-250 as the owner's
board reported it on 16-10-2026: the nct6687 driver bound to the NCT6686 (as nct6686), one Noctua on CPU_FAN1
(channel 2) at 1166 RPM in the firmware's curve, nothing on the other headers, GPU edge 42 °C and CPU Tctl 44 °C."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def set_temps(sys_root: Path, gpu: float | None = None, cpu: float | None = None) -> None:
    if gpu is not None:
        write(sys_root / "class/hwmon/hwmon2/temp1_input", str(int(gpu * 1000)))
    if cpu is not None:
        write(sys_root / "class/hwmon/hwmon3/temp1_input", str(int(cpu * 1000)))


def set_rpm(sys_root: Path, channel: int, rpm: int) -> None:
    write(sys_root / f"class/hwmon/hwmon1/fan{channel}_input", str(rpm))


NCT_LABELS = ["CPU Fan", "Pump Fan", "System Fan #1", "System Fan #2", "System Fan #3", "System Fan #4",
              "System Fan #5", "System Fan #6"]


@pytest.fixture
def sys_root(tmp_path) -> Path:
    root = tmp_path / "sys"
    write(root / "class/dmi/id/board_name", "AMD BC-250")
    hw = root / "class/hwmon"
    write(hw / "hwmon0/name", "nvme")
    write(hw / "hwmon0/temp1_input", "41850")
    write(hw / "hwmon0/temp1_label", "Composite")
    nct = hw / "hwmon1"
    write(nct / "name", "nct6686")
    for channel, label in enumerate(NCT_LABELS, start=1):
        write(nct / f"fan{channel}_label", label)
        write(nct / f"fan{channel}_input", "1166" if channel == 2 else "0")
        write(nct / f"pwm{channel}", "127" if channel <= 5 else "0")
        write(nct / f"pwm{channel}_enable", "2" if channel <= 5 else "1")
    for channel, label in enumerate(["CPU", "System", "VRM MOS"], start=1):
        write(nct / f"temp{channel}_label", label)
        write(nct / f"temp{channel}_input", "44000")
    write(hw / "hwmon2/name", "amdgpu")
    write(hw / "hwmon2/temp1_label", "edge")
    write(hw / "hwmon2/temp1_input", "42000")
    write(hw / "hwmon3/name", "k10temp")
    write(hw / "hwmon3/temp1_label", "Tctl")
    write(hw / "hwmon3/temp1_input", "44125")
    return root


@pytest.fixture
def paths(tmp_path):
    from fan_control import guard
    return guard.Paths(tmp_path / "etc", tmp_path / "run")
