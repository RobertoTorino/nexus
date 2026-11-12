# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's header (the icon at 96 px, the name with the version, the state beside it, Refresh at the
right end) with Bluetooth, the search after boot, the controller batteries and Bluetooth at login on the second row;
below it the devices to pair, the system part (boot.py, installed through pkexec: the search after every boot and the
batteries in the Bluetooth icon), Bluetooth at login (plasma.py, your own setting, no password) and what the search
after this boot did.

The list of names is the app's own until the search after boot is switched on; from then on it is the system part's
(/etc/bc250-bluetooth-pairing/boot.json), and Save writes a changed list there. Each change to the system part asks
for your password; reading it does not. Searching for nearby devices runs off the GUI thread."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QVBoxLayout,
                             QWidget)

from bc250_core import window_title
from bc250_core.settings import SettingsStore
from bc250_core.theme import GREEN, GREY, ORANGE, RED
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, InfoButton, MetricBox, StatusText, Terminal, hint_label, same_width

from . import APP_NAME, INFO, LOGO_PATH, __version__, bluez, boot, plasma, runner

NAMES_KEY = "names"                     # the list while the system part is not installed

ABOUT = ("<b>BC-250 Bluetooth Pairing</b> lets a board without a USB keyboard or mouse be used with Bluetooth ones "
         "from the first boot.<br><br>"
         "<b>Pair after boot</b>: for 5 minutes after every boot, a small system service searches for the devices "
         "listed here. Put one in pairing mode (hold its connect button until the light blinks fast) and it is "
         "paired, trusted and connected within seconds, on the login screen. One that was paired before but "
         "dropped its pairing is paired again. Devices with other names are never paired, and the search stops "
         "once every listed device is connected.<br><br>"
         "<b>Controller batteries</b>: a DualSense reports its battery through its own driver, not Bluetooth, so "
         "the Bluetooth icon shows none; this hands it to Bluetooth every 30 seconds.<br><br>"
         "<b>Bluetooth at login</b>: Plasma switches Bluetooth back to the state it saved when the last session "
         "ended. A reboot from a terminal saves it as off, and the keyboard and mouse then stop at the desktop. "
         "With this on, Plasma switches Bluetooth on at every login (System Settings, Bluetooth, \"When logging "
         "in\").<br><br>"
         "A name can be copied by someone nearby with deliberate effort; the search is limited to the listed names "
         "and to the first minutes after a boot.")


class AddDialog(QDialog):
    """A device to list: one Bluetooth knows (paired, or heard in a search), or a name typed exactly as the device
    gives it."""

    def __init__(self, devices: list[bluez.Device], listed: list[str], search: Callable[[], None],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("Add a device"))
        self.resize(460, 380)
        self.listed = listed
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Devices Bluetooth knows"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.list.currentItemChanged.connect(self._picked)
        layout.addWidget(self.list, 1)
        self.search_button = QPushButton("Search nearby")
        self.search_button.setToolTip(f"Look for devices in pairing mode for {bluez.SCAN_S} seconds")
        self.search_button.clicked.connect(search)
        self.note = hint_label("")
        row = QHBoxLayout()
        row.addWidget(self.search_button)
        row.addWidget(self.note, 1)
        layout.addLayout(row)
        layout.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Exactly as the device gives it")
        self.name.textChanged.connect(self._check)
        layout.addWidget(self.name)
        self.problem = hint_label("")
        layout.addWidget(self.problem)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.show_devices(devices)
        self._check()

    def show_devices(self, devices: list[bluez.Device]) -> None:
        self.list.clear()
        for device in devices:
            state = "connected" if device.connected else "paired" if device.paired else "nearby"
            item = QListWidgetItem(f"{device.name}  ·  {state}")
            item.setData(Qt.ItemDataRole.UserRole, device.name)
            if device.name in self.listed:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setText(f"{device.name}  ·  listed already")
            self.list.addItem(item)

    def searching(self, on: bool) -> None:
        self.search_button.setEnabled(not on)
        self.note.setText(f"Searching for {bluez.SCAN_S} seconds…" if on else "")

    def _picked(self, item: QListWidgetItem | None) -> None:
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.name.setText(item.data(Qt.ItemDataRole.UserRole))

    def _check(self) -> None:
        name = self.name.text()
        problem = boot.name_problem(name) if name else ""
        if not problem and name in self.listed:
            problem = "It is listed already."
        self.problem.setText(problem)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(name) and not problem)

    def chosen(self) -> str:
        return self.name.text()


class MainWindow(QMainWindow):
    def __init__(self, etc_root: Path = Path("/etc"), bt_run: bluez.Runner = bluez.run,
                 kde_run: plasma.Runner = plasma.run, kde: bool | None = None,
                 run_root: Callable[[list[str]], runner.Result] = runner.run_root) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 760)
        self.paths = boot.Paths(etc_root)
        self.bt_run, self.kde_run, self.run_root = bt_run, kde_run, run_root
        self.kde = plasma.available() if kde is None else kde
        self.settings = SettingsStore(INFO, self)
        self.installed: boot.Config | None = None
        self.names: list[str] = []
        self.devices: list[bluez.Device] = []
        self.searcher = UpdateChecker(self)
        self.searcher.finished.connect(self._searched)
        self.add_dialog: AddDialog | None = None

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.state = StatusText()
        header.add_state(self.state)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read Bluetooth, the system part and the last search again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.bluetooth_box = MetricBox("Bluetooth")
        self.boot_box = MetricBox("After boot")
        self.battery_box = MetricBox("Batteries")
        self.login_box = MetricBox("At login")
        same_width([self.bluetooth_box, self.boot_box, self.battery_box, self.login_box])
        for box in (self.bluetooth_box, self.boot_box, self.battery_box, self.login_box):
            header.add_second(box)
        self.about = InfoButton(ABOUT, "What this app does")
        header.add_second(self.about)
        header.second_row.addStretch(1)

        listed = QGroupBox("Devices to pair after boot")
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.add_button = QPushButton("Add…")
        self.add_button.setToolTip("Pick a device Bluetooth knows, search for one in pairing mode, or type its name")
        self.add_button.clicked.connect(self.add_device)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Take the chosen name off the list; the device itself stays paired")
        self.remove_button.clicked.connect(self.remove_device)
        self.save_button = QPushButton("Save")
        self.save_button.setToolTip("Give the search after boot the changed list; it asks for your password")
        self.save_button.clicked.connect(self.save_names)
        list_buttons = QVBoxLayout()
        for button in (self.add_button, self.remove_button, self.save_button):
            list_buttons.addWidget(button)
        list_buttons.addStretch(1)
        list_row = QHBoxLayout()
        list_row.addWidget(self.list, 1)
        list_row.addLayout(list_buttons)
        self.list_note = hint_label("")
        lay_listed = QVBoxLayout(listed)
        lay_listed.addLayout(list_row)
        lay_listed.addWidget(self.list_note)

        system = QGroupBox("Before you log in (a system service; each change asks for your password)")
        self.pair_check = QCheckBox("Pair the listed devices after every boot")
        self.pair_check.setToolTip("Searches for 5 minutes after every boot and stops once every listed device is "
                                   "connected")
        self.pair_check.toggled.connect(self.choose_pair)
        self.search_button = QPushButton("Search now")
        self.search_button.setToolTip("Search again now, without a reboot: put a device in pairing mode first")
        self.search_button.clicked.connect(self.search_now)
        self.update_button = QPushButton("Update")
        self.update_button.setToolTip("Install this version of the system part")
        self.update_button.clicked.connect(self.update_system)
        pair_row = QHBoxLayout()
        pair_row.addWidget(self.pair_check)
        pair_row.addStretch(1)
        pair_row.addWidget(self.update_button)
        pair_row.addWidget(self.search_button)
        self.battery_check = QCheckBox("Show controller batteries in the Bluetooth icon")
        self.battery_check.setToolTip("A DualSense reports its battery through its own driver; this hands it to "
                                      "Bluetooth every 30 seconds")
        self.battery_check.toggled.connect(self.choose_battery)
        self.system_note = hint_label("")
        lay_system = QVBoxLayout(system)
        lay_system.addLayout(pair_row)
        lay_system.addWidget(self.battery_check)
        lay_system.addWidget(self.system_note)

        login = QGroupBox("When you log in (your own setting, no password)")
        self.login_check = QCheckBox("Switch Bluetooth on at every login")
        self.login_check.setToolTip("Plasma's \"When logging in: Enable Bluetooth\". Off: Plasma restores the state "
                                    "it saved when the last session ended")
        self.login_check.toggled.connect(self.choose_login)
        lay_login = QVBoxLayout(login)
        lay_login.addWidget(self.login_check)

        searched = QGroupBox("The search after this boot")
        self.log_view = Terminal()
        self.log_view.setPlaceholderText("The search did not run in this boot.")
        self.log_view.setMinimumHeight(120)
        lay_searched = QVBoxLayout(searched)
        lay_searched.addWidget(self.log_view)

        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.addLayout(header)
        layout.addWidget(listed, 1)
        layout.addWidget(system)
        layout.addWidget(login)
        layout.addWidget(searched, 1)
        self.setCentralWidget(contents)
        self.refresh()

    # --- Reading --------------------------------------------------------------------------------------------------

    def stored_names(self) -> list[str]:
        """The list kept by the app while the system part is not installed."""
        stored = self.settings.qsettings.value(NAMES_KEY, [])
        stored = [stored] if isinstance(stored, str) else list(stored or [])
        return [n for n in stored if isinstance(n, str) and not boot.name_problem(n)]

    def keep_names(self) -> None:
        self.settings.qsettings.setValue(NAMES_KEY, self.names)

    def refresh(self) -> None:
        """Bluetooth, the devices it knows, the system part as installed, the login setting and the last search."""
        self.installed = boot.installed(self.paths)
        self.names = list(self.installed.names) if self.installed is not None else self.stored_names()
        self.devices = bluez.known(self.bt_run)
        self.adapter = bluez.adapter(self.bt_run)
        self.show_names()
        self.show_system()
        self.show_login()
        self.log_view.set_text("\n".join(bluez.last_search(self.bt_run)) if self.installed is not None else "")
        self.show_state()

    def show_names(self) -> None:
        by_name = {d.name: d for d in self.devices}
        self.list.clear()
        for name in self.names:
            device = by_name.get(name)
            state = ("connected" if device.connected else "paired" if device.paired else "known") if device else \
                "not seen yet"
            item = QListWidgetItem(f"{name}  ·  {state}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
        if not self.names:
            self.list_note.setText("No devices listed: Add… picks one Bluetooth knows or finds one in pairing mode.")
        elif self.changed():
            self.list_note.setText("Changed: Save gives the search after boot this list.")
        else:
            self.list_note.setText("")
        self._update_buttons()

    def changed(self) -> bool:
        """Whether the list differs from the one the system part searches for."""
        return self.installed is not None and tuple(self.names) != self.installed.names

    def show_system(self) -> None:
        at_boot = self.installed
        for check, on in ((self.pair_check, at_boot is not None and at_boot.pair),
                          (self.battery_check, at_boot is not None and at_boot.battery)):
            check.blockSignals(True)
            check.setChecked(on)
            check.blockSignals(False)
        stale = at_boot is not None and boot.outdated(self.paths)
        self.update_button.setVisible(stale)
        if at_boot is None:
            self.system_note.setText("Not installed: switching one on installs a small system service.")
        elif stale:
            self.system_note.setText("Installed by another version of the app: Update installs this one.")
        else:
            searching = bluez.unit_state(boot.PAIR_UNIT, self.bt_run) == "active"
            self.system_note.setText(f"Searching now ({boot.PAIR_UNIT})." if searching else "")
        self.boot_box.set_value("On" if at_boot is not None and at_boot.pair else "Off",
                                f"{len(at_boot.names)} device(s) listed" if at_boot is not None else "Not installed")
        self.boot_box.set_colour(GREEN if at_boot is not None and at_boot.pair else GREY)
        battery = at_boot is not None and at_boot.battery
        running = battery and bluez.unit_state(boot.BATTERY_UNIT, self.bt_run) == "active"
        self.battery_box.set_value("On" if running else "Stopped" if battery else "Off",
                                   f"{boot.BATTERY_UNIT}: {'running' if running else 'not running'}" if battery
                                   else "Controller batteries are not handed to Bluetooth")
        self.battery_box.set_colour(GREEN if running else ORANGE if battery else GREY)

    def show_login(self) -> None:
        self.login_check.setEnabled(self.kde)
        state = plasma.launch_state(self.kde_run) if self.kde else ""
        self.login_check.blockSignals(True)
        self.login_check.setChecked(state == plasma.ENABLE)
        self.login_check.blockSignals(False)
        if not self.kde:
            self.login_box.set_value("—", "Not Plasma's desktop: its Bluetooth settings do not apply")
            self.login_box.set_colour(GREY)
            return
        text = {plasma.ENABLE: "On", plasma.DISABLE: "Off", plasma.REMEMBER: "Restored"}[state]
        self.login_box.set_value(text, {plasma.ENABLE: "Plasma switches Bluetooth on at every login",
                                        plasma.DISABLE: "Plasma switches Bluetooth off at every login",
                                        plasma.REMEMBER: "Plasma restores the state saved when the last session "
                                                         "ended"}[state])
        self.login_box.set_colour({plasma.ENABLE: GREEN, plasma.DISABLE: RED, plasma.REMEMBER: ORANGE}[state])

    def show_state(self) -> None:
        adapter = self.adapter
        if not adapter.present:
            self.bluetooth_box.set_value("None", "No Bluetooth adapter found")
            self.bluetooth_box.set_colour(RED)
            self.state.set_status("No Bluetooth adapter", "bad")
            return
        on = adapter.powered and not adapter.blocked
        self.bluetooth_box.set_value("On" if on else "Off", "The adapter is on" if on else
                                     "The adapter is switched off (Plasma's Bluetooth switch, or airplane mode)")
        self.bluetooth_box.set_colour(GREEN if on else RED)
        if not on:
            self.state.set_status("Bluetooth is off", "bad")
        elif self.installed is not None and self.installed.pair and self.installed.names:
            self.state.set_status("Pairs after boot", "ok")
        else:
            self.state.set_status("Not pairing after boot", "neutral")

    def _update_buttons(self) -> None:
        self.remove_button.setEnabled(bool(self.list.selectedItems()))
        self.save_button.setVisible(self.installed is not None)
        self.save_button.setEnabled(self.changed())
        self.search_button.setEnabled(self.installed is not None and self.installed.pair
                                      and bool(self.installed.names))

    # --- The list ---------------------------------------------------------------------------------------------

    def add_device(self) -> None:
        self.add_dialog = AddDialog(self.devices, self.names, self.search_nearby, self)
        try:
            accepted = self.add_dialog.exec() == QDialog.DialogCode.Accepted
            name = self.add_dialog.chosen()
        finally:
            self.add_dialog = None
        if accepted and name and name not in self.names:
            self.names.append(name)
            self.names_changed()

    def search_nearby(self) -> None:
        run = self.bt_run
        if self.searcher.start(lambda: bluez.scan(run)) and self.add_dialog is not None:
            self.add_dialog.searching(True)

    def _searched(self, devices: object) -> None:
        if isinstance(devices, list):
            self.devices = devices
        if self.add_dialog is not None:
            self.add_dialog.searching(False)
            self.add_dialog.show_devices(self.devices)
        self.show_names()

    def remove_device(self) -> None:
        items = self.list.selectedItems()
        if not items:
            return
        self.names.remove(items[0].data(Qt.ItemDataRole.UserRole))
        self.names_changed()

    def names_changed(self) -> None:
        """Kept by the app while the system part is not installed; Save writes it there once it is."""
        if self.installed is None:
            self.keep_names()
        self.show_names()
        self.show_state()

    def save_names(self) -> None:
        if self.installed is None or not self.changed():
            return
        pair = self.installed.pair and bool(self.names)
        if self.apply(boot.Config(tuple(self.names), pair, self.installed.battery), "Save"):
            self.keep_names()
        self.refresh()

    # --- The system part -----------------------------------------------------------------------------------------

    def as_root(self, args: list[str], title: str) -> bool:
        """Runs boot.py as root; a canceled password or a failure shows a message and changes nothing here."""
        result = self.run_root(boot.command(args))
        problem = boot.answer(result.code, result.out)
        if problem:
            QMessageBox.warning(self, window_title(title), problem)
        return not problem

    def apply(self, config: boot.Config, title: str) -> bool:
        """Installs the system part with *config*, or removes it when it neither pairs nor shows batteries."""
        if not config.pair and not config.battery:
            return self.as_root(["uninstall"], title)
        return self.as_root(boot.install_args(config), title)

    def choose_pair(self, on: bool) -> None:
        if on and not self.names:
            QMessageBox.information(self, window_title("Pair after boot"),
                                    "Add the devices to pair first: Add… picks one Bluetooth knows or finds one in "
                                    "pairing mode.")
        else:
            battery = self.installed is not None and self.installed.battery
            if self.apply(boot.Config(tuple(self.names), on, battery), "Pair after boot"):
                self.keep_names()
        self.refresh()                              # as installed: unchanged when the password was canceled

    def choose_battery(self, on: bool) -> None:
        pair = self.installed is not None and self.installed.pair
        if self.apply(boot.Config(tuple(self.names), pair, on), "Controller batteries"):
            self.keep_names()
        self.refresh()

    def update_system(self) -> None:
        if self.installed is not None:
            self.apply(self.installed, "Update")
        self.refresh()

    def search_now(self) -> None:
        if self.as_root(["start"], "Search now"):
            self.list_note.setText("Searching for 5 minutes: put the device in pairing mode now.")
        self.show_system()

    # --- At login ---------------------------------------------------------------------------------------------

    def choose_login(self, on: bool) -> None:
        if not plasma.set_enable(on, self.kde_run):
            QMessageBox.warning(self, window_title("At login"), "Plasma's Bluetooth setting could not be written "
                                                                "(kwriteconfig6 failed).")
        self.show_login()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.searcher.stop()
        super().closeEvent(event)
