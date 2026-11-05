# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards: Windows (its version and its updates), Tools and Apps (lists). A long list is a
ListArea, as Xenia Manager's: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes
down a list of any length and a finger can drag it. The row with the focus says more on the pane's status line.
Every action is a controller button in the window's legend, never a pill (owner, 29-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QScroller, QVBoxLayout, QWidget

from bc250_core.portable import (AMBER, BODY, DIM, ROW_HEIGHT, InfoPill, Pane, Row, px, text_label)

ROW = ROW_HEIGHT

WINDOWS_INFO = (
    "Windows' version, and its updates. Windows Update installs them by itself, and an update often takes effect "
    "only at the next restart, so one can wait for days unnoticed: the card then says Restart to update. It says "
    f"Update late when the newest update Windows installed is more than 40 days old (Windows brings one every "
    "month): open Settings, Windows Update.\n\n"
    "The app only reads this (the registry, and the list of installed updates); installing updates stays "
    "Windows'. The Y button checks again.")
TOOLS_INFO = (
    "What the suite's apps need on this handheld besides themselves: Windows' own tools, Microsoft's Visual C++ "
    "runtime, Steam and the XBOX app. Each row says whether it is there:\n\n"
    "Available: found (the line below says where). Missing: an installed app needs it and it is not there. Not "
    "installed: not there, but the installed apps that use it work without it. Unsupported build: there, in a form "
    "the apps cannot use. Not needed: no installed app uses it.\n\n"
    "The line under the list says which installed apps use the row with the focus, where it was found, and how to "
    "get it when it is not there. The app only looks; it installs nothing.")


def tools_info() -> str:
    """TOOLS_INFO, then what each tool is (checks.TOOLS)."""
    from .checks import TOOLS
    return TOOLS_INFO + "".join(f"\n\n{tool.name}: {tool.about}" for tool in TOOLS)
APPS_INFO = (
    "The suite's apps, as the portal lists them: the version installed against the one the portal brings. Up to "
    "date: the portal's. Update in the portal: an older one, which the portal's Y button updates. Version unknown: "
    "the app is there, but was not installed by the portal. Not installed: not on this handheld.\n\n"
    "Every app is a program with what it needs inside, tested with it: an app is brought up to date as a whole, "
    "by the portal.")


class ListArea(QScrollArea):
    """Rows in a column that scrolls; current(key) when one gets the focus."""

    current = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }")
        self.setMinimumHeight(px(ROW * 2 + 8))
        self.inner = QWidget()
        self.column = QVBoxLayout(self.inner)
        self.column.setContentsMargins(0, 0, px(4), 0)
        self.column.setSpacing(px(6))
        self.column.addStretch()
        self.setWidget(self.inner)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)  # a finger drags
        self.pills: dict[str, Row] = {}
        self._keys: dict[QObject, str] = {}

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        """The list's (key, text) rows, in order; the focus, when a row had it, stays on the row with its key."""
        old = self.pills
        had = next((key for key, pill in old.items() if pill.hasFocus()), None)
        self.pills, self._keys = {}, {}
        for n, (key, text) in enumerate(items):
            pill = Row(text)
            pill.activated.connect(lambda key=key: self.current.emit(key))
            pill.installEventFilter(self)
            self.column.insertWidget(n, pill)
            if self.isVisible():
                pill.show()
            self.pills[key] = pill
            self._keys[pill] = key
        if had is not None:
            keep = self.pills.get(had) or self.first()
            if keep is not None:
                keep.setFocus()
        for pill in old.values():
            pill.removeEventFilter(self)
            pill.hide()
            pill.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FocusIn and obj in self._keys:
            self.ensureWidgetVisible(obj, 0, px(8))
            self.current.emit(self._keys[obj])
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)

    def focused(self) -> str:
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label(title, 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill(title, info)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


class WindowsPane(Pane):
    """Windows: its rows (label and value) and the status line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Windows", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("Windows", WINDOWS_INFO)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def fill(self, rows: Sequence[tuple[str, str]], status: str) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for r, (label, value) in enumerate(rows):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)
        self.status.setText(status)
