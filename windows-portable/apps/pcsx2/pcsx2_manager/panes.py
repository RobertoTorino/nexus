# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the PCSX2 and Settings panes, the BC250 suite's PCSX2 Manager's tabs in the portable design: Your
games (the games in the chosen folders, played on A, in Steam or not), Memory cards (the cards in PCSX2's memcards
folder and the saves on each) and Log (PCSX2's last run and the app's own log).

A long list is a ListArea: pills in a column that scrolls, the one with the focus kept in view, so the d-pad goes
down a list of any length and a finger can drag it. A pane's actions with a controller button (X, Y, LB, RB) are in
the window's legend, not on pills (owner, 29-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QScroller, QVBoxLayout,
                             QWidget)

from bc250_core import covers

from bc250_core.portable import (AMBER, BODY, DIM, RAISED, ROW_HEIGHT, TEXT, InfoPill, Pane, Pill, Row, font,
                                 pill_row, px, text_label)

ROW = ROW_HEIGHT                        # a list's row, as a setting's


class ListArea(QScrollArea):
    """Pills in a column that scrolls; picked(key) when A or a tap acts on one, current(key) when one gets the
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
        """The list's (key, text) rows, in order; the pills of before go. The focus, when a pill had it, stays on the
        row with its key (else the first row): a pill taken away with the focus would hand it to the next card,
        and that card's pane would take this one's place."""
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
            self.current.emit(self._keys[obj])
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line. Its actions are on
    controller buttons, in the legend at the bottom of the window (owner, 29-10-2026), so it has no pills."""

    def __init__(self, title: str, info_title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label(title, 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill(info_title, info)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


GAMES_INFO = (
    "A on a game plays it in PCSX2, alone and full screen; X marks it for Steam or takes the mark away, and Y Update "
    "Steam makes Steam's shortcuts match the marks: each marked game a non-Steam game, \"[PS2] <title>\", in Steam's "
    "library and its Big Picture mode, started the same way. Steam closes for it and starts again.\n\n"
    "Games are the disc images (ISO, CHD, CSO, ZSO, GZ) in your game folders and up to five folders below them. An ISO "
    "is read for its serial, and the title comes from PCSX2's own list of games; a compressed image keeps its file's "
    "name. LB Folders shows the folders: add one of the usual places, a drive (an SD card), or choose any folder; A "
    "twice on a folder takes it off the list (its games stay where they are). LB Games shows the games again.\n\n"
    "Pictures for Steam: with your own SteamGridDB API key (RB Steam artwork keeps it, one key for the suite), Update "
    "Steam fetches each game's pictures; without one, they are drawn from the app's icon. The buttons at the bottom "
    "also work by touch.")
CARDS_INFO = (
    "The PS2 memory cards in PCSX2's memcards folder, with the slot PCSX2 puts each in. A on a card shows its saves; "
    "A on ‹ The cards goes back. X New card makes an 8 MB card, as the PS2's own; Y Copy card copies the card "
    "the focus was on last, under a new name, with its saves. A card is never changed while PCSX2 runs: it keeps the "
    "card in memory and would write its own copy over the change.")
LOG_INFO = ("PCSX2's last run as its own log tells it (it writes the log over at every start), the play time it "
            "counted, and the newest lines of this app's log. Open the log shows the whole file.")


class LogPane(Pane):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Log", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("The log", LOG_INFO)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(8))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addSpacing(px(10))
        self.lines = text_label("", BODY, color=DIM, wrap=True)
        self.lines.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.column.addWidget(self.lines, 1, Qt.AlignmentFlag.AlignTop)
        self.column.addStretch()
        self.open = Pill("Open the log", "A", main=True)
        self.column.addLayout(pill_row(self.open))

    def fill(self, rows: Sequence[tuple[str, str]], lines: Sequence[str]) -> None:
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
        self.lines.setText("\n".join(lines) or "Nothing logged yet.")


# The key: the BC250 app's Steam artwork… dialog (core's covers.edit_key) as a page of the portable window
KEY_TEXT = (
    "Steam's library shows each game with a cover, its page with a banner. A PS2 disc brings no pictures in Steam's "
    "shapes, so the app draws them. With a SteamGridDB API key, Update Steam looks each game up on SteamGridDB by "
    "its title and takes the pictures with the most votes instead.\n\n"
    "The key is free with a SteamGridDB account: in your account click Preferences, then the API tab at the top, "
    f"then Generate API Key, and copy the key ({covers.KEY_PAGE}). Copied in a browser on this device, X Paste puts "
    "it in the field; Y Remove key takes a kept key out, on a second press.\n"
    "It is one key for every app of the suite. Leave it empty to look nothing up.")


class KeyPane(Pane):
    """The SteamGridDB key: the text, the field (masked, as the BC250 app's) and A Save; X Paste and Y Remove key
    are in the legend."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.addWidget(text_label("Steam artwork", 24, QFont.Weight.ExtraBold))
        self.column.addSpacing(px(6))
        self.column.addWidget(text_label(KEY_TEXT, BODY + 1, color=DIM, wrap=True))
        self.column.addSpacing(px(12))
        self.field = QLineEdit()
        self.field.setEchoMode(QLineEdit.EchoMode.Password)
        self.field.setPlaceholderText("Your SteamGridDB API key")
        self.field.setFont(font(BODY + 2))
        self.field.setMinimumHeight(px(44))
        self.field.setStyleSheet(f"QLineEdit {{ color: {TEXT}; background: {RAISED}; border: none; "
                                 f"border-radius: {px(10)}px; padding: 0 {px(12)}px; }}")
        self.column.addWidget(self.field)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.column.addSpacing(px(6))
        self.save = Pill("Save", "A", main=True)
        self.column.addLayout(pill_row(self.save))
