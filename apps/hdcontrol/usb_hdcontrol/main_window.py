# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the controller's state in the header (model, connection, battery, firmware, the latest firmware),
and below it one of three pages: Connect your controller while none is connected, the introduction after the first
one connects (once; Show the introduction brings it back), and the main page with the drawn controller, the
firmware update and, on the DualSense Edge, its four profiles as cards. Every second it looks in /sys for the
controllers; it reads a controller's firmware report and profiles once each time one appears. The update runs in
its own thread; the window shows how far it is."""

from __future__ import annotations

import dataclasses
import html
import math
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSocketNotifier, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractButton, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QGridLayout,
                             QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QSizePolicy,
                             QStackedWidget, QTabBar, QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.settings import restore_geometry, save_geometry
from bc250_core.theme import GREY, STATE_COLORS
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, StatusText, hint_label, same_width

from . import (APP_NAME, INFO, LOGO_PATH, __version__, controller, feedback, firmware, hidraw, idle, inputs, profiles,
               style, updater)
from .battery import BatteryIcon
from .controller import Controller, FirmwareInfo
from .drawing import ControllerView
from .editor import ProfileEditor
from .pages import Box, ConnectPage, InfoDialog, IntroPage, ProfileCard, Section, SoftPill
from .settings import ControlSettings

INTERVAL_MS = 1000
CHECK_AGE_S = 24 * 3600             # the window asks Sony's server again after a day
RETURN_S = 15.0                     # after an update the controller restarts: the main page waits this long for it
# The light bar's colors to choose from; Off saves the battery.
ON_BLUETOOTH = ("The controller is plugged in, but Linux kept its Bluetooth connection: the cable only charges it. Use "
                "the cable disconnects Bluetooth; then unplug the cable and plug it in again.")
CABLE_AGAIN = ("The controller is on the cable, but Linux did not take it while it was on Bluetooth. Unplug the "
               "cable and plug it in again.")
LIGHT_COLOURS = (("Blue", "#0050ff"), ("Red", "#ff2020"), ("Green", "#10d040"), ("Purple", "#a020f0"),
                 ("White", "#ffffff"), ("Off", "#000000"))
# The header's values, short so its boxes stay narrow; the full names are in their tooltips.
SHORT_NAMES = {0x0CE6: "DualSense", 0x0DF2: "Edge"}
SHORT_CONNECTIONS = {"usb": "USB", "bluetooth": "Bluetooth"}


def controller_label(found: Controller) -> str:
    """A controller's tab, shown with two or more connected (owner, 23-10-2026): its player number first (the one its
    lights show), then model, connection and battery, so all of them show at a glance."""
    number = controller.player_number(found)
    parts = [f"Player {number}"] if number else []
    parts += [SHORT_NAMES[found.product], SHORT_CONNECTIONS.get(found.bus, found.bus)]
    if found.battery is not None and found.battery.capacity is not None:
        parts.append(f"{found.battery.capacity} %")
    return " · ".join(parts)


def _job(function: Callable, *args) -> Callable[[], object]:
    """A job for UpdateChecker: its result, or the error it raised (a thread must not raise)."""
    def run():
        try:
            return function(*args)
        except (firmware.FirmwareError, updater.UpdateError, OSError, ValueError) as exc:
            return exc
    return run


class FitText(QLabel):
    """Wrapped text that keeps the height of all its lines: in the Firmware box the layout would cut the last ones
    off (the SHA-256 line, 23-10-2026)."""

    def _fit(self) -> None:
        height = self.heightForWidth(max(1, self.width()))
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        super().setText(text)
        self._fit()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._fit()


def _error(exc: Exception) -> str:
    return (exc.strerror or str(exc)) if isinstance(exc, OSError) else str(exc)


class MainWindow(QWidget):
    def __init__(self, sys_root: Path = controller.SYS, dev: Path = controller.DEV, proc: Path = controller.PROC,
                 open_device: Callable[[Path, dict[int, int]], hidraw.Device] = hidraw.Device,
                 firmware_home: Path | None = None, get: firmware.Get | None = None,
                 update: Callable[..., None] = updater.update, clock: Callable[[], float] = time.time,
                 writable: Callable[[Path], bool] = controller.writable,
                 open_reader: Callable[[Path], inputs.Reader] = inputs.Reader,
                 disconnect: Callable[[str], str] = controller.disconnect_bluetooth,
                 open_rumble: Callable[[Path], feedback.Rumble] = feedback.Rumble,
                 set_lightbar: Callable[..., None] = feedback.set_lightbar,
                 monotonic: Callable[[], float] = time.monotonic, idle_state: Path | None = None):
        super().__init__()
        self.monotonic = monotonic          # the idle service's clock, for its countdown
        self.idle_state = idle_state or idle.state_path()
        self.rate_mark: tuple[int, float] | None = None     # the reader's count and when, for the report rate
        self.setWindowTitle(APP_NAME)
        self.settings = ControlSettings(INFO, self)
        self.sys_root = sys_root
        self.dev = dev
        self.proc = proc
        self.open_device = open_device
        self.firmware_home = firmware_home
        self.get = get or firmware._get
        self.update = update
        self.clock = clock
        self.writable = writable
        self.open_reader = open_reader
        self.disconnect = disconnect
        self.held: list[int] = []           # controllers on the cable that no driver took (still on Bluetooth)
        self.file_checks: dict[Path, tuple[int, str, bool]] = {}    # kept file -> (mtime, SHA-256, known)
        self.open_rumble = open_rumble
        self.set_lightbar = set_lightbar
        self.reader: inputs.Reader | None = None
        self.reader_node = ""               # the hidraw node being read for the drawing
        self.notifier: QSocketNotifier | None = None
        self.rumble: feedback.Rumble | None = None
        self.light_sequence = 0             # Bluetooth output reports count up
        self.controllers: list[Controller] = []
        self.chosen = ""                    # the node of the controller the window shows
        self.read_key = ""                  # the controller (its /sys device) whose reports were read
        self.info: FirmwareInfo | None = None
        self.read_problem = ""
        self.profiles: list[profiles.Profile] = []
        self.progress: updater.Progress | None = None
        self.updating = False
        self.update_target = 0              # the version the running or last update sends
        self.returning_until = 0.0          # after an update: until then a missing controller is restarting
        self.intro_open = False
        self.chosen_slot = ""               # the profile card the user clicked: the drawing lights what it sets
        self.active_slot = ""               # the Edge's profile in use, from its input reports

        layout = QVBoxLayout(self)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText("Looking for a controller")
        header.add_state(self.badge)
        self.controller_box = Box("Controller")
        self.connection_box = Box("Connection")
        # The firmware in two (owner, 23-10-2026): what the controller runs, and Sony's latest, a pill that turns
        # orange and starts the update when one can start, and otherwise asks Sony's server again.
        self.installed_box = Box("Installed firmware")
        self.latest_pill = SoftPill("—", "Latest firmware")
        self.latest_pill.clicked.connect(self.firmware_clicked)
        # Live, after the firmware (owner, 23-10-2026): input reports a second, and the idle switch-off's countdown.
        self.rate_pill = Box("Reports")
        self.off_pill = Box("Bluetooth off in")
        boxes = [self.controller_box, self.connection_box, self.installed_box, self.latest_pill, self.rate_pill,
                 self.off_pill]
        for box in boxes:
            header.add_second(box)
        # Every box as wide as "Bluetooth" needs, so that none changes width when the connection does.
        self.connection_box.value.ensurePolished()
        self.connection_box.value.setMinimumWidth(self.connection_box.value.fontMetrics().horizontalAdvance(
            SHORT_CONNECTIONS["bluetooth"]))
        same_width(boxes)
        header.add_second(QWidget(), 1)     # the boxes stay together on the left
        # The battery stands beside both rows at the right end, its top level with the title (owner, 23-10-2026).
        self.battery_icon = BatteryIcon()
        header.addWidget(self.battery_icon)
        layout.addLayout(header)

        firmware_group = Section("Firmware")
        firmware_layout = firmware_group.body
        # One sentence a line, then a blank line, the controller's lines, a blank line and the buttons
        # (owner, 23-10-2026).
        firmware_layout.addWidget(hint_label(
            "Controller updates are offered officially on a PS5 and in an app for Windows.\n"
            "This app sends the same firmware from the official server, over a USB cable.\n"
            "The controller checks the firmware's signature before it takes it."))
        firmware_layout.addSpacing(self.fontMetrics().lineSpacing())
        self.firmware_text = FitText()
        self.firmware_text.setWordWrap(True)
        self.firmware_text.setTextFormat(Qt.TextFormat.RichText)
        self.firmware_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        firmware_layout.addWidget(self.firmware_text)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.check_button = QPushButton("Check for an update")
        self.check_button.setToolTip(f"Asks {firmware.SOURCE} for the latest firmware of each controller.")
        self.check_button.clicked.connect(self.check_latest)
        self.file_button = QPushButton("Use a file…")
        self.file_button.setToolTip("Sends a firmware file you have (FWUPDATE<target>.bin), for example one saved "
                                    "from the official server before.")
        self.file_button.clicked.connect(self.use_file)
        self.check_at_start = QCheckBox("Check when the window opens")
        self.check_at_start.setToolTip("Asks the official update server for the latest firmware when the window opens, "
                                       "at most once a day.")
        self.check_at_start.setChecked(self.settings.get("check_at_start"))
        self.check_at_start.toggled.connect(lambda on: self.settings.set("check_at_start", on))
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.file_button)
        self.cable_button = QPushButton("Use the cable")
        self.cable_button.setToolTip("Disconnects the controller from Bluetooth, so that Linux can take the cable once "
                                     "it is plugged in again.")
        self.cable_button.clicked.connect(self.use_cable)
        buttons.addWidget(self.cable_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.check_at_start)
        buttons.addStretch(1)
        firmware_layout.addSpacing(self.fontMetrics().lineSpacing())
        firmware_layout.addLayout(buttons)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setVisible(False)
        self.progress_text = QLabel()
        self.progress_text.setWordWrap(True)
        firmware_layout.addWidget(self.progress_bar)
        firmware_layout.addWidget(self.progress_text)

        profile_group = Section("Profiles")
        profile_layout = profile_group.body
        self.profile_text = hint_label("")
        profile_layout.addWidget(self.profile_text)
        self.cards_row = QWidget()
        cards = QHBoxLayout(self.cards_row)
        cards.setContentsMargins(0, 0, 0, 0)
        self.cards = [ProfileCard() for _slot in profiles.SLOTS]
        for card in self.cards:
            card.clicked.connect(self.choose_profile)
            card.create.connect(self.create_profile)
            card.edit.connect(self.edit_profile)
            card.clear.connect(self.clear_profile)
            cards.addWidget(card, 1)
        profile_layout.addWidget(self.cards_row, 1)
        profile_buttons = QHBoxLayout()
        profile_buttons.setSpacing(6)
        self.backup_button = QPushButton("Back up…")
        self.backup_button.setToolTip("Saves the profiles as the controller holds them, in a JSON file.")
        self.backup_button.clicked.connect(self.save_backup)
        self.reread_button = QPushButton("Read again")
        self.reread_button.setToolTip("Reads the firmware and the profiles from the controller again, for example "
                                      "after you changed them on a PS5.")
        self.reread_button.clicked.connect(self.read_again)
        self.intro_button = QPushButton("Show the introduction")
        self.intro_button.setToolTip("The three pages shown after the first controller connected.")
        self.intro_button.clicked.connect(self.show_intro)
        profile_buttons.addWidget(self.backup_button)
        profile_buttons.addWidget(self.reread_button)
        profile_buttons.addStretch(1)
        profile_buttons.addWidget(self.intro_button)
        profile_layout.addLayout(profile_buttons)

        self.main_page = QWidget()
        main = QVBoxLayout(self.main_page)
        main.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(self._controller_box(), 1)     # the two boxes equally wide (owner, 23-10-2026)
        top.addWidget(firmware_group, 1)
        main.addLayout(top)
        main.addWidget(profile_group, 1)
        self.connect_page = ConnectPage()
        self.intro_page = IntroPage()
        self.intro_page.finished.connect(self.finish_intro)
        self.stack = QStackedWidget()
        for page in (self.connect_page, self.intro_page, self.main_page):
            self.stack.addWidget(page)
        self.controller_tabs = QTabBar()        # a tab per controller, with two or more connected
        self.controller_tabs.setExpanding(False)
        self.controller_tabs.setUsesScrollButtons(False)   # a few controllers at most: nothing to scroll
        self.controller_tabs.setStyleSheet("QTabBar::tab { font-size:15px; font-weight:600; padding:7px 18px; }")
        for arrow in self.controller_tabs.findChildren(QAbstractButton):    # Qt makes them all the same
            arrow.setToolTip("More controllers: scroll the tabs.")
        self.controller_tabs.setToolTip("More than one controller is connected: the window shows the chosen one.")
        self.controller_tabs.currentChanged.connect(self.choose)
        layout.addWidget(self.controller_tabs)
        layout.addWidget(self.stack, 1)

        self.check_job = UpdateChecker(self)
        self.check_job.finished.connect(self._check_done)
        self.update_job = UpdateChecker(self)
        self.update_job.finished.connect(self._update_done)

        self.timer = QTimer(self, interval=INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        if not restore_geometry(self, self.settings.qsettings):
            self.resize(1000, 720)
        self.refresh()
        # The window keeps the focus at start: a focused pill draws the blue focus border over its state's color,
        # which hid the orange of a waiting update.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        if self.settings.get("check_at_start") and self._check_is_old():
            self.check_latest()

    def _controller_box(self) -> Section:
        """The drawing, live, on the left with the light bar's colors under it; on its right the light bar's
        color now, what the drawing does and the vibration test (owner, 23-10-2026)."""
        box = Section("Controller")
        layout = QGridLayout()
        box.body.addLayout(layout)
        self.view = ControllerView()
        self.view.setMinimumSize(250, 200)       # small enough for the two top boxes to share the width equally
        self.view.setMaximumWidth(400)
        layout.addWidget(self.view, 0, 0)
        # The spec sheet, top left by the drawing (owner, 23-10-2026).
        self.info_button = QPushButton("i")
        self.info_button.setFixedSize(26, 26)
        self.info_button.setToolTip("The controller's specifications: what it reports now, the model's facts with "
                                    "their sources, and the parts the drawing leaves out.")
        self.info_button.setStyleSheet(f"QPushButton {{ border:1px solid {style.EDGE}; border-radius:13px; "
                                       "font-weight:800; font-style:italic; font-family:serif; padding:0; }")
        self.info_button.clicked.connect(self.show_info)
        layout.addWidget(self.info_button, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # The colors from the drawn controller's left edge to its right, spread out (owner, 23-10-2026): the
        # row's margins follow the drawing as it is resized.
        self.lights_row = QWidget()
        lights = QHBoxLayout(self.lights_row)
        lights.setSpacing(6)                # a section's style sheet leaves no spacing of its own
        self.light_buttons: list[QPushButton] = []
        for name, colour in LIGHT_COLOURS:
            button = QPushButton()
            button.setFixedSize(26, 26)
            button.setToolTip("Light bar off: saves some battery." if name == "Off" else f"Light bar {name.lower()}.")
            button.setStyleSheet(f"QPushButton {{ background:{colour}; border:1px solid palette(mid); "
                                 "border-radius:13px; }")
            button.clicked.connect(lambda _c, colour=colour: self.choose_light(colour))
            lights.addWidget(button)
            lights.addStretch(1)
            self.light_buttons.append(button)
        # Any color: a color wheel, round like the others, so all seven fit across the drawing.
        self.other_light = QPushButton()
        self.other_light.setFixedSize(26, 26)
        self.other_light.setStyleSheet(
            "QPushButton { border:1px solid palette(mid); border-radius:13px; background:qconicalgradient(cx:0.5, "
            "cy:0.5, angle:0, stop:0 #ff0000, stop:0.17 #ffff00, stop:0.33 #00ff00, stop:0.5 #00ffff, "
            "stop:0.67 #0000ff, stop:0.83 #ff00ff, stop:1 #ff0000); }")
        self.other_light.setToolTip("Light bar in any color you choose.")
        self.other_light.clicked.connect(self.pick_light)
        lights.addWidget(self.other_light)
        # Its margins must not widen the box: the row takes the drawing's width, not the other way round.
        self.lights_row.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.lights_row, 1, 0)
        # After the layout has settled: the drawing is resized before the row it lines up.
        self.view.resized.connect(lambda: QTimer.singleShot(0, self._align_lights))
        side = QVBoxLayout()
        light_row = QHBoxLayout()
        light_row.setSpacing(6)
        light_row.addWidget(QLabel("Light bar"))
        self.light_chip = QLabel()
        self.light_chip.setToolTip("The color the app gives the light bar, chosen under the drawing. The app sets it "
                                   "at once and again each time the controller connects while the app is open; the "
                                   "controller forgets it when it disconnects.")
        self.light_chip.setFixedSize(16, 16)
        light_row.addWidget(self.light_chip)
        self.light_name = QLabel()
        light_row.addWidget(self.light_name)
        light_row.addStretch(1)
        side.addLayout(light_row)
        self.controller_text = hint_label("Press a button or move a stick: the drawing follows.")
        side.addWidget(self.controller_text)
        self.vibrate_button = QPushButton("Test vibration")
        self.vibrate_button.setToolTip("Runs the left motor, then the right one, almost a second each: you should "
                                       "feel each on its own side.")
        self.vibrate_button.clicked.connect(self.test_vibration)
        self.off_button = QPushButton("Turn Bluetooth off")
        self.off_button.setToolTip("Switches the controller off by ending its Bluetooth connection; press the PS "
                                   "button to switch it on again. On the USB cable it stays on: the cable powers it.")
        self.off_button.clicked.connect(self.turn_off)
        self.idle_combo = QComboBox()
        for minutes in idle.CHOICES:
            self.idle_combo.addItem(f"after {minutes} min" if minutes else "Never", minutes)
        self.idle_combo.setCurrentIndex(max(0, self.idle_combo.findData(self.settings.get("idle_minutes"))))
        self.idle_combo.setToolTip("Switches a controller on Bluetooth off when no button, stick or trigger was used "
                                   "this long, as a PS5 does; on the USB cable it stays on, and while a game started "
                                   "from Steam runs. A small service that install.sh adds does it, also with the "
                                   "window closed.")
        self.idle_combo.currentIndexChanged.connect(
            lambda _index: self.settings.set("idle_minutes", self.idle_combo.currentData()))
        # The two buttons and the choice equally wide, spread down the column (owner, 23-10-2026).
        controls = (self.vibrate_button, self.off_button, self.idle_combo)
        width = max(widget.sizeHint().width() for widget in controls) + 16
        for widget in controls:
            widget.setFixedWidth(width)
        idle_box = QVBoxLayout()
        idle_box.setSpacing(4)
        idle_box.addWidget(QLabel("Switch Bluetooth off when unused:"))
        idle_box.addWidget(self.idle_combo, 0, Qt.AlignmentFlag.AlignLeft)
        side.addStretch(1)
        side.addWidget(self.vibrate_button, 0, Qt.AlignmentFlag.AlignLeft)
        side.addStretch(1)
        side.addWidget(self.off_button, 0, Qt.AlignmentFlag.AlignLeft)
        side.addStretch(1)
        side.addLayout(idle_box)
        side.addStretch(1)
        layout.addLayout(side, 0, 1, 2, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)
        return box

    def _align_lights(self) -> None:
        """The color row's margins: from where the drawn body starts to where it ends, within the drawing."""
        left, right = self.view.body_span()
        offset = self.view.x() - self.lights_row.x()
        self.lights_row.layout().setContentsMargins(max(0, round(offset + left)), 0,
                                                    max(0, round(self.lights_row.width() - offset - right)), 0)

    # ------------------------------------------------------------------ state
    def current(self) -> Controller | None:
        for found in self.controllers:
            if found.node == self.chosen:
                return found
        return self.controllers[0] if self.controllers else None

    def latest(self) -> int | None:
        return self.settings.latest().get(self.info.target) if self.info else None

    def refresh(self) -> None:
        self.controllers = controller.find(self.sys_root)
        self.held = controller.held_back(self.sys_root)
        found = self.current()
        self.chosen = found.node if found else ""
        key = str(found.sys_path.resolve()) if found else ""
        if key != self.read_key and not self.updating:
            self.read_key = key
            self._read(found)
        if found is not None and not self.settings.get("intro_seen") and not self.intro_open:
            self.show_intro()
        self.show_state()

    # ------------------------------------------------------------------ pages
    def show_intro(self) -> None:
        found = self.current()
        self.intro_open = True
        self.intro_page.start(found.edge if found else True)
        self.show_state()

    def finish_intro(self) -> None:
        self.intro_open = False
        self.settings.set("intro_seen", True)
        self.show_state()

    def _show_page(self, found: Controller | None) -> None:
        """Connect while there is no controller (but not while an update runs or the controller restarts after
        it), the introduction while it is open, else the main page."""
        if found is None and not self.updating and self.clock() >= self.returning_until:
            page = self.connect_page
        elif self.intro_open and found is not None:
            page = self.intro_page
        else:
            page = self.main_page
        if self.stack.currentWidget() is not page:
            self.stack.setCurrentWidget(page)

    def _show_tabs(self) -> None:
        """The tabs follow the controllers; rebuilt only when one comes, goes or its text changes."""
        tabs = self.controller_tabs
        wanted = [(controller_label(each), each.node) for each in self.controllers]
        tabs.setVisible(len(wanted) > 1)
        tabs.blockSignals(True)
        if wanted != [(tabs.tabText(i), tabs.tabData(i)) for i in range(tabs.count())]:
            while tabs.count():
                tabs.removeTab(0)
            for text, node in wanted:
                tabs.setTabData(tabs.addTab(text), node)
        for index in range(tabs.count()):
            if tabs.tabData(index) == self.chosen:
                tabs.setCurrentIndex(index)
        tabs.blockSignals(False)

    def choose(self, index: int) -> None:
        self.chosen = self.controller_tabs.tabData(index) or "" if index >= 0 else ""
        self.refresh()

    def read_again(self) -> None:
        self.read_key = ""
        self.refresh()

    def _read(self, found: Controller | None) -> None:
        """The firmware report and the profiles, once per controller: they do not change while it is connected."""
        self.info, self.profiles, self.read_problem = None, [], ""
        if found is None:
            return
        if not self.writable(found.path(self.dev)):
            self.read_problem = (f"Your user may not use {found.path(self.dev)}. Bazzite gives it to the user at the "
                                 "board; on another system, a udev rule with TAG+=\"uaccess\" for the controller "
                                 "does it.")
            return
        try:
            with self.open_device(found.path(self.dev), found.sizes()) as device:
                self.info = controller.read_info(device)
                if found.edge:
                    self.profiles = profiles.read(device)
        except (OSError, ValueError) as exc:
            self.read_problem = f"The controller could not be read: {_error(exc)}."
            return
        if feedback.parse_colour(self.settings.get("lightbar")):
            self.apply_light(found, quiet=True)

    def show_state(self) -> None:
        found = self.current()
        latest = self.latest()
        self._show_tabs()

        if self.updating:
            state = ("Updating the firmware", "info", "Leave the controller plugged in until the update is done.")
        elif found is None and self.held:
            state = ("Plug the cable in again", "warn", CABLE_AGAIN)
        elif found is None:
            state = ("No controller", "neutral", controller.NOT_FOUND)
        elif found.bus == "bluetooth" and self.held:
            state = ("On Bluetooth, not the cable", "warn", ON_BLUETOOTH)
        elif self.read_problem:
            state = ("Cannot be read", "warn", self.read_problem)
        elif self.info is not None and latest is not None and latest > self.info.update:
            state = ("Update available", "warn", f"Firmware {firmware.version_text(latest)} is out; the controller "
                                                 f"runs {firmware.version_text(self.info.update)}.")
        elif self.info is not None and latest is not None:
            state = ("Up to date", "ok", "The controller runs the latest official firmware.")
        else:
            state = ("Ready", "ok", "Check for an update asks the official update server for the latest firmware.")
        self.badge.set_status(*state)

        self.controller_box.set_value(SHORT_NAMES[found.product] if found else "—", found.name if found else "")
        update_waits = self.info is not None and latest is not None and latest > self.info.update
        self.connection_box.set_value(SHORT_CONNECTIONS.get(found.bus, found.bus) if found else "—",
                                      found.connection + (": the firmware update needs the USB cable."
                                                          if found.bus != "usb" and update_waits else ".")
                                      if found else "")
        self._show_battery(found)
        self._show_pills(found)
        self._show_firmware(found, latest)
        self._show_profiles(found)
        self._show_update(found, latest)
        self.check_button.setEnabled(not self.check_job.running)
        self.cable_button.setVisible(found is not None and found.bus == "bluetooth" and bool(self.held))
        self.connect_page.set_held(bool(self.held))
        self.file_button.setEnabled(found is not None and self.info is not None and found.bus == "usb"
                                    and not self.updating)
        self._show_progress()
        self._show_page(found)
        self._show_controls(found)

    # ------------------------------------------------------------- live input
    def _show_controls(self, found: Controller | None) -> None:
        """The drawing follows the controller while the main page shows it; the controls need one that may be
        written to, and rest while an update runs."""
        live = (found is not None and not self.updating and not self.read_problem
                and self.stack.currentWidget() is self.main_page)
        self._follow(found.node if live else "")
        self.view.set_players(controller.player_lights(found) if found is not None else None)
        ready = found is not None and not self.updating and not self.read_problem
        for button in (*self.light_buttons, self.other_light):
            button.setEnabled(ready)
        self.vibrate_button.setEnabled(ready and self.rumble is None and controller.event_node(found, self.dev)
                                       is not None)
        self.off_button.setEnabled(found is not None and found.bus == "bluetooth" and not self.updating)
        self.info_button.setEnabled(found is not None)
        chosen = self.settings.get("lightbar")
        colour = feedback.parse_colour(chosen)
        self.view.set_light(QColor(*colour) if colour and found is not None else None)
        names = {value: name for name, value in LIGHT_COLOURS}
        self.light_name.setText(names.get(chosen, chosen) if colour else "as the system sets it")
        self.light_chip.setStyleSheet(f"background:{chosen}; border:1px solid palette(mid); border-radius:8px;"
                                      if colour else "border:1px dashed palette(mid); border-radius:8px;")

    def _follow(self, node: str) -> None:
        """Reads the input reports of *node* (a hidraw node's name), or stops with ""."""
        if node == self.reader_node:
            return
        self._stop_reading()
        if not node:
            return
        try:
            self.reader = self.open_reader(self.dev / node)
        except OSError:
            return
        self.reader_node = node
        self.notifier = QSocketNotifier(self.reader.fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._input_ready)

    def _input_ready(self, *_args) -> None:
        if self.reader is None:
            return
        try:
            reading = self.reader.read()
        except OSError:                     # the controller left; the next refresh notices
            self._stop_reading()
            return
        if reading is not None:
            self.view.show_input(set(reading.pressed), reading.sticks, reading.triggers)
            if reading.profile != self.active_slot:
                self.active_slot = reading.profile
                self._show_profiles(self.current())

    def _show_pills(self, found: Controller | None) -> None:
        """The header's live pills: how many input reports a second come in, and how long until the idle service
        switches a controller on Bluetooth off."""
        now = self.monotonic()
        if self.reader is not None:
            if self.rate_mark is not None and now - self.rate_mark[1] >= 0.5:
                rate = (self.reader.count - self.rate_mark[0]) / (now - self.rate_mark[1])
                self.rate_pill.set_value(f"{rate:.0f} Hz", "Input reports a second from the controller now: "
                                         "steady and high is a good connection.")
                self.rate_mark = (self.reader.count, now)
            elif self.rate_mark is None:
                self.rate_mark = (self.reader.count, now)
        else:
            self.rate_mark = None
            self.rate_pill.set_value("—", "Input reports a second, while the drawing reads the controller.")
        self.off_pill.set_value(*self._off_in(found, now))

    def _off_in(self, found: Controller | None, now: float) -> tuple[str, str]:
        if found is None:
            return "—", "How long until an unused controller on Bluetooth is switched off."
        if found.bus != "bluetooth":
            return "Cable", "On the USB cable it stays on: the cable powers it."
        minutes = self.settings.get("idle_minutes")
        if not minutes:
            return "Never", "Switch Bluetooth off when unused is set to Never."
        last = idle.read_state(self.idle_state).get(found.node)
        if last is None:
            return "—", ("The service that switches unused controllers off is not running: install.sh adds it.")
        left = last + minutes * 60 - now
        text = f"{math.ceil(left / 60)} min" if left >= 60 else f"{max(0, round(left))} s"
        return text, f"Switched off after {minutes} minutes unused; any button, stick or trigger starts it over."

    def _stop_reading(self) -> None:
        if self.notifier is not None:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.reader_node = ""
        self.view.clear_input()
        if self.active_slot:
            self.active_slot = ""
            self._show_profiles(self.current())

    def turn_off(self) -> None:
        """A controller over Bluetooth switches itself off when the connection ends, as Steam's Turn off does."""
        found = self.current()
        address = controller.bluetooth_address(found) if found else ""
        if not address:
            return
        problem = self.disconnect(address)
        if problem:
            QMessageBox.warning(self, window_title("Turn Bluetooth off"), f"{problem} Hold the PS button for 10 s "
                                "to switch the controller off.")
            return
        self.refresh()

    def info_rows(self, found: Controller) -> list[tuple[str, str]]:
        """What the controller reports now, for the spec sheet; never its address or serial number."""
        rows = [("Model", found.name), ("Connection", found.connection)]
        if self.info is not None:
            rows += [("Installed firmware", f"{firmware.version_text(self.info.update)}, built "
                                            f"{self.info.build_date} {self.info.build_time}"),
                     ("Firmware target", f"{self.info.target:04X}"),
                     ("Hardware version", f"0x{self.info.hardware:08x}"),
                     ("Firmware build", f"0x{self.info.firmware:08x}")]
        if found.battery is not None and found.battery.capacity is not None:
            rows.append(("Battery", f"{found.battery.capacity} %, {found.battery.status.lower()}"))
        return rows

    def show_info(self) -> None:
        found = self.current()
        if found is None:
            return
        InfoDialog(found.name, self.info_rows(found), found.product, self).exec()

    def use_cable(self) -> None:
        """Drops the Bluetooth connection; the kernel takes the cable only when it is plugged in again."""
        found = self.current()
        address = controller.bluetooth_address(found) if found else ""
        if not address:
            return
        problem = self.disconnect(address)
        if problem:
            QMessageBox.warning(self, window_title("Use the cable"), f"{problem} Switch the controller off (hold the "
                                "PS button for 10 s), then unplug the cable and plug it in again.")
            return
        self.refresh()

    # ---------------------------------------------------------- light, rumble
    def choose_light(self, colour: str) -> None:
        self.settings.set("lightbar", colour)
        found = self.current()
        if found is not None:
            self.apply_light(found)
        self.show_state()

    def pick_light(self) -> None:
        start = QColor(self.settings.get("lightbar") or "#0050ff")
        colour = QColorDialog.getColor(start, self, window_title("Light bar"))
        if colour.isValid():
            self.choose_light(colour.name())

    def apply_light(self, found: Controller, quiet: bool = False) -> None:
        rgb = feedback.parse_colour(self.settings.get("lightbar"))
        if rgb is None:
            return
        self.light_sequence = (self.light_sequence + 1) % 16
        try:
            self.set_lightbar(found.path(self.dev), found.bus, rgb, self.light_sequence)
        except OSError as exc:
            if not quiet:
                self.controller_text.setText(f"The light bar could not be set: {_error(exc)}.")
            return
        if not quiet:
            self.controller_text.setText("The light bar keeps this color until the controller disconnects, or "
                                         "Steam or a game sets another. The app sets it again when the controller "
                                         "connects while the app is open.")

    def test_vibration(self) -> None:
        found = self.current()
        event = controller.event_node(found, self.dev) if found else None
        if event is None or self.rumble is not None:
            return
        try:
            self.rumble = self.open_rumble(event)
        except OSError as exc:
            self.controller_text.setText(f"The motors could not be reached: {_error(exc)}.")
            return
        self.controller_text.setText("The left motor, then the right one: you should feel each on its own side.")
        for when, side, strong, weak in feedback.VIBRATION_STEPS:
            QTimer.singleShot(when, lambda side=side, strong=strong, weak=weak: self._vibrate(side, strong, weak))
        QTimer.singleShot(feedback.VIBRATION_STEPS[-1][0] + 50, self._vibration_done)
        self.show_state()

    def _vibrate(self, side: str, strong: int, weak: int) -> None:
        if self.rumble is None:
            return
        self.view.shake(side)
        if strong or weak:
            try:
                self.rumble.play(strong, weak)
            except OSError as exc:
                self.controller_text.setText(f"The motors could not be started: {_error(exc)}.")
                self._vibration_done()

    def _vibration_done(self) -> None:
        self.view.shake("")
        if self.rumble is not None:
            self.rumble.close()
            self.rumble = None
        self.show_state()

    def _show_update(self, found: Controller | None, latest: int | None) -> None:
        """The Latest firmware pill: Sony's latest version, orange when an update can start (a click starts it),
        otherwise gray, and a click asks Sony's server again. It stays clickable while there is a controller, so it
        is not grayed while the controller is up to date."""
        can = self._can_update(found, latest)
        self.latest_pill.set_value(firmware.version_text(latest) if latest is not None and found is not None else "—")
        self.latest_pill.set_colour(STATE_COLORS["warn"] if can else GREY)
        self.latest_pill.setEnabled(found is not None and self.info is not None and not self.updating)
        if self.updating:
            tip = "The update is running."
        elif can:
            tip = (f"Click to update to firmware {firmware.version_text(latest)}; it asks first. The update takes "
                   "about half a minute.")
        elif found is None or self.info is None:
            tip = "No controller."
        elif latest is not None and latest > self.info.update and found.bus != "usb":
            tip = (f"Firmware {firmware.version_text(latest)} is out. The update needs the USB cable. Click to ask "
                   "the update server again.")
        elif latest is None:
            tip = "The latest version is not known yet. Click to ask the update server."
        else:
            tip = "The controller runs the latest official firmware. Click to ask the update server again."
        self.latest_pill.setToolTip(f"{tip} {self._checked_text()}.")

    def firmware_clicked(self) -> None:
        """Starts the update when one can start; otherwise asks Sony's server for the latest version again."""
        if self._can_update(self.current(), self.latest()):
            self.start_update()
        else:
            self.check_latest()

    def _show_battery(self, found: Controller | None) -> None:
        battery = found.battery if found else None
        self.battery_icon.set_battery(battery.capacity if battery else None, battery.status if battery else "")

    def _show_firmware(self, found: Controller | None, latest: int | None) -> None:
        info = self.info
        if found is None or info is None:
            self.installed_box.set_value("—")
            self.installed_box.set_colour(GREY)
            self.firmware_text.setText(html.escape(self.read_problem) if found else
                                       html.escape(f"No controller found. {controller.NOT_FOUND}"))
            return
        self.installed_box.set_value(firmware.version_text(info.update), f"Built {info.build_date} {info.build_time}")
        newer = latest is not None and latest > info.update
        self.installed_box.set_colour(STATE_COLORS["warn"] if newer else STATE_COLORS["ok"] if latest else GREY)
        lines = [f"<b>{html.escape(found.name)}:</b>",
                 # Its target, hardware version and build are in the spec sheet (i): here one line each.
                 f"firmware {firmware.version_text(info.update)}, built {html.escape(info.build_date)} "
                 f"{html.escape(info.build_time)}."]
        if latest is None:
            lines.append("The latest version is not known yet: Check for an update asks the official update server.")
        elif newer:
            stored = firmware.read(info.target, latest, self.firmware_home) is not None
            lines.append(f"Firmware {firmware.version_text(latest)} is out. "
                         + ("It is downloaded already." if stored else
                            "A click on Latest firmware downloads it (about 1 MB) and sends it."))
        else:
            lines.append(f"It is the latest official firmware ({self._checked_text().lower()}).")
        if latest is not None:
            lines.append(self._file_check(info.target, latest))
        if found.bus == "bluetooth" and self.held:
            lines.append(html.escape(ON_BLUETOOTH))
        elif found.bus != "usb" and newer:     # only then: on the latest firmware it would only confuse (owner)
            lines.append("The update needs the USB cable: connect the controller with it.")
        self.firmware_text.setText("<br>".join(lines))

    def _file_check(self, target: int, version: int) -> str:
        """The kept file of *version* and its SHA-256 check, as USB HD Cam shows its firmware's (owner, 23-10-2026):
        green for a file the app knows, orange for one it does not. Hashed once per file, not every second."""
        where = firmware.path(target, version, self.firmware_home)
        try:
            stamp = where.stat().st_mtime_ns
        except OSError:
            return ""
        if self.file_checks.get(where) is None or self.file_checks[where][0] != stamp:
            data = firmware.read(target, version, self.firmware_home) or b""
            self.file_checks[where] = (stamp, firmware.sha256(data), firmware.known(data) is not None)
        _stamp, digest, known = self.file_checks[where]
        check = (f"SHA-256 checked: it is the known file {firmware.version_text(version)}." if known else
                 "SHA-256 checked: not a file the app knows. The controller still checks its signature.")
        colour = STATE_COLORS["ok" if known else "warn"]
        return (f"{html.escape(where.name)}: <span style='color:{colour}'>{'✓' if known else '!'} {check}</span><br>"
                f"SHA-256 <code style='font-size:10px'>{digest}</code>")

    def _checked_text(self) -> str:
        checked = self.settings.get("checked")
        return f"Checked {checked}" if checked else "Not checked yet"

    def _check_is_old(self) -> bool:
        checked = self.settings.get("checked")
        try:
            return self.clock() - time.mktime(time.strptime(checked, "%Y-%m-%d %H:%M")) > CHECK_AGE_S
        except ValueError:
            return True

    def _show_profiles(self, found: Controller | None) -> None:
        edge = found is not None and found.edge
        if found is None:
            self.profile_text.setText("The DualSense Edge's profiles show here.")
        elif not edge:
            self.profile_text.setText(f"The {found.name} has no profiles: only the DualSense Edge has them.")
        else:
            self.profile_text.setText("The four profiles stored in the controller, as it reports them: hold Fn and "
                                      "press the button to switch. Click one to see on the drawing what it sets. "
                                      "Create…, Edit… and Clear change them over the USB cable; the default "
                                      "profile stays as it is.")
        shown = self.profiles if edge else []
        self.cards_row.setVisible(bool(shown))
        allowed = found is not None and found.bus == "usb" and not self.updating
        reason = ("Wait until the firmware update is done." if self.updating else
                  "Plug in the USB cable to change the profiles.")
        for card, profile in zip(self.cards, shown):
            if card.profile != profile:
                card.set_profile(profile)
            card.set_actions(allowed, reason)
            card.set_active(edge and profile.slot == self.active_slot)
            card.set_chosen(profile.slot == self.chosen_slot)
        chosen = next((p for p in shown if p.slot == self.chosen_slot), None)
        self.view.set_edge(found.edge if found else True)
        self.view.lit({"fn"} | profiles.changed_parts(chosen) if chosen else set())
        self.backup_button.setEnabled(bool(shown) and not self.updating)
        self.reread_button.setEnabled(found is not None and not self.updating)

    def choose_profile(self, profile: profiles.Profile) -> None:
        """A click on a card chooses it, a second click lets go."""
        self.chosen_slot = "" if self.chosen_slot == profile.slot else profile.slot
        self._show_profiles(self.current())

    # ---------------------------------------------------------------- profiles
    def create_profile(self, profile: profiles.Profile) -> None:
        self._edit(profile, creating=True)

    def edit_profile(self, profile: profiles.Profile) -> None:
        self._edit(profile, creating=False)

    def _edit(self, profile: profiles.Profile, creating: bool) -> None:
        """A new profile starts from the default's bytes, an edited one from its own."""
        base = self.profiles[0] if creating else profile
        settings = profiles.settings_of(base)
        if creating:
            settings = dataclasses.replace(settings, name="New profile")
        title = f"{'Create' if creating else 'Edit'} the profile"
        dialog = ProfileEditor(profile.slot, settings, creating, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            parts = profiles.build(dialog.settings(), base.reports, profiles.new_id() if creating else None)
        except profiles.ProfileError as exc:
            QMessageBox.warning(self, window_title(title), f"The profile cannot be saved: {exc}.")
            return
        if self._change(title, lambda device: profiles.write(device, profile.slot, parts)):
            self.chosen_slot = profile.slot             # the drawing lights what it sets

    def clear_profile(self, profile: profiles.Profile) -> None:
        title = "Clear the profile"
        answer = QMessageBox.question(self, window_title(title), f"Remove {profile.name} from Fn + {profile.slot}? "
                                      "The app saves a backup of the profiles first.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._change(title, lambda device: profiles.clear(device, profile.slot)) and \
                self.chosen_slot == profile.slot:
            self.chosen_slot = ""

    def _change(self, title: str, action: Callable) -> bool:
        """Backs up the profiles, changes one, and reads them again."""
        found = self.current()
        if found is None or found.bus != "usb" or self.updating:
            return False
        saved = ""
        try:
            with self.open_device(found.path(self.dev), found.sizes()) as device:
                saved = str(profiles.backup(profiles.read(device), profiles.backup_path(self.firmware_home),
                                            found.name, firmware.version_text(self.info.update) if self.info else ""))
                try:
                    action(device)
                finally:
                    self.profiles = profiles.read(device)
        except (OSError, ValueError, profiles.ProfileError) as exc:
            kept = f" The profiles from before are saved in {saved}." if saved else ""
            QMessageBox.warning(self, window_title(title), f"It did not work: {_error(exc)}.{kept}")
            self._show_profiles(found)
            return False
        self._show_profiles(found)
        return True

    # ---------------------------------------------------------------- latest
    def check_latest(self) -> None:
        if self.check_job.start(_job(firmware.latest, self.get)):
            self.check_button.setEnabled(False)

    def _check_done(self, result) -> None:
        if isinstance(result, Exception):
            self.progress_text.setText(_error(result))
        else:
            self.settings.set_latest(result, time.strftime("%Y-%m-%d %H:%M", time.localtime(self.clock())))
        self.show_state()

    # ---------------------------------------------------------------- update
    def _can_update(self, found: Controller | None, latest: int | None) -> bool:
        return (found is not None and found.bus == "usb" and self.info is not None and latest is not None
                and latest > self.info.update and not self.updating)

    def start_update(self) -> None:
        found, latest = self.current(), self.latest()
        if not self._can_update(found, latest):
            return
        data = firmware.read(self.info.target, latest, self.firmware_home)
        self._confirm_and_run(found, data, latest)

    def use_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, window_title("Use a firmware file"), str(Path.home()),
                                              "Firmware (*.bin);;All files (*)")
        if path:
            self.use_path(Path(path))

    def use_path(self, path: Path) -> None:
        found = self.current()
        if found is None or self.info is None:
            return
        try:
            data = path.read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, window_title("Use a firmware file"), f"{path} could not be read: {_error(exc)}.")
            return
        problem = firmware.problem(data, found, self.info)
        if problem:
            QMessageBox.warning(self, window_title("Use a firmware file"), f"{path.name} was not sent: {problem}")
            return
        self._confirm_and_run(found, data, firmware.header(data).update)

    def _confirm_and_run(self, found: Controller, data: bytes | None, version: int) -> None:
        busy = controller.holders(found.path(self.dev), self.proc)
        if busy:
            QMessageBox.warning(self, window_title("Update the firmware"),
                                f"{', '.join(busy)} has the controller open. Quit it first (Steam: Steam › Exit), "
                                "so that nothing else talks to the controller during the update.")
            return
        if data is not None:
            check = (f"SHA-256 {firmware.sha256(data)}: "
                     + ("a file the app knows from the official server." if firmware.known(data) else
                        "not a file the app knows. The controller still checks its signature."))
        else:
            check = f"The app first downloads it from {firmware.SOURCE} (about 1 MB)."
        battery = found.battery
        level = f" The battery is at {battery.capacity} %." if battery and battery.capacity is not None else ""
        answer = QMessageBox.question(
            self, window_title("Update the firmware"),
            f"This sends firmware {firmware.version_text(version)} to the {found.name}, which runs "
            f"{firmware.version_text(self.info.update)}. {check}\n\n"
            "It takes about half a minute. Leave the USB cable in and the board on until the window says it is done; "
            f"the controller then restarts by itself.{level} The app saves a backup of the profiles first.\n\n"
            "Update the controller now?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(found, data, version)

    def _run(self, found: Controller, data: bytes | None, version: int) -> None:
        info, home, get, update = self.info, self.firmware_home, self.get, self.update
        path, sizes = found.path(self.dev), found.sizes()
        open_device = self.open_device
        edge, model = found.edge, found.name
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
            with open_device(path, sizes) as device:
                if edge:
                    saved = str(profiles.backup(profiles.read(device), profiles.backup_path(home), model,
                                                firmware.version_text(info.update)))
                    progress.note(f"The profiles are saved in {saved}.")
                update(device, image, progress)
            return saved

        self.progress, self.updating, self.update_target = progress, True, version
        self.update_job.start(_job(job))
        self.show_state()

    def _show_progress(self) -> None:
        progress = self.progress
        self.progress_bar.setVisible(self.updating)
        self.view.show_data(progress.done / progress.total if self.updating and progress and progress.total else
                            0.0 if self.updating else None)
        if not self.updating or progress is None:
            return
        if progress.total:
            self.progress_bar.setValue(int(progress.done * 1000 / progress.total))
        step = updater.STEP_NAMES.get(progress.step, "")
        detail = (f"{progress.done // 1024} of {progress.total // 1024} KB" if progress.step == updater.WRITE and
                  progress.total else "")
        last = progress.log[-1] if progress.log else ""
        self.progress_text.setText(" · ".join(part for part in (step, detail, last) if part))

    def _update_done(self, result) -> None:
        self.updating = False
        self.returning_until = self.clock() + RETURN_S
        self.progress_bar.setVisible(False)
        if isinstance(result, Exception):
            text = _error(result)
            self.progress_text.setText(f"The update did not finish: {text}")
            QMessageBox.warning(self, window_title("Update the firmware"), f"The update did not finish. {text}")
        else:
            saved = f" The profiles from before are saved in {result}." if result else ""
            self.progress_text.setText(f"Firmware {firmware.version_text(self.update_target)} is sent: the controller "
                                       "restarts with it and comes back in a few seconds, and the header then shows "
                                       "its new version. For Bluetooth, remove it from the system's Bluetooth "
                                       f"settings and pair it again: the update ends the pairing.{saved}")
        self.read_key = ""                  # read the firmware again when the controller is back
        self.refresh()

    # ---------------------------------------------------------------- backup
    def save_backup(self) -> None:
        found = self.current()
        if found is None or not self.profiles:
            return
        start = profiles.backup_path(self.firmware_home)
        start.parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, window_title("Back up the profiles"), str(start),
                                              "Profiles (*.json)")
        if not path:
            return
        try:
            profiles.backup(self.profiles, Path(path), found.name,
                            firmware.version_text(self.info.update) if self.info else "")
        except OSError as exc:
            QMessageBox.warning(self, window_title("Back up the profiles"), f"{path} could not be written: "
                                f"{_error(exc)}.")

    # ------------------------------------------------------------------- quit
    def shut_down(self) -> None:
        self.timer.stop()
        self._stop_reading()
        self._vibration_done()
        self.check_job.stop(1000)
        self.update_job.stop(600000)        # an update must not be cut off: wait for it

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.updating:
            QMessageBox.information(self, window_title("Update the firmware"),
                                    "The update is still running. The window closes when it is done.")
            event.ignore()
            return
        save_geometry(self, self.settings.qsettings)
        super().closeEvent(event)
