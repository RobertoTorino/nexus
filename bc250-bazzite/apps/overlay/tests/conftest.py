# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, and a fake BC-250 /proc and /sys tree
(k10temp, amdgpu and an nct6686 with one spinning fan, as on a real board)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def proc_stat(busy: int, idle: int) -> str:
    """A /proc/stat whose first line has *busy* jiffies of user time and *idle* of idle time."""
    return f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 {busy} 0 0 {idle} 0 0 0 0 0 0"


@pytest.fixture
def board(tmp_path) -> Path:
    root = tmp_path / "root"
    write(root / "proc/stat", proc_stat(1000, 9000))
    cpu = root / "sys/devices/system/cpu"
    for n, khz in enumerate((2800000, 3200000)):
        write(cpu / f"cpu{n}/cpufreq/scaling_cur_freq", str(khz))
    hwmon = root / "sys/class/hwmon"
    write(hwmon / "hwmon0/name", "nvme")
    write(hwmon / "hwmon0/temp1_input", "39850")
    write(hwmon / "hwmon1/name", "nct6686")
    for n, (label, rpm) in enumerate((("CPU Fan", 0), ("Pump Fan", 1169), ("System Fan #1", 0)), start=1):
        write(hwmon / f"hwmon1/fan{n}_label", label)
        write(hwmon / f"hwmon1/fan{n}_input", str(rpm))
    write(hwmon / "hwmon2/name", "amdgpu")
    write(hwmon / "hwmon2/freq1_input", "2000000000")
    write(hwmon / "hwmon2/power1_input", "95250000")
    write(hwmon / "hwmon2/temp1_input", "61000")
    write(hwmon / "hwmon1/temp1_label", "CPU")
    write(hwmon / "hwmon1/temp1_input", "42000")
    write(hwmon / "hwmon1/temp3_label", "VRM MOS")
    write(hwmon / "hwmon1/temp3_input", "58000")
    write(hwmon / "hwmon2/in0_label", "vddgfx")
    write(hwmon / "hwmon2/in0_input", "1056")
    gpu = hwmon / "hwmon2/device"                   # a symlink to the PCI device on a real system
    write(gpu / "mem_info_vram_used", str(900_000_000))
    write(gpu / "mem_info_vram_total", str(6_000_000_000))
    (gpu / "gpu_metrics").write_bytes(gpu_metrics(4550))
    write(hwmon / "hwmon3/name", "k10temp")
    write(hwmon / "hwmon3/temp1_input", "72125")
    write(root / "proc/meminfo", "MemTotal:        9882072 kB\nMemFree:          100000 kB\n"
                                 "MemAvailable:    4963912 kB\nSwapTotal:      21718008 kB")
    write(root / "proc/net/dev", net_dev(1_000_000, 50_000))
    for disk in ("nvme0n1", "sda", "zram0", "loop0"):
        (root / "sys/block" / disk).mkdir(parents=True)
    write(root / "proc/diskstats", diskstats(2000, 100))
    return root


def gpu_metrics(gfx_activity: int) -> bytes:
    """A 128-byte gpu_metrics v2.2 table with *gfx_activity* (hundredths of a percent) at byte 28."""
    raw = bytearray(128)
    raw[0:4] = (128).to_bytes(2, "little") + bytes([2, 2])
    raw[0x1C:0x1E] = gfx_activity.to_bytes(2, "little")
    return bytes(raw)


def net_dev(rx: int, tx: int) -> str:
    """/proc/net/dev with lo (not counted) and one interface with *rx*/*tx* bytes."""
    return ("Inter-|   Receive  |  Transmit\n face |bytes packets ...\n"
            f"    lo: 999999 1 0 0 0 0 0 0 999999 1 0 0 0 0 0 0\n"
            f"enp4s0: {rx} 10 0 0 0 0 0 0 {tx} 5 0 0 0 0 0 0")


def diskstats(read_sectors: int, written_sectors: int) -> str:
    """/proc/diskstats: the nvme disk gets the sectors; its partition, zram and loop must not be counted."""
    return (f" 259 0 nvme0n1 1 0 {read_sectors} 0 1 0 {written_sectors} 0 0 0 0\n"
            f" 259 1 nvme0n1p1 1 0 {read_sectors} 0 1 0 {written_sectors} 0 0 0 0\n"
            "   8 0 sda 1 0 0 0 0 0 0 0 0 0 0\n"
            " 252 0 zram0 1 0 777 0 1 0 777 0 0 0 0\n"
            "   7 0 loop0 1 0 555 0 0 0 0 0 0 0 0")


class Clock:
    """A clock the test moves by hand."""

    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now
