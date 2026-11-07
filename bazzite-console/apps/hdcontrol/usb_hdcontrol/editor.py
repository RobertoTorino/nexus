# SPDX-License-Identifier: GPL-3.0-or-later
"""The profile editor (owner, 23-10-2026): a profile's name, its sticks' curves and sensitivity, its triggers'
ranges and what each button sends, for Fn + Square, Cross or Circle. It returns the settings; the window writes
them."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QSlider, QSpinBox, QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.theme import muted
from bc250_core.widgets import accent_button

from . import profiles

BACK_BUTTONS = (14, 15)             # the back buttons send nothing of their own to another input


def _percent(value: int) -> int:
    return round(value * 100 / 255)


class StickRow:
    """A stick's curve and its sensitivity. A profile made elsewhere keeps its points until one of them changes."""

    def __init__(self, grid: QGridLayout, row: int, name: str, curve: int, level: int | None):
        self.curve = QComboBox()
        for value, text in profiles.CURVES.items():
            self.curve.addItem(text, value)
        self.curve.setCurrentIndex(max(0, self.curve.findData(curve)))
        self.curve.setToolTip(f"How the {name.lower()} responds: Default as without a profile, Quick and Dynamic "
                              "faster, Precise and Steady finer, Digital all or nothing.")
        self.level = QSlider(Qt.Orientation.Horizontal)
        self.level.setRange(0, profiles.SENSITIVITY_LEVELS - 1)
        self.level.setValue(profiles.DEFAULT_LEVEL if level is None else level)
        self.level.setToolTip("The curve's sensitivity, 0 to 10.")
        self.value = QLabel()
        self.value.setMinimumWidth(80)
        self.kept = level is None           # the points as they are, until the curve or the level changes
        self.curve.currentIndexChanged.connect(self._changed)
        self.level.valueChanged.connect(self._changed)
        grid.addWidget(QLabel(name), row, 0)
        grid.addWidget(self.curve, row, 1)
        grid.addWidget(self.level, row, 2)
        grid.addWidget(self.value, row, 3)
        self._show()

    def _changed(self) -> None:
        self.kept = False
        self._show()

    def _show(self) -> None:
        self.value.setText("as it is" if self.kept else f"level {self.level.value()}")

    def result(self) -> tuple[int, int | None]:
        return self.curve.currentData(), None if self.kept else self.level.value()


class TriggerRow:
    """A trigger's range in percent of its travel; an unchanged value keeps its exact byte."""

    def __init__(self, grid: QGridLayout, row: int, name: str, start: int, end: int):
        self.raw = (start, end)
        self.start, self.end = QSpinBox(), QSpinBox()
        for box, value, what in ((self.start, start, "starts"), (self.end, end, "ends")):
            box.setRange(0, 100)
            box.setSuffix(" %")
            box.setValue(_percent(value))
            box.setToolTip(f"Where on its travel {name} {what} to count.")
        grid.addWidget(QLabel(name), row, 0)
        grid.addWidget(QLabel("from"), row, 1)
        grid.addWidget(self.start, row, 2)
        grid.addWidget(QLabel("to"), row, 3)
        grid.addWidget(self.end, row, 4)

    def result(self) -> tuple[int, int]:
        def byte(box: QSpinBox, raw: int) -> int:
            return raw if box.value() == _percent(raw) else round(box.value() * 255 / 100)
        return byte(self.start, self.raw[0]), byte(self.end, self.raw[1])


class ProfileEditor(QDialog):
    def __init__(self, slot: str, settings: profiles.Settings, creating: bool, parent: QWidget | None = None):
        super().__init__(parent)
        title = f"{'Create' if creating else 'Edit'} the profile Fn + {slot}"
        self.setWindowTitle(window_title(title))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name"))
        self.name = QLineEdit(settings.name)
        self.name.setMaxLength(39)
        self.name.textChanged.connect(self._check)
        name_row.addWidget(self.name, 1)
        layout.addLayout(name_row)

        sticks = QGroupBox("Sticks")
        grid = QGridLayout(sticks)
        self.left = StickRow(grid, 0, "Left stick", settings.left_curve, settings.left_level)
        self.right = StickRow(grid, 1, "Right stick", settings.right_curve, settings.right_level)
        grid.setColumnStretch(2, 1)
        layout.addWidget(sticks)

        triggers = QGroupBox("Triggers")
        grid = QGridLayout(triggers)
        start_l2, end_l2, start_r2, end_r2 = settings.triggers
        self.l2 = TriggerRow(grid, 0, "L2", start_l2, end_l2)
        self.r2 = TriggerRow(grid, 1, "R2", start_r2, end_r2)
        grid.setColumnStretch(5, 1)
        note = QLabel("Saved in the profile. On Linux the controller still reports the whole travel; a PS5 may use "
                      "the range.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{muted()};")
        grid.addWidget(note, 2, 0, 1, 6)
        for row in (self.l2, self.r2):
            row.start.valueChanged.connect(self._check)
            row.end.valueChanged.connect(self._check)
        layout.addWidget(triggers)

        buttons = QGroupBox("Buttons: what each one sends")
        grid = QGridLayout(buttons)
        self.buttons: list[QComboBox] = []
        half = (len(profiles.INPUTS) + 1) // 2
        for index, name in enumerate(profiles.INPUTS):
            combo = QComboBox()
            combo.addItem("Its own", index)
            for value, target in profiles.OUTPUTS.items():
                if value != index and value not in BACK_BUTTONS:
                    combo.addItem(target, value)
            combo.setCurrentIndex(max(0, combo.findData(settings.buttons[index])))
            combo.setToolTip(f"What {name} sends while this profile is on.")
            column = 2 * (index // half)
            grid.addWidget(QLabel(name), index % half, column)
            grid.addWidget(combo, index % half, column + 1)
            self.buttons.append(combo)
        layout.addWidget(buttons)

        self.problem = QLabel()
        self.problem.setStyleSheet(f"color:{muted()};")
        layout.addWidget(self.problem)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = accent_button("Save to the controller")
        self.save_button.setToolTip(f"Writes the profile to Fn + {slot}, after a backup of all four.")
        box.addButton(self.save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self._check()

    def _problem(self) -> str:
        name = self.name.text()
        if not name.strip():
            return "Give the profile a name."
        if not profiles.name_fits(name):
            return "The name is too long."
        for trigger, row in (("L2", self.l2), ("R2", self.r2)):
            if row.start.value() >= row.end.value():
                return f"{trigger}'s range must start before it ends."
        return ""

    def _check(self) -> None:
        problem = self._problem()
        self.problem.setText(problem)
        self.save_button.setEnabled(not problem)

    def settings(self) -> profiles.Settings:
        left_curve, left_level = self.left.result()
        right_curve, right_level = self.right.result()
        return profiles.Settings(self.name.text().strip(), left_curve, left_level, right_curve, right_level,
                                 self.l2.result() + self.r2.result(),
                                 tuple(combo.currentData() for combo in self.buttons))
