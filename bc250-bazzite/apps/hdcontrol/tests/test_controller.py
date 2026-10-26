# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from conftest import DESCRIPTOR, FIRMWARE_REPORT, plug
from usb_hdcontrol import controller, hidraw


def test_feature_sizes_of_the_owners_edge():
    sizes = hidraw.feature_sizes(DESCRIPTOR)
    assert sizes[0x20] == 64
    assert sizes[0xF4] == 64 and sizes[0xF5] == 4
    assert all(sizes[report] == 64 for report in range(0x70, 0x7C))
    assert sizes[0x05] == 41 and sizes[0x09] == 20


def test_feature_sizes_ignore_input_and_output_reports():
    sizes = hidraw.feature_sizes(DESCRIPTOR)
    assert 0x01 not in sizes and 0x02 not in sizes


def test_parse_info_as_hid_playstation_reads_it():
    info = controller.parse_info(FIRMWARE_REPORT)
    assert (info.build_date, info.build_time) == ("Jun 21 2024", "19:09:17")
    assert info.target == 0x0044
    assert info.hardware == 0x01000216 and info.firmware == 0x01000078      # the kernel's log says the same
    assert info.update == 0x0200


@pytest.mark.parametrize("data", [b"", FIRMWARE_REPORT[:40], b"\x21" + FIRMWARE_REPORT[1:]])
def test_parse_info_refuses_another_report(data):
    with pytest.raises(ValueError):
        controller.parse_info(data)


def test_find_the_edge_on_usb_with_its_battery(tmp_path):
    plug(tmp_path)
    [found] = controller.find(tmp_path)
    assert (found.name, found.edge, found.connection, found.node) == ("DualSense Edge", True, "USB cable", "hidraw2")
    assert found.battery == controller.Battery(100, "Full")
    assert found.sizes()[0xF4] == 64


def test_find_a_dualsense_over_bluetooth_and_lists_usb_first(tmp_path):
    plug(tmp_path, "hidraw1", product=0x0CE6, bus=0x05, instance=4, battery=("40", "Discharging"))
    plug(tmp_path, "hidraw3")
    found = controller.find(tmp_path)
    assert [(c.node, c.bus) for c in found] == [("hidraw3", "usb"), ("hidraw1", "bluetooth")]
    assert found[1].name == "DualSense" and not found[1].edge
    assert found[1].battery == controller.Battery(40, "Discharging")


def test_find_skips_other_devices_and_a_missing_battery(tmp_path):
    plug(tmp_path, "hidraw0", product=0x250A, vendor=0x413C, bus=0x05)
    plug(tmp_path, "hidraw2", battery=None)
    [found] = controller.find(tmp_path)
    assert found.node == "hidraw2" and found.battery is None


def test_find_nothing(tmp_path):
    assert controller.find(tmp_path) == []


def test_holders_names_other_programs(tmp_path):
    node = tmp_path / "hidraw2"
    node.touch()
    for pid, name, target in (("100", "steam", node), ("200", "bash", tmp_path / "other")):
        (tmp_path / "proc" / pid / "fd").mkdir(parents=True)
        (tmp_path / "proc" / pid / "comm").write_text(name + "\n")
        (tmp_path / "proc" / pid / "fd" / "3").symlink_to(target)
    assert controller.holders(node, tmp_path / "proc") == ["steam"]


def test_device_pads_reports_to_the_declared_size(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(hidraw.os, "open", lambda *_a: 7)
    monkeypatch.setattr(hidraw.os, "close", lambda _fd: None)
    monkeypatch.setattr(hidraw.fcntl, "ioctl", lambda fd, request, buffer: calls.append((request, bytes(buffer))))
    with hidraw.Device(tmp_path / "hidraw2", {0xF4: 64}) as device:
        device.set_feature(b"\xf4\x01\x02ab")
        with pytest.raises(ValueError):
            device.set_feature(b"\xf4" + bytes(64))
    request, data = calls[0]
    assert len(data) == 64 and data[:5] == b"\xf4\x01\x02ab" and data[5:] == bytes(59)
    assert request == (3 << 30) | (64 << 16) | (ord("H") << 8) | 0x06


def test_event_node_is_the_controllers_own_input(tmp_path):
    plug(tmp_path / "sys")
    [found] = controller.find(tmp_path / "sys")
    assert controller.event_node(found, tmp_path / "dev") == tmp_path / "dev" / "input" / "event22"


def test_event_node_without_input_devices(tmp_path):
    import shutil
    device = plug(tmp_path / "sys")
    shutil.rmtree(device / "input")
    [found] = controller.find(tmp_path / "sys")
    assert controller.event_node(found) is None


def test_held_back_finds_a_cable_no_driver_took(tmp_path):
    from conftest import plug_held_back
    assert controller.held_back(tmp_path) == []
    device = plug_held_back(tmp_path)
    assert controller.held_back(tmp_path) == [0x0DF2]
    (device / "driver").symlink_to(tmp_path)            # taken by a driver: not held back
    assert controller.held_back(tmp_path) == []


def test_bluetooth_address_only_over_bluetooth(tmp_path):
    plug(tmp_path, "hidraw1", bus=0x05)
    plug(tmp_path, "hidraw3", instance=5)
    usb, bluetooth = controller.find(tmp_path)
    assert controller.bluetooth_address(bluetooth) == "aa:bb:cc:dd:ee:ff"
    assert controller.bluetooth_address(usb) == ""


@pytest.mark.parametrize("returncode, out, problem", [(0, "Attempting to disconnect\nSuccessful disconnected", ""),
                                                      # BlueZ 5.87 on the owner's board (23-10-2026)
                                                      (0, "Attempting to disconnect from <mac>\n"
                                                          "Disconnection successful\n", ""),
                                                      (1, "Failed to disconnect", "did not let go"),
                                                      (0, "Device not available", "did not let go")])
def test_disconnect_bluetooth(returncode, out, problem):
    import subprocess
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, out, "")
    result = controller.disconnect_bluetooth("aa:bb:cc:dd:ee:ff", run)
    assert calls == [["bluetoothctl", "disconnect", "aa:bb:cc:dd:ee:ff"]]
    assert (problem in result) if problem else result == ""


def test_disconnect_bluetooth_without_bluetoothctl():
    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])
    assert "not installed" in controller.disconnect_bluetooth("aa:bb:cc:dd:ee:ff", missing)


def test_the_player_lights_as_the_kernel_set_them(tmp_path):
    plug(tmp_path, players="01010")
    plug(tmp_path, node="hidraw5", instance=5, players=None)
    first, second = controller.find(tmp_path)
    assert controller.player_lights(first) == (False, True, False, True, False)
    assert controller.PLAYER_LIGHTS[controller.player_lights(first)] == 2
    assert controller.player_lights(second) is None                    # no LEDs in /sys: unknown


def test_the_player_number(tmp_path):
    plug(tmp_path, players="11011")
    plug(tmp_path, node="hidraw5", instance=5, players="11000")         # not a pattern hid-playstation sets
    four, odd = controller.find(tmp_path)
    assert controller.player_number(four) == 4 and controller.player_number(odd) is None
