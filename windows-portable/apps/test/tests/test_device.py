# SPDX-License-Identifier: GPL-3.0-or-later
"""What Windows reports (device.py): the query's answer as the Device card shows it, one object or a list, missing
parts, the battery, and the query itself."""

from __future__ import annotations

import base64
import json

import pytest

from conftest import ALLY, DOCKED
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


def test_the_hardware_card():
    found = device.parse(json.dumps(DOCKED))
    found.touch_points = 10
    assert found.hardware_rows() == [
        ("Panel", "about 7 inches (15 x 9 cm)"),                       # the built-in one, not the TV
        ("Touch", "NOVATEK TouchPanel, 10 touch points"),                # not Windows' generic name beside it
        ("Wi-Fi", "MediaTek Wi-Fi 6E MT7922 (RZ616) 160MHz Wireless LAN Card, driver 3.6.2.1438"),
        ("Bluetooth", "MediaTek Bluetooth Adapter"),
        ("Audio", "Realtek High Definition Audio, AMD High Definition Audio Device"),
        ("Fingerprint", "EgisTec Touch Fingerprint Sensor"),
        ("Sensors", "Bosch Accelerometer, Simple Device Orientation Sensor"),
        ("USB", "USB4(TM) Host Router, AMD USB 3.10 eXtensible Host Controller - 1.20")]   # each once


def test_the_connected_card_shows_the_dock():
    found = device.parse(json.dumps(DOCKED))
    assert found.connected_rows() == [
        ("Dock or hub", "Realtek USB hub (USB 3, USB 2)"),
        ("Screens", "Mi TV, DisplayPort"),
        ("Network", "Realtek USB GbE Family Controller (not connected)"),
        ("Drives", "4001 GB, WDC WD40 EFRX-68N32N0")]
    assert dict(found.rows())["Storage"] == "1024 GB, SAMSUNG MZVMA1T0HCLD-00BTW"     # the built-in drive only
    report = found.report()
    assert "Dock or hub: Realtek USB hub (USB 3, USB 2)" in report and "Wi-Fi: MediaTek" in report


def test_undocked_nothing_is_connected():
    undocked = dict(DOCKED, hubs=[], screens=DOCKED["screens"][:1], network=DOCKED["network"][:1],
                    disks=DOCKED["disks"][:1])
    assert device.parse(json.dumps(undocked)).connected_rows() == []
    hub = dict(undocked, hubs={"name": "Generic USB Hub", "id": "VID_ABCD&PID_0001"})
    assert device.parse(json.dumps(hub)).connected_rows() == [("Dock or hub", "vendor ABCD USB hub (USB 2)")]


def test_read_counts_the_touch_points(ally_json):
    assert device.read(lambda argv: ally_json, touches=lambda: 10).touch_points == 10
