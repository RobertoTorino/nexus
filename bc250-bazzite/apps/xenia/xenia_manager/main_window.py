# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window, built as RPCS3 Manager's (owner, 07-11-2026: RPCS3 Manager's design is every manager's): the header
with the Refresh pill and the state boxes, a row of action pills (Install and Uninstall for Xenia), the state of each
(Xenia, the game folder) in a line, then three tabs: the games found, each with a box for Steam; Xenia's settings
(core's settings_page over xenia_settings); and the app's log. Downloading Xenia, asking GitHub for a newer one and
changing Steam's files run off the GUI thread; nothing here needs root. The look is the app's own blue (style.py).
Steam artwork… takes the suite's SteamGridDB API key, with which Update Steam looks up each game's pictures first
(core's covers).

The app has no Play button: a game is started from Steam. Xenia's own window (Xenia settings, under the games) stays
for what the Settings tab does not set. What the window says it also writes to the app's log (core's applog), shown
in the Log tab."""

from __future__ import annotations

import time
from html import escape
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core import keep, renamed
from bc250_core.keep_dialog import KeepDialog
from bc250_core.platform import bin_home, private, xdg_open
from bc250_core.settings import SettingsStore
from bc250_core.settings_page import SettingsPage
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, library, shortcuts, style, xenia_settings
from .games import Game, scan

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/xenia/"
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
STEAM_URL = "steam://open/games"        # Steam's library; Steam starts when it does not run
KINDS = {"iso": "ISO", "xex": "XEX", "zar": "ZAR", "god": "Games on Demand", "xbla": "Arcade"}
STEAM, GAME, SERIAL, KIND, FILE = range(5)                  # the table's columns
GAMES, SETTINGS, LOG = range(3)                             # the tabs
# The emulator's line: the state alone, the same words in every manager (owner, 07-11-2026); the version and the
# advice are in its tip.
NOT_INSTALLED = "Not installed.<br>Install it with the Install button."
INSTALLED = "Installed.<br>Uninstall with the Uninstall button."
SETTINGS_LEAD = ("Xenia's settings that matter for playing, written into Xenia's own settings file the moment you "
                 "change one, while Xenia does not run. A game's own settings file in Xenia comes before these; "
                 "everything else is in Xenia's own window (Xenia settings, under Your games).")


class XeniaSettings(SettingsStore):
    DEFAULTS: dict = {}


class MainWindow(QMainWindow):
    def __init__(self, home: Path | None = None, steam_dir: Path | None = None, run: Path | None = None,
                 fetch: emulator.Download = emulator.download, steam_closed=steam.with_steam_closed,
                 steam_running=steam.steam_running, newer_release=emulator.newer_release,
                 covers_home: Path | None = None, covers_get: covers.Get = covers._get, covers_key: Path | None = None,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 xenia_home: Path | None = None, xenia_running=emulator.running, log_path: Path | None = None,
                 open_url=xdg_open):
        """*home*: where the app installs Xenia; *xenia_home*: Xenia's own folder, with its settings file;
        *xenia_running*: whether Xenia runs (its settings are left alone then); *steam_dir*: Steam's folder (None:
        looked up); *run*: the run wrapper the shortcuts start; *fetch*: the download of Xenia; *steam_closed* and
        *steam_running*: closing Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a
        newer Xenia; *covers_home*, *covers_get* and *covers_key*: where the pictures from SteamGridDB are kept, how
        SteamGridDB is asked and the suite's key file (tests never touch the real ones); *user_home*: the home folder
        with the app's own game folder (library.fixed); *drives*: the removable drives looked at for one;
        *log_path*: the app's log file, as the Log tab shows it (__main__ set it up); *open_url*: opens a URL on the
        desktop (the Steam link)."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.xenia_home = xenia_home or emulator.xenia_home()
        self.xenia_running = xenia_running
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.user_home = user_home or Path.home()
        self.drives = drives
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.log_path = log_path or applog.log_file(APP_ID)
        self.open_url = open_url
        self.log = applog.logger(APP_ID)
        self._pin_noted = False                         # another build installed than the app brings: logged once
        self.newer: ReleaseInfo | None = None           # Xenia's newest release, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.settings = XeniaSettings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread: a download or Steam
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.moved: dict[str, str] = {}               # a game found again under another name: its file in Steam
        self._moved_said: set[str] = set()
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""                               # the installed Xenia, "" when none is
        self.folders: list[Path] = []

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        # The state on the right of the title row, ending at the middle of the last pill below it, as in RPCS3
        # Manager: a spacer of half that pill's width after it, set whenever the window's size changes.
        self.pill = StatusText()
        header.add_action(self.pill)
        self.states_spacer = QWidget()
        self.states_spacer.setFixedSize(0, 1)
        header.add_action(self.states_spacer)
        self.refresh_pill = style.action_pill("Refresh", "Click to refresh", "Read the state again and look for games")
        self.refresh_pill.clicked.connect(self.refresh)
        self.emulator_box = MetricBox("Xenia version", style.BLUE)
        self.games_box = MetricBox("Your games", style.BLUE)
        self.steam_box = MetricBox("Available in Steam", style.BLUE)
        # The header's pills spread over the window's width in equal parts, as the action pills below.
        self.header_pills = [self.refresh_pill, self.emulator_box, self.games_box, self.steam_box]
        for box in self.header_pills:
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.add_second(box, 1)
        self.intro = hint_label(
            "XBOX 360 games on the BC-250 with the Xenia emulator (Xenia Canary, experimental on Linux, so not every "
            "game starts). The app installs a tested Xenia build, finds your games and puts them in Steam, so a game "
            "starts straight away, also from Steam's Big Picture Mode. Games come from your own discs and console; "
            "the app never downloads them. " + style.link(self, emulator.RELEASE_PAGE, "Xenia's release notes")
            + " · " + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)   # its lines count in the minimum

        # What there is to do, as pills the size of the header's: what it is for in large type (Xenia), what the pill
        # does under it (Install, Uninstall). A third of the width each, as in the other managers: the last third
        # stays empty.
        self.install_pill = style.action_pill("Xenia", "Install", f"Download Xenia {emulator.VERSION} from GitHub "
                                                                  "and check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("Xenia", "Uninstall", "Remove the installed Xenia; its settings, saves "
                                                                   "and installed content stay")
        self.remove_pill.clicked.connect(self.on_remove)
        self.actions = [self.install_pill, self.remove_pill]
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for pill in self.actions:
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(pill, 1)
        actions.addStretch(1)

        grid = QGridLayout()        # the state of each: Xenia, the game folder
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self.emulator_state, self.folders_state = (self._state_label() for _ in range(2))
        for row, (name, state) in enumerate((("Xenia", self.emulator_state), ("Game folder", self.folders_state))):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label, row, 0)
            grid.addWidget(state, row, 1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["In Steam", "Game title", "Title ID", "Kind", "File"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(column, mode)
        self.table.itemChanged.connect(lambda _item: self._update_buttons())
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.xenia_button = QPushButton("Xenia settings")
        self.xenia_button.setToolTip("Open Xenia's own window for what the Settings tab does not set: its other "
                                     "settings, profiles and installed content")
        self.xenia_button.clicked.connect(self.on_open_xenia)
        self.remove_game_button = QPushButton("Remove game…")
        self.remove_game_button.setToolTip("Delete the chosen game from the disk: a window lists what would go, and "
                                           "you untick what to keep; nothing is deleted before you confirm")
        self.remove_game_button.clicked.connect(self.on_remove_game)
        self.covers_button = QPushButton("Steam artwork…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Steam "
                                      "gives each game its cover, banner and logo from SteamGridDB in Steam")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Steam", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        self.steam_hint = hint_label(f"Tick a game to put it in Steam. A game is started from "
                                     f"{style.link(self, STEAM_URL, 'Steam')}.")
        self.steam_hint.setOpenExternalLinks(False)      # the app opens Steam itself (open_steam)
        self.steam_hint.linkActivated.connect(lambda _url: self.open_steam())
        buttons.addWidget(self.steam_hint, 1)
        buttons.addWidget(self.xenia_button)
        buttons.addWidget(self.remove_game_button)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)
        games_page = QWidget()
        games = QVBoxLayout(games_page)
        games.setContentsMargins(0, 8, 0, 0)
        games.addWidget(self.table, 1)
        games.addLayout(buttons)

        self.settings_page = SettingsPage("Xenia", xenia_settings.SETTINGS,
                                          lambda: xenia_settings.read_settings(self.xenia_home),
                                          lambda setting, value: xenia_settings.write_setting(self.xenia_home, setting,
                                                                                              value),
                                          self.xenia_running, SETTINGS_LEAD, self.log)
        self.output = Terminal()
        self.output.setPlaceholderText("What the app did, with the time, appears here.")
        self.output.set_text(applog.tail(self.log_path))
        log_page = QWidget()
        log = QVBoxLayout(log_page)
        log.setContentsMargins(0, 8, 0, 0)
        log.addWidget(hint_label(f"Everything the app said and did, newest last; the same lines are in "
                                 f"{escape(private(self.log_path))}, which turns over at 1 MB."))
        log.addWidget(self.output, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(games_page, "Your games")
        self.tabs.addTab(self.settings_page, "Settings")
        self.tabs.addTab(log_page, "Log")

        self.running = WrappedLabel()
        self.running.setStyleSheet("font-weight:600;")
        self.running.setWordWrap(True)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(self.intro)
        lay.addSpacing(4)
        lay.addLayout(actions)
        lay.addSpacing(4)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.running)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · Xenia {emulator.VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()
        self.release_check.start(newer_release)

    @staticmethod
    def _state_label() -> QLabel:
        label = WrappedLabel()                  # its lines count in the window's minimum height
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        self.version = emulator.installed_version(self.home)
        self.folders = library.fixed(self.user_home, self.drives)
        self.games = scan(self.folders)
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_cover = ({str(g.file) for g in self.games if str(g.file) in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_cover = {}, set()
        # A game renamed or moved after it was put in Steam keeps its mark (owner, 03-11-2026, from the Windows
        # Portable Suite's managers, 01-11-2026; core's renamed): known by its code, else its file's size.
        found = {str(g.file): renamed.identity(g.title_id, g.file) for g in self.games}
        known = renamed.load(self.settings.qsettings)
        self.moved = renamed.follow(known, found, self.in_steam)
        renamed.remember(self.settings.qsettings, known, found, self.in_steam)
        self._show_state()
        self._fill_table()
        if self.moved and set(self.moved) != self._moved_said:
            self._moved_said = set(self.moved)
            titles = [g.title for g in self.games if str(g.file) in self.moved]
            self.say(f"Found again under a new name or in another folder, with its Steam mark: {', '.join(titles)}. "
                     "Update Steam brings the shortcut in Steam up to date.")
        self.settings_page.load()

    def say(self, text: str, ok: bool = True) -> None:
        """What the window has to say: the line under the tabs, the Log tab and the log file."""
        self.running.setStyleSheet("font-weight:600;" + ("" if ok else "color:#c62828;"))
        self.running.setText(text)
        self.note(text, ok)

    def note(self, text: str, ok: bool = True) -> None:
        """Into the Log tab and the log file only: something that happened, not what the window is doing now."""
        (self.log.info if ok else self.log.error)(text)
        stamp = time.strftime(applog.DATE)
        self.output.appendPlainText(f"{stamp} {'INFO' if ok else 'ERROR'} {text}")

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(NOT_INSTALLED)
            self.emulator_box.set_value("—")
            tip = (f"Install downloads Xenia {pinned}, the build this version of the app was tried with, and checks it "
                   "before installing it.")
        else:
            self.emulator_state.setText(INSTALLED)
            self.emulator_box.set_value(self.version)
            if self.version != pinned:
                tip = f"Xenia {self.version} is installed; this version of the app brings {pinned}: Install puts it in."
                if not self._pin_noted:
                    self.note(tip)
                    self._pin_noted = True
            else:
                tip = (f"Xenia {pinned}, the build this version of the app was tried with: Xenia Canary, experimental "
                       "on Linux, so not every game starts")
        if self.newer is not None:
            tip += (f"\nXenia {self.newer.version} is out ({self.newer.published}). A later version of this app "
                    f"brings it, once it has been tried on the board: {self.newer.url}")
        self.emulator_state.setToolTip(tip)

        # The app's own folders (owner, 03-11-2026): the home folder's, and a removable drive's when it has one.
        where = ", ".join(f"<b>{escape(private(f))}</b>" for f in self.folders)
        self.folders_state.setText(f"{where}: put your games there (ISO images, unpacked discs, .zar archives, Games "
                                   "on Demand and Arcade packages; in folders too). A USB drive or an SD card with a "
                                   "Games/XBOX360 folder on it is looked in too.")
        self.folders_state.setToolTip("\n".join(private(f) for f in self.folders))
        self.games_box.set_value(str(len(self.games)))
        found = {str(g.file) for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install Xenia first.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Put your games in the game folder.")
        else:
            self.pill.set_status("Ready", "ok", "Xenia is installed and games were found.")

    def _release_found(self, release: ReleaseInfo | None) -> None:
        self.newer = release
        if release is not None:
            self._show_state()
            self.note(f"Xenia {release.version} is out ({release.published}); a later version of this app brings it, "
                      f"once it has been tried on the board: {release.url}")

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if str(game.file) in self.in_steam or str(game.file) in self.moved
                              else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam" if str(game.file) in self.in_steam else "Not in Steam")
            self.table.setItem(row, STEAM, box)
            kind = KINDS.get(game.kind, game.kind)
            for column, text in ((GAME, game.title), (SERIAL, game.title_id), (KIND, kind), (FILE, str(game.file))):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.blockSignals(False)
        self._update_buttons()

    def ticked(self) -> list[Game]:
        return [g for row, g in enumerate(self.games)
                if self.table.item(row, STEAM).checkState() == Qt.CheckState.Checked]

    def chosen(self) -> Game | None:
        rows = self.table.selectionModel().selectedRows()
        return self.games[rows[0].row()] if rows and rows[0].row() < len(self.games) else None

    def steam_plan(self) -> tuple[list[Game], list[Game]]:
        """(games to add or bring up to date, games to take out): the ticked ones in, the others out, and the
        shortcuts of games no longer found out too."""
        add = self.ticked()
        found = {str(g.file) for g in self.games}
        remove = [g for g in self.games if str(g.file) in self.in_steam and g not in add]
        remove += [Game(Path(file), name) for file, name in self.in_steam.items() if file not in found]
        return add, remove

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        installed_ = bool(self.version)
        self.refresh_pill.setEnabled(idle)
        self.install_pill.setEnabled(idle and self.version != emulator.VERSION)
        self.remove_pill.setEnabled(idle and installed_)
        self.covers_button.setEnabled(idle)
        self.remove_game_button.setEnabled(idle and self.chosen() is not None)
        self.xenia_button.setEnabled(idle and installed_)
        add, remove = self.steam_plan()
        named = shortcuts.names(add)        # a name in Steam that differs is renamed
        changed = bool(remove) or any(self.in_steam.get(str(g.file)) != named[g.file]
                                      or str(g.file) in self.no_cover for g in add)
        self.steam_button.setEnabled(idle and changed and self.steam_dir is not None and not steam.game_mode())
        if self.steam_dir is None:
            self.steam_button.setToolTip("Steam was never started on this system: start it once first")
        elif steam.game_mode():
            self.steam_button.setToolTip("In Game Mode Steam is the session itself: change it in Desktop Mode")
        else:
            self.steam_button.setToolTip(STEAM_TIP)

    # --- Actions ----------------------------------------------------------------------------------------------

    def _ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, window_title(title), text)
        return answer == QMessageBox.StandardButton.Yes

    def _start(self, text: str, job) -> None:
        if self.worker.start(job):
            self.running.setStyleSheet("font-weight:600;")
            self.running.setText(text)
            self.log.info(text)
            self._update_buttons()

    def _job_done(self, result: tuple[bool, str]) -> None:
        ok, message = result[0], private(result[1])     # a path in an error: the user's folders as ~
        self.refresh()
        self.say(message, ok)

    def on_install(self) -> None:
        if not self._ask("Install", f"Download Xenia {emulator.VERSION} from GitHub (about {emulator.SIZE_MB} MB)?"
                                    "\n\nIt is checked against the SHA-256 this app was tried with before it is "
                                    f"installed in {self.home}."):
            return
        home, fetch = self.home, self.fetch

        def job() -> tuple[bool, str]:
            try:
                return True, emulator.install(home, fetch)
            except (emulator.EmulatorError, OSError) as error:
                return False, f"Xenia was not installed: {error}"
        self._start(f"Downloading Xenia {emulator.VERSION}…", job)

    def on_remove(self) -> None:
        text = "Remove the installed Xenia?\n\nIts own folder, with its settings, saves and installed content, stays."
        if self.in_steam:
            text += "\nThe games in Steam no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.refresh()
            self.say("Xenia was removed.")

    def xenia_command(self, *args: str) -> list[str]:
        """Xenia through the run wrapper (from the app folder when it is not installed yet)."""
        run = self.run_path if self.run_path.is_file() else ROOT / shortcuts.RUN_NAME
        return [str(run), *args]

    def on_open_xenia(self) -> None:
        command = self.xenia_command()
        if QProcess.startDetached(command[0], command[1:])[0]:
            self.note("Xenia's own window was opened.")
        else:
            self.say(f"Xenia could not be started: {command[0]} did not run.", ok=False)

    def open_steam(self) -> None:
        """The Steam link: Steam's library on the desktop (Steam starts when it does not run)."""
        if self.open_url(STEAM_URL):
            self.note("Steam was opened.")
        else:
            self.say("Steam could not be opened: xdg-open is missing.", ok=False)

    def on_remove_game(self) -> None:
        """Remove game… (owner, 03-11-2026, from the Windows Portable Suite's managers: before deleting anything, let
        the user decide what to keep): a window lists what of the chosen game would go, a row each with its size,
        every row ticked; unticking keeps it, Delete marked deletes the rows still ticked (read-only files too) off
        the window's thread, its Steam shortcut through Steam, and Cancel deletes nothing. Xenia's content folder, with the saves,
        stays."""
        game = self.chosen()
        if game is None:
            return
        items, why = library.removal_items(game, self.folders, self.games, str(game.file) in self.in_steam)
        if not items:
            self.say(why, ok=False)
            return
        if KeepDialog(f"Remove {game.title}", items, self).exec() != QDialog.DialogCode.Accepted:
            self.say("Nothing was deleted.")
            return
        chosen = keep.chosen(items)
        kept = [item.label for item in items if not item.delete]
        paths = [path for item in chosen for path in item.paths]
        take_out = any(item.key == library.STEAM_ITEM for item in chosen)
        folder, closed, run, existing = self.steam_dir, self.steam_closed, self.run_path, self.in_steam
        title = game.title

        def job() -> tuple[bool, str]:
            failed = keep.delete(paths)
            library.tidy(game)
            gone = [item.label for item in chosen if item.paths and not any(item.label.startswith(f.split(" (")[0])
                                                                                for f in failed)]
            if take_out and folder is not None:
                try:
                    closed(lambda: steam.write_shortcuts(folder, shortcuts.changes([], [game], run, LOGO_PATH, existing)))
                    gone.append("its shortcut in Steam")
                except (steam.SteamError, steam.ShortcutError, OSError) as error:
                    failed.append(f"its Steam shortcut ({error})")
            text = f"{title}: deleted {', '.join(gone) if gone else 'nothing'}."
            if kept:
                text += f" Kept: {', '.join(kept)}."
            if failed:
                text += f" Not deleted: {', '.join(failed)}."
            return not failed, text
        self._start(f"Deleting {title}…", job)

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.say(f"The shortcuts run {self.run_path}, which is not there: install {APP_NAME} through the "
                     "portal first.", ok=False)
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.say("Install Xenia first: the games in Steam start it.", ok=False)
            return
        text = f"{len(add)} game(s) in Steam" + (f", {len(remove)} taken out." if remove else ".")
        if self.steam_running():
            text += "\n\nSteam closes for it and starts again in the background."
        if not self._ask("Steam", text):
            return
        folder, closed, run, existing = self.steam_dir, self.steam_closed, self.run_path, self.in_steam
        key, home, get = covers.read_key(self.covers_key), self.covers_home, self.covers_get

        def job() -> tuple[bool, str]:
            # The pictures first, off the GUI thread; the artwork is drawn here too, on QImage only.
            notes = (covers.fetch([(shortcuts.cover_name(g), g.title) for g in add], shortcuts.COVERS, key, home,
                                  get) if key else [])
            changes = shortcuts.changes(add, remove, run, LOGO_PATH, existing,
                                        found=lambda g: covers.art(home, shortcuts.cover_name(g), shortcuts.COVERS))
            found: dict[str, str] | None = {}
            extra: list[str] = []

            def change() -> None:
                # Read back right after the write, while Steam is still closed (owner, 03-11-2026, from the Windows
                # Portable Suite's managers: "it still says 0 games in Steam"): whether the shortcuts were written
                # as the app reads them, before Steam touches the file. A failed read is said, not passed over.
                nonlocal found
                steam.write_shortcuts(folder, changes)
                try:
                    found = shortcuts.in_steam(folder)
                except OSError as error:
                    found = None
                    extra.append(f"Steam's file could not be read back: {error}")

            try:
                restarted = closed(change)
            except (steam.SteamError, steam.ShortcutError, OSError) as error:
                return False, "\n".join([*notes, f"Steam was not changed: {error}"])
            if found is not None:
                missing = [g.title for g in add if str(g.file) not in found]
                if missing:
                    extra.append(f"Read back from Steam's file, {len(add) - len(missing)} of the {len(add)} game(s) "
                                 f"are there: not {', '.join(missing)}.")
            again = " Steam was closed for it and starts again in the background." if restarted else ""
            return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in the library"
                                              f"{f'; {len(remove)} taken out' if remove else ''}.{again}", *extra])
        self._start("Looking up covers and changing Steam's shortcuts…" if key else "Changing Steam's shortcuts…",
                    job)

    def on_covers(self) -> None:
        """Asks for the suite's SteamGridDB API key; empty turns the lookup off (the pictures kept stay in use)."""
        if covers.edit_key(self, self.covers_key, "Update Steam"):
            self.refresh()
            self.say("The SteamGridDB key was changed." if covers.read_key(self.covers_key) else
                     "The SteamGridDB key was taken out; the pictures kept stay in use.")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        QTimer.singleShot(0, self.place_states)         # once the pills below have their new width

    def place_states(self) -> None:
        """The state ends at the middle of the last header pill: the spacer after it is half its width."""
        self.states_spacer.setFixedWidth(max(0, self.steam_box.width() // 2))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.worker.running and not self._ask("Close", "A download or a change to Steam is still running. "
                                                          "Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.release_check.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
