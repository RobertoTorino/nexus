# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the Vita3K and Settings panes, as shadPS4 Manager has them: Your games (the games installed in
Vita3K, marked for Steam with A), the browser (the firmware file, a game to install), Log (Vita3K's folder and the
app's own log, read in the app) and the page with one text field (the package's license key, and the SteamGridDB
key).

A long list is a ListArea: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes down
a list of any length and a finger can drag it. Every action is a controller button in the window's legend, A too,
never a pill (owner, 29-10-2026: one way everywhere); the information texts name a button "the A button". A text
field is alone on its page (FieldPane), as the d-pad stays in a field and the touch keyboard covers half the screen."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QScroller, QVBoxLayout,
                             QWidget)

from bc250_core import covers
from bc250_core.portable import (AMBER, BODY, DIM, RAISED, ROW_HEIGHT, TEXT, InfoPill, Pane, Row, TextView,
                                 font, px, text_label)

from . import emulator, userdata

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


VITA3K_INFO = (
    "Vita3K, the PS Vita emulator, installed for your own user: it keeps everything in its folder (portable, beside "
    "its program), the firmware, your games, your saves and its settings. The A button installs the build this "
    "version of the app was tried with; a newer Vita3K comes with a new version of the app.\n\n"
    "Vita3K needs the PS Vita's firmware to start most games, which the app cannot give you: download the system "
    f"software from PlayStation's page ({userdata.FIRMWARE_PAGE}) and the font package from Sony "
    "(the pane's link), each a PSP2UPDAT.PUP, in a browser on this device, into Downloads. Then the LB button "
    "(Firmware) finds each file there and Vita3K installs it, without opening its window. The preinstalled apps are "
    "a third file, optional.\n\n"
    "The RB button (Install a game) finds your own dumps: a .vpk or .zip, or a dumped game folder (the X button on "
    "the open folder), which Vita3K installs and the app closes before the game starts; or a .pkg with its license "
    "key (a zRIF, starting with KO5i), which you paste on the next page. Vita3K installs a game in its storage, so "
    "the file may go afterwards.\n\n"
    "Vita3K for Windows needs Microsoft's Visual C++ runtime, which Steam and most games bring; the pane says when "
    "it is missing (vc_redist.x64.exe from Microsoft installs it). The X button removes Vita3K's program; its "
    "folder, with the firmware, your games and your saves, stays.")
GAMES_INFO = (
    "Your PS Vita games, to play from Steam: the games installed in Vita3K (the RB button on the Vita3K pane installs "
    "one). Press the A button on a game to mark it for Steam, or to take the mark away; then the Y button (Update "
    "Steam) makes Steam match the marks: each marked game becomes a non-Steam game, \"[PS Vita] <title>\", in "
    "Steam's library and its Big Picture mode, and a game without the mark is taken out. Steam closes for it and "
    "starts again. A game starts full screen. To quit a game, hold View, LB and RB together for two seconds: Vita3K "
    "closes, and you are back where you started it. The same works in every game manager of the suite.\n\n"
    "The X button on a game that is in Steam starts it, through Steam (Steam starts first when it does not run). "
    "On a device without Steam the X button starts the game in Vita3K itself. Steam's library opens from the "
    "portal: RT Steam.\n\n"
    "The pictures in Steam come from inside each game (its icon and its LiveArea picture). With your own "
    "SteamGridDB API key (the RB button, Steam artwork; one key for the suite), Update Steam also fetches a cover for "
    "each game. Every entry of the row at the bottom also works by touch.")
BROWSE_INFO = (
    "Find the file. The A button opens the folder the focus is on, or picks the file; the B button goes a level up, "
    "and from the places back to where you came from. When a game is a dumped folder (with sce_sys and eboot.bin), "
    "open that folder and press the X button. The places are your Games, Downloads, Documents and Desktop folders "
    "and every drive, such as an SD card. The browser opens again in the folder you took or picked a file in last.")
LOG_INFO = (
    "Vita3K's folder, where it keeps the firmware, your games, the saves and its settings, and the newest lines of "
    "this app's log. The A button, or a tap on this pane, shows the whole log here: the d-pad scrolls it, the B "
    f"button goes back. Vita3K's own log is {emulator.PORTABLE}\\{userdata.LOG} in its folder, written anew each time "
    "it starts.")


class LogPane(Pane):
    """Vita3K's folder and the newest lines of the log; show_whole() puts the whole log in a TextView in their place
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
        # The newest lines in a view of their own with its end in view (owner, 29-10-2026: as a label they were cut
        # off at the top); the d-pad never lands on it, a tap shows the whole log as the A button does
        self.lines = TextView()
        self.lines.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lines.viewport().installEventFilter(self)
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

    def eventFilter(self, obj, event) -> bool:
        if obj is self.lines.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            self.tapped.emit()
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.lines.show_end()                           # laid out now: the newest line at the bottom

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
# The package's license: the BC250 app's question for the zRIF, as a page
ZRIF_TEXT = (
    "A .pkg installs only with its license key, a zRIF: a long line of letters and digits that starts with KO5i, as "
    "the list you got the package from gives it. Copy it in a browser on this device, then the X button (Paste) puts "
    "it in the field and the A button installs the package; Vita3K does it without its window. The key is used for "
    "this install and kept nowhere. The B button goes back without installing.")


class FieldPane(Pane):
    """One text field on a page of its own: a heading, what it is for, the field and the status line; A and X Paste
    are in the legend (and, for the key, Y Remove key). set_field() makes it the page of another field."""

    def __init__(self, title: str = "", text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.heading = text_label(title, 24, QFont.Weight.ExtraBold)
        self.column.addWidget(self.heading)
        self.column.addSpacing(px(6))
        self.text = text_label(text, BODY + 1, color=DIM, wrap=True)
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

    def set_field(self, title: str, text: str, value: str = "", hidden: bool = False, placeholder: str = "",
                  length: int = 32767) -> None:
        self.heading.setText(title)
        self.text.setText(text)
        self.field.setEchoMode(QLineEdit.EchoMode.Password if hidden else QLineEdit.EchoMode.Normal)
        self.field.setPlaceholderText(placeholder)
        self.field.setMaxLength(length)
        self.field.setText(value)
        self.status.setText("")


class KeyPane(FieldPane):
    """The SteamGridDB key: the text and the field (masked, as the BC250 app's)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Steam artwork", KEY_TEXT, parent)
        self.field.setEchoMode(QLineEdit.EchoMode.Password)
        self.field.setPlaceholderText("Your SteamGridDB API key")
