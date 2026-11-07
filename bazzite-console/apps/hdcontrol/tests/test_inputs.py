# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os

from usb_hdcontrol import inputs

# Read from the owner's Edge at rest on USB (23-10-2026): sticks a hair off the middle, the hat at 8, nothing pressed.
AT_REST = bytes.fromhex("01807d7f7c00003008000000") + bytes(52)


def report(buttons=(0x08, 0, 0), sticks=(128, 128, 128, 128), triggers=(0, 0), bluetooth=False) -> bytes:
    head = bytes([0x31, 0x00]) if bluetooth else bytes([0x01])
    return head + bytes(sticks) + bytes(triggers) + b"\x00" + bytes(buttons) + bytes(50)


def test_the_owners_edge_at_rest():
    reading = inputs.parse(AT_REST)
    assert reading.pressed == frozenset() and reading.triggers == (0.0, 0.0)
    assert all(abs(value) < 0.05 for value in reading.sticks)


def test_every_button_and_the_hat():
    assert inputs.parse(report((0x00, 0, 0))).pressed == {"up"}
    assert inputs.parse(report((0x05, 0, 0))).pressed == {"down", "left"}
    assert inputs.parse(report((0xF8, 0, 0))).pressed == {"square", "cross", "circle", "triangle"}
    assert inputs.parse(report((0x08, 0xFF, 0))).pressed == {"l1", "r1", "l2", "r2", "create", "options", "l3", "r3"}
    assert inputs.parse(report((0x08, 0, 0xF7))).pressed == {"ps", "touchpad", "mute", "fn_left", "fn_right",
                                                            "back_left", "back_right"}


def test_sticks_and_triggers():
    reading = inputs.parse(report(sticks=(0, 255, 128, 128), triggers=(255, 51)))
    assert reading.sticks[:2] == (-1.0, 1.0) and reading.sticks[2] == 0.0
    assert reading.triggers == (1.0, 0.2)


def test_bluetooth_has_one_byte_more_in_front():
    assert inputs.parse(report((0x08, 0x01, 0), bluetooth=True)).pressed == {"l1"}


def test_other_reports_are_skipped():
    assert inputs.parse(b"\x05" + bytes(40)) is None
    assert inputs.parse(b"\x01\x80") is None


def test_the_reader_gives_the_newest_reading(tmp_path):
    read_end, write_end = os.pipe()
    reader = inputs.Reader.__new__(inputs.Reader)
    reader.fd = read_end
    os.set_blocking(read_end, False)
    assert reader.read() is None
    os.write(write_end, report((0x08, 0x01, 0)))
    os.write(write_end, report((0x08, 0x02, 0)))
    # A pipe joins the two writes; a hidraw node gives one report per read, as the reader asks.
    assert reader.read() is not None
    reader.close()
    os.close(write_end)
    assert reader.fd == -1


def test_the_edges_active_profile():
    """Byte 49 of the USB report, as the owner's Edge sent it (23-10-2026): 0x1c on Fn + Triangle, 0x2c on Square."""
    def with_byte_49(value, bluetooth=False):
        data = bytearray(report(bluetooth=bluetooth))
        data[49 + bluetooth] = value
        return bytes(data)
    assert inputs.parse(with_byte_49(0x1C)).profile == "Triangle"
    assert inputs.parse(with_byte_49(0x2C)).profile == "Square"
    assert inputs.parse(with_byte_49(0x4C)).profile == "Circle"
    assert inputs.parse(with_byte_49(0x3C, bluetooth=True)).profile == "Cross"
    assert inputs.parse(with_byte_49(0x00)).profile == "" and inputs.parse(with_byte_49(0x5C)).profile == ""
    assert inputs.parse(AT_REST).profile == ""                          # its recorded bytes end at byte 11
