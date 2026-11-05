# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, the settings and the suite's folders in
a temp folder (never Windows' registry), and a fake controller: hidapi's list entry for it, and a device that answers
feature reports with the reports and the report descriptor of the owner's DualSense Edge (the BC250 app's tests,
23-10-2026; its MAC address left out). No test touches a real controller."""

from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DESCRIPTOR = bytes.fromhex(
    "05010905a1018501093009310932093509330934150026ff007508950681020600ff09209501810205010939150025073500463b0165"
    "14750495018142650005091901290f150025017501950f81020600ff0921950d81020600ff0922150026ff0075089534810285020923"
    "953f9102850509339528b10285080934952fb102850909249513b102850a0925951ab10285200926953fb102852109279504b1028522"
    "0940953fb10285800928953fb10285810929953fb1028582092a9509b1028583092b953fb1028584092c953fb1028585092d9502b102"
    "85a0092e9501b10285e0092f953fb10285f00930953fb10285f10931953fb10285f209329534b10285f40935953fb10285f509369503"
    "b10285600941953fb10285610942b10285620943b10285630944b10285640945b10285650946b10285680947b10285700948b1028571"
    "0949b1028572094ab1028573094bb1028574094cb1028575094db1028576094eb1028577094fb10285780950b10285790951b102857a"
    "0952b102857b0953b102c0")
FIRMWARE_REPORT = bytes.fromhex(
    "204a756e203231203230323431393a30393a313703004400160200017800000151c8000000000000000000000002000014000000090002"
    "000600000000000000")
DEFAULT_PROFILE = (
    bytes.fromhex("700001000000440065006600610075006c0074002000500072006f00660069006c006500000000000000000000000000"
                  "00000000000000000000000000000000"),
    bytes.fromhex("71010000" + "00" * 60),
    bytes.fromhex("7202000000ff00ff0000000102030405060708090a0b0c0d0e0f0000c000000000000000000000000000000000000000"
                  "0000000000000000fe6c831800000000"),
)
USB_PATH = b"\\\\?\\HID#VID_054C&PID_0DF2&MI_03#8&1a2b3c4d&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
BT_PATH = (b"\\\\?\\HID#{00001124-0000-1000-8000-00805f9b34fb}_VID&0002054c_PID&0ce6#9&aabbccdd&0&0000"
           b"#{4d1e55b2-f16f-11cf-88cb-001111000030}")


def entry(path: bytes = USB_PATH, product: int = 0x0DF2, bus: int | None = 1, vendor: int = 0x054C,
          usage: tuple[int, int] = (0x01, 0x05)) -> dict:
    """hidapi's list entry for a controller, as hid.enumerate() gives it (the serial number left out)."""
    found = {"path": path, "vendor_id": vendor, "product_id": product, "serial_number": "", "release_number": 0x100,
             "manufacturer_string": "Sony Interactive Entertainment", "product_string": "DualSense Edge Wireless "
             "Controller", "usage_page": usage[0], "usage": usage[1], "interface_number": 3}
    if bus is not None:
        found["bus_type"] = bus
    return found


def empty_slot(first: int) -> tuple[bytes, bytes, bytes]:
    return tuple(bytes([first + part, 0x10]) + bytes(62) for part in range(3))


def profile_reports(first: int, name: str, third: bytes | None = None) -> tuple[bytes, bytes, bytes]:
    """A profile as the controller holds it, with its CRC: *third* replaces part 2's bytes 2 to 55."""
    encoded = name.encode("utf-16-le").ljust(54 + 26, b"\0")
    part0 = bytes([first, 0, 1, 0, 0, 0]) + encoded[:54] + bytes(4)
    part1 = bytes([first + 1, 1]) + encoded[54:80] + bytes(36)
    body = third if third is not None else DEFAULT_PROFILE[2][2:56]
    part2 = bytes([first + 2, 2]) + body
    crc = zlib.crc32(part0[2:60] + part1[2:60] + part2[2:56])
    return part0, part1, part2 + crc.to_bytes(4, "little") + bytes(4)


def input_report(buttons=(0x08, 0, 0), status: int = 0x08, bluetooth: bool = False) -> bytes:
    """An input report at rest with *buttons*, its status byte *status* (0x08: 85 %, on its battery)."""
    data = bytearray(([0x31, 0x00] if bluetooth else [0x01]) + [128, 128, 128, 128, 0, 0, 0, *buttons] + [0] * 60)
    data[(2 if bluetooth else 1) + 52] = status
    return bytes(data)


class FakeDevice:
    """A controller's HID device: answers the firmware report and the profile reports, records what is sent and
    written, gives the input reports queued, and keeps a profile written or cleared as the owner's Edge did
    (23-10-2026): a part written with 0x60 to 0x63 reads back under its slot's read report with bytes 60 to 63 zero,
    and 0x68 empties the slot byte 1 names."""

    def __init__(self, reports: dict[int, bytes] | None = None):
        self.reports = {0x20: FIRMWARE_REPORT}
        for first, report in zip((0x70, 0x71, 0x72), DEFAULT_PROFILE):
            self.reports[first] = report
        for index in (1, 2, 3):
            for part, report in enumerate(empty_slot(0x70 + 3 * index)):
                self.reports[0x70 + 3 * index + part] = report
        self.reports.update(reports or {})
        self.sent: list[bytes] = []
        self.written: list[bytes] = []
        self.inputs: list[bytes] = []
        self.asked: list[int] = []
        self.closed = False
        self.opened = 0

    def __call__(self, path, sizes=None, blocking=True):
        """As hiddevice.Device: the window opens it by its path."""
        self.opened += 1
        self.closed = False
        return self

    def get_feature(self, report_id: int) -> bytes:
        self.asked.append(report_id)
        if report_id not in self.reports:
            raise OSError(32, "Broken pipe")
        return self.reports[report_id]

    def set_feature(self, data: bytes) -> None:
        self.sent.append(bytes(data))
        if 0x60 <= data[0] <= 0x63:
            first = 0x70 + 3 * {0x63: 0, 0x60: 1, 0x61: 2, 0x62: 3}[data[0]]
            self.reports[first + data[1]] = bytes([first + data[1]]) + bytes(data[1:60]) + bytes(4)
        elif data[0] == 0x68:
            first = 0x70 + 3 * (data[1] - 1)
            self.reports.update(zip(range(first, first + 3), empty_slot(first)))

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))

    def read(self, size: int = 128) -> bytes:
        return self.inputs.pop(0) if self.inputs else b""

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), in the temp folder: never Windows' registry. The suite's
    folders (the firmware, the backups, the log) go to the temp folder too."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
