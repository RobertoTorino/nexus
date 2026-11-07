# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import struct
import zlib

import pytest

from usb_hdcontrol import feedback


def test_the_rumble_effect_as_the_kernel_reads_it():
    effect = feedback.rumble_effect(0xC000, 0x1000, 900)
    assert len(effect) == 48
    assert struct.unpack_from("<HhH", effect, 0) == (feedback.FF_RUMBLE, -1, 0)
    assert struct.unpack_from("<HH", effect, 10) == (900, 0)
    assert struct.unpack_from("<HH", effect, 16) == (0xC000, 0x1000)


def test_rumble_uploads_plays_and_closes(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(feedback.os, "open", lambda *_a: 9)
    monkeypatch.setattr(feedback.os, "close", lambda fd: calls.append(("close", fd)))
    monkeypatch.setattr(feedback.os, "write", lambda fd, data: calls.append(("write", data)) or len(data))

    def ioctl(fd, request, effect):
        struct.pack_into("<h", effect, 2, 4)        # the kernel gives the effect its id
        calls.append(("ioctl", request))
    monkeypatch.setattr(feedback.fcntl, "ioctl", ioctl)
    rumble = feedback.Rumble(tmp_path / "event11")
    rumble.play(0, feedback.STRONG)
    rumble.close()
    rumble.close()
    assert calls[0] == ("ioctl", feedback.EVIOCSFF)
    assert calls[1] == ("write", struct.pack("<qqHHi", 0, 0, feedback.EV_FF, 4, 1))
    assert calls[2:] == [("close", 9)]


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


@pytest.mark.parametrize("text, color", [("#ff2020", (255, 32, 32)), ("#000000", (0, 0, 0)), ("", None),
                                          ("red", None), ("#zzzzzz", None)])
def test_parse_colour(text, color):
    assert feedback.parse_colour(text) == color
