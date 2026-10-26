# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers connected (controllers.py), read from the kernel's list as the run wrapper reads it."""

from __future__ import annotations

from rpcs3_manager import controllers
from test_run_wrapper import DS4_AND_STEAM, STEAM_ONLY

# The owner's DualSense Edge over Bluetooth (24-10-2026): the kernel gives its motion sensors a joystick handler too.
BLUETOOTH_EDGE = """\
I: Bus=0005 Vendor=054c Product=0df2 Version=8100
N: Name="DualSense Edge Wireless Controller"
H: Handlers=event11 js0

I: Bus=0005 Vendor=054c Product=0df2 Version=8100
N: Name="DualSense Edge Wireless Controller Motion Sensors"
H: Handlers=event12 js1

I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 0"
H: Handlers=event14 js2
"""


def test_the_controllers_connected(tmp_path):
    devices = tmp_path / "devices"
    assert controllers.connected(devices) == []                                 # no file (not Linux)
    devices.write_text(DS4_AND_STEAM)
    assert controllers.connected(devices) == ["Sony Interactive Entertainment Wireless Controller"]
    devices.write_text(STEAM_ONLY)                                              # Steam's virtual one only
    assert controllers.connected(devices) == []
    devices.write_text(DS4_AND_STEAM + "\nI: Bus=0005 Vendor=045e Product=0b13 Version=0509\n"
                       'N: Name="Xbox Wireless Controller"\nH: Handlers=event20 js2\n')
    assert controllers.connected(devices) == ["Sony Interactive Entertainment Wireless Controller",
                                              "Xbox Wireless Controller"]
    devices.write_text('N: Name="Dell Keybd KB740"\nH: Handlers=sysrq kbd event3\n')
    assert controllers.connected(devices) == []
    devices.write_text(BLUETOOTH_EDGE)                                          # the motion sensors: a js too
    assert controllers.connected(devices) == ["DualSense Edge Wireless Controller"]


def test_the_controllers_as_sdl_names_them(tmp_path):
    """The names come from SDL3 itself, in a process of the app's own Python: one a line, in SDL's order; None
    when SDL3 is not there (the probe exits 3), when Python fails or when it does not answer in time."""
    fake = tmp_path / "python"
    fake.write_text('#!/bin/sh\n[ "$1" = -I ] && [ "$2" = -c ] || exit 9\n'
                    'printf "DualSense Edge Wireless Controller\\nXbox Series X Controller\\n"\n')
    fake.chmod(0o755)
    assert controllers.sdl_names(str(fake)) == ["DualSense Edge Wireless Controller", "Xbox Series X Controller"]
    fake.write_text("#!/bin/sh\nexit 3\n")
    assert controllers.sdl_names(str(fake)) is None
    fake.write_text("#!/bin/sh\nprintf ''\n")
    assert controllers.sdl_names(str(fake)) == []
    assert controllers.sdl_names(str(tmp_path / "missing")) is None
    fake.write_text("#!/bin/sh\nsleep 5\n")
    assert controllers.sdl_names(str(fake), timeout=0.2) is None
    assert "SDL_GetGamepads" in controllers.SDL_PROBE and "0x28DE" in controllers.SDL_PROBE   # Steam's left out
