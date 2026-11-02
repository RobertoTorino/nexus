# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as RPCS3 Manager and shadPS4 Manager lay it out: the cards on the left
(Xenia, Your games, Settings, Log: the BC250 suite's Xenia Manager's parts, and the settings its Xenia settings button
opened), what the focused one shows on the right, the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a pane to its card,
the key's page to Your games), View exits the app and Menu shows the information of the pane that shows. Nothing is
browsed to (owner, 30-10-2026: fixed folders, no folder selecting): the games are put in the app's own folders
(library.fixed: Games\\XBOX360 in your user folder, and on an SD card).

The Xenia pane: what is installed, the games and where, and when a newer build is out; A Install until Xenia is
installed, Y Update when another build is there, X Remove Xenia (a second press). A press that cannot act now says why
on the status line. Nothing downloads before A. The download and the unpacking run off the window's thread; the pane
counts the megabytes. View (exit) while a job runs asks first, as the portal does. Xenia needs nothing set up: it is
portable by itself on Windows, and a game's line gives it full screen.

The Your games pane (panes.py, library.py): the games in the app's own Games\\XBOX360 folders (owner, 30-10-2026: the
games are dropped there; library.fixed, an SD card's too), played from Steam (owner, 29-10-2026: the app starts one
in Steam, X Play; on a device without Steam X Play starts it in the app's play mode itself, owner 30-10-2026: a
fallback, as its shortcut would start it; core's play: View, LB and RB held quit any game); A marks one for Steam, Y
Update Steam makes Steam's shortcuts match the marks and brings a shortcut made before the play mode to it; RB Remove
game shows the keep page (owner, 01-11-2026: before deleting anything, let the user decide what to keep; core's
keep.py): a row for each part of the game (library.removal) and its Steam shortcut, every row marked Delete at
first, A Keep or Delete, X deletes the marked ones off the window's thread, B deletes nothing; LB Steam artwork keeps
the SteamGridDB key; Steam's library is the portal's RT Steam (owner, 30-10-2026: Open Steam moved there). The Log
pane: Xenia's folder, where Games\\XBOX360 is and the newest lines of the app's log; A (or a tap on the pane) shows the
whole log in the pane.

The Settings pane: Xenia's settings that matter on the handheld, in tabs (LB and RB: Picture, Speed, Sound, Console), a
row each with its value; A steps to the next value and writes it into xenia-canary.config.toml at once
(xenia_settings), never while Xenia runs."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, keep, platform, play, power, renamed, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, KEYBOARD, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)
from bc250_core.updates import ReleaseInfo

from . import APP_ID, APP_NAME, LOGO_PATH, __version__, emulator, library, shortcuts, xenia_settings
from .games import Game, scan
from .panes import GAMES_INFO, KEEP_INFO, XENIA_INFO, KeyPane, ListPane, LogPane
from .xenia_settings import TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and View (exit) while a job runs, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
CARD_HEIGHT = 100               # the cards and their gaps fit the column at 720 px high
ABOUT = ("Xenia, the XBOX 360 emulator, installed for your own user: its settings, the content of your games and "
         "their saves stay in its folder.")
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
KINDS = {"iso": "ISO", "xex": "XEX", "zar": "ZAR", "god": "Games on Demand", "xbla": "Arcade"}
RUNNING = "Xenia is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install Xenia first: the settings are in its folder."
BUSY = "Wait a moment: the app is still busy with the step before."
ALL_SETTINGS = xenia_settings.SETTINGS
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; Xenia "
                  "reads the settings when a game starts. A game's own settings in Xenia come before these.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}
PICK_A_GAME = "Put the focus on a game first: the X button starts it in Steam."
STEAM_ITEM = "steam"            # the keep page's row of the game's Steam shortcut
NOTHING_MARKED = "Nothing is marked Delete: B goes back, and nothing is deleted."
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


class _Worker(QObject):
    """Runs a job off the window's thread; done (the result, or the exception) and what it is doing (said) arrive on
    the window's."""

    done = pyqtSignal(object)
    said = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.busy = False

    def run(self, job: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return True

    def _run(self, job: Callable[[], object]) -> None:
        try:
            result = job()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class SettingsPane(Pane):
    """The settings in tabs, as RPCS3 Manager's: LB and RB step through Picture, Speed, Sound and Console, a tap picks
    one; a tab is a page of rows, "Graphics: Direct3D 12", and A on one steps to the next value (the window writes
    it). The information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("Xenia's settings", TAB_INFO[TABS[0][0]])
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(4))
        self.tabs = Tabs([(key, name) for key, name, _group in TABS])
        self.column.addWidget(self.tabs)
        self.column.addSpacing(px(8))
        self.pages = QStackedWidget()
        self.pills: dict[str, Row] = {}
        self.first: dict[str, Row] = {}                 # a tab's first row
        for key, _name, group in TABS:
            page = QWidget()
            rows = QVBoxLayout(page)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(px(6))
            for setting in group:
                pill = Row(setting.label)
                self.pills[setting.key] = pill
                self.first.setdefault(key, pill)
                rows.addWidget(pill)
            rows.addStretch()
            self.pages.addWidget(page)
        self.column.addWidget(self.pages, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.tabs.changed.connect(self.show_tab)

    def show_tab(self, key: str) -> None:
        """The tab's page and its information; the focus, when it was on a row, moves to the page's first row."""
        keys = [k for k, _name, _group in TABS]
        inside = any(pill.hasFocus() for pill in self.pills.values())
        if inside:
            self.setFocus()                             # off the old page first: a row hidden with the focus would
        self.pages.setCurrentIndex(keys.index(key))     # hand it to a card, and that card's pane would show
        self.info.info = TAB_INFO[key]
        if inside:
            self.focus_first()

    def focus_first(self) -> None:
        self.first[self.tabs.current].setFocus()


class MainWindow(PortableWindow):
    release_found = pyqtSignal(object)                  # Xenia's newest build, from the check's thread

    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, running: Callable[[Path], bool] = emulator.running,
                 runtime_missing: Callable[[], list[str]] = emulator.runtime_missing,
                 newer_release: Callable[[], ReleaseInfo | None] = emulator.newer_release,
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 settings: QSettings | None = None,
                 open_url: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *runtime_missing*: the Visual
        C++ runtime's files that are missing; *newer_release*: asks GitHub for a newer Xenia build; *user_home*: the
        user's folder (where Games\\XBOX360 is); *drives*: the removable drives, whose Games\\XBOX360 is looked in
        too; *settings*: the app's (its .ini, create_app's); *open_url*: hands a steam:// address to Steam (Play);
        *start*: starts a program on its own (Xenia with a game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running = install, running
        self.runtime_missing = runtime_missing
        self.newer_release = newer_release
        self.newer: ReleaseInfo | None = None           # Xenia's newest build, when newer than the pinned one
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…"
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed = steam_closed
        self._job = ""                                  # "install", "steam" or "remove" while one runs
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.start_program = start
        self.user_home, self.drives = user_home, drives
        self.settings = settings if settings is not None else QSettings()
        self.open_url = open_url
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.moved: dict[str, str] = {}                 # a game found again: its file in Steam (renamed)
        self.removing: Game | None = None               # the game the keep page shows
        self.keeping: list[keep.Item] = []              # its rows: what would go, each marked Delete or Keep

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.xenia_card = Card("Xenia", "Install it.")
        self.games_card = Card("Your games", "Mark them for Steam, play them, remove them.")
        self.settings_card = Card("Settings", "The picture, the speed, the sound and the console.")
        self.log_card = Card("Log", "Xenia's folder, and this app's log.")
        for card in (self.xenia_card, self.games_card, self.settings_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        heading = QHBoxLayout()
        heading.addWidget(text_label("Xenia", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.xenia_info = InfoPill("Xenia", XENIA_INFO)
        heading.addWidget(self.xenia_info, 0, Qt.AlignmentFlag.AlignTop)
        self.pane.column.addLayout(heading)
        self.pane.column.addWidget(text_label(ABOUT, BODY + 1, color=DIM, wrap=True))
        self.pane.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.pane.column.addLayout(self.grid)
        self.pane.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.pane.column.addWidget(self.status)
        self.settings_pane = SettingsPane()
        self.games_pane = ListPane("Your games", "Your games", GAMES_INFO)
        self.key_pane = KeyPane()
        self.log_pane = LogPane()
        self.keep_pane = ListPane("Remove", "Keep or delete", KEEP_INFO)
        for pane in (self.pane, self.games_pane, self.settings_pane, self.log_pane, self.key_pane, self.keep_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.xenia_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.log_pane: self.log_card,
                      self.key_pane: self.games_card, self.keep_pane: self.games_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.worker.said.connect(self._said)
        self.release_found.connect(self._release_found)
        self.xenia_card.focused.connect(lambda: self.show_pane(self.pane))
        self.xenia_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.game_picked)
        self.keep_pane.list.picked.connect(self.keep_picked)
        self.confirm_key = False                        # Remove key pressed once
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("accept", self.a_action)
        self.bind("y", self.y_action)
        self.bind("x", self.x_action)
        self.bind("previous", self.lb_action)
        self.bind("next", self.rb_action)
        self.bind("lt", self.lt_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.refresh)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the games, the focus on the Xenia card, and
        GitHub asked for a newer build (off the window's thread)."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.refresh_games()
        self.refresh()
        self.xenia_card.setFocus()
        ask = self.newer_release
        threading.Thread(target=lambda: self.release_found.emit(ask()), daemon=True).start()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def _release_found(self, release: object) -> None:
        self.newer = release if isinstance(release, ReleaseInfo) else None
        if self.newer is not None:
            self.log.info(f"Xenia build {self.newer.version} is out ({self.newer.published}); this app brings "
                          f"{emulator.VERSION}.")
            self.refresh()

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy and self._job == "remove":
            return "A game is being removed (Your games).", "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.1f} of {emulator.SIZE / emulator.MB:.1f} MB" if self.got else ""
            return f"Downloading Xenia {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if version != emulator.VERSION:
            return f"This app installs Xenia {emulator.VERSION}: the Y button updates it.", "", "Update"
        missing = self.runtime_missing()
        if missing:
            return (f"Xenia needs Microsoft's Visual C++ runtime ({', '.join(missing)} missing in System32): "
                    "install vc_redist.x64.exe from Microsoft, then open the app again.", "", "")
        return "", "", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        rows = [("Installed", version or "not installed"), ("This app installs", emulator.VERSION)]
        if self.newer is not None:
            rows.append(("Newest build", f"{self.newer.version} ({self.newer.published}): a later version of this "
                                         "app brings it, once tried on the handheld"))
        rows.append(("Games", str(len(self.games))))
        return [*rows, ("Folder", wrappable(self.home))]

    def refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for r, (label, value) in enumerate(self.rows()):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)
        status = self.state()[0]
        if self.confirm_remove:
            status = "Press the X button again to remove Xenia: its folder, with your saves and its settings, stays."
        self.status.setText(self.message or status)
        self.refresh_settings()
        self.update_legend()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        values = xenia_settings.read_settings(self.home) if ready else {}
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(values[setting.key])}" if ready else setting.label)
        if not ready and not self.settings_pane.status.text():
            self.settings_pane.status.setText(NOT_INSTALLED)
        elif ready and self.settings_pane.status.text() == NOT_INSTALLED:
            self.settings_pane.status.setText("")

    def show_pane(self, pane: Pane) -> None:
        if pane is not self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
        self.panes.setCurrentWidget(pane)
        if pane is self.log_pane:
            self.refresh_log()
        self.update_legend()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows: its actions on the controller's buttons, A too (a tap on an entry does
        the same), then core's Menu Info, B Back (in a pane, and on the key page and the whole log) and View Exit. A
        press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []),
                     *([("X", "Press again" if self.confirm_remove else "Remove Xenia")] if installed else []),
                     *([("Y", other)] if other else [])]
        elif pane is self.games_pane:
            game = self.focused_game()
            items = [("A", "Steam mark"), *([("X", "Play")] if game else []), ("Y", "Update Steam"),
                     ("LB", "Steam artwork"), *([("RB", "Remove game")] if game else []), ("LT", "Refresh")]
        elif pane is self.keep_pane:
            item = next((i for i in self.keeping if i.key == self.keep_pane.list.focused()), None)
            items = [*([("A", "Keep" if item.delete else "Delete")] if item else []), ("X", "Delete marked")]
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key"),
                     KEYBOARD]
        on_a_page = pane in (self.key_pane, self.keep_pane) or self.log_pane.viewing
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def game_folders(self) -> list[Path]:
        """The app's own Games\\XBOX360 folders (made when missing): the user's, then each SD card's."""
        return library.fixed(self.user_home, self.drives)

    def scan(self) -> list[Game]:
        return scan(self.game_folders())

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games, which are in Steam (*in_steam* when given: what Update Steam read back, else Steam's file now),
        and the list as the view shows it."""
        self.games = self.scan()
        if in_steam is not None:
            self.in_steam = in_steam
        else:
            try:
                self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir is not None else {}
            except OSError as error:
                self.in_steam = {}
                self.log.error(f"Steam's shortcuts could not be read: {error}")
        try:
            self.outdated = shortcuts.outdated(self.steam_dir) if self.steam_dir is not None else set()
        except OSError:
            self.outdated = set()
        found = {str(g.file): renamed.identity(g.title_id, g.file) for g in self.games}
        known = renamed.load(self.settings)
        self.moved = renamed.follow(known, found, self.in_steam)     # renamed or moved: the mark goes along
        renamed.remember(self.settings, known, found, self.in_steam)
        self.marked = ({f for f in self.marked if f in found}
                       | {f for f in [*self.in_steam, *self.moved] if f in found and f not in self._unmarked})
        self.show_games()
        if self.moved:
            self.games_pane.status.setText(self.moved_text())

    def moved_text(self) -> str:
        """The status line for the games in Steam found again under a new name or in another folder."""
        return renamed.said(g.title for g in self.games if str(g.file) in self.moved)

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        own = self.game_folders()
        in_steam = sum(1 for g in self.games if str(g.file) in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(own)} folder(s)"
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        rows = [(str(g.file), self.game_text(g)) for g in self.games]
        if not rows:
            pane.status.setText(pane.status.text() or
                                f"No games yet: put your XBOX 360 games in {private(own[0])}, or in Games\\XBOX360 "
                                "on an SD card.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        mark = "✓ Steam" if str(game.file) in self.marked else ""
        changed = ((str(game.file) in self.marked) != (str(game.file) in self.in_steam)
                   or str(game.file) in self.marked and str(game.file) in self.outdated)
        parts = (game.title, game.title_id, KINDS.get(game.kind, game.kind), mark + (" (Update Steam)" if changed else ""))
        return "  ·  ".join(p for p in parts if p)

    def game_picked(self, key: str) -> None:
        """A on a row: a game's Steam mark."""
        self.mark_game(key)

    def focused_game(self) -> Game | None:
        """The game whose row has the focus."""
        key = self.games_pane.list.focused()
        return next((game for game in self.games if str(game.file) == key), None)

    def play(self) -> None:
        """X on a game: started through Steam, as its shortcut there (owner, 29-10-2026: a game started from the
        app; Steam keeps its controller layout and its overlay). Steam starts first when it is not open. On a device
        without Steam Xenia starts it itself."""
        game = self.focused_game()
        if game is None:
            self.games_pane.status.setText(PICK_A_GAME)
            return
        if self.steam_dir is None:
            self.play_without_steam(game)
            return
        try:
            number = (shortcuts.numbers(self.steam_dir) if self.steam_dir is not None else {}).get(str(game.file))
        except OSError as error:
            number = None
            self.log.error(f"Steam's shortcuts could not be read: {error}")
        if number is None:
            self.games_pane.status.setText(f"{game.title} is not in Steam yet: A marks it, then Y Update Steam puts "
                                           "it there.")
            return
        try:
            self.open_url(steam.play_url(number))
        except OSError as error:
            self.games_pane.status.setText(f"Steam could not be asked to start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in Steam failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in Steam… {play.QUIT_HINT}")
        self.log.info(f"Play: {game.title}, started in Steam.")

    def play_without_steam(self, game: Game) -> None:
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): Xenia started with it full screen,
        as its Steam shortcut would start it, outside the app's bundle (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install Xenia first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"Xenia could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in Xenia failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in Xenia… {play.QUIT_HINT}")
        self.log.info(f"Play: {game.title}, started in Xenia, without Steam.")

    def remove_game(self) -> None:
        """RB on a game (owner, 30-10-2026: a game that no longer plays goes; owner, 01-11-2026: before deleting
        anything, let the user decide what to keep): the keep page, a row for each part of the game
        (library.removal: its file or folder, or a console title's game, title updates and add-ons) and one for its
        Steam shortcut, every row marked Delete at first. Its saves and content in Xenia's folder are never listed."""
        game = self.focused_game()
        if game is None:
            return
        if self.busy:
            self.games_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.games_pane.status.setText("Xenia is open: quit the game first, then remove it.")
            return
        items, why = library.removal(game, self.game_folders(), self.games)
        if not items:
            self.games_pane.status.setText(private(why))
            return
        if str(game.file) in self.in_steam:
            items.append(keep.Item(STEAM_ITEM, "Steam shortcut"))
        keep.measure(items)
        self.removing, self.keeping = game, items
        self.keep_pane.heading.setText(f"Remove {game.title}")
        self.keep_pane.status.setText("")
        self.show_keep()
        self.show_pane(self.keep_pane)
        self.focus_list(self.keep_pane)
        self.update_legend()

    def show_keep(self) -> None:
        """The keep page's rows and what the X button frees."""
        marked = keep.chosen(self.keeping)
        self.keep_pane.summary.setText(
            (f"The X button deletes the rows marked Delete ({keep.human(keep.total(self.keeping))})"
             if marked else "Every row is marked Keep") +
            ". The A button keeps a row or deletes it; the B button goes back and deletes nothing. Your saves stay "
            "in Xenia's folder.")
        self.keep_pane.list.set_items(keep.rows(self.keeping))

    def keep_picked(self, key: str) -> None:
        """A on a row of the keep page: Delete becomes Keep, Keep Delete; the focus stays on the row."""
        if keep.toggle(self.keeping, key) is None:
            return
        self.keep_pane.status.setText("")
        self.show_keep()
        pill = self.keep_pane.list.pills.get(key)
        if pill is not None:
            pill.setFocus()
        self.update_legend()

    def leave_keep(self, said: str = "") -> None:
        self.removing, self.keeping = None, []
        self.show_pane(self.games_pane)
        self.games_pane.status.setText(said)
        self.focus_list(self.games_pane)

    def delete_marked(self) -> None:
        """X on the keep page: the rows marked Delete deleted off the window's thread, the Steam shortcut first
        (through Update Steam's change, Steam closed around it); then back to Your games, saying what was deleted
        and what was kept."""
        game, items = self.removing, list(self.keeping)
        if game is None:
            return
        chosen = keep.chosen(items)
        if not chosen:
            self.keep_pane.status.setText(NOTHING_MARKED)
            return
        if self.busy:
            self.keep_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.keep_pane.status.setText("Xenia is open: quit the game first, then remove it.")
            return
        out_of_steam = any(i.key == STEAM_ITEM for i in chosen)
        steam_dir = self.steam_dir if out_of_steam else None
        paths = [p for i in chosen for p in i.paths]
        kept = [i.label for i in items if not i.delete]
        deleted = [i.label for i in chosen]
        closed, program, existing = self.steam_closed, emulator.program(self.home), self.in_steam

        def job() -> tuple[bool, str, dict[str, str] | None]:
            found = None
            if steam_dir is not None:
                ok, said, found = library.update_steam(steam_dir, [], [game], program, LOGO_PATH, existing, closed)
                if not ok:
                    return False, f"{game.title}: nothing was deleted. {said}", None
            failed = keep.delete(paths)
            library.tidy(game)
            if failed:
                return False, f"{game.title}: not deleted {', '.join(failed)}.", found
            return True, (f"{game.title}: deleted {', '.join(deleted)}"
                          + (f"; kept {', '.join(kept)}" if kept else "")
                          + ". Your saves stay in Xenia's folder."), found
        self.busy, self.message = True, ""
        self._job = "remove"
        self.leave_keep(f"Removing {game.title}…")
        self.log.info(f"Removing {game.title}: {', '.join(str(p) for p in paths) or 'nothing on the disk'}"
                      + (", and its Steam shortcut" if steam_dir is not None else "")
                      + (f"; kept {', '.join(kept)}." if kept else "."))
        self.worker.run(job)

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {str(g.file) for g in self.games}:
            return
        if key in self.marked:
            self.marked.discard(key)
            if key in self.in_steam or key in self.moved:
                self._unmarked = self._unmarked | {key}
        else:
            self.marked.add(key)
            self._unmarked = self._unmarked - {key}
        self.show_games()
        self.games_pane.list.pills[key].setFocus()

    def rescan(self) -> None:
        """LT Refresh: the game folders read again, for a game put there, renamed or taken away while the app is open
        (owner, 01-11-2026: it showed only after the app started again); the focus stays on its game."""
        if self.busy:
            if self._job != "steam":                    # Steam's own job says so on the line already
                self.games_pane.status.setText(BUSY)
            return
        self.refresh_games()
        changed = library.pending(self.games, self.marked, self.in_steam, self.outdated)
        self.games_pane.status.setText(f"The game folders were read again: {len(self.games)} game(s)."
                                       + (f" {self.moved_text()}" if self.moved else
                                          " Steam does not match the marks yet: the Y button updates it."
                                          if changed and self.steam_dir is not None else ""))

    def update_steam(self) -> None:
        """Y Update Steam: the marked games in Steam, the others out, off the window's thread. Y always answers: a
        press that changes nothing says why on the status line."""
        if self.busy:
            if self._job != "steam":                    # Steam's own job says so on the line already
                self.games_pane.status.setText(BUSY)
            return
        if self.steam_dir is None:
            self.games_pane.status.setText(NO_STEAM)
            return
        if not library.pending(self.games, self.marked, self.in_steam, self.outdated):
            self.games_pane.status.setText(NOTHING_TO_CHANGE)
            return
        add, remove = library.plan(self.games, self.marked, self.in_steam)
        if add and not emulator.installed(self.home):
            self.games_pane.status.setText("Install Xenia first (the Xenia card): the games in Steam start it.")
            return
        folder, closed, program, existing = self.steam_dir, self.steam_closed, emulator.program(self.home), self.in_steam
        key = covers.read_key(library.key_file())
        self.busy, self.message = True, ""
        self.games_pane.status.setText("Looking up covers and changing Steam's shortcuts…" if key else
                                       "Changing Steam's shortcuts…")
        self.log.info(f"Update Steam: {len(add)} in, {len(remove)} out.")
        self._job = "steam"
        self._steam_plan = (add, remove)
        self.worker.run(lambda: library.update_steam(folder, add, remove, program, LOGO_PATH, existing, closed, key))

    # The SteamGridDB key (the BC250 app's Covers… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's pictures." if old else
                                     "No key: Update Steam draws the pictures from the app's icon.")
        self.show_pane(self.key_pane)
        self.key_pane.field.setFocus()

    def paste_key(self) -> None:
        """The key from the clipboard (copied in a browser on the device): typing 32 characters on a handheld is
        the hard way."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.key_pane.status.setText("The clipboard is empty: copy the key on SteamGridDB's API page first.")
            return
        self.key_pane.field.setText(text.split()[0])
        self.key_pane.status.setText("The key is in the field: the A button saves it.")

    def save_key(self) -> None:
        key = self.key_pane.field.text().strip()
        old = covers.read_key(library.key_file())
        if key == old:
            self.back_to_games()
            return
        try:
            covers.write_key(key, library.key_file())
        except OSError as error:
            self.key_pane.status.setText(f"The key was not saved: {error.strerror or error}")
            self.log.error(f"Saving the SteamGridDB key failed: {error.strerror or error}")
            return
        self.log.info("The SteamGridDB key was changed." if key else "The SteamGridDB key was taken out.")
        self.back_to_games("The SteamGridDB key was changed." if key else
                           "The SteamGridDB key was taken out; the pictures kept stay in use.")

    def remove_key(self) -> None:
        """Remove key asks for a second press (no dialog on a handheld); the pictures kept stay in use."""
        if not covers.read_key(library.key_file()):
            self.key_pane.status.setText("There is no key to remove: the X button pastes one, the A button saves it.")
            return
        if not self.confirm_key:
            self.confirm_key = True
            self.confirm_timer.start()
            self.key_pane.status.setText("Press the Y button again to remove the key.")
            self.update_legend()
            return
        self._confirm_over()
        try:
            covers.write_key("", library.key_file())
        except OSError as error:
            self.key_pane.status.setText(f"The key was not taken out: {error.strerror or error}")
            return
        self.log.info("The SteamGridDB key was taken out.")
        self.back_to_games("The SteamGridDB key was taken out; the pictures kept stay in use.")

    def back_to_games(self, said: str = "") -> None:
        self.key_pane.field.clear()                     # the key is not left in the window
        self.show_pane(self.games_pane)
        if said:
            self.games_pane.status.setText(said)
        self.focus_list(self.games_pane)

    # The legend's buttons: what A (beside a card or a row), X, Y, LB and RB do on the pane that shows (a tap on the
    # legend's entry does the same)

    def a_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.key_pane:
            self.save_key()
        elif pane is self.pane:
            self.main_action()
        elif pane is self.log_pane:
            self.view_log()

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_action()
        elif pane is self.games_pane:
            self.play()
        elif pane is self.key_pane:
            self.paste_key()
        elif pane is self.keep_pane:
            self.delete_marked()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.other_action()
        elif pane is self.games_pane:
            self.update_steam()
        elif pane is self.key_pane:
            self.remove_key()

    def lb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.games_pane:
            self.remove_game()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def lt_action(self) -> None:
        if self.panes.currentWidget() is self.games_pane:
            self.rescan()

    # Log

    def refresh_log(self) -> None:
        rows: list[tuple[str, str]] = [("Xenia's folder", wrappable(self.home))]
        if emulator.installed(self.home):
            rows += [("Games", wrappable(self.game_folders()[0])), ("Games found", str(len(self.games)))]
        self.log_pane.fill(rows, [private(line) for line in self.log_lines()[-LOG_LINES:]])

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The whole log (its newest lines) in the Log pane: the d-pad scrolls it, B goes back (owner, 29-10-2026:
        Notepad, where it opened before, has no button to close it)."""
        self.show_pane(self.log_pane)
        self.log_pane.show_whole(private("\n".join(self.log_lines()[-LOG_MAX:])))   # older lines too
        self.update_legend()

    # The Settings pane

    def focus_settings(self) -> None:
        self.settings_pane.focus_first()

    def step_setting(self, setting: Setting) -> None:
        """A on a setting's row: its next value, written now, unless Xenia runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(xenia_settings.read_setting(self.home, setting))
        try:
            xenia_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, X and Y on the Xenia pane

    def main_action(self) -> None:
        """A on the Xenia card or pane: Install while Xenia is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        if self.running(self.home):
            self.message = "Xenia is open: close it first, then update it."
            self.refresh()
            return
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._job = "install"
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing Xenia {emulator.VERSION} in {self.home}.")
        self.worker.run(lambda: self.install_job(self.home, progress=self._progress, say=self.worker.said.emit))

    def _progress(self, got: int) -> None:
        self.got = got                                  # read by refresh() on the window's thread

    def _said(self, text: str) -> None:
        self.stage = text
        self.refresh()

    def _done(self, result: object) -> None:
        job, self._job = self._job, ""
        if job == "steam":
            self._steam_done(result)
            return
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if job == "remove":
            ok, text, found = result if isinstance(result, tuple) else (False, f"The game was not removed: {result}",
                                                                        None)
            self.games_pane.status.setText(private(text))
            (self.log.info if ok else self.log.error)(text)
            self.refresh()
            self.refresh_games(found)
            self.focus_list(self.games_pane)
            return
        if isinstance(result, Exception):
            self.message = private(f"Xenia could not be installed: {result}")
            self.log.error(f"Installing Xenia failed: {result}")
        else:
            self.message = f"Xenia {result} is installed."
            self.log.info(f"Xenia {result} installed.")
        self.refresh()

    def _steam_done(self, result: object) -> None:
        """What Update Steam did, and the games in Steam as it read them back right after the write (PCSX2
        Manager's check): a game written but not read back is logged by name, so the log tells whether the file or
        the reading is at fault."""
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        ok, text, found = result if isinstance(result, tuple) else (False, f"Steam was not changed: {result}", None)
        add, _remove = getattr(self, "_steam_plan", ([], []))
        if ok and found is not None:
            missing = [g.title for g in add if str(g.file) not in found]
            if missing:
                text += (f"\nRead back from Steam's file, {len(add) - len(missing)} of the {len(add)} game(s) are "
                         f"there: not {', '.join(missing)}. The log has the details.")
                self.log.error(f"Update Steam wrote {len(add)} game(s), but reading Steam's file back finds "
                               f"{len(add) - len(missing)}; not found: {', '.join(missing)}. Steam's file names "
                               f"{len(found)} game(s) of this app in all.")
            else:
                self.log.info(f"Steam's file names {len(found)} game(s) of this app, read back after the write.")
        self.games_pane.status.setText(text)
        (self.log.info if ok else self.log.error)(text.replace("\n", " "))
        self._unmarked = set()
        self.refresh_games(found)
        self.refresh()

    def remove_action(self) -> None:
        """X Remove Xenia asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "Xenia is not installed: there is nothing to remove."
            self.refresh()
            return
        if self.running(self.home):
            self.message = "Xenia is open: close it first, then remove it."
            self.refresh()
            return
        if not self.confirm_remove:
            self.confirm_remove, self.message = True, ""
            self.confirm_timer.start()
            self.refresh()
            return
        self._confirm_over()
        try:
            emulator.remove(self.home)
        except OSError as error:
            self.message = f"Xenia could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing Xenia failed: {error}")
        else:
            self.message = "Xenia is removed. Its folder, with your saves, its settings and your games' content, stays."
            self.log.info("Xenia removed.")
        self.refresh()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.confirm_key:
            self.confirm_key = False
            if self.key_pane.status.text().startswith("Press the Y button again"):
                self.key_pane.status.setText("")
        changed = self.confirm_remove or self.close_asked
        if self.close_asked and self.message.startswith("Press View again"):
            self.message = ""
        self.confirm_remove = self.close_asked = False
        if changed:
            self.refresh()
        self.update_legend()

    # B

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): the whole log to its summary, the key page to Your games
        (nothing saved), a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.keep_pane:
            self.leave_keep("Nothing was deleted.")
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the job (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = {"steam": "Press View again to exit: Steam's shortcuts may be left half changed.",
                            "remove": "Press View again to exit: the game is left half deleted."
                            }.get(self._job, "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
