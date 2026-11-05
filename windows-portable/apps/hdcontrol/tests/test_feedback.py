# SPDX-License-Identifier: GPL-3.0-or-later
"""The output reports: the light bar's (the BC250 app's, byte for byte) and the motors', in the layout hid-playstation
sends them."""

from __future__ import annotations

import zlib

import pytest

from hd_controller import feedback


def test_the_vibration_test_runs_left_then_right():
    steps = feedback.VIBRATION_STEPS
    assert [(side, strong > 0, weak > 0) for _when, side, strong, weak in steps] == [
        ("left", True, False), ("", False, False), ("right", False, True), ("", False, False)]
    assert [when for when, *_rest in steps] == sorted(when for when, *_rest in steps)


def test_the_light_bar_over_usb():
    report = feedback.lightbar_report("usb", (10, 20, 30))
    assert len(report) == 63 and report[0] == 0x02
    assert report[1] == 0 and report[2] == feedback.LIGHTBAR_CONTROL
    assert report[45:48] == bytes((10, 20, 30)) and report[48:] == bytes(15)


def test_the_light_bar_over_bluetooth_with_its_crc():
    report = feedback.lightbar_report("bluetooth", (10, 20, 30), sequence=3)
    assert len(report) == 78 and report[:3] == bytes((0x31, 0x30, 0x10))
    assert report[4] == feedback.LIGHTBAR_CONTROL and report[47:50] == bytes((10, 20, 30))
    assert int.from_bytes(report[-4:], "little") == zlib.crc32(b"\xa2" + report[:-4])


def test_the_motors_over_usb_with_the_first_flag():
    """A DualSense before firmware 0x0215: the compatible vibration in valid flag 0, the left motor at byte 3 of the
    common part, the right one at byte 2, each the magnitude's high byte."""
    report = feedback.rumble_report("usb", 0xC000, 0x1000, v2=False)
    assert len(report) == 63 and report[0] == 0x02
    assert report[1] == feedback.HAPTICS_SELECT | feedback.COMPATIBLE_VIBRATION and report[2] == 0
    assert (report[1 + 3], report[1 + 2]) == (0xC0, 0x10)
    assert report[1 + 38] == 0 and report[1 + 44:1 + 47] == bytes(3)        # the light bar left alone


def test_the_motors_with_the_second_flag_and_over_bluetooth():
    report = feedback.rumble_report("bluetooth", 0, 0xC000, v2=True, sequence=5)
    assert len(report) == 78 and report[:3] == bytes((0x31, 0x50, 0x10))
    assert report[3] == feedback.HAPTICS_SELECT and report[3 + 38] == feedback.COMPATIBLE_VIBRATION2
    assert (report[3 + 3], report[3 + 2]) == (0, 0xC0)
    assert int.from_bytes(report[-4:], "little") == zlib.crc32(b"\xa2" + report[:-4])


@pytest.mark.parametrize("edge, update, v2", [(True, None, True), (True, 0x0100, True), (False, 0x0214, False),
                                              (False, 0x0215, True), (False, None, False)])
def test_which_flag_as_hid_playstation_chooses_it(edge, update, v2):
    assert feedback.vibration_v2(edge, update) is v2


@pytest.mark.parametrize("text, color", [("#ff2020", (255, 32, 32)), ("#000000", (0, 0, 0)), ("", None),
                                          ("red", None), ("#zzzzzz", None)])
def test_parse_colour(text, color):
    assert feedback.parse_colour(text) == color
