# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's own widgets on the portable window: the strip under the tiles (what the focused app is and does,
with its pills), the details page of an app and the Settings page (the portal's own version and update). The tabs
(LB and RB step through the categories) are core's Tabs. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from bc250_core.portable import AMBER, BODY, DIM, TEXT, Pane, Row, Tabs, px, text_label

WALLPAPER_FOLDER = r"%LOCALAPPDATA%\windows-portable-suite\wallpapers"   # as the user finds it
NAME = 24                               # pt: the name at the top of a pane


class AppPane(Pane):
    """The strip under the tiles: the focused app's name, its versions and one line of what it does. What A and Y
    do (Install or Open, Update) is in the window's legend, never a pill (owner, 29-10-2026: one way everywhere):
    main and other keep their texts for it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.setContentsMargins(px(24), px(14), px(24), px(14))
        row = QHBoxLayout()
        row.setSpacing(px(12))
        texts = QVBoxLayout()
        texts.setSpacing(px(2))
        self.name = text_label("", 22, QFont.Weight.ExtraBold)
        self.versions = text_label("", BODY + 1, color=DIM)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        for label in (self.name, self.versions, self.summary, self.status):
            texts.addWidget(label)
        row.addLayout(texts, 1)
        self.main = self.other = ""                     # A's and Y's text in the legend; "" for none
        self.column.addLayout(row)

    def fill(self, name: str, versions: str, summary: str, status: str, main: str, other: str) -> None:
        """The texts, and A's and Y's in the legend: "" for none (no Y without an update)."""
        self.name.setText(name)
        self.versions.setText(versions)
        self.summary.setText(summary)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.main, self.other = main, other


def _rows(grid: QGridLayout, rows: Sequence[tuple[str, str]]) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()                           # gone now, not when Qt deletes it later
            widget.deleteLater()
    for r, (label, value) in enumerate(rows):
        grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
        shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
        grid.addWidget(shown, r, 1)
    grid.setColumnStretch(1, 1)


class DetailsPane(Pane):
    """An app's details page (X): its versions, where it is and what it does; A Open and Y Remove are in the
    window's legend (open, remove: their texts, "" for none)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.name = text_label("", NAME, QFont.Weight.ExtraBold)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.name)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.open = self.remove = ""                    # A's and Y's text in the legend; "" for none

    def fill(self, name: str, summary: str, rows: Sequence[tuple[str, str]], status: str, can_open: bool,
             can_remove: bool, remove_text: str = "Remove") -> None:
        self.name.setText(name)
        self.summary.setText(summary)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.open = "Open" if can_open else ""
        self.remove = remove_text if can_remove else ""


class SuitePane(Pane):
    """The Settings page (Menu): the portal's own version, the newest release on GitHub and what it changes, with Update
    (Y) when there is a newer one; and the suite's settings, a row each that A switches (owner, 28-10-2026: the
    wallpaper on or off; 29-10-2026: the sound on or off; 30-10-2026: which wallpaper, and its transparency), with a
    line under it of what it does. They had a page of their own on View until View became
    the suite's Exit app (owner, 29-10-2026)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.name = text_label("", NAME, QFont.Weight.ExtraBold)
        self.version = text_label("", BODY + 1, color=DIM)
        self.column.addWidget(self.name)
        self.column.addWidget(self.version)
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addSpacing(px(16))
        self.wallpaper = Row("Wallpaper: Built-in")       # side by side: the page fits the Ally's screen
        self.transparency = Row("Transparency: 59 %")
        pair = QHBoxLayout()
        pair.setSpacing(px(12))
        pair.addWidget(self.wallpaper, 3)
        pair.addWidget(self.transparency, 2)
        self.column.addLayout(pair)
        self.column.addSpacing(px(4))
        self.wallpaper_text = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.wallpaper_text)
        self.column.addSpacing(px(12))
        self.sound = Row("Sound: On")
        self.column.addWidget(self.sound)
        self.column.addSpacing(px(4))
        self.column.addWidget(text_label("The portal's intro sound, for the suite. A switches it; it is kept for the "
                                         "next start.", BODY + 1, color=DIM, wrap=True))
        self.xbox = Row("Xbox menu: Add")
        self.xbox_text = text_label("The suite in the Xbox app's library, so Xbox mode starts it from its home. A adds "
                                    "it; the Xbox app closes for a moment.", BODY + 1, color=DIM, wrap=True)
        self.column.addSpacing(px(12))
        self.column.addWidget(self.xbox)
        self.column.addSpacing(px(4))
        self.column.addWidget(self.xbox_text)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.action = ""                                # Y's text in the legend: Check again, Update to x.y.z

    def fill(self, name: str, version: str, rows: Sequence[tuple[str, str]], status: str, action: str) -> None:
        self.name.setText(name)
        self.version.setText(version)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.action = action

    def set_wallpaper(self, name: str, refused: dict[str, str] | None = None) -> None:
        """The Wallpaper row: *name* (Off, Built-in or a picture's), and under it where pictures go, with the pictures
        in the folder that cannot be one (*refused*: name, why: the rule it breaks; the wiki has PICTURE_RULES)."""
        self.wallpaper.set_text(f"Wallpaper: {name}")
        text = f"Off, Built-in, or each picture in {WALLPAPER_FOLDER}. Transparency: the background over it."
        if refused:
            text += " Not used: " + "; ".join(f"{name} ({why})" for name, why in refused.items()) + "."
        self.wallpaper_text.setText(text)

    def set_transparency(self, percent: int) -> None:
        self.transparency.set_text(f"Transparency: {percent} %")

    def set_sound(self, on: bool) -> None:
        self.sound.set_text(f"Sound: {'On' if on else 'Off'}")

    def set_xbox(self, state: str) -> None:
        """The Xbox menu row: "" without the Xbox app (hidden), else what it says after "Xbox menu: "."""
        self.xbox.setVisible(bool(state))
        self.xbox_text.setVisible(bool(state))
        if state:
            self.xbox.set_text(f"Xbox menu: {state}")


__all__ = ["AppPane", "DetailsPane", "SuitePane", "Tabs", "TEXT"]
