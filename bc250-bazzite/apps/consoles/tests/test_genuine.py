# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whether a Sony controller is genuine or fake (genuine.py): the owner's DualShock 4 (CUH-ZCT1, Bluetooth;
its answers read on the board on 13-10-2026, the versions as the kernel logged them), the same answers in the USB
order, a DualSense built to the kernel driver's layout, and the ways a copy fails."""

from __future__ import annotations

import datetime
import struct

import pytest

from consoles_link import genuine
from consoles_link.genuine import BUS_BLUETOOTH, BUS_USB, SONY

TODAY = datetime.date(2026, 10, 13)
FIRMWARE = bytes.fromhex("a34d61792031352032303135000000000030373a33393a3137000000000000000000"
                         "011454010000003320030100800300")
CALIBRATION_BT = bytes.fromhex("050b000400000009227f2226240ede83dddddb1c021c02141febe07b2085df86207bdf0300613471fd")


def _usb_order(bt: bytes) -> bytes:
    """The same calibration in the USB order: each gyro axis's plus and minus side by side."""
    values = list(struct.unpack_from("<17h", bt, 1))
    plus, minus = values[3:6], values[6:9]
    values[3:9] = [plus[0], minus[0], plus[1], minus[1], plus[2], minus[2]]
    return bytes([0x02]) + struct.pack("<17h", *values) + bytes(2)


def reader(reports: dict[int, bytes | None]):
    return lambda report_id, size: reports.get(report_id)


def test_the_owners_dualshock4_over_bluetooth():
    result = genuine.check(SONY, 0x05C4, BUS_BLUETOOTH, reader({0xA3: FIRMWARE, 0x05: CALIBRATION_BT}), TODAY)
    assert result.model == "DualShock 4 v1 (CUH-ZCT1)" and result.passed
    assert [c.detail for c in result.checks] == ["Built 15 May 2015.", "Hardware 0x5414, firmware 0x2033.",
                                                 "Calibrated, both directions of every axis alike."]
    assert result.label() == "Genuine DS4v1"
    assert result.verdict() == "Genuine DS4v1: it answers as a genuine DualShock 4 v1 (CUH-ZCT1) does."


def test_over_usb_the_calibration_comes_in_the_other_order():
    usb = _usb_order(CALIBRATION_BT)
    v2 = genuine.check(SONY, 0x09CC, BUS_USB, reader({0xA3: FIRMWARE, 0x02: usb}), TODAY)
    assert v2.passed and v2.label() == "Genuine DS4v2"
    # Read in the Bluetooth order, the same values would not be symmetric: the order matters.
    assert not genuine.check(SONY, 0x05C4, BUS_BLUETOOTH, reader({0xA3: FIRMWARE, 0x05: usb}), TODAY).passed
    # Sony's USB adapter is on the USB bus but uses the Bluetooth order.
    assert genuine.check(SONY, 0x0BA0, BUS_USB, reader({0xA3: FIRMWARE, 0x02: CALIBRATION_BT}), TODAY).passed


@pytest.mark.parametrize("change, failed", [
    ({0xA3: None}, "firmware information"),
    ({0xA3: FIRMWARE[:1] + bytes(32) + FIRMWARE[33:]}, "build date"),                    # no date
    ({0xA3: FIRMWARE[:1] + b"Jan 01 2009".ljust(16, b"\0") + FIRMWARE[17:]}, "build date"),  # before the DS4
    ({0xA3: FIRMWARE[:1] + b"Jan 01 2031".ljust(16, b"\0") + FIRMWARE[17:]}, "build date"),  # in the future
    ({0xA3: FIRMWARE[:35] + bytes(8) + FIRMWARE[43:]}, "versions"),
    ({0x05: None}, "motion calibration"),
    ({0x05: bytes(41)}, "motion calibration"),
    ({0x05: CALIBRATION_BT[:7] + struct.pack("<h", 2000) + CALIBRATION_BT[9:]}, "motion calibration"),  # lopsided
])
def test_what_a_copy_gets_wrong(change, failed):
    reports = {0xA3: FIRMWARE, 0x05: CALIBRATION_BT} | change
    result = genuine.check(SONY, 0x05C4, BUS_BLUETOOTH, reader(reports), TODAY)
    assert not result.passed and result.label() == "Fake DS4" and f"({failed}" in result.verdict()
    assert result.verdict().startswith("Fake DS4: it does not answer as a genuine DualShock 4 v1 (CUH-ZCT1) does")


def test_a_dualsense():
    firmware = bytearray(64)
    firmware[0] = 0x20
    struct.pack_into("<II", firmware, 24, 0x00000110, 0x00000412)
    calibration = bytes([0x05]) + _usb_order(CALIBRATION_BT)[1:] + bytes(4)
    result = genuine.check(SONY, 0x0CE6, BUS_USB, reader({0x20: bytes(firmware), 0x05: calibration}), TODAY)
    assert result.model == "DualSense" and result.passed and result.label() == "Genuine DualSense"
    assert [c.name for c in result.checks] == ["Versions", "Motion calibration"]       # no build date to check


def test_other_controllers_are_not_checked():
    assert genuine.check(0x045E, 0x0B12, BUS_USB, reader({}), TODAY) is None           # an Xbox controller
    assert genuine.check(SONY, 0x0268, BUS_USB, reader({}), TODAY) is None              # a DualShock 3
    assert genuine.check_device("/dev/input/event3") is None
    assert genuine.check_device("/dev/hidraw-none") is None
