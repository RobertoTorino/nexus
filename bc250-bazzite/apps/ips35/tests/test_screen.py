# SPDX-License-Identifier: GPL-3.0-or-later
"""The protocol bytes, the models by their HELLO answer, finding the screen in /sys, and drawing on a fake port."""

from __future__ import annotations

from pathlib import Path

import pytest

from usb_ips35 import screen
from conftest import FakePort, plug


def test_command_packs_four_10_bit_values():
    # The whole 320x480 screen: x 0, y 0, end x 319, end y 479.
    assert screen.command(screen.DISPLAY_BITMAP, 0, 0, 319, 479) == bytes([0, 0, 4, 0xFD, 0xDF, 197])
    assert screen.bitmap_command(20, 20, 64, 64) == screen.command(197, 20, 20, 83, 83)
    assert screen.command(screen.SCREEN_ON) == bytes([0, 0, 0, 0, 0, 109])


@pytest.mark.parametrize("percent, value", [(100, 0), (0, 255), (50, 128), (150, 0), (-5, 255)])
def test_brightness_runs_from_255_darkest_to_0_brightest(percent, value):
    # On the owner's Turing 3.5" (22-10-2026) 25 was bright and 230 dim.
    assert screen.brightness_command(percent) == bytes([value >> 2, (value & 3) << 6, 0, 0, 0, 110])


def test_orientation_command_names_the_screen_size():
    data = screen.orientation_command(screen.Model("x", "x", 480, 800))
    assert len(data) == 16 and data[5] == 121 and data[6] == 100
    assert data[7:11] == bytes([480 >> 8, 480 & 255, 800 >> 8, 800 & 255])


@pytest.mark.parametrize("reply, name, size", [
    (b"", 'Turing Smart Screen 3.5"', (320, 480)),          # the owner's screen does not answer
    (bytes([1] * 6), 'UsbMonitor 3.5"', (320, 480)),
    (bytes([2] * 6), 'UsbMonitor 5"', (480, 800)),
    (bytes([3] * 6), 'UsbMonitor 7"', (600, 1024)),
    (b"\x07\x07", 'Turing Smart Screen 3.5"', (320, 480)),  # anything else
])
def test_hello_tells_the_model(reply, name, size):
    port = FakePort(reply)
    model = screen.Screen(port).hello()
    assert (model.name, (model.width, model.height)) == (name, size)
    assert port.writes == [bytes([69] * 6)]


def test_start_sets_portrait_and_switches_on():
    port = FakePort()
    lcd = screen.Screen(port)
    lcd.start()
    assert port.writes == [screen.orientation_command(screen.TURING_35), screen.command(109)]


def test_draw_sends_the_rectangle_row_by_row():
    port = FakePort()
    lcd = screen.Screen(port)
    lcd.model = screen.Model("tiny", "tiny", 4, 3)
    frame = bytes(range(24))                           # 4x3 pixels of 2 bytes
    lcd.draw(frame, (1, 1, 2, 2))
    # The command apart from its pixels: the screen drops whatever shares a USB packet with a command.
    assert port.writes == [screen.bitmap_command(1, 1, 2, 2), frame[10:14] + frame[18:22]]
    with pytest.raises(ValueError):
        lcd.draw(frame[:-2], (0, 0, 4, 3))


def test_find_by_usb_id(tmp_path):
    sys_root = tmp_path / "sys"
    plug(sys_root, "ttyACM0", vendor="2e8a", product="000a")        # another serial device
    plug(sys_root, "ttyACM1")
    found = screen.find(sys_root, tmp_path / "dev")
    assert found == [screen.Found(tmp_path / "dev/ttyACM1", "UsbMonitor", "USB35INCHIPSV2")]
    assert not found[0].usable                                       # no such port to open


def test_find_nothing(tmp_path):
    assert screen.find(tmp_path / "sys", tmp_path / "dev") == []


def test_usable_is_read_and_write_access(tmp_path):
    port = tmp_path / "ttyACM0"
    port.write_text("")
    assert screen.Found(port, "", "").usable
    port.chmod(0o444)
    assert not screen.Found(port, "", "").usable or Path("/").stat().st_uid == 0     # root may write anyway


def test_reset_floods_the_command_byte():
    port = FakePort()
    screen.Screen(port).reset()
    assert set(port.data) == {screen.RESET}
    assert len(port.data) >= 600 * 1024 * 2 + 6                     # a whole picture of the largest model and more
