# SPDX-License-Identifier: GPL-3.0-or-later
"""A settings page for an emulator manager, and the window that holds it (owner, 03-11-2026: the settings that
matter for playing offered in the app, as PCSX2 Manager's and RPCS3 Manager's Settings tabs do, for the managers
whose window has no tabs: PPSSPP, Vita3K and Xenia). One box per group, each setting a choice, a switch or a
percentage, read from the emulator's settings file and written the moment it is changed, while the emulator does
not run.

The page knows no file: the app gives it its settings and two functions. A setting is any object with *key* (the
app's own name), *group* (the box it is shown in), *label*, *kind*, *choices* ((value, as shown) pairs) and *tip*:
a setting with choices is shown as a choice whatever its kind (an app's own kind, such as a number, is one too), a
PERCENT as a percentage (it may give *top*, 100 when it does not), anything else as a switch. *read()* gives every
value by key, a SWITCH as "true" or "false", a PERCENT as a number, a CHOICE as one of its values (a value the app
does not offer is shown as it is); *write(setting, value)* writes one in the same form. The first group's box
stands on the left, the whole height; the others under each other on the right (as PCSX2 Manager's).

SettingsDialog is the page in a window of its own, opened by the window's Settings… button."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
                             QLabel, QSpinBox, QVBoxLayout, QWidget)

from .widgets import hint_label

CHOICE, SWITCH, PERCENT = "choice", "switch", "percent"
Read = Callable[[], dict[str, str]]
Write = Callable[[object, str], None]


def running_text(emulator: str) -> str:
    return f"{emulator} is running: close it first, it writes its own settings over the change when it closes."


class SettingsPage(QWidget):
    """*emulator*: its name, for the words; *settings*: the settings, in the order the boxes show them, their
    groups in the order of their first setting; *read* and *write*: see above; *running*: whether the emulator
    runs (tests pass their own); *lead*: the line above the boxes; *log*: the app's log."""

    def __init__(self, emulator: str, settings: Sequence, read: Read, write: Write, running: Callable[[], bool],
                 lead: str = "", log: logging.Logger | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.emulator = emulator
        self.settings = list(settings)
        self.read = read
        self.write = write
        self.running = running
        self.log = log or logging.getLogger(__name__)
        self.widgets: dict[str, QWidget] = {}
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        names = list(dict.fromkeys(setting.group for setting in self.settings))
        groups: dict[str, QFormLayout] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        others = names[1:]
        for n, name in enumerate(names):
            box = QGroupBox(name)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            groups[name] = form
            if n == 0:
                grid.addWidget(box, 0, 0, max(len(others), 1), 1, Qt.AlignmentFlag.AlignTop)
            else:
                grid.addWidget(box, n - 1, 1, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for setting in self.settings:
            widget = self._widget(setting)
            widget.setToolTip(setting.tip)
            self.widgets[setting.key] = widget
            label = QLabel(setting.label)
            label.setToolTip(setting.tip)
            groups[setting.group].addRow(label, widget)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        if lead:
            lay.addWidget(hint_label(lead, follow_height=True))
        lay.addLayout(grid)
        lay.addStretch(1)
        lay.addWidget(self.status)
        self.load()

    @staticmethod
    def kind(setting) -> str:
        """How the setting is shown: CHOICE, PERCENT or SWITCH (see above)."""
        if setting.kind == PERCENT:
            return PERCENT
        return CHOICE if setting.choices else SWITCH

    def _widget(self, setting) -> QWidget:
        if self.kind(setting) == CHOICE:
            box = QComboBox()
            for value, text in setting.choices:
                box.addItem(text, value)
            box.currentIndexChanged.connect(lambda _i, s=setting, b=box: self.change(s, b.currentData()))
            return box
        if self.kind(setting) == PERCENT:
            spin = QSpinBox()
            spin.setRange(0, getattr(setting, "top", 100))
            spin.setSuffix(" %")
            spin.valueChanged.connect(lambda value, s=setting: self.change(s, str(value)))
            return spin
        check = QCheckBox()
        check.toggled.connect(lambda on, s=setting: self.change(s, "true" if on else "false"))
        return check

    def load(self) -> None:
        """The values as the file holds them (or the emulator's defaults while there is none)."""
        values = self.read()
        for setting in self.settings:
            widget = self.widgets[setting.key]
            value = values.get(setting.key, "")
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                at = widget.findData(value)
                if at < 0 and value:                        # a value the emulator knows and the app does not
                    widget.addItem(value, value)
                    at = widget.count() - 1
                widget.setCurrentIndex(max(at, 0))
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(float(value)))
                except ValueError:
                    widget.setValue(widget.maximum())
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value == "true")
            widget.blockSignals(False)

    @classmethod
    def shown(cls, setting, value: str) -> str:
        """A value in words, for the status and the log."""
        if cls.kind(setting) == CHOICE:
            return next((text for v, text in setting.choices if v == value), value)
        if cls.kind(setting) == PERCENT:
            return f"{value} %"
        return "on" if value == "true" else "off"

    def change(self, setting, value: str) -> None:
        if self.running():
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(running_text(self.emulator))
            self.load()
            return
        try:
            self.write(setting, value)
        except OSError as error:
            self.status.setStyleSheet("font-weight:600;color:#c62828;")
            self.status.setText(f"{setting.label} was not changed: {error}")
            self.log.error("Settings: %s was not changed: %s", setting.label, error)
            self.load()
            return
        text = f"{setting.label}: {self.shown(setting, value)}."
        self.status.setStyleSheet("")
        self.status.setText(text)
        self.log.info("Settings: %s", text)


class SettingsDialog(QDialog):
    """The page in a window of its own, with a Close button; *title* is the window's. The page is *page*."""

    def __init__(self, title: str, emulator: str, settings: Sequence, read: Read, write: Write,
                 running: Callable[[], bool], lead: str = "", log: logging.Logger | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(820)
        self.page = SettingsPage(emulator, settings, read, write, running, lead, log, self)
        lay = QVBoxLayout(self)
        lay.addWidget(self.page)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
