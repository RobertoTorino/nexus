# SPDX-License-Identifier: GPL-3.0-or-later
"""What Windows reports (device.py): the query's answer as the Device card shows it, one object or a list, missing
parts, the battery, and the query itself."""

from __future__ import annotations

import base64
import json

import pytest

from conftest import ALLY
from portable_test import device


def test_the_ally_as_windows_reported_it(ally_json):
    found = device.parse(ally_json)
    assert found.name == "ROG Xbox Ally X"
    assert dict(found.rows()) == {
        "Device": "ROG Xbox Ally X", "Processor": "AMD Ryzen AI Z2 Extreme", "Cores": "8 cores, 16 threads",
        "Graphics": "AMD Radeon(TM) 890M Graphics", "Driver": "32.0.32015.7029", "Memory": "24 GB, 15.6 GB usable",
        "Storage": "1024 GB, SAMSUNG MZVMA1T0HCLD-00BTW", "System": "Windows 11 Home, build 26300",
        "Firmware": "RC73XA.319", "Battery": "82 %, on battery"}
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


@pytest.mark.parametrize("status, text", [(1, "82 %, on battery"), (2, "82 %, plugged in"), (3, "82 %, full"),
                                          (6, "82 %, charging"), (11, "82 %")])
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
