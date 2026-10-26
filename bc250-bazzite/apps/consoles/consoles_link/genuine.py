# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whether a Sony controller is genuine or fake: "Genuine DS4v1" or "Fake DS4" (owner's decision, 13-10-2026: a
controller that fails the check is shown as fake, faulty or not).

A DualShock 4 or DualSense answers HID feature reports that many copies answer wrongly or not at all: its firmware
information (build date, hardware and firmware version) and the calibration of its motion sensors. The layouts are
those the Linux kernel's driver reads (hid-playstation), which logs the same versions when a controller connects.
The check reads these reports through the controller's hidraw device (reading only; nothing is sent to it) and looks
whether they make sense: a build date of the controller's era, versions that are not empty, a calibration that is
there and symmetric (a sensor's plus and minus about as large).

The check is built from genuine controllers' answers; what fakes answer is to be learned from a fake on the owner's
board. A real proof would be the console's own challenge, which a genuine controller signs with Sony's key; that is
not done here."""

from __future__ import annotations

import datetime
import fcntl
import os
import struct
from dataclasses import dataclass
from typing import Callable

SONY = 0x054C
DUALSHOCK4 = {0x05C4: "DualShock 4 v1 (CUH-ZCT1)", 0x09CC: "DualShock 4 v2 (CUH-ZCT2)",
              0x0BA0: "DualShock 4 USB wireless adapter"}
DUALSENSE = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
SHORT = {0x05C4: "DS4v1", 0x09CC: "DS4v2", 0x0BA0: "DS4 adapter", 0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
FAKE = {0x05C4: "DS4", 0x09CC: "DS4", 0x0BA0: "DS4 adapter", 0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
BUS_USB, BUS_BLUETOOTH = 3, 5

DS4_FIRMWARE, DS4_FIRMWARE_SIZE = 0xA3, 49
DS4_CALIBRATION_USB, DS4_CALIBRATION_USB_SIZE = 0x02, 37
DS4_CALIBRATION_BT, DS4_CALIBRATION_BT_SIZE = 0x05, 41
DS_FIRMWARE, DS_FIRMWARE_SIZE = 0x20, 64
DS_CALIBRATION, DS_CALIBRATION_SIZE = 0x05, 41
EARLIEST_YEAR = 2013                     # the DualShock 4 came out in 2013

ReadFeature = Callable[[int, int], bytes | None]        # (report id, size) -> the report, or None when refused


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Result:
    model: str
    checks: list[Check]
    product: int = 0

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def label(self) -> str:
        """"Genuine DS4v2" or "Fake DS4"."""
        if self.passed:
            return f"Genuine {SHORT.get(self.product, self.model)}"
        return f"Fake {FAKE.get(self.product, self.model)}"

    def verdict(self) -> str:
        if self.passed:
            return f"{self.label()}: it answers as a genuine {self.model} does."
        failed = ", ".join(check.name.lower() for check in self.checks if not check.ok)
        return f"{self.label()}: it does not answer as a genuine {self.model} does ({failed})."


def _date(text: bytes, today: datetime.date) -> datetime.date | None:
    try:
        date = datetime.datetime.strptime(text.split(b"\0")[0].decode("ascii").strip(), "%b %d %Y").date()
    except (UnicodeDecodeError, ValueError):
        return None
    return date if EARLIEST_YEAR <= date.year and date <= today else None


def _firmware(report: bytes | None, date_at: slice | None, hw_at: int, fw_at: int, wide: bool,
              today: datetime.date) -> list[Check]:
    """The build date (where its place is known) and the hardware and firmware versions."""
    if report is None:
        return [Check("Firmware information", False, "The controller does not answer the request for it.")]
    unpack = "<I" if wide else "<H"
    size = 4 if wide else 2
    hw, = struct.unpack_from(unpack, report, hw_at)
    fw, = struct.unpack_from(unpack, report, fw_at)
    checks = []
    if date_at is not None:
        date = _date(report[date_at], today)
        checks.append(Check("Build date", date is not None, f"Built {date:%d %b %Y}." if date else
                            "No build date of the controller's era in its answer."))
    checks.append(Check("Versions", bool(hw and fw) and hw != (1 << 8 * size) - 1 and fw != (1 << 8 * size) - 1,
                        f"Hardware {hw:#06x}, firmware {fw:#06x}."))
    return checks


def _calibration(report: bytes | None, bluetooth_order: bool) -> Check:
    """The gyro's and accelerometer's calibration: each axis's plus value positive, its minus value negative, both
    about as large, and the gyro's speed not zero (the kernel falls back to defaults when it is)."""
    if report is None:
        return Check("Motion calibration", False, "The controller does not answer the request for it.")
    values = struct.unpack_from("<17h", report, 1)
    gyro = values[3:9]
    if bluetooth_order:                  # plus, plus, plus, minus, minus, minus
        pairs = [(gyro[0], gyro[3]), (gyro[1], gyro[4]), (gyro[2], gyro[5])]
    else:                                # plus, minus for each axis
        pairs = [(gyro[0], gyro[1]), (gyro[2], gyro[3]), (gyro[4], gyro[5])]
    speed_plus, speed_minus = values[9], values[10]
    accel = values[11:17]
    pairs += [(accel[0], accel[1]), (accel[2], accel[3]), (accel[4], accel[5])]
    symmetric = all(plus > 0 > minus and 0.8 <= plus / -minus <= 1.25 for plus, minus in pairs)
    ok = symmetric and speed_plus + speed_minus != 0
    return Check("Motion calibration", ok,
                 "Calibrated, both directions of every axis alike." if ok else
                 "Missing, empty or lopsided: the motion sensors may be off or absent.")


def check(vendor: int, product: int, bus: int, read: ReadFeature, today: datetime.date | None = None) -> Result | None:
    """The checks for a Sony DualShock 4 or DualSense, or None for any other controller."""
    today = today or datetime.date.today()
    if vendor != SONY:
        return None
    if product in DUALSHOCK4:
        firmware = read(DS4_FIRMWARE, DS4_FIRMWARE_SIZE)
        checks = _firmware(firmware, slice(1, 17), 35, 41, False, today)
        if bus == BUS_BLUETOOTH:
            calibration = read(DS4_CALIBRATION_BT, DS4_CALIBRATION_BT_SIZE)
        else:
            calibration = read(DS4_CALIBRATION_USB, DS4_CALIBRATION_USB_SIZE)
        # Over Bluetooth and through Sony's USB adapter the gyro's values come in another order (the kernel's).
        checks.append(_calibration(calibration, bus == BUS_BLUETOOTH or product == 0x0BA0))
        return Result(DUALSHOCK4[product], checks, product)
    if product in DUALSENSE:
        firmware = read(DS_FIRMWARE, DS_FIRMWARE_SIZE)
        checks = _firmware(firmware, None, 24, 28, True, today)      # the kernel reads no build date from it
        checks.append(_calibration(read(DS_CALIBRATION, DS_CALIBRATION_SIZE), False))
        return Result(DUALSENSE[product], checks, product)
    return None


# --- The controller's hidraw device ------------------------------------------------------------------------------

def _ioc(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | number


def device_info(path: str) -> tuple[int, int, int] | None:
    """(bus, vendor, product) of a hidraw device, or None when it cannot be opened."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        info = bytearray(8)
        fcntl.ioctl(fd, _ioc(2, 0x03, 8), info)              # HIDIOCGRAWINFO
        bus, vendor, product = struct.unpack("<Ihh", info)
        return bus, vendor & 0xFFFF, product & 0xFFFF
    except OSError:
        return None
    finally:
        os.close(fd)


def feature_reader(path: str) -> ReadFeature:
    """Reads feature reports from a hidraw device (HIDIOCGFEATURE): None when the controller refuses one."""
    def read(report_id: int, size: int) -> bytes | None:
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            return None
        try:
            buf = bytearray(size)
            buf[0] = report_id
            length = fcntl.ioctl(fd, _ioc(3, 0x07, size), buf)   # HIDIOCGFEATURE
            return bytes(buf) if length > 0 and buf[0] == report_id else None
        except OSError:
            return None
        finally:
            os.close(fd)
    return read


def check_device(path: str) -> Result | None:
    """The check for the controller at a hidraw path (as SDL gives it), or None when it is not a Sony controller or
    the device cannot be read."""
    if not path.startswith("/dev/hidraw"):
        return None
    info = device_info(path)
    if info is None:
        return None
    bus, vendor, product = info
    return check(vendor, product, bus, feature_reader(path))
