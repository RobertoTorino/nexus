# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers connected (controllers.py), read from the kernel's list as the run wrapper reads it."""

from __future__ import annotations

from shadps4_manager import controllers
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
