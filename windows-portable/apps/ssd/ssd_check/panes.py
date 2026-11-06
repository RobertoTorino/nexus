# SPDX-License-Identifier: GPL-3.0-or-later
"""The pane beside the drives' cards: the drive's model with the information icon, what kind of drive it is, its
state, its values in two columns (the health, the power cycles, the hours and days, the data read and written; the
firmware, the interface, the link, the port, the rated and the measured speeds), a line on what they mean, and the
status line. Every action is a controller button in the window's legend (the suite's rule)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from bc250_core.portable import AMBER, BODY, DIM, TEXT, InfoPill, Pane, px, text_label

ABOUT = (
    "Health: how much of its rated life the drive has left, by the drive's own count. An NVMe drive reports how much "
    "it has used; health is 100 minus that. At 0 % the drive has used its rated endurance: many drives keep working "
    "long after that, but keep your backup current.\n\n"
    "Power cycles: how often the drive was switched on. Power-on hours: how long it has run in all; the days count "
    "full days only. Host reads and writes: how much data the handheld has read from and written to it in all.\n\n"
    "Windows' storage driver gives these values of an NVMe drive to any user. A SATA drive's need an administrator, "
    "so a SATA drive shows its specs only; a drive on USB and a memory card pass none on.\n\n"
    "Speed: the PCIe link the drive runs at now. Board link: the most the port above it offers, when Windows says "
    "(amber when that is less than the drive can do). Rated: the maker's read and write speeds, from SSD Check's "
    "list of drives. Measured: X writes a test file of 1 GB to the drive, reads it back and deletes it; it shows what "
    "the drive does in this handheld.\n\n"
    "The app only reads the drive (the speed test's file aside): nothing on it changes. The serial number is never "
    "read. Y reads the drives again; RB saves a screenshot in your Pictures folder.")
LEFT = ("Health", "Power cycles", "Power-on hours", "Power-on days", "Host reads", "Host writes")
RIGHT = ("Firmware", "Interface", "Speed", "Board link", "Rated R / W MB/s", "Measured R / W MB/s")


class DrivePane(Pane):
    """One drive: set_drive() fills it, set_value() changes one value, status the line at the bottom."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        self.title = text_label("", 24, QFont.Weight.ExtraBold, wrap=True)
        heading.addWidget(self.title, 1)
        self.info = InfoPill("About these values", ABOUT)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.kind = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.kind)
        self.state = text_label("", BODY + 2, QFont.Weight.Bold, wrap=True)
        self.column.addWidget(self.state)
        self.column.addSpacing(px(10))
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(16))
        grid.setVerticalSpacing(px(6))
        self.values: dict[str, QLabel] = {}
        for column, names in enumerate((LEFT, RIGHT)):
            for row, name in enumerate(names):
                grid.addWidget(text_label(name, BODY + 1, color=DIM), row, column * 2)
                value = text_label("—", BODY + 1, QFont.Weight.DemiBold)
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(value, row, column * 2 + 1)
                self.values[name] = value
        grid.setColumnMinimumWidth(2, px(40))
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.column.addLayout(grid)
        self.column.addSpacing(px(10))
        self.note = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.note)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def set_value(self, name: str, text: str, color: str = TEXT) -> None:
        label = self.values[name]
        label.setText(text)
        label.setStyleSheet(f"color: {color}; background: transparent;")

    def set_state(self, text: str, color: str) -> None:
        self.state.setText(text)
        self.state.setStyleSheet(f"color: {color}; background: transparent;")

    def set_values(self, values: Sequence[tuple[str, str, str]]) -> None:
        """(name, text, color) of each value; the ones not named show —."""
        named = {name: (text, color) for name, text, color in values}
        for name in self.values:
            self.set_value(name, *named.get(name, ("—", TEXT)))
