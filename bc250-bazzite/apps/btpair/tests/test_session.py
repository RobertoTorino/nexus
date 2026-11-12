# SPDX-License-Identifier: GPL-3.0-or-later
"""What the window reads as you (bluez.py) and Plasma's Bluetooth at login (plasma.py), on recorded output."""

from __future__ import annotations

import json

from bluetooth_pairing import bluez, plasma

KEYBOARD, MOUSE, PAD, OLD_PAD = ("AA:00:00:00:00:01", "AA:00:00:00:00:02", "AA:00:00:00:00:03",
                                 "AA:00:00:00:00:04")
SHOW = "Controller 00:00:00:00:00:00 (public)\n\tName: board\n\tPowered: {powered}\n\tPowerState: {state}\n"


def answers(table):
    calls = []

    def run(argv, timeout=15):
        calls.append(argv)
        return table.get(" ".join(argv), (0, ""))
    run.calls = calls
    return run


def test_the_adapter_and_its_switch():
    assert bluez.adapter(answers({"bluetoothctl show": (0, SHOW.format(powered="yes", state="on"))})) == \
        bluez.Adapter(True, True, False)
    assert bluez.adapter(answers({"bluetoothctl show": (0, SHOW.format(powered="no", state="off-blocked"))})) == \
        bluez.Adapter(True, False, True)
    assert bluez.adapter(answers({"bluetoothctl show": (1, "No default controller available\n")})) == \
        bluez.Adapter(False)


def test_known_devices_paired_first_each_name_once():
    run = answers({
        "bluetoothctl devices": (0, f"Device {PAD} DualSense Wireless Controller\nDevice {KEYBOARD} Slim X1 Keyboard\n"
                                    f"Device {MOUSE} Satechi M1 Mouse\nDevice {OLD_PAD} DualSense Wireless Controller\n"
                                    "Device 11:22:33:44:55:66 11-22-33-44-55-66\n"),
        "bluetoothctl devices Paired": (0, f"Device {KEYBOARD} Slim X1 Keyboard\nDevice {MOUSE} Satechi M1 Mouse\n"
                                           f"Device {OLD_PAD} DualSense Wireless Controller\n"),
        "bluetoothctl devices Connected": (0, f"Device {MOUSE} Satechi M1 Mouse\n"
                                              f"Device {OLD_PAD} DualSense Wireless Controller\n")})
    found = bluez.known(run)
    assert [(d.name, d.paired, d.connected) for d in found] == [
        ("DualSense Wireless Controller", True, True), ("Satechi M1 Mouse", True, True),
        ("Slim X1 Keyboard", True, False)]                              # the unnamed one is left out
    assert found[0].address == OLD_PAD                                  # the connected one of that name


def test_scan_searches_then_lists():
    run = answers({"bluetoothctl devices": (0, f"Device {KEYBOARD} Slim X1 Keyboard\n")})
    assert [d.name for d in bluez.scan(run, seconds=3)] == ["Slim X1 Keyboard"]
    assert run.calls[0] == ["bluetoothctl", "--timeout", "3", "scan", "on"]


def test_the_last_search_has_its_times_and_no_host_name():
    def line(seconds, message):
        return json.dumps({"__REALTIME_TIMESTAMP": str(int(seconds * 1e6)), "MESSAGE": message,
                           "_HOSTNAME": "someones-board"})
    out = "\n".join([line(1_800_000_000, "searching for Slim X1 Keyboard for 300 s."),
                     line(1_800_000_004, list(b"pairing Slim X1 Keyboard")), "not json",
                     line(1_800_000_005, "")])
    lines = bluez.last_search(answers({" ".join(["journalctl", "-b", "-u", bluez.PAIR_UNIT, "-o", "json",
                                                 "--no-pager", "-n", str(bluez.LOG_LINES)]): (0, out)}))
    assert [text.split(" ", 1)[1] for text in lines] == ["searching for Slim X1 Keyboard for 300 s.",
                                                          "pairing Slim X1 Keyboard"]
    assert all(len(text.split(" ", 1)[0]) == 8 for text in lines) and "someones-board" not in "".join(lines)
    assert bluez.last_search(answers({})) == []
    assert bluez.last_search(lambda argv, timeout=15: (1, "No journal files were found.")) == []


def test_unit_state():
    assert bluez.unit_state(bluez.PAIR_UNIT, answers({f"systemctl is-active {bluez.PAIR_UNIT}": (3, "inactive\n")})) \
        == "inactive"


# --- Plasma -------------------------------------------------------------------------------------------------------

def kde(value=None):
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[0] == "kreadconfig6":
            return 0, (value or plasma.REMEMBER) + "\n"
        return 0, ""
    run.calls = calls
    return run


def test_plasma_login_state_is_read_and_written():
    assert plasma.launch_state(kde("enable")) == plasma.ENABLE
    assert plasma.launch_state(kde()) == plasma.REMEMBER
    assert plasma.launch_state(kde("nonsense")) == plasma.REMEMBER
    assert plasma.launch_state(lambda argv: (127, "")) == plasma.REMEMBER
    run = kde()
    assert plasma.set_enable(True, run) and plasma.set_enable(False, run)
    assert run.calls == [["kwriteconfig6", "--file", "bluedevilglobalrc", "--group", "General", "--key", "launchState",
                          "enable"],
                         ["kwriteconfig6", "--file", "bluedevilglobalrc", "--group", "General", "--key", "launchState",
                          "--delete"]]
    assert not plasma.set_enable(True, lambda argv: (1, ""))
    assert plasma.available(lambda name: f"/usr/bin/{name}")
    assert not plasma.available(lambda name: None)
