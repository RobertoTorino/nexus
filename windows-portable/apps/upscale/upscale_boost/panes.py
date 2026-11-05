# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards, as Xenia Manager has them: HelixSR (the payload, its build and its output), the lists
(Games, Deployments, and the pages they open: OptiScaler, NVIDIA's DLL, Apply to a game, the folder browser), the
Settings (helixsr.ini in tabs) and the Log.

A long list is a ListArea: rows in a column that scrolls, the one with the focus kept in view, so the d-pad goes down
a list of any length and a finger can drag it. Every action is a controller button in the window's legend, A too,
never a pill (owner, 29-10-2026: one way everywhere); the information texts name a button "the A button". Text that
does not fit a pane is behind its information icon (owner, 01-11-2026: an info symbol where space is limited)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QScroller, QStackedWidget, QVBoxLayout, \
    QWidget

from bc250_core.portable import AMBER, BODY, DIM, ROW_HEIGHT, InfoPill, Pane, Row, Tabs, TextView, px, text_label

from . import HELIXSR_URL, OPTISCALER_URL
from .acquire import DLSS_DLL, FALLBACK_VERSION, SUPPORTED_MAJOR
from .backend import SECOND_UPSCALER_DLL
from .ini_settings import TABS

ROW = ROW_HEIGHT                        # a list's row, as a setting's
CHECK_AT_START = "check_at_start"       # the Settings card's row of the app's own setting, beside helixsr.ini's

HELIXSR_INFO = (
    "HelixSR runs NVIDIA's DLSS upscaling network on AMD graphics: a game talks to it as AMD FSR 3.1. Its network is "
    "built on this PC from NVIDIA's DLSS DLL; that build is NVIDIA's property, for this PC only, and never part of "
    "this app.\n\n"
    "The A button (Get HelixSR) downloads the newest HelixSR release from GitHub, checked against the SHA-256 GitHub "
    "publishes for it, then what HelixSR's own setup pins, at the same time and each checked: NVIDIA's DLSS 310.7.0 "
    "DLL, Python with numpy, and Microsoft's DirectX Shader Compiler. Then it runs HelixSR's own builder, unchanged, "
    "and keeps the result as the payload, what the app puts into your games. NVIDIA's DLL is deleted afterwards. It "
    "takes a few minutes and about 1.5 GB of free space while it runs; the X button cancels it. Frame generation is "
    "not built: the app does not put it in. HelixSR's own setup would go on to install HelixSR into every game it "
    "finds; the app leaves your games to the Games and Deployments cards.\n\n"
    f"The app sets up HelixSR 1.x and {SUPPORTED_MAJOR}.x. When a later major version is out, the pane says so and "
    "the app keeps getting the newest release it supports.\n\n"
    f"The LB button switches the version to get: the latest release, or HelixSR {FALLBACK_VERSION}, the version "
    "HelixSR's developer recommends when the latest one does not work for you (then please open an issue at "
    f"{HELIXSR_URL}/issues with the game's helixsr.log). {FALLBACK_VERSION} also brings OptiScaler, which the payload "
    "keeps when you switch back. After a switch, Get HelixSR builds that version; then the Deployments card's RB "
    "button puts it into your games.\n\n"
    f"The RB button (NVIDIA's DLL) takes a {DLSS_DLL} 310.7.0 from a game you own instead of NVIDIA's download: Find "
    "in Steam compares checksums and offers only the exact build HelixSR pins.\n\n"
    "The Y button checks GitHub for a newer HelixSR (also at every start, unless the Settings card's More tab turns "
    "that off). The app itself is updated by the portal.\n\n"
    "The LT button (Import) takes a HelixSR release you built yourself: the X button on its folder, or the A button "
    "on its zip. Only HelixSR's own files are copied.")
GAMES_INFO = (
    "Every Steam game on this handheld, and the folders you added, each looked through for an AMD FSR 3.1 DLL. "
    "HelixSR goes in place of that DLL, so only the games that ship one can use it: they come first.\n\n"
    "The A button (Run with HelixSR) puts HelixSR in when it is not there yet, again after a game update put the "
    "game's own DLL back, or when the payload has a newer build, then starts the game through Steam. The first time "
    "for a game it asks for a second press. It does nothing while the game runs: HelixSR goes in before the game "
    "starts. Choose AMD FSR in the game's graphics settings. For a folder you added the A button puts HelixSR in; "
    "start the game as you always do.\n\n"
    "The game's own file is kept as .original.dll. The Y button (Go back) deletes HelixSR's files and gives it its "
    "name back, on a second press.\n\n"
    "A game that only offers DLSS, XeSS or FSR 2 can still use HelixSR through OptiScaler: the X button.\n\n"
    "The LB button adds a game folder that is not in Steam (another store's, or a copy of your own): open a place, "
    "then the folder, and the X button adds it. The RB button takes an added folder off the list; the game stays. "
    "The LT button reads the games again.")
DEPLOY_INFO = (
    "Every place the app put HelixSR, with its state now. In place: the payload's HelixSR. Older build: the payload "
    "was updated since. Newer build: the payload went back to the fallback version. Original restored: a game update "
    "or Steam's file check put the game's own DLL back. Network files missing, Only the backup is left, Removed, "
    "Folder gone: what the words say.\n\n"
    "The RB button (Update older games) puts the payload's HelixSR into every game with an older build or with its "
    "own DLL back. The helixsr.ini there is kept, and so is the game's backup. A game that is running is left alone.\n\n"
    "The Y button (Go back) deletes HelixSR's files there and puts the game's own DLL back (or deletes the "
    "stand-alone folder, and OptiScaler with it), on a second press. The X button (Forget) drops a line from the "
    "list without touching the game, on a second press.")
OPTI_INFO = (
    "For a game without AMD FSR 3.1 (DLSS, XeSS, FSR 2 or 3.0 games). OptiScaler hands the game's upscaler calls to "
    "an FSR 3.1 DLL. The X button writes HelixSR under both FidelityFX names into a folder of its own in the game's "
    "folder (HelixSR), with its helixsr.ini.\n\n"
    "OptiScaler next to the game's .exe: with a payload that has OptiScaler (HelixSR 1.7.0 to 1.8.1 ship it, newer "
    f"ones do not; get the fallback {FALLBACK_VERSION} once and the payload keeps it), the app installs OptiScaler as "
    "dxgi.dll (or under the name of an OptiScaler the game already has), with fakenvapi, and points its "
    "OptiScaler.ini at the HelixSR folder. Select DLSS in the game; OptiScaler's menu (Insert) shows FSR HelixSR. A "
    "file of the game it replaces is kept in the HelixSR folder's backup folder; Go back puts it back. Windows loads "
    "it from the game's folder by itself: no launch options are needed.\n\n"
    "Without it, install OptiScaler yourself as its documentation says, and paste the OptiScaler.ini lines the LB "
    f"button copies ({OPTISCALER_URL}).\n\n"
    "Second upscaler: another FidelityFX upscaler DLL (for example AMD's amd_fidelityfx_upscaler_dx12.dll with "
    f"FSR 4) goes into the folder as {SECOND_UPSCALER_DLL}; OptiScaler's FFX Upscaler menu lists its upscalers "
    "after HelixSR. The A button on its row picks the DLL, again takes it out.\n\n"
    "The Y button (Go back) deletes the folder's files and OptiScaler, and puts back what it replaced, on a second "
    "press.")
DLSS_INFO = (
    f"HelixSR builds its network from NVIDIA's {DLSS_DLL} 310.7.0. By default the app downloads it from NVIDIA's "
    "GitHub, under NVIDIA's license, uses it once and deletes it. A game you own may ship the same DLL: the Y button "
    "looks through your Steam games and lists only the files with the exact checksum HelixSR pins; the A button uses "
    "one. Pick a file takes one from anywhere; HelixSR's builder checks it.")
APPLY_INFO = (
    "The settings of the Settings card written as the helixsr.ini of one game that has HelixSR: the A button on the "
    "game writes it. HelixSR reads it at the game's next start.")
LOG_INFO = (
    "Where the app keeps HelixSR, and the newest lines of this app's log: what was downloaded, the builder's output, "
    "every game changed. The A button, or a tap on this pane, shows the whole log here: the d-pad scrolls it, the B "
    "button goes back. HelixSR writes its own helixsr.log next to its DLL in a game's folder.")
BROWSE_INFO = (
    "The places first: your Games, Downloads, Documents and Desktop folders, then every drive (an SD card too). The A "
    "button opens a folder, or picks a file; the B button goes a level up. Where a folder is what is asked for, the X "
    "button takes the folder you are in.")


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


def heading_row(title: str, info_title: str, info: str) -> tuple[QHBoxLayout, QWidget, InfoPill]:
    heading = QHBoxLayout()
    label = text_label(title, 24, QFont.Weight.ExtraBold)
    heading.addWidget(label)
    heading.addStretch()
    pill = InfoPill(info_title, info)
    heading.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
    return heading, label, pill


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line. Its actions are on
    controller buttons, in the legend at the bottom of the window (owner, 29-10-2026), so it has no pills."""

    def __init__(self, title: str, info_title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        heading, self.heading, self.info = heading_row(title, info_title, info)
        self.column.addLayout(heading)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


def fill_grid(grid: QGridLayout, rows: Sequence[tuple[str, str]]) -> None:
    """A pane's label and value rows, the values on the right, wrapping."""
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
    for r, (label, value) in enumerate(rows):
        grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
        shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
        shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(shown, r, 1)
    grid.setColumnStretch(1, 1)


class HelixPane(Pane):
    """HelixSR: the payload and the release in rows, the newest lines of the build's output (the d-pad passes them
    by), and the status line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading, _label, self.info = heading_row("HelixSR", "HelixSR", HELIXSR_INFO)
        self.column.addLayout(heading)
        self.column.addSpacing(px(8))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addSpacing(px(8))
        self.lines = TextView(background="transparent")
        self.lines.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lines.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.column.addWidget(self.lines, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)

    def fill(self, rows: Sequence[tuple[str, str]], lines: Sequence[str]) -> None:
        fill_grid(self.grid, rows)
        self.lines.setPlainText("\n".join(lines))
        self.lines.show_end()


class LogPane(Pane):
    """The app's folders and the newest lines of the log; show_whole() puts the whole log in a TextView in their
    place (owner, 29-10-2026: not in Notepad, which no button closes), show_summary() goes back."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading, _label, self.info = heading_row("Log", "The log", LOG_INFO)
        self.column.addLayout(heading)
        self.column.addSpacing(px(8))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addSpacing(px(10))
        # The newest lines in a view of their own, the last in sight; the d-pad passes it by, and a tap goes to the
        # pane: A or the tap shows the whole log
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
        fill_grid(self.grid, rows)
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


class SettingsPane(Pane):
    """helixsr.ini's settings in tabs, as Xenia Manager's: LB and RB step through Sharpening, Model E and More, a
    tap picks one; a tab is a page of rows, "Sharpener: rcas", and A on one steps to the next value (the window
    writes it). The information icon tells what the tab's settings do. show_only() hides the rows the payload's
    HelixSR does not read."""

    def __init__(self, tab_info: dict[str, str], parent: QWidget | None = None):
        super().__init__(parent)
        self.tab_info = tab_info
        heading, _label, self.info = heading_row("Settings", "helixsr.ini", tab_info[TABS[0][0]])
        self.column.addLayout(heading)
        self.column.addSpacing(px(4))
        self.tabs = Tabs([(key, name) for key, name, _group in TABS])
        self.column.addWidget(self.tabs)
        self.column.addSpacing(px(8))
        self.pages = QStackedWidget()
        self.pills: dict[str, Row] = {}
        self.rows: dict[str, list[Row]] = {}            # a tab's rows, in order
        for key, _name, group in TABS:
            page = QWidget()
            rows = QVBoxLayout(page)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(px(6))
            keys = [setting.key for setting in group] + ([CHECK_AT_START] if key == TABS[-1][0] else [])
            for name in keys:
                pill = Row(name)
                self.pills[name] = pill
                self.rows.setdefault(key, []).append(pill)
                rows.addWidget(pill)
            rows.addStretch()
            self.pages.addWidget(page)
        self.column.addWidget(self.pages, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.tabs.changed.connect(self.show_tab)

    def show_only(self, keys: set[str]) -> None:
        """The rows of *keys* shown, the others hidden (a hidden row never takes the focus)."""
        for name, pill in self.pills.items():
            pill.setVisible(name in keys or name == CHECK_AT_START)

    def show_tab(self, key: str) -> None:
        """The tab's page and its information; the focus, when it was on a row, moves to the page's first row."""
        keys = [k for k, _name, _group in TABS]
        inside = any(pill.hasFocus() for pill in self.pills.values())
        if inside:
            self.setFocus()                             # off the old page first: a row hidden with the focus would
        self.pages.setCurrentIndex(keys.index(key))     # hand it to a card, and that card's pane would show
        self.info.info = self.tab_info[key]
        if inside:
            self.focus_first()

    def focus_first(self) -> None:
        first = next((pill for pill in self.rows[self.tabs.current] if not pill.isHidden()), None)
        if first is not None:
            first.setFocus()

    def focused(self) -> str:
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")
