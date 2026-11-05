# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the controllers in hidapi's list, the firmware report, and the programs that talk to the controller."""

from __future__ import annotations

import pytest

from conftest import BT_PATH, FIRMWARE_REPORT, USB_PATH, FakeDevice, entry
from hd_controller import controller


def test_the_owners_edge_on_usb():
    found = controller.find(lambda: [entry()])
    assert found == [controller.Controller(USB_PATH, 0x0DF2, "usb")]
    assert found[0].name == "DualSense Edge" and found[0].edge and found[0].connection == "USB cable"


def test_usb_first_then_bluetooth_and_other_devices_left_out():
    found = controller.find(lambda: [
        entry(BT_PATH, 0x0CE6, bus=2), entry(b"mouse", vendor=0x046D), entry(b"ds4", product=0x09CC),
        entry(USB_PATH), entry(USB_PATH), entry(b"other collection", usage=(0xFF00, 0x01))])
    assert [(c.name, c.bus) for c in found] == [("DualSense Edge", "usb"), ("DualSense", "bluetooth")]


def test_an_older_hidapi_without_the_bus_tells_bluetooth_by_its_path():
    found = controller.find(lambda: [entry(BT_PATH, 0x0CE6, bus=None), entry(USB_PATH, bus=None)])
    assert [c.bus for c in found] == ["usb", "bluetooth"]


def test_hidapi_failing_finds_nothing():
    def broken():
        raise OSError("no HID")
    assert controller.find(broken) == []


def test_the_owners_firmware_report():
    info = controller.parse_info(FIRMWARE_REPORT)
    assert (info.build_date, info.build_time) == ("Jun 21 2024", "19:09:17")
    assert info.target == 0x0044 and info.update == 0x0200
    assert controller.read_info(FakeDevice()) == info


def test_a_short_firmware_report_is_an_error():
    with pytest.raises(ValueError):
        controller.parse_info(FIRMWARE_REPORT[:20])


def test_the_programs_that_talk_to_the_controller():
    assert controller.holders(lambda: {"steam.exe", "explorer.exe", "ds4windows.exe"}) == ["DS4Windows", "Steam"]
    assert controller.holders(lambda: {"explorer.exe"}) == []


def test_the_process_list_reads_on_windows():
    """Windows' own list: this test's Python is in it."""
    import sys
    names = controller.programs()
    if sys.platform == "win32":
        assert any(name.startswith("python") for name in names)
    else:
        assert names == set()
