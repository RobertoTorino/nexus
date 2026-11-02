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
# over the dock's DisplayPort, a drive on USB; and its USB devices (02-11-2026): the built-in fingerprint reader,
# Bluetooth and controller, the JSAUX dock's two Realtek hubs (USB 3 and USB 2) with its Realtek network chip (no
# cable), the PS5 HD Camera's boot loader (no driver) and the Turzx screen behind them, and a Ugreen adapter (ASIX) on
# the handheld's other port.
PLUGGED = [
    {"id": "VID_1C7A&PID_0588", "class": "Biometric", "name": "EgisTec Touch Fingerprint Sensor", "service": "WUDFRd",
     "own": "ETU905A86-E", "parent": -1, "box": 0, "local": True, "problem": 0},
    {"id": "VID_0BDA&PID_8153", "class": "Net", "name": "Realtek USB GbE Family Controller #2",
     "service": "rtu53cx22x64", "own": "USB 10/100/1000 LAN", "parent": 3, "box": 1, "local": False, "problem": 0},
    {"id": "VID_0B95&PID_1790", "class": "Net", "name": "ASIX AX88179 USB 3.0 to Gigabit Ethernet Adapter",
     "service": "AX88179", "own": "AX88179B", "parent": -1, "box": 2, "local": False, "problem": 0},
    {"id": "VID_0BDA&PID_0411", "class": "USB", "name": "Generic SuperSpeed USB Hub", "service": "USBHUB3",
     "own": "USB3.2 Hub", "parent": -1, "box": 3, "local": False, "problem": 0},
    {"id": "VID_0489&PID_E0F5", "class": "USB", "name": "USB Composite Device", "service": "usbccgp",
     "own": "Wireless_Device", "parent": -1, "box": 0, "local": True, "problem": 0},
    {"id": "VID_0BDA&PID_5411", "class": "USB", "name": "Generic USB Hub", "service": "USBHUB3", "own": "USB2.1 Hub",
     "parent": -1, "box": 3, "local": False, "problem": 0},
    {"id": "VID_1A86&PID_5722", "class": "Ports", "name": "USB Serial Device (COM3)", "service": "usbser",
     "own": "UsbMonitor", "parent": 5, "box": 4, "local": False, "problem": 0},
    {"id": "VID_0489&PID_E0F5&MI_00", "class": "Bluetooth", "name": "MediaTek Bluetooth Adapter", "service": "BTHUSB",
     "own": "BT_FUNCTION", "parent": 4, "box": 0, "local": True, "problem": 0},
    {"id": "VID_05A9&PID_0580", "class": None, "name": "USB Boot", "service": None, "own": "USB Boot", "parent": 3,
     "box": 5, "local": False, "problem": 28},
    {"id": "VID_0B05&PID_1B4C&MI_05", "class": "HIDClass", "name": "ROG Xbox Ally Device Gamepad", "service": "HidUsb",
     "own": "ASUSTeK Computer Inc.", "parent": 11, "box": 0, "local": True, "problem": 0},
    {"id": "VID_0B05&PID_1B4C&MI_00", "class": "HIDClass", "name": "USB Input Device", "service": "HidUsb",
     "own": "ASUSTeK Computer Inc.", "parent": 11, "box": 0, "local": True, "problem": 0},
    {"id": "VID_0B05&PID_1B4C", "class": "USB", "name": "USB Composite Device", "service": "usbccgp",
     "own": "N-KEY Device", "parent": -1, "box": 0, "local": True, "problem": 0},
    {"id": "VID_174C&PID_1153", "class": "SCSIAdapter", "name": "USB Attached SCSI (UAS) Mass Storage Device",
     "service": "UASPStor", "own": "", "parent": 3, "box": 6, "local": False, "problem": 0},  # the drive's
]
HARDWARE = {
    "panel": [{"width": 15, "height": 9, "internal": True}, {"width": 188, "height": 105, "internal": False}],
    "network": [{"name": "MediaTek Wi-Fi 6E MT7922 (RZ616) 160MHz Wireless LAN Card", "media": "Native 802.11",
                 "driver": "3.6.2.1438", "up": True, "status": "Up", "usb": False, "device": -1},
                {"name": "Realtek USB GbE Family Controller #2", "media": "802.3", "driver": "1153.15.20.327",
                 "up": False, "status": "Disconnected", "speed": 0, "usb": True, "device": 1},
                {"name": "ASIX AX88179 USB 3.0 to Gigabit Ethernet Adapter", "media": "802.3",
                 "driver": "1.18.19.1128", "up": True, "status": "Up", "speed": 1_000_000_000, "usb": True,
                 "device": 2}],
    "plugged": PLUGGED, "problems": [],
    "bluetooth": "MediaTek Bluetooth Adapter",
    "audio": ["Realtek High Definition Audio", "AMD High Definition Audio Device"],
    "touch": ["NOVATEK TouchPanel", "HID-compliant touch screen"],
    "fingerprint": "EgisTec Touch Fingerprint Sensor", "camera": [],
    "sensors": ["Bosch Accelerometer", "Simple Device Orientation Sensor"],
    "usb": ["USB4(TM) Host Router (Microsoft)", "AMD USB 3.10 eXtensible Host Controller - 1.20 (Microsoft)",
            "AMD USB 3.10 eXtensible Host Controller - 1.20 (Microsoft)"],
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
    from bc250_core import portable
    portable.pin_scale((1280, 720))     # the Ally's screen, not the offscreen one (800 x 800): the windows fit-tested
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
