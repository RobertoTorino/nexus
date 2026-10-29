# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's own widgets on the portable window: the tabs (LB and RB step through the categories), the strip
under the tiles (what the focused app is and does, with its pills), the details page of an app and the Suite page
(the portal's own version and update). Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from bc250_core.portable import AMBER, BODY, DIM, TAB, TEXT, Glyph, Pane, Pill, Row, pill_row, px, text_label

NAME = 24                               # pt: the name at the top of a pane


class _TabLabel(QLabel):
    pressed = pyqtSignal(str)

    def __init__(self, key: str, name: str):
        super().__init__(name)
        self.key = key
        self.setFont(text_label("", TAB, QFont.Weight.Bold).font())
        self.setContentsMargins(px(4), 0, px(4), px(6))
        self.paint(False)

    def paint(self, selected: bool) -> None:
        line = f"{px(3)}px solid {AMBER if selected else 'transparent'}"
        self.setStyleSheet(f"color: {AMBER if selected else DIM}; background: transparent; border-bottom: {line};")

    def mousePressEvent(self, event) -> None:
        self.pressed.emit(self.key)
        event.accept()


class Tabs(QWidget):
    """The categories as tabs between the LB and RB glyphs: those buttons step through them, a tap picks one; the
    selected tab is amber with a line under it."""

    changed = pyqtSignal(str)

    def __init__(self, tabs: Sequence[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(px(14))
        self.keys = [key for key, _ in tabs]
        self.labels: dict[str, _TabLabel] = {}
        self.current = ""
        row.addWidget(Glyph("LB"))
        for key, name in tabs:
            label = _TabLabel(key, name)
            label.pressed.connect(self.select)
            self.labels[key] = label
            row.addWidget(label)
        row.addWidget(Glyph("RB"))
        row.addStretch()
        if self.keys:
            self.select(self.keys[0])

    def select(self, key: str) -> None:
        if key not in self.labels or key == self.current:
            return
        self.current = key
        for other, label in self.labels.items():
            label.paint(other == key)
        self.changed.emit(key)

    def step(self, delta: int) -> None:
        """LB (-1) or RB (+1): the next tab round."""
        if not self.keys:
            return
        at = self.keys.index(self.current) if self.current in self.keys else 0
        self.select(self.keys[(at + delta) % len(self.keys)])


class AppPane(Pane):
    """The strip under the tiles: the focused app's name, its versions and one line of what it does, with the pills
    for touch (A Install or Open, Y Update) so the strip keeps showing what A does."""

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
        self.other = Pill("Update", "Y")
        self.main = Pill("Open", "A", main=True)
        row.addWidget(self.other, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.main, 0, Qt.AlignmentFlag.AlignVCenter)
        self.column.addLayout(row)

    def fill(self, name: str, versions: str, summary: str, status: str, main: str, other: str) -> None:
        """The texts, and the pills: a pill without a text is hidden (no Y without an update)."""
        self.name.setText(name)
        self.versions.setText(versions)
        self.summary.setText(summary)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        for pill, text in ((self.main, main), (self.other, other)):
            pill.set_text(text)
            pill.setVisible(bool(text))


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
    """An app's details page (X): its versions, where it is and what it does, with Open (A) and Remove (Y)."""

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
        self.remove = Pill("Remove", "Y")
        self.open = Pill("Open", "A", main=True)
        self.column.addLayout(pill_row(self.remove, self.open))

    def fill(self, name: str, summary: str, rows: Sequence[tuple[str, str]], status: str, can_open: bool,
             can_remove: bool, remove_text: str = "Remove") -> None:
        self.name.setText(name)
        self.summary.setText(summary)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.open.setVisible(can_open)
        self.remove.set_text(remove_text)
        self.remove.setVisible(can_remove)


class SuitePane(Pane):
    """The Suite page (Start or View): the portal's own version, the newest release on GitHub and what it changes,
    with Update (A) when there is a newer one."""

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
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.action = Pill("Check again", "A", main=True)
        self.column.addLayout(pill_row(self.action))

    def fill(self, name: str, version: str, rows: Sequence[tuple[str, str]], status: str, action: str) -> None:
        self.name.setText(name)
        self.version.setText(version)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.action.set_text(action)
        self.action.setVisible(bool(action))


class SettingsPane(Pane):
    """The Settings page (View): the portal's own settings, a row each that A switches (owner, 28-10-2026: the
    wallpaper on or off), with a line under it of what it does."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.addWidget(text_label("Settings", NAME, QFont.Weight.ExtraBold))
        self.column.addWidget(text_label("How the portal looks. A switches the focused setting; it is kept for the "
                                         "next start.", BODY + 1, color=DIM, wrap=True))
        self.column.addSpacing(px(16))
        self.wallpaper = Row("Wallpaper: On")
        self.column.addWidget(self.wallpaper)
        self.column.addSpacing(px(4))
        self.column.addWidget(text_label("A picture behind the tiles, which show it through them, in every app "
                                         "of the suite.", BODY + 1, color=DIM, wrap=True))
        self.column.addStretch()

    def fill(self, wallpaper: bool) -> None:
        self.wallpaper.set_text(f"Wallpaper: {'On' if wallpaper else 'Off'}")


__all__ = ["AppPane", "DetailsPane", "SettingsPane", "SuitePane", "Tabs", "TEXT"]
