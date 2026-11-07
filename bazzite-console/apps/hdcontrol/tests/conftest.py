# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and the XDG folders in a temp folder, a fake /sys with a
controller connected, and a fake controller that answers feature reports, with the reports and the report descriptor
of the owner's DualSense Edge (23-10-2026; its MAC address left out)."""

from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it

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


class FakeDevice:
    """A controller's hidraw node: answers the firmware report and the profile reports, records what is sent, and
    keeps a profile written or cleared as the owner's Edge did (23-10-2026): a part written with 0x60 to 0x63 reads
    back under its slot's read report with bytes 60 to 63 zero, and 0x68 empties the slot byte 1 names."""

    def __init__(self, reports: dict[int, bytes] | None = None):
        self.reports = {0x20: FIRMWARE_REPORT}
        for first, report in zip((0x70, 0x71, 0x72), DEFAULT_PROFILE):
            self.reports[first] = report
        for index in (1, 2, 3):
            for part, report in enumerate(empty_slot(0x70 + 3 * index)):
                self.reports[0x70 + 3 * index + part] = report
        self.reports.update(reports or {})
        self.sent: list[bytes] = []
        self.closed = False

    def get_feature(self, report_id: int) -> bytes:
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

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry. The
    firmware and profile folders go to the temp folder too."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def plug(sys_root: Path, node: str = "hidraw2", product: int = 0x0DF2, bus: int = 0x03, instance: int = 3,
         battery: tuple[str, str] | None = ("100", "Full"), vendor: int = 0x054C,
         players: str | None = "00100") -> Path:
    """A controller as the kernel shows it: /sys/class/hidraw/<node>/device links to the HID device, with its
    uevent, report descriptor, power_supply (named after the controller's address, as hid-playstation does), its
    player lights (*players*: their brightness, left to right) and its four input devices (the controller, its motion
    sensors, touchpad and headset jack), each with its event node."""
    device = sys_root / "devices/usb6/6-2" / f"{bus:04X}:{vendor:04X}:{product:04X}.{instance:04X}"
    write(device / "uevent", f"DRIVER=playstation\nHID_ID={bus:04X}:{vendor:08X}:{product:08X}\n"
                             "HID_NAME=Sony Interactive Entertainment Wireless Controller\nHID_UNIQ=aa:bb:cc:dd:ee:ff")
    (device / "report_descriptor").write_bytes(DESCRIPTOR)
    if battery:
        supply = device / "power_supply/ps-controller-battery-00:00:00:00:00:00"
        write(supply / "capacity", battery[0])
        write(supply / "status", battery[1])
    for index, on in enumerate(players or ""):
        write(device / "leds" / f"input{10 + 4 * instance}:white:player-{index + 1}" / "brightness", on)
    for index, suffix in enumerate(("", " Motion Sensors", " Touchpad", " Headset Jack")):
        number = 10 + 4 * instance + index          # the joystick first, as the kernel registers them
        write(device / "input" / f"input{number}" / "name",
              f"Sony Interactive Entertainment Wireless Controller{suffix}")
        (device / "input" / f"input{number}" / f"event{number}").mkdir()
    link = sys_root / "class/hidraw" / node / "device"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(device)
    return device


def plug_held_back(sys_root: Path, product: int = 0x0DF2, instance: int = 8) -> Path:
    """A controller on the cable that no driver took: its USB HID device without a driver link."""
    device = sys_root / "bus/hid/devices" / f"0003:054C:{product:04X}.{instance:04X}"
    device.mkdir(parents=True)
    return device


def unplug(sys_root: Path, node: str = "hidraw2") -> None:
    import shutil
    folder = sys_root / "class/hidraw" / node
    target = (folder / "device").resolve()
    shutil.rmtree(folder)
    shutil.rmtree(target)
