# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, the settings in a temp folder (never
Windows' registry), and the Ally X as Windows reported it on the owner's handheld (26-10-2026)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GB = 1024 ** 3
ALLY = {"maker": "ASUSTeK COMPUTER INC.", "model": "ROG Xbox Ally X RC73XA_RC73XA", "family": "ROG Xbox Ally X",
        "usable": 16_750_000_000, "installed": 24 * GB, "windows": "Microsoft Windows 11 Home",
        "version": "10.0.26300", "build": "26300",
        "cpu": {"name": "AMD Ryzen AI Z2 Extreme", "cores": 8, "threads": 16},
        "gpu": {"name": "AMD Radeon(TM) 890M Graphics", "driver": "32.0.32015.7029"},
        "disks": {"model": "SAMSUNG MZVMA1T0HCLD-00BTW", "size": 1_024_203_640_320},
        "battery": {"charge": 82, "status": 1}, "firmware": "RC73XA.319"}
# Its hardware as Windows reported it on the owner's Ally, docked to a TV (28-10-2026): the built-in panel and the TV
# over the dock's DisplayPort, the dock's Realtek hub (USB 3 and USB 2) and Ethernet port, a drive on USB.
HARDWARE = {
    "panel": [{"width": 15, "height": 9, "internal": True}, {"width": 188, "height": 105, "internal": False}],
    "network": [{"name": "MediaTek Wi-Fi 6E MT7922 (RZ616) 160MHz Wireless LAN Card", "media": "Native 802.11",
                 "driver": "3.6.2.1438", "up": True, "usb": False},
                {"name": "Realtek USB GbE Family Controller #2", "media": "802.3", "driver": "1153.15.20.327",
                 "up": False, "usb": True}],
    "bluetooth": "MediaTek Bluetooth Adapter",
    "audio": ["Realtek High Definition Audio", "AMD High Definition Audio Device"],
    "touch": ["NOVATEK TouchPanel", "HID-compliant touch screen"],
    "fingerprint": "EgisTec Touch Fingerprint Sensor", "camera": [],
    "sensors": ["Bosch Accelerometer", "Simple Device Orientation Sensor"],
    "usb": ["USB4(TM) Host Router (Microsoft)", "AMD USB 3.10 eXtensible Host Controller - 1.20 (Microsoft)",
            "AMD USB 3.10 eXtensible Host Controller - 1.20 (Microsoft)"],
    "hubs": [{"name": "Generic SuperSpeed USB Hub", "id": "VID_0BDA&PID_0411"},
             {"name": "Generic USB Hub", "id": "VID_0BDA&PID_5411"}],
    "screens": [{"name": "", "output": 2147483648}, {"name": "Mi TV", "output": 10}],
}
DOCKED = dict(ALLY, **HARDWARE, disks=[dict(ALLY["disks"], usb=False),
                                       {"model": "WDC WD40 EFRX-68N32N0 SCSI Disk Device", "size": 4_000_787_030_016,
                                        "usb": True}])


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


@pytest.fixture
def ally_json() -> str:
    return json.dumps(ALLY)
