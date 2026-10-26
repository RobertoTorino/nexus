# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings tab: PCSX2's settings that matter for playing, in the app (owner, 24-10-2026: every setting through
the manager, PCSX2's own window is not opened). One box per group (pcsx2_settings.SETTINGS: the picture, the
emulation, the sound, the controllers), each setting a choice, a switch or a percentage, read from PCSX2.ini and
written the moment it is changed, while PCSX2 does not run. Player 2 on the second controller and quitting a game
with Select + Start are here too, each written with its own function. The Sound box also shows, beside PCSX2's
volume, the volume Bazzite's sound settings remember for PCSX2 (core's sound; owner, 24-10-2026: as RPCS3
Manager's): the window passes it (show_sound), and Unmute beside it turns a muted one on again (core's sound.unmute;
owner, 24-10-2026)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QVBoxLayout, QWidget)

from bc250_core import sound
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import hint_label

from . import memcards, pcsx2_settings
from .pcsx2_settings import CHOICE, PERCENT, SWITCH, Setting

RUNNING = "PCSX2 is running: close it first, it would write its own settings over the change."
STREAM = "PCSX2"                        # PCSX2's sound stream, as PipeWire names it (core's sound)
SOUND_MUTED = sound.muted_text(STREAM)
SOUND_DOWN = sound.down_text(STREAM)
PLAYER2 = Setting("player2", pcsx2_settings.CONTROLLERS, "Player 2 on the second controller", "Pad2", ("Type",),
                  SWITCH, tip="A second controller connected is player 2, with the same buttons as player 1. Off, "
                              "PCSX2 has no player 2.")
QUIT = Setting("quit", pcsx2_settings.CONTROLLERS, "Quit a game with Select + Start", "Hotkeys", ("ShutdownVM",),
               SWITCH, tip="Select (Share, Create or View) and Start (Options or Menu) pressed together on the first "
                           "controller end the game and close PCSX2, without a question; on from the start. Off, a "
                           "game is left through Steam's menu, or Esc on a keyboard for PCSX2's own menu.")
OWN = (PLAYER2, QUIT)                                   # the switches with a function of their own


class SettingsPage(QWidget):
    """*pcsx2_home*: PCSX2's own folder; *running*: whether PCSX2 runs (tests pass their own); *log*: the app's
    log."""

    sound_changed = pyqtSignal()            # Unmute changed Bazzite's volume for the emulator

    def __init__(self, pcsx2_home: Path, running: Callable[[], bool] = memcards.pcsx2_running,
                 log: logging.Logger | None = None, parent=None):
        super().__init__(parent)
        self.sound_path: Path | None = None         # WirePlumber's file (the window's, for the tests' own)
        self.unmute = sound.unmute                  # tests pass their own
        self.unmuting = UpdateChecker(self)         # off the GUI thread: it takes a moment or two
        self.unmuting.finished.connect(self._unmuted)
        self.unmute_button = QPushButton("Unmute")
        self.unmute_button.setToolTip(f"Turn {STREAM}'s sound on again in Bazzite's sound settings, which keep it "
                                      "muted for every game until it is turned on")
        self.unmute_button.clicked.connect(self.on_unmute)
        self.unmute_button.hide()                   # while it is muted only
        self.pcsx2_home = pcsx2_home
        self.running = running
        self.log = log or logging.getLogger(__name__)
        self.widgets: dict[str, QWidget] = {}
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # The picture's box on the left, the whole height; the three others under each other on the right. (A box
        # placed under the picture's span lay over it and hid its lower rows; owner, 24-10-2026.)
        groups: dict[str, QFormLayout] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        others = (pcsx2_settings.EMULATION, pcsx2_settings.SOUND, pcsx2_settings.CONTROLLERS)
        for n, name in enumerate((pcsx2_settings.PICTURE, *others)):
            box = QGroupBox(name)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            groups[name] = form
            if n == 0:
                grid.addWidget(box, 0, 0, len(others), 1, Qt.AlignmentFlag.AlignTop)
            else:
                grid.addWidget(box, n - 1, 1, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.system_sound = QLabel("—")             # Bazzite's volume for PCSX2, read only (show_sound)
        self.system_sound.setToolTip(sound.tip(STREAM))
        for setting in (*pcsx2_settings.SETTINGS, *OWN):
            widget = self._widget(setting)
            widget.setToolTip(setting.tip)
            self.widgets[setting.key] = widget
            label = QLabel(setting.label)
            label.setToolTip(setting.tip)
            field: QWidget = widget
            if setting.key == "volume":             # beside PCSX2's volume, on the same row (the tab's height)
                field = QWidget()
                row = QHBoxLayout(field)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(8)
                row.addWidget(widget)
                system_label = QLabel("Bazzite's volume for PCSX2:")
                system_label.setToolTip(sound.tip(STREAM))
                row.addWidget(system_label)
                row.addWidget(self.system_sound)
                row.addWidget(self.unmute_button)
                row.addStretch(1)
            groups[setting.group].addRow(label, field)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(hint_label("PCSX2's settings, written into PCSX2's own settings file the moment you change "
                                 "one, while PCSX2 does not run. A game's own settings in PCSX2 come before these. "
                                 "How a game fills the screen is set per game, in the Your games tab.",
                                 follow_height=True))        # its lines count in the page's minimum
        lay.addLayout(grid)
        lay.addStretch(1)
        lay.addWidget(self.status)
        self.load()

    def show_sound(self, state: tuple[float, bool] | None) -> tuple[str, bool]:
        """*state*: (volume, muted) as Bazzite remembers it for PCSX2, None while it has none (PCSX2 has not played
        yet). Returns (what is wrong in words, whether something is: muted, or turned down to nothing)."""
        text, problem = sound.describe(STREAM, state)
        self.system_sound.setStyleSheet("font-weight:600;color:#c62828;" if problem else "")
        self.system_sound.setText(text)
        self.unmute_button.setVisible(bool(state and state[1]))
        return problem, bool(problem)

    def on_unmute(self) -> None:
        name, path, unmute = STREAM, self.sound_path, self.unmute

        def job():
            try:
                return True, unmute(name, path)
            except sound.SoundError as error:
                return False, str(error)
        if self.unmuting.start(job):
            self.unmute_button.setEnabled(False)
            self.status.setStyleSheet("")
            self.status.setText(f"Unmuting {STREAM}…")

    def _unmuted(self, result: tuple[bool, object]) -> None:
        ok, detail = result
        self.unmute_button.setEnabled(True)
        if ok and detail is not None and not detail[1]:
            text = f"{STREAM}'s sound is on again in Bazzite's sound settings."
            self.status.setStyleSheet("")
            self.log.info("Settings: %s", text)
        else:
            text = detail if not ok else f"{STREAM}'s sound did not come on in Bazzite's sound settings."
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.log.error("Settings: %s", text)
        self.status.setText(str(text))
        self.sound_changed.emit()

    def _widget(self, setting: Setting) -> QWidget:
        if setting.kind == CHOICE:
            box = QComboBox()
            for value, text in setting.choices:
                box.addItem(text, value)
            box.currentIndexChanged.connect(lambda _i, s=setting, b=box: self.change(s, b.currentData()))
            return box
        if setting.kind == PERCENT:
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setSuffix(" %")
            spin.valueChanged.connect(lambda value, s=setting: self.change(s, str(value)))
            return spin
        check = QCheckBox()
        check.toggled.connect(lambda on, s=setting: self.change(s, "true" if on else "false"))
        return check

    def load(self) -> None:
        """The values as PCSX2.ini holds them (or PCSX2's defaults while there is none)."""
        values = pcsx2_settings.read_settings(self.pcsx2_home)
        values[PLAYER2.key] = "true" if pcsx2_settings.player2(self.pcsx2_home) else "false"
        values[QUIT.key] = "true" if pcsx2_settings.quit_chord(self.pcsx2_home) else "false"
        for setting in (*pcsx2_settings.SETTINGS, *OWN):
            widget = self.widgets[setting.key]
            value = values[setting.key]
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                at = widget.findData(value)
                if at < 0 and value:                        # a value PCSX2 knows and the app does not: shown as is
                    widget.addItem(value, value)
                    at = widget.count() - 1
                widget.setCurrentIndex(max(at, 0))
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(float(value)))
                except ValueError:
                    widget.setValue(100)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value == "true")
            widget.blockSignals(False)

    def shown(self, setting: Setting, value: str) -> str:
        """A value in words, for the status and the log."""
        if setting.kind == CHOICE:
            return next((text for v, text in setting.choices if v == value), value)
        if setting.kind == PERCENT:
            return f"{value} %"
        return "on" if value == "true" else "off"

    def change(self, setting: Setting, value: str) -> None:
        if self.running():
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(RUNNING)
            self.load()
            return
        try:
            if setting is PLAYER2:
                pcsx2_settings.set_player2(self.pcsx2_home, value == "true")
            elif setting is QUIT:
                pcsx2_settings.set_quit_chord(self.pcsx2_home, value == "true")
            else:
                pcsx2_settings.write_setting(self.pcsx2_home, setting, value)
        except OSError as error:
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(f"{setting.label} was not changed: {error}")
            self.log.error("Settings: %s was not changed: %s", setting.label, error)
            return
        text = f"{setting.label}: {self.shown(setting, value)}."
        self.status.setStyleSheet("")
        self.status.setText(text)
        self.log.info("Settings: %s", text)
