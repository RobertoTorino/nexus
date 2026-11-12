# SPDX-License-Identifier: GPL-3.0-or-later
"""The system part (boot.py): its files, install and uninstall as root (systemctl recorded), what the app is told,
and the search after boot against a fake Bluetooth that answers bluetoothctl and busctl as BlueZ 5.8x does."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from bluetooth_pairing import boot

KEYBOARD, MOUSE = "AA:00:00:00:00:01", "AA:00:00:00:00:02"


def recorder():
    calls = []

    def run(argv):
        calls.append(argv)
        return boot.Result(0, "")
    return calls, run


# --- Names, files, install --------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, problem", [
    ("Slim X1 Keyboard", ""), ("DualSense Wireless Controller", ""), ("Clavier Été", ""),
    ("", "empty"), ("  ", "empty"), (" Mouse", "space"), ("Mouse\n", "space"), ("Mo\tuse", "not printable"),
    ("x" * 249, "248 bytes")])
def test_names_are_checked(name, problem):
    assert (problem in boot.name_problem(name)) if problem else boot.name_problem(name) == ""


def test_install_writes_the_system_part_and_enables_what_is_chosen(tmp_path):
    paths = boot.Paths(tmp_path / "etc")
    calls, run = recorder()
    config = boot.Config(("Slim X1 Keyboard", "Satechi M1 Mouse"), pair=True, battery=False)
    boot.install(paths, config, run)
    assert boot.installed(paths) == config and not boot.outdated(paths)
    assert json.loads(paths.config.read_text()) == {"names": ["Slim X1 Keyboard", "Satechi M1 Mouse"], "pair": True,
                                                    "battery": False}
    assert paths.script.read_bytes() == Path(boot.__file__).read_bytes()
    assert f"ExecStart=/usr/bin/python3 -I /etc/{boot.FOLDER}/boot.py pair" in paths.pair_unit.read_text()
    assert "PartOf=bluetooth.service" in paths.battery_unit.read_text()
    for path in (paths.script, paths.config, paths.pair_unit, paths.battery_unit):
        assert path.stat().st_mode & 0o777 == 0o644
    assert ["systemctl", "daemon-reload"] in calls
    assert ["systemctl", "enable", boot.PAIR_UNIT] in calls
    assert ["systemctl", "disable", "--now", boot.BATTERY_UNIT] in calls
    calls.clear()
    boot.install(paths, boot.Config(config.names, pair=False, battery=True), run)
    assert ["systemctl", "disable", boot.PAIR_UNIT] in calls
    assert ["systemctl", "enable", boot.BATTERY_UNIT] in calls and ["systemctl", "restart", boot.BATTERY_UNIT] in calls
    paths.script.write_text("# an older version\n")
    assert boot.outdated(paths)


def test_install_refuses_a_bad_name_before_writing_anything(tmp_path):
    paths = boot.Paths(tmp_path / "etc")
    with pytest.raises(ValueError, match="empty"):
        boot.install(paths, boot.Config(("Mouse", ""), pair=True), recorder()[1])
    assert not paths.folder.exists()


def test_uninstall_stops_and_removes_everything(tmp_path):
    paths = boot.Paths(tmp_path / "etc")
    calls, run = recorder()
    boot.install(paths, boot.Config(("Mouse",), True, True), run)
    calls.clear()
    boot.uninstall(paths, run)
    assert calls[0] == ["systemctl", "disable", "--now", boot.PAIR_UNIT, boot.BATTERY_UNIT]
    assert not paths.folder.exists() and not paths.pair_unit.exists() and not paths.battery_unit.exists()
    assert boot.installed(paths) is None


def test_a_broken_config_is_not_installed(tmp_path):
    paths = boot.Paths(tmp_path / "etc")
    boot.install(paths, boot.Config(("Mouse",), True), recorder()[1])
    for text in ("{", "[]", '{"names": "Mouse"}', '{"names": ["", "Mouse"]}'):
        paths.config.write_text(text)
        assert boot.installed(paths) is None


def test_what_the_app_runs_and_is_told():
    command = boot.command(["start"])
    assert command[0] == "pkexec" and command[2] == "-I"
    assert command[-2:] == [str(Path(boot.__file__).resolve()), "start"]
    assert boot.install_args(boot.Config(("A B", "C"), True, False)) == ["install", "--name", "A B", "--name", "C",
                                                                          "--pair"]
    assert boot.install_args(boot.Config((), False, True)) == ["install", "--battery"]
    assert boot.answer(0, 'noise\n{"ok": true}\n') == ""
    assert boot.answer(1, '{"ok": false, "error": "disk full"}') == "disk full"
    assert boot.answer(126, "") == boot.answer(127, "") and "canceled" in boot.answer(126, "")
    assert boot.answer(1, "Traceback …") == "Traceback …"


def test_main_installs_under_another_root(tmp_path, monkeypatch, capsys):
    calls, run = recorder()
    monkeypatch.setattr(boot, "run", run)
    monkeypatch.setenv("BC250_SYSTEM_ROOT", str(tmp_path))
    assert boot.main(["install", "--name", "Slim X1 Keyboard", "--name", "Satechi M1 Mouse", "--pair"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert boot.installed(boot.Paths(tmp_path / "etc")) == boot.Config(("Slim X1 Keyboard", "Satechi M1 Mouse"), True)
    assert boot.main(["install", "--name", " bad", "--pair"]) == 1
    assert "space" in json.loads(capsys.readouterr().out)["error"]
    assert boot.main(["uninstall"]) == 0 and boot.installed(boot.Paths(tmp_path / "etc")) is None
    assert ["systemctl", "enable", boot.PAIR_UNIT] in calls          # systemctl through the module's run


def test_start_says_when_systemctl_failed():
    with pytest.raises(OSError, match="not loaded"):
        boot.start(lambda argv: boot.Result(5, "Unit not loaded."))


# --- Parsing bluetoothctl -----------------------------------------------------------------------------------------

def test_devices_and_info_fields_are_read():
    text = (f"Device {KEYBOARD} Slim X1 Keyboard\nDevice {MOUSE} Satechi M1 Mouse\n"
            "[CHG] Controller 00:00:00:00:00:00 Discovering: yes\nDevice short name\n")
    assert boot.devices(text) == [(KEYBOARD, "Slim X1 Keyboard"), (MOUSE, "Satechi M1 Mouse")]
    info = f"Device {KEYBOARD} (public)\n\tName: Slim X1 Keyboard\n\tPaired: yes\n\tRSSI: 0xffffffc4 (-60)\n"
    assert boot.info_field(info, "Paired") == "yes" and boot.info_field(info, "RSSI").endswith("(-60)")
    assert boot.info_field(info, "Connected") == ""


# --- The search after boot ----------------------------------------------------------------------------------------

@dataclass
class Device:
    name: str
    paired: bool = False
    connected: bool = False
    heard: bool = True                  # in pairing mode and in range: it has an RSSI
    pairs: bool = True                  # pairing it works
    keeps_pairing: bool = True          # it accepts its old pairing (a connect works)
    resolved: bool = False


class FakeProcess:
    def __init__(self, on_poll=None):
        self.on_poll, self.ended = on_poll, False

    def poll(self):
        if self.on_poll is not None and not self.ended:
            self.on_poll()
            self.ended = True
        return 0 if self.ended else None

    def terminate(self):
        self.ended = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.ended = True


class Bluetooth:
    """BlueZ as bluetoothctl and busctl show it."""

    def __init__(self, devices: dict[str, Device], adapter_after: int = 0, powered: bool = True):
        self.devices, self.adapter_after, self.powered = devices, adapter_after, powered
        self.calls: list[list[str]] = []
        self.spawned: list[list[str]] = []
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds

    def clock(self):
        return self.now

    def run(self, argv):
        self.calls.append(argv)
        args = [a for a in argv if a not in ("--timeout",) and not a.isdigit()]
        if args[0] == "busctl":
            if args[1] == "tree":
                return boot.Result(0, "\n".join(f"/org/bluez/hci0/dev_{a.replace(':', '_')}" for a in self.devices))
            address = args[3].rsplit("dev_", 1)[1].replace("_", ":")
            return boot.Result(0, "b true" if self.devices[address].resolved else "b false")
        command = args[1:]
        if command == ["show"]:
            if self.adapter_after > 0:
                self.adapter_after -= 1
                return boot.Result(1, "No default controller available")
            return boot.Result(0, f"Controller 00:00:00:00:00:00 (public)\n\tPowered: {'yes' if self.powered else 'no'}\n")
        if command == ["power", "on"]:
            self.powered = True
            return boot.Result(0, "")
        if command[:1] == ["devices"]:
            shown = {a: d for a, d in self.devices.items() if command[1:] != ["Connected"] or d.connected}
            return boot.Result(0, "".join(f"Device {a} {d.name}\n" for a, d in shown.items()))
        address = command[1]
        device = self.devices[address]
        if command[0] == "info":
            return boot.Result(0, f"Device {address}\n\tName: {device.name}\n\tPaired: {'yes' if device.paired else 'no'}"
                                  f"\n\tConnected: {'yes' if device.connected else 'no'}\n"
                                  + ("\tRSSI: 0xffffffc4 (-60)\n" if device.heard else ""))
        if command[0] == "connect":
            device.connected = device.paired and device.keeps_pairing
            return boot.Result(0 if device.connected else 1, "")
        if command[0] == "remove":
            device.paired = device.connected = False
            device.keeps_pairing = True
            return boot.Result(0, "")
        return boot.Result(0, "")                   # trust

    def spawn(self, argv):
        self.spawned.append(argv)
        if argv[-2] == "pair":
            device = self.devices[argv[-1]]

            def paired():
                if device.pairs:
                    device.paired = device.connected = device.resolved = True
            return FakeProcess(paired)
        return FakeProcess()

    def search(self, names, **more):
        return boot.Search(tuple(names), run=self.run, spawn=self.spawn, sleep=self.sleep, clock=self.clock, **more)


def test_listed_devices_in_pairing_mode_are_paired_and_the_search_stops(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard"), MOUSE: Device("Satechi M1 Mouse"),
                    "BB:00:00:00:00:09": Device("Someone's Headphones")})
    assert bt.search(["Slim X1 Keyboard", "Satechi M1 Mouse"]).loop() == 0
    out = capsys.readouterr().out
    assert "searching for Slim X1 Keyboard, Satechi M1 Mouse for 300 s." in out
    assert f"Slim X1 Keyboard: paired, trusted, connected: yes" in out and "every listed device is connected." in out
    assert bt.devices[KEYBOARD].paired and bt.devices[MOUSE].connected
    assert not bt.devices["BB:00:00:00:00:09"].paired                       # another name: never
    assert ["bluetoothctl", "--timeout", "300", "scan", "on"] in bt.spawned
    pair = next(a for a in bt.spawned if "pair" in a)
    assert pair[:5] == ["bluetoothctl", "--timeout", "25", "--agent", "NoInputNoOutput"]
    assert bt.calls.count(["bluetoothctl", "trust", KEYBOARD]) == 2     # before pairing, and after
    assert bt.now < 10


def test_a_device_not_in_pairing_mode_is_left_alone_until_the_window_ends(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard", heard=False)})
    assert bt.search(["Slim X1 Keyboard"], window=20).loop() == 0
    assert not bt.devices[KEYBOARD].paired
    assert "search ended; not connected: Slim X1 Keyboard" in capsys.readouterr().out
    assert bt.now >= 20


def test_a_paired_device_reconnects_and_one_that_dropped_its_pairing_is_paired_again(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard", paired=True),
                    MOUSE: Device("Satechi M1 Mouse", paired=True, keeps_pairing=False)})
    assert bt.search(["Slim X1 Keyboard", "Satechi M1 Mouse"]).loop() == 0
    out = capsys.readouterr().out
    assert "Slim X1 Keyboard reconnected." in out
    assert f"Satechi M1 Mouse ({MOUSE}) no longer accepts its old pairing; pairing it again." in out
    assert ["bluetoothctl", "remove", MOUSE] in bt.calls
    assert bt.devices[MOUSE].connected and "every listed device is connected." in out


def test_a_failed_pairing_is_tried_again(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard", pairs=False)})
    bt.search(["Slim X1 Keyboard"], window=5).loop()
    out = capsys.readouterr().out
    assert out.count("pairing Slim X1 Keyboard failed; trying again.") >= 2


def test_one_connected_device_of_a_name_is_enough(capsys):
    """Every DualSense calls itself the same: once one is connected, another in pairing mode is not paired."""
    other = "CC:00:00:00:00:03"
    bt = Bluetooth({KEYBOARD: Device("DualSense Wireless Controller", paired=True, connected=True),
                    other: Device("DualSense Wireless Controller")})
    bt.search(["DualSense Wireless Controller"]).loop()
    assert not bt.devices[other].paired and "every listed device is connected." in capsys.readouterr().out


def test_the_adapter_is_waited_for_and_switched_on(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard")}, adapter_after=3, powered=False)
    bt.search(["Slim X1 Keyboard"]).loop()
    assert ["bluetoothctl", "power", "on"] in bt.calls and bt.devices[KEYBOARD].connected
    bt = Bluetooth({}, adapter_after=boot.ADAPTER_WAIT_S + 1)
    bt.search(["Slim X1 Keyboard"]).loop()
    assert "no Bluetooth adapter found." in capsys.readouterr().out and not bt.spawned


def test_dry_run_and_no_names_pair_nothing(capsys):
    bt = Bluetooth({KEYBOARD: Device("Slim X1 Keyboard")})
    bt.search(["Slim X1 Keyboard"], window=3, dry=True).loop()
    assert f"would pair Slim X1 Keyboard ({KEYBOARD}), paired now: no" in capsys.readouterr().out
    assert not bt.devices[KEYBOARD].paired
    assert bt.search([]).loop() == 0 and "nothing to do" in capsys.readouterr().out


# --- The batteries ----------------------------------------------------------------------------------------------

def test_controller_battery_levels_are_read_from_the_driver(tmp_path):
    for name, capacity in (("ps-controller-battery-aa:bb:cc:dd:ee:ff", "85"), ("ps-controller-battery-11:22", "120"),
                           ("ps-controller-battery-bad", "x"), ("BAT0", "50")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "capacity").write_text(capacity)
    assert boot.levels(tmp_path) == {"AA:BB:CC:DD:EE:FF": 85, "11:22": 100}
