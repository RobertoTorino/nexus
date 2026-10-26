# SPDX-License-Identifier: GPL-3.0-or-later
"""python -m usb_hdcontrol --info: what it prints, without a window."""

from __future__ import annotations

from conftest import FakeDevice, plug

from usb_hdcontrol import __main__ as entry, controller


def test_info(tmp_path, capsys):
    plug(tmp_path)
    assert entry.print_info(lambda: controller.find(tmp_path), open_device=lambda path, sizes: FakeDevice()) == 0
    out = capsys.readouterr().out
    assert "DualSense Edge on USB cable (hidraw2)" in out and "Battery: 100 %, Full" in out
    assert "Firmware: 0x0200 (built Jun 21 2024 19:09:17, target 0044" in out
    assert "Fn + Triangle: Default Profile, sticks Default and Default" in out and "Fn + Circle: empty" in out


def test_info_without_a_controller(capsys):
    assert entry.print_info(lambda: []) == 1
    assert capsys.readouterr().out.startswith("No controller found.")


def test_info_when_the_controller_cannot_be_read(tmp_path, capsys):
    plug(tmp_path, battery=None)

    def denied(path, sizes):
        raise PermissionError(13, "Permission denied")
    assert entry.print_info(lambda: controller.find(tmp_path), open_device=denied) == 0
    out = capsys.readouterr().out
    assert "Battery: ? %, not reported" in out and "Could not be read: Permission denied" in out
