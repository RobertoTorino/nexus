# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards: an InfoPane (a heading with the information icon, the rows of what was found and the
status line) for the BIOS file and the device, a ListPane (a heading, a line, a list that scrolls and the status
line) for the pages and the file browser, and a ScreenPane for one menu of the setup screens (its title, where it
is, its lines with their values, the focused line's value and default, the status line), as USB HD Cam has them.

A list is a ListArea: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes down a
list of any length and a finger can drag it. A menu's subtitles are plain text between its rows: the d-pad never
lands on them. Every action is a controller button in the window's legend, A too, never a pill (owner, 29-10-2026:
one way everywhere); the information texts name a button "the A button"."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QScroller, QSizePolicy, QVBoxLayout, QWidget

from bc250_core.portable import AMBER, BODY, DIM, PILL, ROW_HEIGHT, TEXT, InfoPill, Pane, Row, px, text_label

from .screens import Entry

LINK = "›"                                 # a link's mark at the row's right end


class ValueRow(Row):
    """A row with the setting's value at its right end; a hidden one dimmed and in italics, a locked one dimmed."""

    def __init__(self, prompt: str, value: str = "", dim: bool = False, italic: bool = False,
                 parent: QWidget | None = None):
        super().__init__(prompt, parent)
        self.dim, self.italic = dim, italic
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)   # a long prompt is cut
        self.value = text_label(value, PILL - 1, QFont.Weight.DemiBold)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.layout().addWidget(self.value)
        for label in (self.label, self.value):
            shown = label.font()
            shown.setItalic(italic)
            label.setFont(shown)
        self._colors()

    def _colors(self) -> None:
        color = DIM if getattr(self, "dim", False) or not self.isEnabled() else TEXT
        self.label.setStyleSheet(f"color: {color}; background: transparent;")
        if hasattr(self, "value"):
            self.value.setStyleSheet(f"color: {color}; background: transparent;")


class ListArea(QScrollArea):
    """Rows in a column that scrolls; picked(key) when A or a tap acts on one, current(key) when one takes the
    focus."""

    picked = pyqtSignal(str)
    current = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A thin bar of where in the list it is, no arrows: the d-pad and a finger scroll (as core's TextView)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }"
                           f" QScrollBar:vertical {{ background: transparent; width: {px(6)}px; margin: 0; }}"
                           f" QScrollBar::handle:vertical {{ background: {DIM}; border-radius: {px(3)}px;"
                           f" min-height: {px(24)}px; }}"
                           " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                           " QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")
        self.setMinimumHeight(px(ROW_HEIGHT * 2 + 8))
        self.inner = QWidget()
        self.column = QVBoxLayout(self.inner)
        self.column.setContentsMargins(0, 0, px(4), 0)
        self.column.setSpacing(px(6))
        self.column.addStretch()
        self.setWidget(self.inner)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)  # a finger drags
        self.pills: dict[str, Row] = {}
        self.widgets: list[QWidget] = []                # the rows and the subtitles, in order
        self._keys: dict[QObject, str] = {}

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        """The list's (key, text) rows, in order; the rows of before go."""
        self._fill([(key, Row(text)) for key, text in items])

    def set_entries(self, entries: Sequence[Entry]) -> None:
        """A menu's lines: a subtitle as text, every other line a row keyed by its place in *entries*."""
        rows: list[tuple[str, QWidget]] = []
        for n, entry in enumerate(entries):
            if entry.statement is None:
                heading = text_label(entry.prompt, BODY, QFont.Weight.Bold, AMBER)
                heading.setContentsMargins(px(4), px(6), 0, 0)
                rows.append(("", heading))
                continue
            value = LINK if entry.link else (f"[{entry.value}]" if entry.value and entry.statement.is_question
                                             else entry.value)
            rows.append((str(n), ValueRow(entry.prompt, value, dim=entry.hidden or entry.grayed,
                                          italic=entry.hidden)))
        self._fill(rows)

    def _fill(self, rows: Sequence[tuple[str, QWidget]]) -> None:
        """The rows of before go: a row taken away with the focus would hand it to the next card, so the focus, when
        a row had it, moves to the row with its key (else the first row)."""
        old, old_widgets = self.pills, self.widgets
        had = next((key for key, pill in old.items() if pill.hasFocus()), None)
        self.pills, self._keys, self.widgets = {}, {}, []
        for n, (key, widget) in enumerate(rows):
            self.column.insertWidget(n, widget)
            if self.isVisible():
                widget.show()                           # shown now, so it can take the focus at once
            self.widgets.append(widget)
            if key and isinstance(widget, Row):
                widget.activated.connect(lambda key=key: self.picked.emit(key))
                widget.installEventFilter(self)
                self.pills[key] = widget
                self._keys[widget] = key
        if had is not None:
            keep = self.pills.get(had) or self.first()
            if keep is not None:
                keep.setFocus()
        for widget in old_widgets:
            widget.removeEventFilter(self)
            widget.hide()
            widget.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FocusIn and obj in self._keys:
            self.ensureWidgetVisible(obj, 0, px(8))
            self.current.emit(self._keys[obj])
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)

    def focused(self) -> str:
        """The key of the row with the focus, "" when none has it."""
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")


def _heading(pane: Pane, title: str, info_title: str, info: str) -> tuple[QHBoxLayout, InfoPill]:
    heading = QHBoxLayout()
    label = text_label(title, 24, QFont.Weight.ExtraBold)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)        # a long title is cut
    heading.addWidget(label, 1)
    pill = InfoPill(info_title, info)
    heading.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
    pane.column.addLayout(heading)
    pane.title = label
    return heading, pill


class InfoPane(Pane):
    """A heading with the information icon, a line under it, the rows of what was found (labels and values) and the
    status line. *action* is the legend's text for A."""

    def __init__(self, title: str, about: str, info: str, action: str, parent: QWidget | None = None):
        super().__init__(parent)
        _, self.info = _heading(self, title, title, info)
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

    def rows(self) -> list[tuple[str, str]]:
        """What show_rows() shows, for the tests."""
        cells = [self.grid.itemAt(i).widget().text() for i in range(self.grid.count())]
        return list(zip(cells[::2], cells[1::2]))


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        _, self.info = _heading(self, title, title, info)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


class ScreenPane(Pane):
    """One menu of the setup screens: its title with the information icon (the focused line's whole text), where it
    is (the menus above it), its lines, the focused line's value and default under them, and the status line."""

    def __init__(self, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.about = info                               # the icon's text while no line has the focus
        _, self.info = _heading(self, "", "Setup screens", info)
        self.path = text_label("", BODY, color=DIM, wrap=True)
        self.column.addWidget(self.path)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.column.addSpacing(px(6))
        self.line = text_label("", BODY + 1, color=TEXT, wrap=True)
        self.line.setMinimumHeight(px(BODY * 2 * 1.5))
        self.line.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.column.addWidget(self.line)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def set_detail(self, title: str, text: str) -> None:
        """What the information icon shows: the focused line's whole text (or what the pane is, without one)."""
        self.info.title = title or "Setup screens"
        self.info.info = text or self.about
