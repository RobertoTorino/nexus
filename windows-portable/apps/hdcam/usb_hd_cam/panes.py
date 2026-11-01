# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards: an InfoPane (a heading with the information icon, the rows of what was found and the
status line) for the Camera and Firmware cards, and a ListPane (a heading, a line, a list that scrolls and the status
line) for the Bandwidth card and the file browser, as the suite's managers have them.

A list is a ListArea: pills in a column that scrolls, the one with the focus kept in view, so the d-pad goes down a
list of any length and a finger can drag it. Every action is a controller button in the window's legend, A too,
never a pill (owner, 29-10-2026: one way everywhere); the information texts name a button "the A button"."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QScroller, QVBoxLayout, QWidget

from bc250_core.portable import AMBER, BODY, DIM, ROW_HEIGHT, InfoPill, Pane, Row, px, text_label


class ListArea(QScrollArea):
    """Pills in a column that scrolls; picked(key) when A or a tap acts on one."""

    picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }")
        self.setMinimumHeight(px(ROW_HEIGHT * 2 + 8))
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
        """The list's (key, text) rows, in order; the pills of before go. The focus, when a pill had it, stays on the
        row with its key (else the first row): a pill taken away with the focus would hand it to the next card."""
        old = self.pills
        had = next((key for key, pill in old.items() if pill.hasFocus()), None)
        self.pills, self._keys = {}, {}
        for n, (key, text) in enumerate(items):
            pill = Row(text)
            pill.activated.connect(lambda key=key: self.picked.emit(key))
            pill.installEventFilter(self)
            self.column.insertWidget(n, pill)
            if self.isVisible():
                pill.show()                             # shown now, so it can take the focus at once
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
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)


def _heading(pane: Pane, title: str, info_title: str, info: str) -> InfoPill:
    heading = QHBoxLayout()
    heading.addWidget(text_label(title, 24, QFont.Weight.ExtraBold))
    heading.addStretch()
    pill = InfoPill(info_title, info)
    heading.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
    pane.column.addLayout(heading)
    return pill


class InfoPane(Pane):
    """A heading with the information icon, a line under it, the rows of what was found (labels and values) and the
    status line. *action* is the legend's text for A."""

    def __init__(self, title: str, about: str, info: str, action: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.info = _heading(self, title, title, info)
        self.column.addWidget(text_label(about, BODY + 1, color=DIM, wrap=True))
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.action = action

    def show_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()                           # gone now, not when Qt deletes it later
                widget.deleteLater()
        for r, (label, value) in enumerate(rows):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)    # a long value wraps
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.info = _heading(self, title, title, info)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


class PicturePane(Pane):
    """A heading with the information icon, the mode under it, the camera's picture (preview.PictureView) and the
    status line."""

    def __init__(self, title: str, info: str, view: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.info = _heading(self, title, title, info)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.view = view
        self.column.addWidget(view, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
