# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards, as the suite's apps have them (sFTP Tools' panes.py): a ListPane (a heading with the
information icon, a line under it, a list that scrolls and the status line) for every card, which can show a long text
in place of its list (show_text(): the log), the d-pad scrolling it, and the page with one text field (FieldPane) for
the header's text and the weather's place. Preview is the picture the screen shows, beside the panes.

A list is a ListArea: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes down a
list of any length and a finger can drag it. Every action is a controller button in the window's legend, A too, never
a pill (owner, 29-10-2026: one way everywhere); the information texts name a button "the A button". A text field is
alone on its page, as the d-pad stays in a field and the touch keyboard covers half the screen."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QScroller, QSizePolicy, QVBoxLayout,
                             QWidget)

from bc250_core.portable import (AMBER, BODY, DIM, RAISED, ROW_HEIGHT, TEXT, InfoPill, Pane, Row, TextView, font, px,
                                 text_label)


class ListArea(QScrollArea):
    """Rows in a column that scrolls; picked(key) when A or a tap acts on one, current(key) when one gets the
    focus."""

    picked = pyqtSignal(str)
    current = pyqtSignal(str)

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

    def set_items(self, items: Sequence[tuple[str, str]], focus: str = "") -> None:
        """The list's (key, text) rows, in order; the rows of before go. The focus, when a row had it, goes to the
        row with *focus*'s key, else stays on the row with its own (else the first row): a row taken away with the
        focus would hand it to the next card, and that card's pane would take this one's place. The same keys again only change the texts (the
        Transfers card, every second while one moves)."""
        if [key for key, _text in items] == list(self.pills):
            for key, text in items:
                self.pills[key].set_text(text)
            return
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
            keep = self.pills.get(focus) or self.pills.get(had) or self.first()
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
        """The key of the row with the focus, "" when none has it."""
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")

    def focus(self, key: str) -> bool:
        """The focus on the row with *key* (else the first one); whether there was a row."""
        pill = self.pills.get(key) or self.first()
        if pill is None:
            return False
        pill.setFocus()
        return True


class _Page(Pane):
    """A heading with the information icon, a line under it, the pane's body, a text view in its place while one is
    read (show_text) and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        self.heading = text_label(title, 24, QFont.Weight.ExtraBold)
        heading.addWidget(self.heading)
        heading.addStretch()
        self.info = InfoPill(title, info)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.body = QWidget()
        self.body_column = QVBoxLayout(self.body)
        self.body_column.setContentsMargins(0, 0, 0, 0)
        self.column.addWidget(self.body, 1)
        self.view = TextView()
        self.view.hide()
        self.column.addWidget(self.view, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.text_title = ""                            # what the view shows: "" while the body shows

    @property
    def viewing(self) -> bool:
        return not self.view.isHidden()

    def show_text(self, title: str, text: str, end: bool = False) -> None:
        """*text* in place of the body, the focus on it (the d-pad scrolls it, B goes back: show_body); at its end
        with *end* (a log's newest lines). The view takes the focus before the body hides: a row hidden with the focus
        would hand it to the first card, and that card's pane would take this one's place."""
        self.text_title = title
        self.view.setPlainText(text)
        self.view.show()
        self.view.setFocus()
        self.body.hide()
        if end:
            self.view.show_end()
        else:
            self.view.verticalScrollBar().setValue(0)

    def show_body(self) -> None:
        self.text_title = ""
        self.view.hide()
        self.view.clear()
        self.body.show()


class ListPane(_Page):
    """A heading with the information icon, a line under it, a ListArea and the status line."""

    def __init__(self, title: str, info: str, parent: QWidget | None = None):
        super().__init__(title, info, parent)
        self.list = ListArea()
        self.body_column.addWidget(self.list, 1)


class FieldPane(Pane):
    """One text field on a page of its own: a heading, what it is for, the field and the status line; A Keep and
    X Paste are in the legend, with R3 for the touch keyboard. set_field() makes it the page of another field."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading = text_label("", 24, QFont.Weight.ExtraBold)
        self.column.addWidget(self.heading)
        self.column.addSpacing(px(6))
        self.text = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.text)
        self.column.addSpacing(px(12))
        self.field = QLineEdit()
        self.field.setFont(font(BODY + 2))
        self.field.setMinimumHeight(px(44))
        self.field.setStyleSheet(f"QLineEdit {{ color: {TEXT}; background: {RAISED}; border: none; "
                                 f"border-radius: {px(10)}px; padding: 0 {px(12)}px; }}")
        self.column.addWidget(self.field)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.key = ""                                   # which field it is (the window's name for it)

    def set_field(self, key: str, title: str, text: str, value: str, hidden: bool = False, placeholder: str = "",
                  length: int = 32767) -> None:
        self.key = key
        self.heading.setText(title)
        self.text.setText(text)
        self.field.setEchoMode(QLineEdit.EchoMode.Password if hidden else QLineEdit.EchoMode.Normal)
        self.field.setPlaceholderText(placeholder)
        self.field.setMaxLength(length)
        self.field.setText(value)
        self.status.setText("")


class Preview(QLabel):
    """What the screen shows, upright, as large as the room beside the panes allows (owner, 02-11-2026: a fixed square
    left a portrait picture small): the whole height of the body, its width following the picture's shape, at most
    *widest* (logical px) so a landscape picture leaves the panes their room."""

    MINIMUM = 200                                       # logical px high: the window's layout never asks for more

    def __init__(self, widest: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.widest = widest
        self.image: QImage | None = None
        self.aspect = 2 / 3                             # width / height; the Turing 3.5" standing until a picture
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(px(self.MINIMUM))
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._fit()

    def show_image(self, image: QImage) -> None:
        self.image = image
        aspect = image.width() / image.height() if image.height() else self.aspect
        if aspect != self.aspect:
            self.aspect = aspect
            self._fit()
        self._draw()

    def _fit(self) -> None:
        """The width for the picture at the whole height, at most *widest*."""
        width = min(px(self.widest), max(1, round(self.height() * self.aspect)))
        if width != self.width() or self.minimumWidth() != width:
            self.setFixedWidth(width)

    def _draw(self) -> None:
        if self.image is None or self.width() < 2 or self.height() < 2:
            return
        self.setPixmap(QPixmap.fromImage(self.image).scaled(self.width(), self.height(),
                                                            Qt.AspectRatioMode.KeepAspectRatio,
                                                            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._fit()
        self._draw()
