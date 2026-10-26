# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings tab: shadPS4's settings that matter for playing, in the app (owner, 24-10-2026: every manager takes
the Settings tab when it is rebuilt on PCSX2 Manager's). One box per group (shadps4_settings.SETTINGS: the picture,
the sound, the controller and mouse, what shows in a game), each setting a choice, a switch or a percentage, read
from config.json and written the moment it is changed, while shadPS4 does not run. Built as RPCS3 Manager's
settings_page. The Sound box also shows, beside shadPS4's volume, the volume Bazzite's sound settings remember for
shadPS4 (muted there, a game plays without a sound; seen on the board, 24-10-2026): the window passes it
(show_sound), and Unmute beside it turns a muted one on again (core's sound.unmute; owner, 24-10-2026)."""

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

from . import shadps4_settings, userdata
from .shadps4_settings import CHOICE, PERCENT, Setting

RUNNING = "shadPS4 is running: close it first, it writes its own settings over the change when it closes."
STREAM = "shadPS4"                      # shadPS4's sound stream, as PipeWire names it (core's sound; seen on the board)
SOUND_TIP = sound.tip(STREAM)
SOUND_MUTED = sound.muted_text(STREAM)
SOUND_DOWN = sound.down_text(STREAM)


class SettingsPage(QWidget):
    """*shad_home*: shadPS4's own folder; *running*: whether shadPS4 runs (tests pass their own); *log*: the app's
    log."""

    sound_changed = pyqtSignal()            # Unmute changed Bazzite's volume for the emulator

    def __init__(self, shad_home: Path, running: Callable[[], bool] = userdata.shadps4_running,
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
        self.shad_home = shad_home
        self.running = running
        self.log = log or logging.getLogger(__name__)
        self.widgets: dict[str, QWidget] = {}
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # The picture's box on the left, the whole height; the three others under each other on the right (as
        # PCSX2 Manager's).
        groups: dict[str, QFormLayout] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        others = (shadps4_settings.SOUND, shadps4_settings.CONTROLLER, shadps4_settings.IN_GAME)
        for n, name in enumerate((shadps4_settings.PICTURE, *others)):
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
        self.system_sound = QLabel("—")             # Bazzite's volume for shadPS4, read only (show_sound)
        self.system_sound.setToolTip(SOUND_TIP)
        for setting in shadps4_settings.SETTINGS:
            widget = self._widget(setting)
            widget.setToolTip(setting.tip)
            self.widgets[setting.key] = widget
            label = QLabel(setting.label)
            label.setToolTip(setting.tip)
            field: QWidget = widget
            if setting.key == "volume":             # beside shadPS4's volume, on the same row (the tab's height)
                field = QWidget()
                row = QHBoxLayout(field)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(8)
                row.addWidget(widget)
                system_label = QLabel("Bazzite's volume for shadPS4:")
                system_label.setToolTip(SOUND_TIP)
                row.addWidget(system_label)
                row.addWidget(self.system_sound)
                row.addWidget(self.unmute_button)
                row.addStretch(1)
            groups[setting.group].addRow(label, field)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        intro = hint_label("shadPS4's settings, written into its own settings file the moment you change one, "
                           "while shadPS4 does not run.", follow_height=True)   # its lines count in the minimum
        intro.setToolTip("A game's own settings in shadPS4 (made in shadPS4's own window) come before these.")
        lay.addWidget(intro)
        lay.addLayout(grid)
        lay.addStretch(1)
        lay.addWidget(self.status)
        self.load()

    def show_sound(self, state: tuple[float, bool] | None) -> tuple[str, bool]:
        """*state*: (volume, muted) as Bazzite remembers it for shadPS4, None while it has none (shadPS4 has not
        played yet). Returns (what is wrong in words, whether something is: muted, or turned down to nothing)."""
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
            spin.setRange(0, setting.top)
            spin.setSuffix(" %")
            spin.valueChanged.connect(lambda value, s=setting: self.change(s, value))
            return spin
        check = QCheckBox()
        check.toggled.connect(lambda on, s=setting: self.change(s, on != s.inverted))
        return check

    def load(self) -> None:
        """The values as config.json holds them (or shadPS4's defaults while there is none)."""
        values = shadps4_settings.read_settings(self.shad_home)
        for setting in shadps4_settings.SETTINGS:
            widget = self.widgets[setting.key]
            value = values[setting.key]
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                at = widget.findData(value)
                if at < 0:                                  # a value shadPS4 knows and the app does not: shown as is
                    widget.addItem(str(value), value)
                    at = widget.count() - 1
                widget.setCurrentIndex(at)
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(value))
                except (TypeError, ValueError):
                    widget.setValue(int(setting.default))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value) != setting.inverted)
            widget.blockSignals(False)

    def shown(self, setting: Setting, value) -> str:
        """A value in words, for the status and the log."""
        if setting.kind == CHOICE:
            return next((text for v, text in setting.choices if v == value), str(value))
        if setting.kind == PERCENT:
            return f"{value} %"
        return "on" if bool(value) != setting.inverted else "off"

    def change(self, setting: Setting, value) -> None:
        if self.running():
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(RUNNING)
            self.load()
            return
        try:
            shadps4_settings.write_setting(self.shad_home, setting, value)
        except userdata.UserDataError as error:
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(f"{setting.label} was not changed: {error}")
            self.log.error("Settings: %s was not changed: %s", setting.label, error)
            return
        text = f"{setting.label}: {self.shown(setting, value)}."
        self.status.setStyleSheet("")
        self.status.setText(text)
        self.log.info("Settings: %s", text)
