# SPDX-License-Identifier: GPL-3.0-or-later
"""What Windows reports (device.py): the query's answer as the Device card shows it, one object or a list, missing
parts, the battery, the query itself, and what is plugged in: a dock's hubs and what is behind them, the devices this
suite knows, Device Manager's problems and the network adapters' state."""

from __future__ import annotations

import base64
import json

import pytest

from conftest import ALLY, DOCKED, PLUGGED
from portable_test import device


def test_the_ally_as_windows_reported_it(ally_json):
    found = device.parse(ally_json)
    assert found.name == "ROG Xbox Ally X"
    assert dict(found.rows()) == {
        "Device": "ROG Xbox Ally X", "Processor": "AMD Ryzen AI Z2 Extreme", "Cores": "8 cores, 16 threads",
        "Graphics": "AMD Radeon(TM) 890M Graphics", "Driver": "32.0.32015.7029", "Memory": "24 GB, 15.6 GB usable",
        "Storage": "1024 GB, SAMSUNG MZVMA1T0HCLD-00BTW", "System": "Windows 11 Home, build 26300",
        "Firmware": "RC73XA.319", "Battery": "82%, on battery"}
    assert found.report().splitlines()[0] == "Device: ROG Xbox Ally X"


def test_lists_of_several(ally_json):
    data = json.loads(ally_json)
    data["gpu"] = [data["gpu"], {"name": "Microsoft Basic Display Adapter", "driver": ""}]
    data["disks"] = [data["disks"], {"model": "SD card", "size": 128_000_000_000}]
    found = device.parse(json.dumps(data))
    rows = dict(found.rows())
    assert rows["Graphics"] == "AMD Radeon(TM) 890M Graphics, Microsoft Basic Display Adapter"
    assert rows["Driver"] == "32.0.32015.7029"
    assert rows["Storage"] == "1024 GB, SAMSUNG MZVMA1T0HCLD-00BTW, 128 GB, SD card"


def test_what_windows_did_not_answer_is_left_out():
    found = device.parse(json.dumps({"maker": "Some Maker", "model": "Handheld 1", "family": None,
                                     "battery": None, "cpu": None}))
    assert found.rows() == [("Device", "Some Maker Handheld 1")] and found.battery is None


@pytest.mark.parametrize("status, text", [(1, "82%, on battery"), (2, "82%, plugged in"), (3, "82%, full"),
                                          (6, "82%, charging"), (11, "82%")])
def test_the_battery(status, text):
    data = dict(ALLY, battery={"charge": 82, "status": status})
    assert dict(device.parse(json.dumps(data)).rows())["Battery"] == text


def test_read_runs_the_query_in_powershell(ally_json):
    seen = []

    def run(argv):
        seen.append(argv)
        return ally_json
    assert device.read(run).name == "ROG Xbox Ally X"
    script = base64.b64decode(seen[0][-1]).decode("utf-16-le")
    assert seen[0][0] == "powershell.exe" and "Win32_ComputerSystem" in script and "ConvertTo-Json" in script
    assert "SerialNumber" not in script                                  # nothing personal is asked for
    assert "MacAddress" not in script and "^(USB|PCI)" in script         # of Bluetooth, the adapter only
    assert "InLocalMachineContainer" in script and "GetDeviceProperties" in script
    assert r"id = ($d.InstanceId -split '\\')[1]" in script           # the USB ID, never the instance's serial


def test_the_hardware_card():
    found = device.parse(json.dumps(DOCKED))
    found.touch_points = 10
    assert found.hardware_rows() == [
        ("Panel", "about 7 inches (15 x 9 cm)"),                       # the built-in one, not the TV
        ("Touch", "NOVATEK TouchPanel, 10 touch points"),                # not Windows' generic name beside it
        ("Controller", "ROG Xbox Ally Device Gamepad"),                  # the built-in one
        ("Wi-Fi", "MediaTek Wi-Fi 6E MT7922 (RZ616) 160MHz Wireless LAN Card, driver 3.6.2.1438"),
        ("Bluetooth", "MediaTek Bluetooth Adapter"),
        ("Audio", "Realtek High Definition Audio, AMD High Definition Audio Device"),
        ("Fingerprint", "EgisTec Touch Fingerprint Sensor"),
        ("Sensors", "Bosch Accelerometer, Simple Device Orientation Sensor"),
        ("USB", "USB4(TM) Host Router, AMD USB 3.10 eXtensible Host Controller - 1.20")]   # each once


def test_the_connected_card_shows_the_dock():
    # The owner's Ally on 02-11-2026: the camera and the screen were missing, the dock's network chip looked like an
    # adapter no longer plugged in, and the dock read as a Realtek USB hub
    found = device.parse(json.dumps(DOCKED))
    assert found.connected_rows() == [
        ("Dock or hub", "Realtek hub chip (USB 3, USB 2)"),
        ("Devices", "Turzx USB screen (via the hub), PlayStation camera without its firmware (no driver, via the hub)"),
        ("Screens", "Mi TV, DisplayPort"),
        ("Network", "Realtek USB GbE Family Controller (no cable, via the hub), "
                    "ASIX AX88179 USB 3.0 to Gigabit Ethernet Adapter (connected, 1 Gbps)"),
        ("Drives", "4001 GB, WDC WD40 EFRX-68N32N0")]                     # the drive's own row, once
    assert dict(found.rows())["Storage"] == "1024 GB, SAMSUNG MZVMA1T0HCLD-00BTW"     # the built-in drive only
    report = found.report()
    assert "Dock or hub: Realtek hub chip (USB 3, USB 2)" in report and "Wi-Fi: MediaTek" in report
    assert "Problems" not in dict(found.hardware_rows())                  # the camera is plugged in, not built in


def test_undocked_nothing_is_connected():
    undocked = dict(DOCKED, plugged=[part for part in PLUGGED if part["local"]], screens=DOCKED["screens"][:1],
                    network=DOCKED["network"][:1], disks=DOCKED["disks"][:1])
    assert device.parse(json.dumps(undocked)).connected_rows() == []
    hub = dict(undocked, plugged={"id": "VID_ABCD&PID_0001", "class": "USB", "name": "Concentrateur USB générique",
                                  "service": "USBHUB3", "box": 1})          # a hub by its driver, in any language
    assert device.parse(json.dumps(hub)).connected_rows() == [("Dock or hub", "vendor ABCD hub chip (USB 2)")]


@pytest.mark.parametrize("parts, name", [
    ([{"id": "VID_05A9&PID_058C", "class": "Camera", "name": "USB Camera-OV580"}], "PS5 HD Camera"),
    ([{"id": "VID_046D&PID_C52B", "class": "USB", "name": "USB Composite Device", "own": "USB Receiver"},
      {"id": "VID_046D&PID_C52B&MI_00", "class": "Keyboard", "name": "HID Keyboard Device", "parent": 0}],
     "HID Keyboard Device"),                                                 # the part with a class of its own
    ([{"id": "VID_1234&PID_0001", "class": "USB", "name": "USB Composite Device", "own": "Stick 3000"}],
     "Stick 3000"),                                                          # the device's own name
    ([{"id": "VID_0BDA&PID_1234", "class": "USB", "name": "USB Composite Device"}], "a USB device by Realtek"),
])
def test_a_plugged_in_device_by_its_best_name(parts, name):
    data = dict(ALLY, plugged=[dict(part, box=1, parent=part.get("parent", -1)) for part in parts])
    assert dict(device.parse(json.dumps(data)).connected_rows())["Devices"] == name


def test_device_managers_problems_of_built_in_devices():
    plugged = [dict(PLUGGED[0], problem=10)]
    found = device.parse(json.dumps(dict(ALLY, plugged=plugged, problems=[{"name": "AMD PSP", "problem": 22},
                                                                          {"name": None, "problem": 99}])))
    assert dict(found.hardware_rows())["Problems"] == ("EgisTec Touch Fingerprint Sensor (cannot start), "
                                                       "AMD PSP (disabled), a device without a name (problem code 99)")


@pytest.mark.parametrize("status, speed, media, state", [
    ("Up", 1_000_000_000, "802.3", "connected, 1 Gbps"), ("Up", 2_500_000_000, "802.3", "connected, 2.5 Gbps"),
    ("Up", 100_000_000, "802.3", "connected, 100 Mbps"), ("Up", 0, "802.3", "connected"),
    ("Disconnected", 0, "802.3", "no cable"), ("Disconnected", 0, "Unspecified", "not connected"),
    ("Disabled", 0, "802.3", "disabled")])
def test_a_network_adapters_state(status, speed, media, state):
    assert device.Adapter("A", status=status, speed=speed, media=media).state == state


def test_a_loop_of_parents_ends():
    found = device.Device(plugged=[device.Plugged("VID_1", parent=1), device.Plugged("VID_2", parent=0)])
    assert not found.behind_hub(0) and not found.behind_hub(-1)


def test_read_counts_the_touch_points(ally_json):
    assert device.read(lambda argv: ally_json, touches=lambda: 10).touch_points == 10
