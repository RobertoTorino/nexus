# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as Windows Portable Test lays it out: the cards on the left (PCSX2,
Settings), what the focused one shows on the right, the controller's buttons at the bottom.

The PCSX2 pane: what is installed, where, and the pills: A Install or Open PCSX2, Y Reinstall or Update, Remove with
a second press. Nothing downloads before A. The download and the unpacking run off the window's thread; the pane
counts the megabytes. B while they run asks first, as the portal does.

The Settings pane: PCSX2's settings that matter on the handheld, a pill each with its value; A steps to the next
value and writes it into PCSX2.ini at once (pcsx2_settings), never while PCSX2 runs (it writes its own settings back
when it closes). What the app owns in PCSX2.ini is set after an install, when the window opens and before PCSX2
opens (pcsx2_settings.prepare), so PCSX2 opens ready to play: the BC250 suite's PCSX2 Manager's rules."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, power
from bc250_core.gamepad import Gamepad
from bc250_core.portable import (AMBER, BODY, DIM, Card, InfoPill, Legend, Pane, Pill, PortableHeader,
                                 PortableWindow, px, status_clock, text_label)

from . import APP_ID, APP_NAME, __version__, emulator, pcsx2_settings
from .pcsx2_settings import SWITCH, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and B while PCSX2 is being installed, ask for a second press within this
CARDS_WIDTH = 520               # the cards' column; the panes take the rest
SETTING_HEIGHT = 40             # a setting's pill: nine of them fit the pane at 720 px high
ABOUT = ("PCSX2, the PlayStation 2 emulator, installed for your own user in portable mode: its settings, the BIOS, "
         "the memory cards and the save states stay in its folder.")
LEGEND = (("B", "Close"),)
RUNNING = "PCSX2 is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install PCSX2 first: the settings are in its folder."
# The switches with a function of their own in pcsx2_settings, after SETTINGS
PLAYER2 = Setting("player2", "Player 2", "Pad2", ("Type",), SWITCH,
                  tip="a second controller is player 2, with the same buttons as player 1.")
QUIT = Setting("quit", "Quit with Select + Start", "Hotkeys", ("ShutdownVM",), SWITCH,
               tip="View and Menu together end the game; off, PCSX2's pause menu does.")
BIG_PICTURE = Setting("bigpicture", "Big Picture", "UI", ("StartBigPictureMode",), SWITCH,
                      tip="PCSX2 opens full screen, made for a controller; off, its desktop window.")
OWN = {PLAYER2.key: (pcsx2_settings.player2, pcsx2_settings.set_player2),
       QUIT.key: (pcsx2_settings.quit_chord, pcsx2_settings.set_quit_chord),
       BIG_PICTURE.key: (pcsx2_settings.big_picture, pcsx2_settings.set_big_picture)}
ALL_SETTINGS = (*pcsx2_settings.SETTINGS, PLAYER2, QUIT, BIG_PICTURE)
SETTINGS_INFO = ("A changes the setting the focus is on; PCSX2 reads it the next time it opens.\n\n"
                 + "\n".join(f"{setting.label}: {setting.tip}" for setting in ALL_SETTINGS))


class _Worker(QObject):
    """Runs the install off the window's thread; done (the version, or the exception) and what it is doing (said)
    arrive on the window's."""

    done = pyqtSignal(object)
    said = pyqtSignal(str)

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


class SettingsPane(Pane):
    """A pill per setting, "Renderer: Automatic"; A on one steps to the next value (the window writes it)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("PCSX2's settings", SETTINGS_INFO)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(8))
        self.pills: dict[str, Pill] = {}
        for setting in ALL_SETTINGS:
            pill = Pill(setting.label)
            pill.setFixedHeight(px(SETTING_HEIGHT))
            self.pills[setting.key] = pill
            self.column.addWidget(pill)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, start: Callable[[Path], None] = emulator.start,
                 running: Callable[[Path], bool] = emulator.running):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.start_program, self.running = install, start, running
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…"
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False

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
        cards.setSpacing(px(12))
        self.pcsx2_card = Card("PCSX2", "Install, open, update or remove the emulator.")
        self.settings_card = Card("Settings", "The picture, the controllers and how PCSX2 opens.")
        for card in (self.pcsx2_card, self.settings_card):
            card.setFixedHeight(px(104))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        self.pane.column.addWidget(text_label("PCSX2", 24, QFont.Weight.ExtraBold))
        self.pane.column.addWidget(text_label(ABOUT, BODY + 1, color=DIM, wrap=True))
        self.pane.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.pane.column.addLayout(self.grid)
        self.pane.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.pane.column.addWidget(self.status)
        self.pane.column.addSpacing(px(8))
        pills = QHBoxLayout()
        pills.setSpacing(px(12))
        self.remove_pill = Pill("Remove")
        self.other = Pill("Reinstall", "Y")
        self.main = Pill("Install", "A", main=True)
        pills.addWidget(self.remove_pill)
        pills.addStretch()
        pills.addWidget(self.other)
        pills.addWidget(self.main)
        self.pane.column.addLayout(pills)
        self.settings_pane = SettingsPane()
        self.panes.addWidget(self.pane)
        self.panes.addWidget(self.settings_pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend(LEGEND)
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._installed)
        self.worker.said.connect(self._said)
        self.pcsx2_card.focused.connect(lambda: self.panes.setCurrentWidget(self.pane))
        self.pcsx2_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.panes.setCurrentWidget(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.main.activated.connect(self.main_action)
        self.other.activated.connect(self.other_action)
        self.remove_pill.activated.connect(self.remove_action)
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("y", self.other_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.refresh)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, PCSX2's settings brought to what the app owns,
        and the focus on the PCSX2 card."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.refresh()
        self.pcsx2_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([power.text(self.battery()), *status_clock()])

    def prepare(self) -> bool:
        """pcsx2_settings.prepare() while PCSX2 is installed and not running; whether PCSX2.ini is ready."""
        if not emulator.installed(self.home) or self.running(self.home):
            return False
        try:
            done = pcsx2_settings.prepare(self.home)
        except OSError as error:
            self.log.error(f"PCSX2's settings could not be written: {error}")
            return False
        if done:
            self.log.info(f"PCSX2's settings: {', '.join(done)}.")
        return True

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), the main pill's text (A) and the other's (Y); "" hides a pill."""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading PCSX2 {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if emulator.replaced(self.home):
            return (f"PCSX2 replaced itself with another build. Reinstall puts {emulator.VERSION} back.",
                    "Open PCSX2", "Reinstall")
        if version != emulator.VERSION:
            return f"This app installs PCSX2 {emulator.VERSION}.", "Open PCSX2", f"Update to {emulator.VERSION}"
        return "", "Open PCSX2", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        installed = version + (", replaced by another build" if version and emulator.replaced(self.home) else "")
        return [("Installed", installed or "not installed"), ("This app installs", emulator.VERSION),
                ("Folder", str(self.home))]

    def setting_value(self, setting: Setting) -> str:
        if setting.key in OWN:
            return "true" if OWN[setting.key][0](self.home) else "false"
        return pcsx2_settings.read_setting(self.home, setting)

    def refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for r, (label, value) in enumerate(self.rows()):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)
        status, main, other = self.state()
        self.status.setText(self.message or status)
        self.main.set_text(main)
        self.main.setVisible(bool(main))
        self.other.set_text(other)
        self.other.setVisible(bool(other))
        self.remove_pill.set_text("Press again to remove" if self.confirm_remove else "Remove")
        self.remove_pill.setVisible(not self.busy and bool(emulator.installed(self.home)))
        self.refresh_settings()
        focus = self.focusWidget()
        if focus is not None and not focus.isVisible() and focus in (self.main, self.other, self.remove_pill):
            visible = [pill for pill in (self.main, self.other, self.remove_pill) if pill.isVisible()]
            (visible[0] if visible else self.pcsx2_card).setFocus()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(self.setting_value(setting))}" if ready
                          else setting.label)
            pill.setEnabled(ready)
        if not ready and not self.settings_pane.status.text():
            self.settings_pane.status.setText(NOT_INSTALLED)
        elif ready and self.settings_pane.status.text() == NOT_INSTALLED:
            self.settings_pane.status.setText("")

    # The Settings pane

    def focus_settings(self) -> None:
        first = self.settings_pane.pills[ALL_SETTINGS[0].key]
        if first.isEnabled():
            first.setFocus()

    def step_setting(self, setting: Setting) -> None:
        """A on a setting's pill: its next value, written now, unless PCSX2 runs."""
        if self.busy or not emulator.installed(self.home):
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(self.setting_value(setting))
        try:
            if setting.key in OWN:
                OWN[setting.key][1](self.home, value == "true")
            else:
                pcsx2_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, Y and Remove

    def main_action(self) -> None:
        if self.busy:
            return
        _, main, _ = self.state()
        if main == "Install":
            self.install()
        elif main == "Open PCSX2":
            self.open_pcsx2()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing PCSX2 {emulator.VERSION} in {self.home}.")
        self.worker.run(lambda: self.install_job(self.home, progress=self._progress, say=self.worker.said.emit))

    def _progress(self, got: int) -> None:
        self.got = got                                  # read by refresh() on the window's thread

    def _said(self, text: str) -> None:
        self.stage = text
        self.refresh()

    def _installed(self, result: object) -> None:
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if isinstance(result, Exception):
            self.message = f"PCSX2 could not be installed: {result}"
            self.log.error(f"Installing PCSX2 failed: {result}")
        else:
            self.message = f"PCSX2 {result} is installed."
            self.log.info(f"PCSX2 {result} installed.")
            self.prepare()                              # before its first start: no setup wizard, no updater
        self.refresh()
        self.main.setFocus()

    def open_pcsx2(self) -> None:
        if self.running(self.home):
            self.message = "PCSX2 is open already."
            self.refresh()
            return
        self.prepare()
        try:
            self.start_program(self.home)
        except OSError as error:
            self.message = f"PCSX2 could not be started: {error}"
            self.log.error(f"PCSX2 could not be started: {error}")
            self.refresh()
            return
        self.message = ""
        self.log.info("Opened PCSX2.")
        self.refresh()

    def remove_action(self) -> None:
        """Remove asks for a second press (no dialog on a handheld): the pill says so for a few seconds."""
        if self.busy or not emulator.installed(self.home):
            return
        if not self.confirm_remove:
            self.confirm_remove = True
            self.confirm_timer.start()
            self.refresh()
            return
        self._confirm_over()
        try:
            emulator.remove(self.home)
        except OSError as error:
            self.message = f"PCSX2 could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing PCSX2 failed: {error}")
        else:
            self.message = "PCSX2 is removed. Its BIOS, memory cards and settings stay in its folder."
            self.log.info("PCSX2 removed.")
        self.refresh()
        self.main.setFocus()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        changed = self.confirm_remove or self.close_asked
        if self.close_asked:
            self.legend.set_items(LEGEND)
            if self.message.startswith("Press B again"):
                self.message = ""
        self.confirm_remove = self.close_asked = False
        if changed:
            self.refresh()

    # B

    def on_back(self) -> None:
        if self.busy and not self.close_asked:          # closing drops the download (owner, 28-10-2026: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = "Press B again to close: the download stops."
            self.legend.set_items([("B", "Press again to close")])
            self.refresh()
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
