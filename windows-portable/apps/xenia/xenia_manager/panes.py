# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the Xenia and Settings panes, as RPCS3 Manager has them: Your games (the games in the chosen
folders, marked for Steam with A), the folder browser, Log (Xenia's folder and the app's own log, read in the app) and
the SteamGridDB key.

A long list is a ListArea: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes down
a list of any length and a finger can drag it. Every action is a controller button in the window's legend, A too,
never a pill (owner, 29-10-2026: one way everywhere); the information texts name a button "the A button"."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QScroller, QVBoxLayout,
                             QWidget)

from bc250_core import covers
from bc250_core.portable import (AMBER, BODY, DIM, RAISED, ROW_HEIGHT, TEXT, InfoPill, Pane, Row, TextView,
                                 font, px, text_label)

from . import emulator

ROW = ROW_HEIGHT                        # a list's row, as a setting's


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
        """The list's (key, text) rows, in order; the rows of before go. The focus, when a row had it, stays on the
        row with its key (else the first row): a row taken away with the focus would hand it to the next card,
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

    def focused(self) -> str:
        """The key of the row with the focus, "" when none has it."""
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line. Its actions are on
    controller buttons, in the legend at the bottom of the window (owner, 29-10-2026), so it has no pills."""

    def __init__(self, title: str, info_title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        self.heading = text_label(title, 24, QFont.Weight.ExtraBold)
        heading.addWidget(self.heading)
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


XENIA_INFO = (
    "Xenia, the Xbox 360 emulator, installed for your own user: it keeps everything beside its program, its "
    "settings, the content of your games and their saves. The A button installs the build this version of the app "
    "was tried with; a newer Xenia comes with a new version of the app.\n\n"
    "Xenia needs no firmware: your games are all it needs (see Your games). Xenia for Windows needs Microsoft's "
    "Visual C++ runtime, which Steam and most games bring; the pane says when it is missing (vc_redist.x64.exe from "
    "Microsoft installs it). The X button removes Xenia's program; its folder, with your saves and its settings, "
    "stays.")
GAMES_INFO = (
    "Your Xbox 360 games, to play from Steam. Press the A button on a game to mark it for Steam, or to take the mark "
    "away; then the Y button (Update Steam) makes Steam match the marks: each marked game becomes a non-Steam game, "
    "\"[X360] <title>\", in Steam's library and its Big Picture mode, and a game without the mark is taken out. Steam "
    "closes for it and starts again. A game starts full screen. To quit a game, hold View and Menu together for two "
    "seconds: Xenia closes, and you are back where you started it. The same works in every game manager of the "
    "suite; Steam's own menu and its Exit game end it too.\n\n"
    "The X button starts the game the focus is on, through Steam, once Update Steam has put it there; Steam "
    "starts first when it is not open. On a device without Steam the X button starts the game in Xenia itself. "
    "Steam's library opens from the portal: RT Steam.\n\n"
    "The games are found in your game folders and up to six folders below them: a disc image (.iso), an unpacked "
    "disc (the default.xex in its folder), a .zar, and the packages of Games on Demand and Arcade titles, in the "
    "folders the console keeps them in (<title ID>\\00007000 or 000D0000).\n\n"
    "The LB button (Folders) shows your game folders: add one of the usual places or a drive (an SD card), or browse "
    "to any folder with the controller. The A button twice on a folder takes it off the list; its games stay where "
    "they are. The LB button again shows the games.\n\n"
    "The pictures in Steam are drawn from this app's icon, with the game's title. With your own SteamGridDB API key "
    "(the RB button, Steam artwork; one key for the suite), Update Steam fetches each game's pictures instead. Every "
    "entry of the row at the bottom also works by touch.")
BROWSE_INFO = (
    "Find the folder. The A button opens the folder the focus is on; the B button goes a level up, and from the "
    "places back to your folders. The X button takes the folder that is open as a game folder. The places are your "
    "Games, Downloads, Documents and Desktop folders and every drive, such as an SD card.")
LOG_INFO = (
    "Xenia's folder, where it keeps its settings, the content of your games and their saves, and the newest lines of "
    "this app's log. The A button, or a tap on this pane, shows the whole log here: the d-pad scrolls it, the B "
    f"button goes back. Xenia's own log is {emulator.LOG} in its folder, written anew each time it starts.")


class LogPane(Pane):
    """Xenia's folder and the newest lines of the log; show_whole() puts the whole log in a TextView in their place
    (owner, 29-10-2026: not in Notepad, which no button closes), show_summary() goes back."""

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
        # The newest lines in a view of their own, the last in sight: as a label they ran off the pane's top
        # (owner, 29-10-2026); the d-pad passes it by, and a tap goes to the pane: A or the tap shows the whole log
        self.lines = TextView(background="transparent")
        self.lines.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lines.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.column.addWidget(self.lines, 1)
        self.view = TextView()
        self.view.hide()
        self.column.addWidget(self.view, 1)

    @property
    def viewing(self) -> bool:
        return not self.view.isHidden()

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
        self.lines.setPlainText("\n".join(lines) or "Nothing logged yet.")
        self.lines.show_end()

    def show_whole(self, text: str) -> None:
        self.lines.hide()
        self.view.setPlainText(text or "Nothing logged yet.")
        self.view.show()
        self.view.show_end()                            # the newest lines first in view
        self.view.setFocus()

    def show_summary(self) -> None:
        self.view.hide()
        self.lines.show()
        self.lines.show_end()


# The key: the BC250 app's Covers… dialog (core's covers.edit_key) as a page of the portable window
KEY_TEXT = (
    "Steam's library shows each game with a cover, its page with a banner. The app draws them from the pictures "
    "inside the game. With a SteamGridDB API key, Update Steam looks each game up on SteamGridDB by its title and "
    "takes the cover with the most votes for the library instead.\n\n"
    "The key is free with a SteamGridDB account: in your account click Preferences, then the API tab at the top, "
    f"then Generate API Key, and copy the key ({covers.KEY_PAGE}). Copied in a browser on this device, the X button "
    "(Paste) puts it in the field and the A button saves it; the Y button (Remove key) takes a kept key out, on a "
    "second press. The B button goes back without saving.\n"
    "It is one key for every app of the suite. Leave it empty to look nothing up.")


class KeyPane(Pane):
    """The SteamGridDB key: the text and the field (masked, as the BC250 app's); A Save, X Paste and Y Remove key
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
