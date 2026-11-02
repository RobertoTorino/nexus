# SPDX-License-Identifier: GPL-3.0-or-later
"""The protocol bytes (as the BC250 app's), the models by their HELLO answer, finding the screen among Windows' USB
devices with its COM port, and drawing on a fake port."""

from __future__ import annotations

import pytest

from smart_screen import screen
from conftest import FakePort

SCREEN = r"USB\VID_1A86&PID_5722\USB35INCHIPSV2"         # the owner's, 02-11-2026


def test_command_packs_four_10_bit_values():
    # The whole 320x480 screen: x 0, y 0, end x 319, end y 479.
    assert screen.command(screen.DISPLAY_BITMAP, 0, 0, 319, 479) == bytes([0, 0, 4, 0xFD, 0xDF, 197])
    assert screen.bitmap_command(20, 20, 64, 64) == screen.command(197, 20, 20, 83, 83)
    assert screen.command(screen.SCREEN_ON) == bytes([0, 0, 0, 0, 0, 109])


@pytest.mark.parametrize("percent, value", [(100, 0), (0, 255), (50, 128), (150, 0), (-5, 255)])
def test_brightness_runs_from_255_darkest_to_0_brightest(percent, value):
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
    screen.Screen(port).start()
    assert port.writes == [screen.orientation_command(screen.TURING_35), screen.command(109)]


def test_draw_sends_the_command_and_the_pixels_apart():
    port = FakePort()
    lcd = screen.Screen(port)
    lcd.model = screen.Model("tiny", "tiny", 4, 3)
    frame = bytes(range(24))                           # 4x3 pixels of 2 bytes
    lcd.draw(frame, (1, 1, 2, 2))
    # The command apart from its pixels: the screen drops whatever shares a USB packet with a command.
    assert port.writes == [screen.bitmap_command(1, 1, 2, 2), frame[10:14] + frame[18:22]]
    with pytest.raises(ValueError):
        lcd.draw(frame[:-2], (0, 0, 4, 3))


def test_reset_floods_the_command_byte():
    port = FakePort()
    screen.Screen(port).reset()
    assert set(port.data) == {screen.RESET}
    assert len(port.data) >= 600 * 1024 * 2 + 6                     # a whole picture of the largest model and more


def test_find_by_usb_id_with_its_com_port():
    devices = [r"USB\VID_2E8A&PID_000A\E66138", SCREEN, r"USB\VID_1A86&PID_57220\X",
               r"USB\VID_1A86&PID_5722&MI_00\7&1&0&0000", r"USB\VID_1A86&PID_5722\NOPORT"]
    ports = {SCREEN: "COM3", r"USB\VID_1A86&PID_5722&MI_00\7&1&0&0000": "COM7"}
    found = screen.find(lambda: devices, lambda instance: ports.get(instance, ""))
    assert found == [screen.Found("COM3", SCREEN), screen.Found("COM7", r"USB\VID_1A86&PID_5722&MI_00\7&1&0&0000")]


def test_find_nothing():
    assert screen.find(lambda: [], lambda _instance: "COM1") == []


def test_a_port_another_program_holds_is_in_use():
    assert screen.PortError(screen.ERROR_ACCESS_DENIED, "Opening COM3").in_use
    assert not screen.PortError(screen.ERROR_FILE_NOT_FOUND, "Opening COM3").in_use
