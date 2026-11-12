# SPDX-License-Identifier: GPL-3.0-or-later
"""The window on a fake Bluetooth, Plasma and pkexec: the list is the app's until the search after boot is switched
on, each change to the system part goes through boot.py as root, and the login setting needs no password."""

from __future__ import annotations

import json

from PyQt6.QtWidgets import QDialog, QMessageBox

from bluetooth_pairing import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, boot, bluez, runner
from bluetooth_pairing.main_window import AddDialog, MainWindow

KEYBOARD, MOUSE = "AA:00:00:00:00:01", "AA:00:00:00:00:02"


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()


class World:
    """Bluetooth (bluetoothctl, systemctl, journalctl), Plasma's setting and pkexec running boot.py on a temp /etc."""

    def __init__(self, tmp_path, powered=True, login="remember"):
        self.etc = tmp_path / "etc"
        self.powered, self.login = powered, login
        self.root_calls: list[list[str]] = []
        self.cancel = False

    def bt(self, argv, timeout=15):
        joined = " ".join(argv)
        if joined == "bluetoothctl show":
            return 0, f"Controller 00:00:00:00:00:00 (public)\n\tPowered: {'yes' if self.powered else 'no'}\n"
        if joined == "bluetoothctl devices":
            return 0, f"Device {KEYBOARD} Slim X1 Keyboard\nDevice {MOUSE} Satechi M1 Mouse\n"
        if joined == "bluetoothctl devices Paired":
            return 0, f"Device {KEYBOARD} Slim X1 Keyboard\n"
        if joined == "bluetoothctl devices Connected":
            return 0, f"Device {KEYBOARD} Slim X1 Keyboard\n"
        if argv[0] == "systemctl":
            return 0, "inactive\n"
        if argv[0] == "journalctl":
            return 0, json.dumps({"__REALTIME_TIMESTAMP": "1800000000000000",
                                  "MESSAGE": "every listed device is connected."}) + "\n"
        return 0, ""

    def kde(self, argv):
        if argv[0] == "kreadconfig6":
            return 0, self.login + "\n"
        self.login = "enable" if argv[-1] == "enable" else "remember"
        return 0, ""

    def run_root(self, argv):
        """pkexec python3 -I boot.py <args>: boot.py's own functions on the temp /etc, systemctl recorded."""
        assert argv[0] == "pkexec" and argv[3].endswith("boot.py")
        args = argv[4:]
        self.root_calls.append(args)
        if self.cancel:
            return runner.Result(126, "")
        paths = boot.Paths(self.etc)
        try:
            if args[0] == "install":
                names = tuple(args[i + 1] for i, a in enumerate(args) if a == "--name")
                boot.install(paths, boot.Config(names, "--pair" in args, "--battery" in args),
                             lambda a: boot.Result(0, ""))
            elif args[0] == "uninstall":
                boot.uninstall(paths, lambda a: boot.Result(0, ""))
        except ValueError as exc:
            return runner.Result(1, json.dumps({"ok": False, "error": str(exc)}))
        return runner.Result(0, json.dumps({"ok": True}))

    def window(self, kde=True):
        return MainWindow(self.etc, self.bt, self.kde, kde, self.run_root)


def items(window):
    return [window.list.item(i).text() for i in range(window.list.count())]


def test_window_opens_with_the_suites_header(qapp, tmp_path):
    world = World(tmp_path)
    window = world.window()
    window.show()
    assert window.windowTitle() == APP_NAME
    assert window.state.text() == "Not pairing after boot"
    assert window.bluetooth_box.value.text() == "On" and window.boot_box.value.text() == "Off"
    assert window.login_box.value.text() == "Restored" and not window.login_check.isChecked()
    assert items(window) == [] and not window.save_button.isVisible() and not window.search_button.isEnabled()
    assert window.log_view.toPlainText() == ""                          # not installed: no search ran
    window.close()


def test_names_are_kept_by_the_app_then_installed_with_the_search(qapp, tmp_path, monkeypatch):
    world = World(tmp_path)
    window = world.window()
    monkeypatch.setattr(AddDialog, "exec", lambda self: (self.name.setText("Slim X1 Keyboard"),
                                                         QDialog.DialogCode.Accepted)[1])
    window.add_device()
    monkeypatch.setattr(AddDialog, "exec", lambda self: (self.name.setText("Satechi M1 Mouse"),
                                                         QDialog.DialogCode.Accepted)[1])
    window.add_device()
    assert items(window) == ["Slim X1 Keyboard  ·  connected", "Satechi M1 Mouse  ·  known"]
    assert world.root_calls == []                                       # no password for the app's own list
    assert world.window().names == ["Slim X1 Keyboard", "Satechi M1 Mouse"]   # kept
    window.pair_check.setChecked(True)                                  # installs, with the password
    assert world.root_calls == [["install", "--name", "Slim X1 Keyboard", "--name", "Satechi M1 Mouse", "--pair"]]
    assert boot.installed(boot.Paths(world.etc)) == boot.Config(("Slim X1 Keyboard", "Satechi M1 Mouse"), True)
    assert window.state.text() == "Pairs after boot" and window.boot_box.value.text() == "On"
    assert window.search_button.isEnabled() and window.log_view.toPlainText().endswith(
        "every listed device is connected.")
    # A changed list waits for Save, which asks for the password once.
    window.list.setCurrentRow(1)
    window.remove_device()
    assert window.save_button.isEnabled() and "Save" in window.list_note.text()
    window.save_names()
    assert world.root_calls[-1] == ["install", "--name", "Slim X1 Keyboard", "--pair"]
    assert not window.save_button.isEnabled()
    window.close()


def test_switching_pairing_on_without_names_asks_for_them(qapp, tmp_path, monkeypatch):
    world = World(tmp_path)
    window = world.window()
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: told.append(args[2]))
    window.pair_check.setChecked(True)
    assert told and "Add the devices" in told[0] and world.root_calls == [] and not window.pair_check.isChecked()
    window.close()


def test_a_canceled_password_changes_nothing(qapp, tmp_path, monkeypatch):
    world = World(tmp_path)
    world.cancel = True
    window = world.window()
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args[2]))
    window.battery_check.setChecked(True)
    assert warned and "canceled" in warned[0]
    assert not window.battery_check.isChecked() and boot.installed(boot.Paths(world.etc)) is None
    window.close()


def test_batteries_alone_then_off_removes_the_system_part(qapp, tmp_path):
    world = World(tmp_path)
    window = world.window()
    window.battery_check.setChecked(True)
    assert world.root_calls[-1] == ["install", "--battery"]
    assert window.battery_box.value.text() == "Stopped"                 # the fake systemctl says inactive
    window.battery_check.setChecked(False)
    assert world.root_calls[-1] == ["uninstall"] and not boot.Paths(world.etc).folder.exists()
    window.close()


def test_another_versions_system_part_offers_update(qapp, tmp_path):
    world = World(tmp_path)
    paths = boot.Paths(world.etc)
    boot.install(paths, boot.Config(("Slim X1 Keyboard",), True), lambda a: boot.Result(0, ""))
    paths.script.write_text("# an older version\n")
    window = world.window()
    assert not window.update_button.isHidden() and "another version" in window.system_note.text()
    window.update_system()
    assert world.root_calls[-1] == ["install", "--name", "Slim X1 Keyboard", "--pair"]
    assert window.update_button.isHidden()
    window.search_now()
    assert world.root_calls[-1] == ["start"] and "pairing mode" in window.list_note.text()
    window.close()


def test_bluetooth_at_login_needs_no_password(qapp, tmp_path):
    world = World(tmp_path)
    window = world.window()
    window.login_check.setChecked(True)
    assert world.login == "enable" and window.login_box.value.text() == "On" and world.root_calls == []
    window.login_check.setChecked(False)
    assert world.login == "remember" and window.login_box.value.text() == "Restored"
    window.close()
    other = world.window(kde=False)
    assert not other.login_check.isEnabled() and other.login_box.value.text() == "—"
    other.close()


def test_bluetooth_off_is_said(qapp, tmp_path):
    window = World(tmp_path, powered=False).window()
    assert window.state.text() == "Bluetooth is off" and window.bluetooth_box.value.text() == "Off"
    window.close()


def test_add_dialog_checks_the_name_and_marks_listed_ones(qapp):
    devices = [bluez.Device(KEYBOARD, "Slim X1 Keyboard", True, True), bluez.Device(MOUSE, "Satechi M1 Mouse")]
    dialog = AddDialog(devices, ["Slim X1 Keyboard"], lambda: None)
    ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
    assert dialog.list.item(0).text() == "Slim X1 Keyboard  ·  listed already" and not ok.isEnabled()
    dialog.list.setCurrentRow(1)
    assert dialog.chosen() == "Satechi M1 Mouse" and ok.isEnabled()
    dialog.name.setText("Slim X1 Keyboard")
    assert not ok.isEnabled() and "listed already" in dialog.problem.text()
    dialog.name.setText(" Mouse")
    assert not ok.isEnabled() and "space" in dialog.problem.text()
    dialog.searching(True)
    assert not dialog.search_button.isEnabled() and "Searching" in dialog.note.text()
    dialog.close()
