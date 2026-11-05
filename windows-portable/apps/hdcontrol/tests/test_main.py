# SPDX-License-Identifier: GPL-3.0-or-later
"""--info: each controller's connection, battery, firmware and profiles, without a window and without the network;
never its path or its address."""

from __future__ import annotations

from conftest import BT_PATH, USB_PATH, FakeDevice, input_report
from hd_controller import __main__ as entry
from hd_controller import controller


def test_info_describes_the_edge():
    device = FakeDevice()
    device.inputs.append(input_report(status=0x14))
    lines = entry.describe(controller.Controller(USB_PATH, 0x0DF2, "usb"), device, sleep=lambda _s: None)
    assert lines[0] == "DualSense Edge on USB cable"
    assert lines[1] == "  Battery: 45 %, Charging"
    assert lines[2].startswith("  Firmware: 0x0200 (built Jun 21 2024 19:09:17, target 0044")
    assert lines[3] == "  Fn + Triangle: Default Profile, sticks Default and Default"
    assert lines[4:] == ["  Fn + Square: empty", "  Fn + Cross: empty", "  Fn + Circle: empty"]


def test_info_says_what_could_not_be_read():
    class Exclusive(FakeDevice):
        def __call__(self, path, sizes=None, blocking=True):
            raise OSError("it could not be opened")
    lines = entry.describe(controller.Controller(BT_PATH, 0x0CE6, "bluetooth"), Exclusive(), sleep=lambda _s: None)
    assert lines == ["DualSense on Bluetooth", "  Battery: ? %, not reported", "  Could not be read: it could not be "
                     "opened"]
    assert not any(BT_PATH.decode() in line for line in lines)


def test_info_without_a_controller(capsys):
    assert entry.print_info(lambda: []) == 1
    assert capsys.readouterr().out.startswith("No controller found. Plug the controller in")
    assert entry.print_info(lambda: [controller.Controller(USB_PATH, 0x0DF2, "usb")], lambda found: ["one"]) == 0
    assert capsys.readouterr().out == "one\n"
