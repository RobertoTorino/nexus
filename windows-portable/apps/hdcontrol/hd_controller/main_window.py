# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window with the BC250 app's parts as cards on the left (Controller, Test,
Firmware, Profiles, Settings), what the focused one shows on the right, the controller's buttons at the bottom.

Every second the window looks for the controllers in Windows' list of HID devices (hidapi's, without opening them).
Nothing is read from a controller before A on the Controller card asks (owner, 28-10-2026: a card that reads the
device reads on A); from then on each controller is read once as it appears, as the BC250 app does: its firmware
report, its profiles, and its input reports for the drawing, the battery and the report rate. The update and the
check for the latest firmware run off the window's thread; the pane shows how far the update is.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). What the BC250 app asked in a dialog asks for a second press
within five seconds (the firmware update, clearing a profile), with the legend's entry and the status line saying so;
Windows' own windows are not used (the firmware file is picked in core's browser, a profile's backup goes to the
app's folder). Core's rule ends the legend: B goes back (a pane to its card, a page to where it came from), View exits
the app and Menu shows the information of the pane that shows. While the test runs, every button of every
controller only lights the drawing (the controller tested is also one the app answers to); holding B for two seconds,
or a tap on B in the legend, ends it. While the firmware update runs the app does not close: a cut-off update would
leave the controller without its firmware (the BC250 app's rule)."""

from __future__ import annotations

import dataclasses
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, DIM, EXIT, KEYBOARD, Card, Legend, Pane, PortableHeader, PortableWindow, px,
                                 status_clock)

from . import APP_ID, APP_NAME, INFO, __version__, controller, feedback, firmware, inputs, profiles, updater
from .controller import Controller, FirmwareInfo
from .editor import Editor
from .hiddevice import Device
from .panes import (BROWSE_INFO, CONTROLLER_INFO, EDITOR_INFO, SETTINGS_INFO, SYMBOLS, ControllerPane, FirmwarePane,
                    IntroPane, ListPane, NamePane, ProfilesPane, TestPane, fill_grid, spec_text, wrappable)
from .settings import ControlSettings

STATUS_MS = 30_000              # the header's battery and time
INTERVAL_MS = 1000              # the controllers looked for in Windows' list
INPUT_MS = 16                   # the input reports read: Windows keeps 32, the controller sends 250 a second
PROGRESS_MS = 250               # the update's progress
CONFIRM_MS = 5000               # the update and Clear ask for a second press within this
HOLD_MS = 2000                  # B held this long ends the test
CHECK_AGE_S = 24 * 3600         # the app asks Sony's server again after a day
RETURN_S = 15.0                 # after an update the controller restarts: the app waits this long for it
CARDS_WIDTH = 400               # the cards' column; the panes take the rest
CARD_HEIGHT = 92                # five cards and their gaps fit the column at 720 px high
# The light bar's colors to choose from, in turn; Off saves the battery, "" leaves it as the system sets it.
LIGHT_COLOURS = (("Blue", "#0050ff"), ("Red", "#ff2020"), ("Green", "#10d040"), ("Purple", "#a020f0"),
                 ("White", "#ffffff"), ("Off", "#000000"), ("As the system sets it", ""))
SHORT_NAMES = {0x0CE6: "DualSense", 0x0DF2: "Edge"}
SHORT_CONNECTIONS = {"usb": "USB", "bluetooth": "Bluetooth"}
TEST_CARD = "Buttons, sticks, motors, light bar."
REMAPS_SHOWN = 6                # a profile's changed buttons listed under the rows; the editor shows them all
TEST_HINT = "Press a button or move a stick: the drawing follows."
TESTING = ("The test runs: every button of every controller only lights the drawing. Hold B for two seconds to end "
           "it, or tap B in the row at the bottom.")
ENDED = "The test ended: the buttons move the app again."
NOT_READ = "Press the A button on the Controller card first: the app reads the controller then."
UPDATING = "Wait until the firmware update is done."
NO_CONTROLLER = "No controller: connect one, then the A button on the Controller card reads it."
BROWSED = "firmware"            # the browser's folder kept for next time (browse.remember)


def controller_label(found: Controller, battery: controller.Battery | None) -> str:
    """A controller's line on its card: model, connection and battery, so all of them show at a glance."""
    parts = [SHORT_NAMES[found.product], SHORT_CONNECTIONS.get(found.bus, found.bus)]
    if battery is not None and battery.capacity is not None:
        parts.append(f"{battery.capacity} %")
    return " · ".join(parts)


def _error(exc: Exception) -> str:
    return (exc.strerror or str(exc)) if isinstance(exc, OSError) else str(exc)


class _Worker(QObject):
    """Runs a job off the window's thread; done (the result, or the exception) arrives on the window's."""

    done = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.busy = False

    def run(self, job: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return True

    def _run(self, job: Callable[[], object]) -> None:
        try:
            result = job()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 find: Callable[[], list[Controller]] = controller.find,
                 open_device: Callable[..., Device] = Device,
                 open_reader: Callable[[Controller], inputs.Reader] | None = None,
                 firmware_home: Path | None = None, get: firmware.Get | None = None,
                 update: Callable[..., None] = updater.update, clock: Callable[[], float] = time.time,
                 holders: Callable[[], list[str]] = controller.holders,
                 monotonic: Callable[[], float] = time.monotonic,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None):
        """*find*: the controllers Windows has; *open_device*: opens one (hiddevice.Device); *open_reader*: reads
        its input reports (inputs.Reader); *firmware_home*: the app's folder for the firmware and the backups (None:
        the suite's); *get*: fetches a URL (Sony's server); *update*: sends an image (updater.update); *holders*: the
        programs that talk to the controller; *roots* and *user_home*: the browser's places."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.settings = ControlSettings(INFO, self)
        self.find, self.open_device, self.holders = find, open_device, holders
        self.open_reader = open_reader or (lambda found: inputs.Reader(found.path, found.bus, open_device))
        self.firmware_home = firmware_home
        self.get = get or firmware._get
        self.update_image = update
        self.clock, self.monotonic = clock, monotonic
        self.roots, self.user_home = roots, user_home
        self.controllers: list[Controller] = []
        self.chosen = b""                   # the path of the controller the window shows
        self.reading = False                # A asked to read: from then on each controller is read as it appears
        self.read_key = b""                 # the controller whose reports were read
        self.info: FirmwareInfo | None = None
        self.read_problem = ""
        self.profiles: list[profiles.Profile] = []
        self.reader: inputs.Reader | None = None
        self.reader_key = b""
        self.rate_mark: tuple[int, float] | None = None     # the reader's count and when, for the report rate
        self.rate = ""
        self.active_slot = ""               # the Edge's profile in use, from its input reports
        self.light_sequence = 0             # Bluetooth output reports count up
        self.rumble: Device | None = None   # the controller, open for the vibration test
        self.testing = False
        self.progress: updater.Progress | None = None
        self.updating = False
        self.update_target = 0              # the version the running or last update sends
        self.returning_until = 0.0          # after an update: until then a missing controller is restarting
        self.firmware_message = ""          # the last outcome on the Firmware pane
        self.controller_message = ""        # why A, LB or RB on the Controller pane did nothing
        self.confirm = ""                   # "update" or "clear": pressed once, waiting for the second press
        self.confirm_data: tuple = ()
        self.file_checks: dict[Path, tuple[int, str, bool]] = {}    # kept file -> (mtime, SHA-256, known)
        self.intro_open = False
        self.editor: Editor | None = None
        self.editing: profiles.Profile | None = None
        self.browser: browse.Browser | None = None

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(10))
        self.controller_card = Card("Controller", "Looking for a controller…")
        self.test_card = Card("Test", TEST_CARD)
        self.firmware_card = Card("Firmware", "")
        self.profiles_card = Card("Profiles", "")
        self.settings_card = Card("Settings", "")
        for card in (self.controller_card, self.test_card, self.firmware_card, self.profiles_card,
                     self.settings_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.controller_pane = ControllerPane()
        self.test_pane = TestPane()
        self.firmware_pane = FirmwarePane()
        self.profiles_pane = ProfilesPane()
        self.settings_pane = ListPane("Settings", "The settings", SETTINGS_INFO)
        self.intro_pane = IntroPane()
        self.editor_pane = ListPane("Edit the profile", "The profile editor", EDITOR_INFO)
        self.name_pane = NamePane()
        self.browse_pane = ListPane("Use a file", "Pick the firmware", BROWSE_INFO)
        for pane in (self.controller_pane, self.test_pane, self.firmware_pane, self.profiles_pane,
                     self.settings_pane, self.intro_pane, self.editor_pane, self.name_pane, self.browse_pane):
            self.panes.addWidget(pane)
        self.cards: dict[Pane, Card] = {
            self.controller_pane: self.controller_card, self.test_pane: self.test_card,
            self.firmware_pane: self.firmware_card, self.profiles_pane: self.profiles_card,
            self.settings_pane: self.settings_card, self.intro_pane: self.controller_card,
            self.editor_pane: self.profiles_card, self.name_pane: self.profiles_card,
            self.browse_pane: self.firmware_card}
        self.pages = (self.intro_pane, self.editor_pane, self.name_pane, self.browse_pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.check_worker = _Worker()
        self.check_worker.done.connect(self._check_done)
        self.update_worker = _Worker()
        self.update_worker.done.connect(self._update_done)
        for pane, card in ((self.controller_pane, self.controller_card), (self.test_pane, self.test_card),
                           (self.firmware_pane, self.firmware_card), (self.profiles_pane, self.profiles_card),
                           (self.settings_pane, self.settings_card)):
            card.focused.connect(lambda pane=pane: self.show_pane(pane))
        self.controller_card.activated.connect(lambda: self.card_a(self.read_controller))
        self.test_card.activated.connect(lambda: self.card_a(self.start_test))
        self.firmware_card.activated.connect(lambda: self.card_a(self.update_action))
        self.profiles_card.activated.connect(lambda: self.card_a(lambda: self.focus_list(self.profiles_pane)))
        self.settings_card.activated.connect(lambda: self.card_a(lambda: self.focus_list(self.settings_pane)))
        self.profiles_pane.list.picked.connect(self.profile_picked)
        self.profiles_pane.list.current.connect(lambda _key: self.show_profiles())
        self.settings_pane.list.picked.connect(self.setting_picked)
        self.editor_pane.list.picked.connect(self.editor_picked)
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.test_pane.view.named.connect(self.test_pane.status.setText)
        self.controller_pane.tapped.connect(lambda: self.card_a(self.read_controller))
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("y", self.y_action)
        self.bind("previous", lambda: self.choose_step(-1))
        self.bind("next", lambda: self.choose_step(1))
        self.bind("lt", self.lt_action)
        self.back.connect(self.on_back)
        self.gamepad.raw.connect(self._raw)

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.timer = QTimer(self)
        self.timer.setInterval(INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.input_timer = QTimer(self)
        self.input_timer.setInterval(INPUT_MS)
        self.input_timer.timeout.connect(self._input_ready)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.show_state)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.setInterval(HOLD_MS)
        self.hold_timer.timeout.connect(self.end_test)
        self.show_settings()
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the focus on the Controller card, the
        controllers looked for every second, and Sony's server asked when the setting says so (off the window's
        thread)."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.timer.start()
        self.controller_card.setFocus()
        self.show_pane(self.controller_pane)
        if self.settings.get("check_at_start") and self._check_is_old():
            self.check_latest()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    @property
    def busy(self) -> bool:
        """The app may not start again on another screen meanwhile (PortableWindow.can_restart)."""
        return self.updating

    # ------------------------------------------------------------------ state
    def current(self) -> Controller | None:
        for found in self.controllers:
            if found.path == self.chosen:
                return found
        return self.controllers[0] if self.controllers else None

    def latest(self) -> int | None:
        return self.settings.latest().get(self.info.target) if self.info else None

    def refresh(self) -> None:
        """The controllers in Windows' list; a controller read once as it appears, once A asked to read."""
        before = [c.path for c in self.controllers]
        self.controllers = self.find()
        if [c.path for c in self.controllers] != before:
            self.controller_message = ""
        found = self.current()
        self.chosen = found.path if found else b""
        key = found.path if found and self.reading else b""
        if key != self.read_key and not self.updating:
            self.read_key = key
            self._read(found if self.reading else None)
        self.show_state()

    def read_controller(self) -> None:
        """A on the Controller card: the controller read now (again, when it was read before)."""
        found = self.current()
        if found is None or self.updating:
            self.controller_message = f"No controller found. {controller.NOT_FOUND}" if found is None else UPDATING
            self.show_state()
            return
        self.controller_message = ""
        self.reading = True
        self.read_key = b""
        self.refresh()
        if self.info is not None and not self.settings.get("intro_seen"):
            self.show_intro()

    def _read(self, found: Controller | None) -> None:
        """The firmware report and the profiles, once per controller: they do not change while it is connected."""
        self.info, self.profiles, self.read_problem = None, [], ""
        self._stop_reading()
        if found is None:
            return
        try:
            with self.open_device(found.path, None) as device:
                self.info = controller.read_info(device)
                if found.edge:
                    self.profiles = profiles.read(device)
        except (OSError, ValueError) as exc:
            self.read_problem = f"The controller could not be read: {_error(exc)}."
            self.log.error(f"{found.name} on {found.connection}: {self.read_problem}")
            return
        self.log.info(f"Read the {found.name} on {found.connection}: firmware "
                      f"{firmware.version_text(self.info.update)}, target {self.info.target:04X}"
                      + (f", {sum(not p.empty for p in self.profiles)} profile(s)" if found.edge else "") + ".")
        if feedback.parse_colour(self.settings.get("lightbar")):
            self.apply_light(found, quiet=True)

    def choose_step(self, delta: int) -> None:
        """LB and RB on the Controller pane: the controller before or after, with two or more connected."""
        if self.panes.currentWidget() is not self.controller_pane:
            return
        if len(self.controllers) < 2 or self.updating:
            self.controller_message = (UPDATING if self.updating else
                                       "One controller is connected: LB and RB choose between two or more.")
            self.show_state()
            return
        self.controller_message = ""
        index = next((i for i, c in enumerate(self.controllers) if c.path == self.chosen), 0)
        self.chosen = self.controllers[(index + delta) % len(self.controllers)].path
        self.refresh()

    # ------------------------------------------------------------------ what shows
    def show_state(self) -> None:
        found = self.current()
        latest = self.latest()
        self._follow(found)
        self._show_rate()
        self._show_controller(found, latest)
        self._show_test(found)
        self._show_firmware(found, latest)
        self.show_profiles()
        self.update_legend()

    def _battery(self) -> controller.Battery | None:
        return self.reader.battery if self.reader is not None else None

    def _show_controller(self, found: Controller | None, latest: int | None) -> None:
        pane, card = self.controller_pane, self.controller_card
        pane.show_found(found is not None or self.updating)
        if found is None:
            pane.heading.setText("Connect your controller" if not self.updating else "Controller")
            card.set_text("The controller restarts…" if self.updating or self.clock() < self.returning_until
                          else "No controller")
            pane.info.info = CONTROLLER_INFO
            pane.status.setText(self.controller_message or ("" if self.updating else
                                "Plug your DualSense or DualSense Edge into a USB port of the handheld, with a USB-C "
                                "cable. The app finds it by itself. A controller paired over Bluetooth shows up too; "
                                "only the firmware update needs the cable."))
            return
        battery = self._battery()
        count = len(self.controllers)
        more = f" · {self.controllers.index(found) + 1} of {count}" if count > 1 else ""
        if not self.reading:
            card.set_text(f"{found.name} on {SHORT_CONNECTIONS[found.bus]}: the A button reads it{more}", AMBER)
        else:
            card.set_text(controller_label(found, battery) + more, DIM)
        pane.heading.setText(found.name)
        rows = self.info_rows(found)
        if self.reading and self.info is not None:
            chosen = self.settings.get("lightbar")
            names = {value: name for name, value in LIGHT_COLOURS}
            rows.append(("Light bar", names.get(chosen, chosen) if chosen else "as the system sets it"))
            rows.append(("Reports", self.rate or "—"))
        fill_grid(pane.grid, rows)
        pane.battery.set_battery(battery.capacity if battery else None, battery.status if battery else "")
        pane.battery.setVisible(self.reading)
        pane.info.info = CONTROLLER_INFO + "\n\n" + spec_text(self.info_rows(found), found.product)
        if self.updating:
            state = "Updating the firmware: leave the controller plugged in until the update is done."
        elif not self.reading:
            state = "The A button reads the controller: its firmware, its profiles and its battery."
        elif self.read_problem:
            state = self.read_problem
        elif self.info is not None and latest is not None and latest > self.info.update:
            state = (f"Firmware {firmware.version_text(latest)} is out; the controller runs "
                     f"{firmware.version_text(self.info.update)}: see the Firmware card.")
        elif self.info is not None and latest is not None:
            state = "The controller runs the latest official firmware."
        else:
            state = "Ready. Check for an update (the Firmware card) asks the official update server for the latest."
        pane.status.setText(self.controller_message or state)

    def info_rows(self, found: Controller) -> list[tuple[str, str]]:
        """What the controller reports now, for the pane and the spec sheet; never its address or serial number."""
        rows = [("Model", found.name), ("Connection", found.connection)]
        if self.info is not None:
            rows += [("Installed firmware", f"{firmware.version_text(self.info.update)}, built "
                                            f"{self.info.build_date} {self.info.build_time}"),
                     ("Firmware target", f"{self.info.target:04X}"),
                     ("Hardware version", f"0x{self.info.hardware:08x}"),
                     ("Firmware build", f"0x{self.info.firmware:08x}")]
        battery = self._battery()
        if battery is not None and battery.capacity is not None:
            rows.append(("Battery", f"{battery.capacity} %, {battery.status.lower()}"))
        return rows

    # ------------------------------------------------------------- live input
    def _follow(self, found: Controller | None) -> None:
        """Reads the input reports of the controller shown, once it was read; stops while an update runs."""
        live = found is not None and self.reading and self.info is not None and not self.updating
        key = found.path if live else b""
        if key == self.reader_key:
            return
        self._stop_reading()
        if not key:
            return
        try:
            self.reader = self.open_reader(found)
        except OSError:
            return
        self.reader_key = key
        self.input_timer.start()

    def _input_ready(self) -> None:
        if self.reader is None:
            return
        try:
            reading = self.reader.read()
        except OSError:                     # the controller left; the next refresh notices
            self._stop_reading()
            return
        if reading is not None:
            view = self.test_pane.view
            view.show_input(set(reading.pressed), reading.sticks, reading.triggers)
            if reading.profile != self.active_slot:
                self.active_slot = reading.profile
                self.show_profiles()

    def _show_rate(self) -> None:
        """How many input reports a second come in."""
        now = self.monotonic()
        if self.reader is None:
            self.rate_mark, self.rate = None, ""
        elif self.rate_mark is not None and now - self.rate_mark[1] >= 0.5:
            self.rate = f"{(self.reader.count - self.rate_mark[0]) / (now - self.rate_mark[1]):.0f} Hz"
            self.rate_mark = (self.reader.count, now)
        elif self.rate_mark is None:
            self.rate_mark = (self.reader.count, now)

    def _stop_reading(self) -> None:
        self.input_timer.stop()
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.reader_key = b""
        self.test_pane.view.clear_input()
        if self.active_slot:
            self.active_slot = ""
            self.show_profiles()

    # ------------------------------------------------------------- the test
    def _show_test(self, found: Controller | None) -> None:
        view = self.test_pane.view
        view.set_edge(found.edge if found else True)
        colour = feedback.parse_colour(self.settings.get("lightbar"))
        view.set_light(QColor(*colour) if colour and found is not None else None)
        if self.testing:
            self.test_card.set_text("The test runs: hold B to end it.", AMBER)
        else:
            self.test_card.set_text(TEST_CARD, DIM)
        status = self.test_pane.status.text()
        if not status or status in (TEST_HINT, NOT_READ, NO_CONTROLLER, TESTING):
            self.test_pane.status.setText(TESTING if self.testing else TEST_HINT if self.reader is not None else
                                          NOT_READ if found is not None else NO_CONTROLLER)

    def _ready(self, status) -> Controller | None:
        """The controller shown when it was read and no update runs; else says why on *status* and gives None."""
        found = self.current()
        if found is None:
            status.setText(f"No controller found. {controller.NOT_FOUND}")
        elif self.updating:
            status.setText(UPDATING)
        elif not self.reading or self.info is None:
            status.setText(self.read_problem or NOT_READ)
        else:
            return found
        return None

    def start_test(self) -> None:
        """A on the Test card: every button only lights the drawing from now on, until B is held."""
        if self._ready(self.test_pane.status) is None:
            return
        self.testing = True
        self.test_pane.status.setText(TESTING)
        self.show_state()

    def end_test(self) -> None:
        self.hold_timer.stop()
        if not self.testing:
            return
        self.testing = False
        self.test_pane.status.setText(ENDED)
        self.test_card.setFocus()
        self.show_state()

    def on_action(self, action: str) -> None:
        """The controller's buttons: while the test runs they only light the drawing (_raw ends it)."""
        if self.testing:
            return
        super().on_action(action)

    def _raw(self, kind: str, name: str, value: object) -> None:
        """B held during the test: after HOLD_MS it ends."""
        if not self.testing or kind != "button" or name != "b":
            return
        if value:
            self.hold_timer.start()
        else:
            self.hold_timer.stop()

    def next_light(self) -> None:
        """Y on the Test pane: the light bar's next color, set at once."""
        found = self._ready(self.test_pane.status)
        if found is None:
            return
        values = [value for _name, value in LIGHT_COLOURS]
        chosen = self.settings.get("lightbar")
        colour = values[(values.index(chosen) + 1) % len(values)] if chosen in values else values[0]
        self.settings.set("lightbar", colour)
        if colour:
            self.apply_light(found)
        else:
            self.test_pane.status.setText("The app leaves the light bar alone now: Windows, Steam or a game sets it.")
        self.show_state()

    def apply_light(self, found: Controller, quiet: bool = False) -> None:
        rgb = feedback.parse_colour(self.settings.get("lightbar"))
        if rgb is None:
            return
        self.light_sequence = (self.light_sequence + 1) % 16
        try:
            with self.open_device(found.path, None) as device:
                device.write(feedback.lightbar_report(found.bus, rgb, self.light_sequence))
        except OSError as exc:
            if not quiet:
                self.test_pane.status.setText(f"The light bar could not be set: {_error(exc)}.")
            return
        if not quiet:
            self.test_pane.status.setText("The light bar keeps this color until the controller disconnects, or "
                                          "Steam or a game sets another. The app sets it again when the controller "
                                          "connects while the app is open.")

    def test_vibration(self) -> None:
        """X on the Test pane: the left motor, then the right one."""
        found = self._ready(self.test_pane.status)
        if found is None:
            return
        if self.rumble is not None:
            self.test_pane.status.setText("The vibration test runs.")
            return
        try:
            self.rumble = self.open_device(found.path, None)
        except OSError as exc:
            self.test_pane.status.setText(f"The motors could not be reached: {_error(exc)}.")
            return
        self.test_pane.status.setText("The left motor, then the right one: you should feel each on its own side.")
        v2 = feedback.vibration_v2(found.edge, self.info.update if self.info else None)
        for when, side, strong, weak in feedback.VIBRATION_STEPS:
            QTimer.singleShot(when, lambda side=side, strong=strong, weak=weak, bus=found.bus:
                              self._vibrate(bus, side, strong, weak, v2))
        QTimer.singleShot(feedback.VIBRATION_STEPS[-1][0] + 50, self._vibration_done)

    def _vibrate(self, bus: str, side: str, strong: int, weak: int, v2: bool) -> None:
        if self.rumble is None:
            return
        self.test_pane.view.shake(side)
        self.light_sequence = (self.light_sequence + 1) % 16
        try:
            self.rumble.write(feedback.rumble_report(bus, strong, weak, v2, self.light_sequence))
        except OSError as exc:
            self.test_pane.status.setText(f"The motors could not be started: {_error(exc)}.")
            self._vibration_done()

    def _vibration_done(self) -> None:
        self.test_pane.view.shake("")
        if self.rumble is not None:
            self.rumble.close()
            self.rumble = None

    # ------------------------------------------------------------- firmware
    def _can_update(self, found: Controller | None, latest: int | None) -> bool:
        return (found is not None and found.bus == "usb" and self.info is not None and latest is not None
                and latest > self.info.update and not self.updating)

    def _check_is_old(self) -> bool:
        checked = self.settings.get("checked")
        try:
            return self.clock() - time.mktime(time.strptime(checked, "%Y-%m-%d %H:%M")) > CHECK_AGE_S
        except ValueError:
            return True

    def _show_firmware(self, found: Controller | None, latest: int | None) -> None:
        pane, card = self.firmware_pane, self.firmware_card
        info = self.info
        progress = self.progress
        pane.show_sending((progress.done / progress.total if progress and progress.total else 0.0)
                          if self.updating else None)
        newer = info is not None and latest is not None and latest > info.update
        if self.updating:
            done = round(progress.done * 100 / progress.total) if progress and progress.total else 0
            card.set_text(f"Updating to {firmware.version_text(self.update_target)}… {done} %", AMBER)
        elif found is None or info is None:
            card.set_text("Not read yet" if found is not None and not self.reading else
                          "Cannot be read" if found is not None and self.read_problem else "No controller", DIM)
        elif newer:
            card.set_text(f"{firmware.version_text(info.update)}: {firmware.version_text(latest)} is out", AMBER)
        else:
            card.set_text(f"{firmware.version_text(info.update)}"
                          + (", the latest" if latest is not None else ": the latest is not known yet"), DIM)
        rows: list[tuple[str, str]] = []
        lines: list[str] = []
        if found is not None and info is not None:
            rows = [("Controller", f"{found.name} on {found.connection}"),
                    ("Installed", f"{firmware.version_text(info.update)}, built {info.build_date} {info.build_time}"),
                    ("Latest official", firmware.version_text(latest) if latest is not None else "not known yet"),
                    ("Asked the update server", self.settings.get("checked") or "not yet")]
            if latest is not None:
                rows += self._file_check(info.target, latest)
            if latest is None:
                lines.append("The latest version is not known yet: the Y button asks the official update server.")
            elif newer:
                stored = firmware.read(info.target, latest, self.firmware_home) is not None
                lines.append(f"Firmware {firmware.version_text(latest)} is out. "
                             + ("It is downloaded already." if stored else
                                "The A button downloads it (about 1 MB) and sends it."))
            else:
                lines.append("It is the latest official firmware.")
            if found.bus != "usb" and newer:    # only then: on the latest firmware it would only confuse (owner)
                lines.append("The update needs the USB cable: connect the controller with it.")
        elif found is not None:
            lines.append(self.read_problem or NOT_READ)
        else:
            lines.append(f"No controller found. {controller.NOT_FOUND}")
        fill_grid(pane.grid, rows)
        if self.confirm == "update":
            return                          # the question stays until it is answered or its time is over
        if self.updating and progress is not None:
            step = updater.STEP_NAMES.get(progress.step, "")
            detail = (f"{progress.done // 1024} of {progress.total // 1024} KB" if progress.step == updater.WRITE
                      and progress.total else "")
            last = progress.log[-1] if progress.log else ""
            pane.status.setText(" · ".join(part for part in (step, detail, last) if part))
        else:
            pane.status.setText(self.firmware_message or " ".join(lines))

    def _file_check(self, target: int, version: int) -> list[tuple[str, str]]:
        """The kept file of *version* and its SHA-256 check (the BC250 app's, as USB HD Cam shows its firmware's):
        a ✓ for a file the app knows, a ! for one it does not. Hashed once per file, not every second."""
        where = firmware.path(target, version, self.firmware_home)
        try:
            stamp = where.stat().st_mtime_ns
        except OSError:
            return []
        if self.file_checks.get(where) is None or self.file_checks[where][0] != stamp:
            data = firmware.read(target, version, self.firmware_home) or b""
            self.file_checks[where] = (stamp, firmware.sha256(data), firmware.known(data) is not None)
        _stamp, digest, known = self.file_checks[where]
        check = (f"✓ the known file {firmware.version_text(version)}" if known else
                 "! not a file the app knows; the controller still checks its signature")
        return [("Kept file", f"{where.name}: {check}"), ("SHA-256", wrappable(digest))]

    def check_latest(self) -> None:
        """Y on the Firmware pane: Sony's list of the latest versions, off the window's thread."""
        if self.check_worker.run(lambda: firmware.latest(self.get)):
            self.firmware_message = "Asking the official update server…"
            self.show_state()

    def _check_done(self, result: object) -> None:
        if isinstance(result, Exception):
            self.firmware_message = _error(result)
            self.log.error(f"The check for the latest firmware failed: {_error(result)}")
        else:
            self.settings.set_latest(result, time.strftime("%Y-%m-%d %H:%M", time.localtime(self.clock())))
            self.firmware_message = ""
            self.log.info("The latest firmware: " + ", ".join(f"{target:04X} {firmware.version_text(version)}"
                                                              for target, version in sorted(result.items())) + ".")
        self.show_state()

    def update_action(self) -> None:
        """A on the Firmware card or pane: the update when one can start (a second press runs it); otherwise why
        not."""
        if self.updating:
            self.firmware_pane.status.setText("The update is running.")
            return
        if self.confirm == "update":
            data, version = self.confirm_data
            self._confirm_over()
            found = self.current()
            if found is not None and found.bus == "usb" and self.info is not None:
                self._run(found, data, version)
            return
        found, latest = self.current(), self.latest()
        if not self._can_update(found, latest):
            self.firmware_message = self._why_not(found, latest)
            self.show_state()
            return
        self._ask(found, firmware.read(self.info.target, latest, self.firmware_home), latest)

    def _why_not(self, found: Controller | None, latest: int | None) -> str:
        if found is None:
            return f"No controller found. {controller.NOT_FOUND}"
        if self.info is None:
            return self.read_problem or NOT_READ
        if latest is None:
            return "The latest version is not known yet: the Y button asks the official update server."
        if latest <= self.info.update:
            return "The controller runs the latest official firmware: there is nothing to update."
        return "The update needs the USB cable: connect the controller with it."

    def _ask(self, found: Controller, data: bytes | None, version: int) -> None:
        """What the BC250 app's question said, on the status line, and the second press it waits for."""
        busy = self.holders()
        if busy:
            self.firmware_message = (f"{', '.join(busy)} is running. Quit it first (Steam: Steam, Exit), so that "
                                     "nothing else talks to the controller during the update.")
            self.show_state()
            return
        if data is not None:
            check = (f"SHA-256 {firmware.sha256(data)[:16]}…: "
                     + ("a file the app knows from the official server." if firmware.known(data) else
                        "not a file the app knows. The controller still checks its signature."))
        else:
            check = f"The app first downloads it from {firmware.SOURCE} (about 1 MB)."
        battery = self._battery()
        level = f" The battery is at {battery.capacity} %." if battery and battery.capacity is not None else ""
        self.confirm, self.confirm_data, self.firmware_message = "update", (data, version), ""
        self.confirm_timer.start()
        self.firmware_pane.status.setText(
            f"This sends firmware {firmware.version_text(version)} to the {found.name}, which runs "
            f"{firmware.version_text(self.info.update)}. {check} It takes about half a minute: leave the USB cable in "
            f"until the pane says it is done; the controller then restarts by itself.{level} The app saves a backup "
            "of the profiles first. Press the A button again to update the controller now.")
        self.show_state()

    def _run(self, found: Controller, data: bytes | None, version: int) -> None:
        info, home, get, update = self.info, self.firmware_home, self.get, self.update_image
        open_device = self.open_device
        edge, model, path = found.edge, found.name, found.path
        progress = updater.Progress()

        def job() -> str:
            """The update; the backup of the profiles it made first, or "" (a DualSense has none)."""
            saved = ""
            image = data
            if image is None:
                progress.note("Downloading the firmware…")
                image = firmware.download(info.target, version, home, get)
            problem = firmware.problem(image, found, info)
            if problem:
                raise firmware.FirmwareError(problem)
            with open_device(path, None) as device:
                if edge:
                    saved = str(profiles.backup(profiles.read(device), profiles.backup_path(home), model,
                                                firmware.version_text(info.update)))
                    progress.note(f"The profiles are saved in {private(saved)}.")
                update(device, image, progress)
            return saved

        self.end_test()
        self._vibration_done()
        self.progress, self.updating, self.update_target, self.firmware_message = progress, True, version, ""
        self._stop_reading()
        self.log.info(f"Updating the {model} from {firmware.version_text(info.update)} to "
                      f"{firmware.version_text(version)}.")
        self.update_worker.run(job)
        self.progress_timer.start()
        self.show_state()

    def _update_done(self, result: object) -> None:
        self.updating = False
        self.progress_timer.stop()
        self.returning_until = self.clock() + RETURN_S
        if isinstance(result, Exception):
            text = _error(result)
            self.firmware_message = f"The update did not finish: {text}"
            self.log.error(f"The update did not finish: {text}")
        else:
            saved = f" The profiles from before are saved in {private(result)}." if result else ""
            self.firmware_message = (f"Firmware {firmware.version_text(self.update_target)} is sent: the controller "
                                     "restarts with it and comes back in a few seconds, and the pane then shows its "
                                     "new version. For Bluetooth, remove it from Windows' Bluetooth settings and pair "
                                     f"it again: the update ends the pairing.{saved}")
            self.log.info(f"Firmware {firmware.version_text(self.update_target)} sent.")
        self.read_key = b""                 # read the firmware again when the controller is back
        self.refresh()

    # The firmware browser (core's browse)

    def show_browser(self) -> None:
        """X on the Firmware pane: a firmware file of yours, picked in core's browser."""
        if self.updating:
            self.firmware_pane.status.setText("The update is running.")
            return
        found = self.current()
        if found is None or self.info is None:
            self.firmware_message = self._why_not(found, None)
            self.show_state()
            return
        self.browser = browse.Browser(browse.places(self.user_home, self.roots), (".bin",),
                                      path=browse.remembered(self.settings.qsettings, BROWSED))
        self.browse_pane.status.setText("")
        self.open_page(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(private(path) if path is not None else
                                         "Where is the firmware file? Open a place, then the folder it is in.")
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is None:
            self.show_browse()
            return
        found = self.current()
        if found is None or self.info is None:
            self.browse_pane.status.setText("The controller is gone: connect it again, then pick the file.")
            return
        try:
            data = picked.read_bytes()
        except OSError as exc:
            self.browse_pane.status.setText(f"{picked.name} could not be read: {_error(exc)}.")
            return
        problem = firmware.problem(data, found, self.info)
        if problem:
            self.browse_pane.status.setText(f"{picked.name} is not sent: {problem}")
            return
        if found.bus != "usb":
            self.browse_pane.status.setText("The update needs the USB cable: connect the controller with it.")
            return
        browse.remember(self.settings.qsettings, BROWSED, picked.parent)
        self.leave_browser()
        self._ask(found, data, firmware.header(data).update)

    def leave_browser(self) -> None:
        self.browser = None
        self.open_page(self.firmware_pane)

    # ------------------------------------------------------------- profiles
    def focused_profile(self) -> profiles.Profile | None:
        key = self.profiles_pane.list.focused()
        return next((p for p in self.profiles if p.slot == key), None)

    def show_profiles(self) -> None:
        if not hasattr(self, "profiles_pane"):
            return
        pane, card = self.profiles_pane, self.profiles_card
        found = self.current()
        edge = found is not None and found.edge
        if found is None:
            text = "The DualSense Edge's profiles show here."
        elif not edge:
            text = f"The {found.name} has no profiles: only the DualSense Edge has them."
        elif not self.reading or self.info is None:
            text = self.read_problem or NOT_READ
        else:
            text = ""                       # the rows say it; the information explains them
        pane.summary.setText(text)
        pane.summary.setVisible(bool(text))
        shown = self.profiles if edge else []
        active = next((p for p in shown if p.slot == self.active_slot), None)
        named = [p for p in shown if not p.empty]
        card.set_text(f"{len(named)} of 4: {', '.join(p.name for p in named)}" if named else
                      "Only on the DualSense Edge" if found is not None and not edge else
                      "No profile yet" if shown else "Not read yet" if found is not None else "No controller",
                      DIM)
        rows = []
        for profile in shown:
            name = ("Empty" if profile.empty else profile.name
                    + ("" if profile.crc_ok else " (checksum does not match)"))
            rows.append((profile.slot, f"Fn + {SYMBOLS[profile.slot]}  {profile.slot}  ·  {name}"
                                       + ("  ·  Active" if profile is active else "")))
        pane.list.set_items(rows)
        pane.list.setVisible(bool(rows))
        chosen = self.focused_profile() or active
        details: list[tuple[str, str]] = []
        if chosen is not None and not chosen.empty:
            l_start, l_end, r_start, r_end = chosen.triggers
            details = [("Profile", f"{chosen.label}: {chosen.name}"), ("Left stick", chosen.left_curve),
                       ("Right stick", chosen.right_curve), ("L2", profiles.trigger_text(l_start, l_end)),
                       ("R2", profiles.trigger_text(r_start, r_end)),
                       ("Buttons", self.remaps(chosen))]
        elif chosen is not None:
            details = [("Profile", f"{chosen.label}: no profile in this slot")]
        fill_grid(pane.grid, details)
        focused = self.focused_profile()
        pane.view.set_edge(True)
        pane.view.lit({"fn"} | profiles.changed_parts(focused) if focused is not None else set())

    @staticmethod
    def remaps(profile: profiles.Profile) -> str:
        """The buttons a profile sends elsewhere, at most REMAPS_SHOWN of them: the editor shows them all."""
        shown = [f"{source} → {target}" for source, target in profile.remapped[:REMAPS_SHOWN]]
        more = len(profile.remapped) - REMAPS_SHOWN
        return ", ".join(shown) + (f", and {more} more (A Edit shows them)" if more > 0 else "") or "each its own"

    def _profile_ready(self, profile: profiles.Profile | None) -> bool:
        """Whether *profile* may be changed now; else the status line says why."""
        status = self.profiles_pane.status
        found = self.current()
        if profile is None:
            status.setText("Put the focus on a profile first.")
        elif profile.slot not in profiles.WRITE_REPORTS:
            status.setText(f"Fn + {profile.slot} is the default profile: the app does not change it.")
        elif self.updating:
            status.setText(UPDATING)
        elif found is None or found.bus != "usb":
            status.setText("Plug in the USB cable to change the profiles.")
        else:
            return True
        return False

    def profile_picked(self, key: str) -> None:
        """A on a profile: the editor, creating one in an empty slot, editing one in a full one."""
        profile = next((p for p in self.profiles if p.slot == key), None)
        if not self._profile_ready(profile):
            return
        creating = profile.empty
        base = self.profiles[0] if creating else profile
        settings = profiles.settings_of(base)
        if creating:
            settings = dataclasses.replace(settings, name="New profile")
        self.editor, self.editing = Editor(profile.slot, settings, creating), profile
        self.editor_pane.heading.setText(self.editor.title)
        self.editor_pane.summary.setText("A profile made from the default one's settings." if creating else
                                         f"{profile.name}, as the controller holds it.")
        self.editor_pane.status.setText("")
        self.open_page(self.editor_pane)
        self.show_editor()
        self.focus_list(self.editor_pane)

    def show_editor(self) -> None:
        if self.editor is not None:
            self.editor_pane.list.set_items(self.editor.rows())
            problem = self.editor.problem()
            if problem or self.editor_pane.status.text().startswith(("Give", "The name", "L2", "R2")):
                self.editor_pane.status.setText(problem)

    def editor_picked(self, key: str) -> None:
        """A on a row of the editor: its next value; on the name, the name's page."""
        if self.editor is None:
            return
        if key == "name":
            self.name_pane.heading.setText(f"Name of Fn + {self.editor.slot}")
            self.name_pane.field.setText(self.editor.name)
            self.name_pane.status.setText("")
            self.open_page(self.name_pane)
            self.name_pane.field.setFocus()
            return
        self.editor.step(key, 1)
        self.show_editor()

    def editor_back_step(self) -> None:
        """X on the editor: the focused row's value before."""
        key = self.editor_pane.list.focused()
        if self.editor is None or not key or key == "name":
            return
        self.editor.step(key, -1)
        self.show_editor()

    def take_name(self) -> None:
        """A on the name's page: the name taken, back to the editor."""
        if self.editor is None:
            return
        self.editor.set_name(self.name_pane.field.text())
        self.back_to_editor()

    def back_to_editor(self) -> None:
        self.name_pane.field.clear()
        self.open_page(self.editor_pane)
        self.show_editor()
        pill = self.editor_pane.list.pills.get("name")
        (pill or self.profiles_card).setFocus()

    def save_profile(self) -> None:
        """Y on the editor: backs up, writes the profile, reads it back (profiles.write checks it)."""
        editor, profile = self.editor, self.editing
        if editor is None or profile is None:
            return
        problem = editor.problem()
        if problem:
            self.editor_pane.status.setText(problem)
            return
        base = self.profiles[0] if editor.creating else profile
        try:
            parts = profiles.build(editor.settings(), base.reports, profiles.new_id() if editor.creating else None)
        except profiles.ProfileError as exc:
            self.editor_pane.status.setText(f"The profile cannot be saved: {exc}.")
            return
        said = self._change(lambda device: profiles.write(device, profile.slot, parts))
        if said:
            self.editor_pane.status.setText(said)
            return
        self.log.info(f"Profile {editor.name} saved in Fn + {profile.slot}.")
        self.leave_editor(f"{editor.name} is saved in Fn + {profile.slot}.")

    def leave_editor(self, said: str = "") -> None:
        self.editor, self.editing = None, None
        self.open_page(self.profiles_pane)
        self.show_profiles()
        self.profiles_pane.status.setText(said)
        self.focus_list(self.profiles_pane)

    def clear_profile(self) -> None:
        """X on a profile: cleared on a second press, after a backup."""
        profile = self.focused_profile()
        if not self._profile_ready(profile):
            return
        if profile.empty:
            self.profiles_pane.status.setText(f"Fn + {profile.slot} holds no profile: there is nothing to clear.")
            return
        if self.confirm != "clear" or self.confirm_data != (profile.slot,):
            self.confirm, self.confirm_data = "clear", (profile.slot,)
            self.confirm_timer.start()
            self.profiles_pane.status.setText(f"Press the X button again to remove {profile.name} from Fn + "
                                              f"{profile.slot}. The app saves a backup of the profiles first.")
            self.update_legend()
            return
        self._confirm_over()
        said = self._change(lambda device: profiles.clear(device, profile.slot))
        if not said:
            self.log.info(f"Profile {profile.name} cleared from Fn + {profile.slot}.")
        self.profiles_pane.status.setText(said or f"{profile.name} is removed from Fn + {profile.slot}.")

    def _change(self, action: Callable) -> str:
        """Backs up the profiles, changes one, and reads them again; what went wrong, or ""."""
        found = self.current()
        if found is None or found.bus != "usb" or self.updating:
            return "Plug in the USB cable to change the profiles."
        saved = ""
        try:
            with self.open_device(found.path, None) as device:
                saved = str(profiles.backup(profiles.read(device), profiles.backup_path(self.firmware_home),
                                            found.name, firmware.version_text(self.info.update) if self.info else ""))
                try:
                    action(device)
                finally:
                    self.profiles = profiles.read(device)
        except (OSError, ValueError, profiles.ProfileError) as exc:
            kept = f" The profiles from before are saved in {private(saved)}." if saved else ""
            self.log.error(f"Changing a profile failed: {_error(exc)}")
            self.show_profiles()
            return f"It did not work: {_error(exc)}.{kept}"
        self.show_profiles()
        return ""

    def save_backup(self) -> None:
        """Y on the Profiles pane: the profiles as the controller holds them, in a JSON file in the app's folder."""
        found = self.current()
        if found is None or not found.edge or not self.profiles:
            self.profiles_pane.status.setText("A DualSense Edge's profiles, once read, are what is backed up.")
            return
        try:
            path = profiles.backup(self.profiles, profiles.backup_path(self.firmware_home), found.name,
                                   firmware.version_text(self.info.update) if self.info else "")
        except OSError as exc:
            self.profiles_pane.status.setText(f"The backup could not be written: {_error(exc)}.")
            return
        self.profiles_pane.status.setText(f"The profiles are saved in {private(path)}.")

    def read_again(self) -> None:
        """LT on the Profiles pane: the firmware and the profiles read from the controller again."""
        if self._ready(self.profiles_pane.status) is None:
            return
        self.read_key = b""
        self.refresh()
        self.profiles_pane.status.setText(self.read_problem or "The profiles are read again.")

    # ------------------------------------------------------------- settings
    def show_settings(self) -> None:
        on = self.settings.get("check_at_start")
        self.settings_card.set_text(f"Check at start: {'On' if on else 'Off'}")
        self.settings_pane.summary.setText("The A button changes the setting the focus is on.")
        self.settings_pane.list.set_items([
            ("check", f"Check for an update when the app opens: {'On' if on else 'Off'}"),
            ("intro", "Show the introduction")])

    def setting_picked(self, key: str) -> None:
        if key == "check":
            self.settings.set("check_at_start", not self.settings.get("check_at_start"))
            self.show_settings()
        elif key == "intro":
            self.show_intro()

    # ------------------------------------------------------------- introduction
    def show_intro(self) -> None:
        found = self.current()
        self.intro_pane.start(found.edge if found else True)
        self.open_page(self.intro_pane)             # A on the Controller card goes through the pages (card_a)
        self.intro_open = True

    def intro_next(self) -> None:
        if self.intro_pane.last:
            self.finish_intro()
        else:
            self.intro_pane.go(self.intro_pane.index + 1)
            self.update_legend()

    def finish_intro(self) -> None:
        self.intro_open = False
        self.settings.set("intro_seen", True)
        self.open_page(self.controller_pane)

    def card_a(self, action: Callable[[], None]) -> None:
        """A on a card: the introduction's next page while it shows, else the card's own action."""
        if self.intro_open and self.panes.currentWidget() is self.intro_pane:
            self.intro_next()
        else:
            action()

    # ------------------------------------------------------------- panes and buttons
    def show_pane(self, pane: Pane) -> None:
        current = self.panes.currentWidget()
        if current is self.intro_pane and pane is not self.intro_pane and self.intro_open:
            self.intro_open = False
            self.settings.set("intro_seen", True)
        if self.testing and pane is not self.test_pane:
            self.end_test()
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def open_page(self, pane: Pane) -> None:
        """*pane* (or a page) shown, its card holding the focus first: a row hidden with the focus would hand it to
        another card, and that card's pane would show instead (Xenia Manager's settings tabs)."""
        card = self.cards[pane]
        if not card.hasFocus():
            card.setFocus()
        self.show_pane(pane)

    def focus_list(self, pane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows: its actions on the controller's buttons, A too, then core's Menu
        Info, B Back and View Exit. A press that cannot act now says why on the pane's status line."""
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        found = self.current()
        if pane is self.controller_pane:
            items = [("A", "Read again" if self.reading and found is not None else "Read")]
            if len(self.controllers) > 1:
                items += [("LB", "Controller before"), ("RB", "Next controller")]
        elif pane is self.intro_pane:
            items = [("A", "Start" if self.intro_pane.last else "Next"),
                     *([("X", "Page before")] if self.intro_pane.index else []), ("B", "Skip")]
            return [*items, EXIT]
        elif pane is self.test_pane:
            if self.testing:
                return [("X", "Test vibration"), ("Y", "Light bar"), ("B", "Hold: end the test"), EXIT]
            items = [("A", "Start the test"), ("X", "Test vibration"), ("Y", "Light bar")]
        elif pane is self.firmware_pane:
            if not self.updating:
                items = [("A", "Press again" if self.confirm == "update" else "Update"),
                         ("X", "Use a file"), ("Y", "Check for an update")]
        elif pane is self.profiles_pane:
            if found is not None and found.edge:
                profile = self.focused_profile()
                items = [("A", "Create" if profile is not None and profile.empty else "Edit"),
                         ("X", "Press again" if self.confirm == "clear" else "Clear"), ("Y", "Back up"),
                         ("LT", "Read again")]
        elif pane is self.settings_pane:
            items = [("A", "Change")]
        elif pane is self.editor_pane:
            items = [("A", "Next value"), ("X", "Value before"), ("Y", "Save to the controller")]
        elif pane is self.name_pane:
            items = [("A", "Take the name"), KEYBOARD]
        elif pane is self.browse_pane:
            items = [("A", "Open")]
        return [*items, *self.common_items(True if pane in self.pages else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def a_action(self) -> None:
        """A beside a card or a row (a text field, the pane itself)."""
        pane = self.panes.currentWidget()
        if pane is self.name_pane:
            self.take_name()
        elif pane is self.intro_pane:
            self.intro_next()

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.test_pane:
            self.test_vibration()
        elif pane is self.firmware_pane:
            self.show_browser()
        elif pane is self.profiles_pane:
            self.clear_profile()
        elif pane is self.editor_pane:
            self.editor_back_step()
        elif pane is self.intro_pane and self.intro_pane.index:
            self.intro_pane.go(self.intro_pane.index - 1)
            self.update_legend()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.test_pane:
            self.next_light()
        elif pane is self.firmware_pane:
            if self.updating:
                self.firmware_pane.status.setText("The update is running.")
            else:
                self.check_latest()
        elif pane is self.profiles_pane:
            self.save_backup()
        elif pane is self.editor_pane:
            self.save_profile()

    def lt_action(self) -> None:
        if self.panes.currentWidget() is self.profiles_pane:
            self.read_again()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        was, self.confirm, self.confirm_data = self.confirm, "", ()
        if was == "clear" and self.profiles_pane.status.text().startswith("Press the X button again"):
            self.profiles_pane.status.setText("")
        if was:
            self.show_state()

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): the introduction skipped, the name's page to the
        editor (the name not taken), the editor to the profiles (nothing saved), the browser a level up and from the
        places to the Firmware card, the test ended; a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if self.testing:
            self.end_test()
        elif pane is self.intro_pane:
            self.finish_intro()
        elif pane is self.name_pane:
            self.back_to_editor()
        elif pane is self.editor_pane:
            self.leave_editor("Nothing was saved.")
        elif pane is self.browse_pane:
            if self.browser is not None and self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
        else:
            self.go_back()

    def exit_app(self) -> None:
        """View: the app closes, but not while the firmware update runs (the BC250 app's rule)."""
        if self.updating:
            self.firmware_pane.status.setText("The update is still running: the app closes once it is done.")
            self.show_pane(self.firmware_pane)
            return
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.updating:
            event.ignore()
            return
        for timer in (self.status_timer, self.timer, self.input_timer, self.progress_timer, self.confirm_timer,
                      self.hold_timer):
            timer.stop()
        self._stop_reading()
        self._vibration_done()
        super().closeEvent(event)
