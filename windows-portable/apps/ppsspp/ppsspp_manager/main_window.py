# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as PCSX2 Manager lays it out: the cards on the left (PPSSPP, Your games,
Settings, Log: the BC250 suite's PPSSPP Manager's parts), what the focused one shows on the right, the controller's
buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a pane to its card,
the folders to the games, the browser a level up), View exits the app and Menu shows the information of the pane that
shows.

The Your games pane (panes.py, library.py): the games in the chosen folders and on PPSSPP's memory stick, played from
Steam (owner, 29-10-2026: X Play starts one in Steam), and on a device without Steam X Play starts it in the app's
play mode itself (owner, 30-10-2026: a fallback, as its shortcut would start it; core's play: View and Menu held quit
any game); A marks one for Steam, Y Update Steam makes Steam's shortcuts match the marks and brings a shortcut made
before the play mode to it; LB Folders lists the folders, the usual places and a drive to add, and Browse, which opens
the folder browser (core's browse: the controller's own way to a folder, where Windows' folder window is not); LB
Games goes back; RB Steam artwork keeps the SteamGridDB key; Steam's library is the portal's RT Steam (owner,
30-10-2026: Open Steam moved there). The Log pane: PPSSPP's memory stick and the newest lines
of the app's log; A (or a tap on the pane) shows the whole log in the pane, B goes back.

The PPSSPP pane: what is installed and where; A Install until PPSSPP is installed, Y Update when an older PPSSPP is
there, X Remove PPSSPP (a second press). A press that cannot act now says why on the status line. Nothing downloads
before A. The download and the unpacking run off the window's thread; the pane counts the megabytes. View (exit)
while they run asks first, as the portal does.

The Settings pane: PPSSPP's settings that matter on the handheld, in tabs (LB and RB: Picture, Game, Controller, On
screen), a row each with its value; A steps to the next value and writes it into ppsspp.ini at once
(ppsspp_settings), never while PPSSPP runs (it writes its own settings back when it closes). What the app owns in
ppsspp.ini is set after an install, when the window opens (ppsspp_settings.prepare)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, covers, platform, play, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)

from . import APP_ID, APP_NAME, LOGO_PATH, __version__, emulator, library, ppsspp_settings, shortcuts
from .games import Game, memstick_game, scan
from .panes import BROWSE_INFO, GAMES_INFO, KeyPane, ListPane, LogPane
from .ppsspp_settings import TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and View (exit) while PPSSPP is being installed, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
ABOUT = ("PPSSPP, the PSP emulator, installed for your own user in portable mode: its settings, the saves and the "
         "save states stay on its memory stick, in its folder.")
CARD_HEIGHT = 100               # the cards and their gaps fit the column at 720 px high
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
FOLDERS, GAMES_VIEW = "folders", "games"
FOLDERS_BROWSED = "folders"     # the browser's folder kept for next time (browse.remember)
BROWSE_KEY = "browse"           # the folders' last row: the folder browser
RUNNING = "PPSSPP is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install PPSSPP first: the settings are in its folder."
BUSY = "Wait a moment: the app is still busy with the step before."
OPEN_A_FOLDER = "Open a folder first: the A button opens the one the focus is on, then the X button adds it."
ALL_SETTINGS = ppsspp_settings.SETTINGS
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; PPSSPP "
                  "reads the settings the next time it opens.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


def count(folder: Path) -> int:
    """The folders in *folder* (a save each, in PSP\\SAVEDATA), or its files (the save states); 0 without it."""
    try:
        return sum(1 for _ in folder.iterdir())
    except OSError:
        return 0


class _Worker(QObject):
    """Runs the install off the window's thread; done (the version, or the exception) and what it is doing (said)
    arrive on the window's."""

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


NOT_THE_GAMES = "Update Steam works on the games: the LB button shows them again."
PICK_A_GAME = "Put the focus on a game first: the X button starts it."
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")


class SettingsPane(Pane):
    """The settings in tabs, as PCSX2 Manager's: LB and RB step through Picture, Game, Controller and On screen, a
    tap picks one; a tab is a page of rows, "Renderer: Vulkan", and A on one steps to the next value (the window
    writes it). Seven rows fit a page at 720 px high. The information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("PPSSPP's settings", TAB_INFO[TABS[0][0]])
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
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, running: Callable[[Path], bool] = emulator.running,
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 roots: Callable[[], list[Path]] = browse.drives, settings: QSettings | None = None,
                 open_url: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *user_home*: the user's folder
        (the usual places); *drives*: the removable drives offered as folders, *roots*: every drive the browser
        offers; *settings*: the app's (its .ini, create_app's), where the game folders are kept;
        *open_url*: hands a steam:// address to Steam (Play); *start*: starts a program on its own (PPSSPP with a
        game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running = install, running
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…"
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed = steam_closed
        self._job = ""                                  # "steam" while Update Steam runs in the worker
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.user_home, self.drives, self.roots = user_home, drives, roots
        self.settings = settings if settings is not None else QSettings()
        self.open_url = open_url
        self.start_program = start
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.games_view = GAMES_VIEW
        self.forget_asked = ""                          # a folder pressed once: A again takes it off the list
        self.browser: browse.Browser | None = None      # the folder browser, while it shows

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
        self.ppsspp_card = Card("PPSSPP", "Install, update or remove it.")
        self.games_card = Card("Your games", "Mark them for Steam, and their folders.")
        self.settings_card = Card("Settings", "The picture, the game and the controller.")
        self.log_card = Card("Log", "PPSSPP's memory stick, and this app's log.")
        for card in (self.ppsspp_card, self.games_card, self.settings_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        self.pane.column.addWidget(text_label("PPSSPP", 24, QFont.Weight.ExtraBold))
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
        self.browse_pane = ListPane("Choose a folder", "Choosing a folder", BROWSE_INFO)
        self.key_pane = KeyPane()
        self.log_pane = LogPane()
        for pane in (self.pane, self.games_pane, self.settings_pane, self.log_pane, self.key_pane, self.browse_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.ppsspp_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.log_pane: self.log_card,
                      self.key_pane: self.games_card, self.browse_pane: self.games_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._installed)
        self.worker.said.connect(self._said)
        self.ppsspp_card.focused.connect(lambda: self.show_pane(self.pane))
        self.ppsspp_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.game_picked)
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.confirm_key = False                        # Remove key pressed once
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("accept", self.a_action)
        self.bind("y", self.y_action)
        self.bind("x", self.x_action)
        self.bind("previous", self.lb_action)
        self.bind("next", self.rb_action)
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
        """After the window is shown: the controller, the status line, PPSSPP's settings brought to what the app owns,
        and the focus on the PPSSPP card."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.refresh()
        self.refresh_games()
        self.ppsspp_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([power.text(self.battery()), *status_clock()])

    def prepare(self) -> bool:
        """ppsspp_settings.prepare() while PPSSPP is installed and not running; whether ppsspp.ini is ready."""
        if not emulator.installed(self.home) or self.running(self.home):
            return False
        try:
            done = ppsspp_settings.prepare(self.home)
        except OSError as error:
            self.log.error(f"PPSSPP's settings could not be written: {error}")
            return False
        if done:
            self.log.info(f"PPSSPP's settings: {', '.join(done)}.")
        return True

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading PPSSPP {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if version != emulator.VERSION:
            return f"This app installs PPSSPP {emulator.VERSION}: the Y button updates it.", "", "Update"
        return "", "", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        return [("Installed", version or "not installed"), ("This app installs", emulator.VERSION),
                ("Folder", wrappable(self.home))]

    def setting_value(self, setting: Setting) -> str:
        return ppsspp_settings.read_setting(self.home, setting)

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
            status = "Press the X button again to remove PPSSPP: its memory stick stays."
        self.status.setText(self.message or status)
        self.refresh_settings()
        self.update_legend()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(self.setting_value(setting))}" if ready
                          else setting.label)
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
        the same), then core's Menu Info, B Back (in a pane, and on the folders, the browser, the key page and the
        whole log) and View Exit app. A press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []),
                     *([("X", "Press again" if self.confirm_remove else "Remove PPSSPP")] if installed else []),
                     *([("Y", other)] if other else [])]
        elif pane is self.games_pane:
            items = ([("A", "Steam mark"), *([("X", "Play")] if self.focused_game() else []),
                      ("Y", "Update Steam"), ("LB", "Folders")]
                     if self.games_view == GAMES_VIEW else [("A", "Choose"), ("LB", "Games")]) + \
                    [("RB", "Steam artwork")]
        elif pane is self.browse_pane:
            items = [("A", "Open"), ("X", "Add this folder")]
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key")]
        on_a_page = (pane in (self.key_pane, self.browse_pane) or self.log_pane.viewing
                     or (pane is self.games_pane and self.games_view == FOLDERS))
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def scan(self) -> list[Game]:
        """The games in the chosen folders and on PPSSPP's memory stick."""
        return scan(library.folders(self.settings), memstick_game(emulator.memstick(self.home)))

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
        found = {str(g.file) for g in self.games}
        self.marked = {f for f in self.marked if f in found} | {f for f in self.in_steam if f in found
                                                                  and f not in self._unmarked}
        self.show_games()

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        chosen = library.folders(self.settings)
        in_steam = sum(1 for g in self.games if str(g.file) in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(chosen)} folder(s) and on PPSSPP's memory stick"
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        if self.games_view == FOLDERS:
            rows = [(f"folder:{f}", ("Press A again to take it off the list" if self.forget_asked == str(f)
                                     else f"{private(f)}  ·  {len(scan([f]))} game(s)")) for f in chosen]
            rows += [(f"add:{p}", f"+ Add {private(p)}") for p in library.suggested(chosen, self.user_home, self.drives)]
            rows.append((BROWSE_KEY, "+ Browse to a folder…"))
        else:
            rows = [(str(g.file), self.game_text(g)) for g in self.games]
            if not rows:
                pane.status.setText(pane.status.text() or "No games yet: the LB button shows your game folders, "
                                                           "to add the one your games are in.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        mark = "✓ Steam" if str(game.file) in self.marked else ""
        changed = ((str(game.file) in self.marked) != (str(game.file) in self.in_steam)
                   or str(game.file) in self.marked and str(game.file) in self.outdated)
        return "  ·  ".join(p for p in (game.title, game.disc_id, mark + (" (Update Steam)" if changed else "")) if p)

    def game_picked(self, key: str) -> None:
        """A on a row: a game's Steam mark, a folder's second press, a place to add, or the browser."""
        if key == BROWSE_KEY:
            self.show_browser()
        elif key.startswith("add:"):
            self.add_folder(Path(key[4:]))
        elif key.startswith("folder:"):
            self.forget_folder(Path(key[7:]))
        else:
            self.mark_game(key)

    def focused_game(self) -> Game | None:
        """The game whose row has the focus, on the games' view."""
        if self.games_view != GAMES_VIEW:
            return None
        key = next((key for key, pill in self.games_pane.list.pills.items() if pill.hasFocus()), None)
        return next((game for game in self.games if str(game.file) == key), None)

    def play(self) -> None:
        """X on a game: started through Steam, as its shortcut there (owner, 29-10-2026: a game started from the
        app; Steam keeps its controller layout and its overlay). Steam starts first when it is not open. On a device
        without Steam PPSSPP starts it itself."""
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
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): PPSSPP started with it full screen,
        as its Steam shortcut would start it, outside the app's bundle (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install PPSSPP first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"PPSSPP could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in PPSSPP failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in PPSSPP… {play.QUIT_HINT}")
        self.log.info(f"Play: {game.title}, started in PPSSPP, without Steam.")

    def toggle_folders(self) -> None:
        self.games_view = GAMES_VIEW if self.games_view == FOLDERS else FOLDERS
        self.forget_asked = ""
        self.games_pane.status.setText("")
        self.show_games()
        self.show_pane(self.games_pane)
        self.focus_list(self.games_pane)

    def add_folder(self, folder: Path) -> None:
        browse.remember(self.settings, FOLDERS_BROWSED, folder)        # the browser opens here next time
        chosen = library.folders(self.settings)
        if str(folder) not in {str(f) for f in chosen}:
            library.set_folders(self.settings, chosen + [folder])
        self.refresh_games()
        found = sum(1 for g in self.games if g.folder == folder or folder in g.file.parents)
        self.games_pane.status.setText(f"{folder.name or folder} is a game folder now: {found} game(s) in it.")
        self.log.info(f"Game folder added: {folder} ({found} game(s)).")

    def forget_folder(self, folder: Path) -> None:
        """A on a folder asks for a second press (no dialog on a handheld); the second takes it off the list."""
        if self.forget_asked != str(folder):
            self.forget_asked = str(folder)
            self.confirm_timer.start()
            self.show_games()
            self.games_pane.list.pills[f"folder:{folder}"].setFocus()
            return
        self.forget_asked = ""
        library.set_folders(self.settings, [f for f in library.folders(self.settings) if f != folder])
        self.refresh_games()
        self.games_pane.status.setText(f"{folder.name or folder} is no longer a game folder; its games stay where "
                                       "they are.")
        self.log.info(f"Game folder taken off the list: {folder}.")
        self.focus_list(self.games_pane)

    # The folder browser (core's browse)

    def show_browser(self) -> None:
        self.browser = browse.Browser(browse.places(self.user_home, self.roots),
                                      path=browse.remembered(self.settings, FOLDERS_BROWSED))
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(wrappable(path) if path is not None else
                                         "Where are your games? Open a place, then the folder they are in.")
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is not None:
            self.browser.open(key)
            self.browse_pane.status.setText("")
            self.show_browse()

    def add_browsed(self) -> None:
        """X in the browser: the open folder becomes a game folder; back to the folders."""
        if self.browser is None or self.browser.path is None:
            self.browse_pane.status.setText(OPEN_A_FOLDER)
            return
        folder = self.browser.path
        self.leave_browser()
        self.add_folder(folder)

    def leave_browser(self) -> None:
        self.browser = None
        self.games_view = FOLDERS
        self.show_games()
        self.show_pane(self.games_pane)
        self.focus_list(self.games_pane)

    # The SteamGridDB key (the BC250 app's Covers… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's cover." if old else
                                     "No key: Update Steam draws the pictures from the game's own.")
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
        elif pane is self.browse_pane:
            self.add_browsed()
        elif pane is self.games_pane:
            self.play()
        elif pane is self.key_pane:
            self.paste_key()

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
            self.toggle_folders()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {str(g.file) for g in self.games}:
            return
        if key in self.marked:
            self.marked.discard(key)
            if key in self.in_steam:
                self._unmarked = self._unmarked | {key}
        else:
            self.marked.add(key)
            self._unmarked = self._unmarked - {key}
        self.show_games()
        self.games_pane.list.pills[key].setFocus()

    def update_steam(self) -> None:
        """Y Update Steam: the marked games in Steam, the others out, off the window's thread. Y always answers: a
        press that changes nothing says why on the status line."""
        if self.busy:
            if self._job != "steam":                    # Steam's own job says so on the line already
                self.games_pane.status.setText(BUSY)
            return
        if self.games_view != GAMES_VIEW:
            self.games_pane.status.setText(NOT_THE_GAMES)
            return
        if self.steam_dir is None:
            self.games_pane.status.setText(NO_STEAM)
            return
        if not library.pending(self.games, self.marked, self.in_steam, self.outdated):
            self.games_pane.status.setText(NOTHING_TO_CHANGE)
            return
        add, remove = library.plan(self.games, self.marked, self.in_steam)
        if add and not emulator.installed(self.home):
            self.games_pane.status.setText("Install PPSSPP first (the PPSSPP card): the games in Steam start it.")
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

    # Log

    def refresh_log(self) -> None:
        stick = emulator.memstick(self.home)
        rows: list[tuple[str, str]] = [("Memory stick", wrappable(stick))]
        if emulator.installed(self.home):
            rows += [("Saves", str(count(stick / "PSP" / "SAVEDATA"))),
                     ("Save states", str(count(stick / "PSP" / "PPSSPP_STATE")))]
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
        """A on a setting's row: its next value, written now, unless PPSSPP runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(self.setting_value(setting))
        try:
            ppsspp_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, X and Y on the PPSSPP pane

    def main_action(self) -> None:
        """A on the PPSSPP card or pane: Install while PPSSPP is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing PPSSPP {emulator.VERSION} in {self.home}.")
        self.worker.run(lambda: self.install_job(self.home, progress=self._progress, say=self.worker.said.emit))

    def _progress(self, got: int) -> None:
        self.got = got                                  # read by refresh() on the window's thread

    def _said(self, text: str) -> None:
        self.stage = text
        self.refresh()

    def _installed(self, result: object) -> None:
        if self._job == "steam":
            self._job = ""
            self._steam_done(result)
            return
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if isinstance(result, Exception):
            self.message = private(f"PPSSPP could not be installed: {result}")
            self.log.error(f"Installing PPSSPP failed: {result}")
        else:
            self.message = f"PPSSPP {result} is installed."
            self.log.info(f"PPSSPP {result} installed.")
            self.prepare()                              # before its first start
        self.refresh()
        self.refresh_games()                            # its memory stick is there now

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

    def remove_action(self) -> None:
        """X Remove PPSSPP asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "PPSSPP is not installed: there is nothing to remove."
            self.refresh()
            return
        if self.running(self.home):
            self.message = "PPSSPP is open: close it first, then remove it."
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
            self.message = f"PPSSPP could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing PPSSPP failed: {error}")
        else:
            self.message = "PPSSPP is removed. Its memory stick, with the saves and the settings, stays in its folder."
            self.log.info("PPSSPP removed.")
        self.refresh()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.forget_asked:
            self.forget_asked = ""
            self.show_games()
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
        """B goes back (the suite's rule, owner 29-10-2026): the whole log to its summary, the browser a level up (from
        the places to the folders), the key page to Your games (nothing saved), the folders to the games, a pane to its
        card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.browse_pane:
            if self.browser is not None and self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.games_pane and self.games_view == FOLDERS:
            self.toggle_folders()
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the download (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = ("Press View again to exit: Steam's shortcuts may be left half changed."
                            if self._job == "steam" else "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
