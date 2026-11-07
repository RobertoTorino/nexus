# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window, built as PCSX2 Manager's and RPCS3 Manager's (owner, 24-10-2026: the manager that works is the
pattern for the others): the header with the Refresh pill and the state boxes, a row of action pills (Install and
Uninstall for shadPS4, Install for the system modules, Install (Extract PKG) and Add folder for the games, Account
for shadNet; the owner's order, 24-10-2026) in place of the four numbered steps with buttons, the state of each
(shadPS4, the system modules, the game folders, shadNet) in a short line, then three tabs: the games found, each
with a box for Steam; shadPS4's settings (settings_page.py); and the app's log. Downloading shadPS4, asking GitHub
for a newer one and changing Steam's files run off the GUI thread; nothing here needs root. The look is the app's
own blue (style.py). Games Install (or a package dropped on the window, or given to the app) opens the package
extractor (extract_dialog.py) on the game folders. Steam artwork… takes the suite's SteamGridDB API key, with which
Update Steam looks up a cover for each game's portrait first (core's covers).

The app has no Play button: a game is started from Steam. The window keeps what the app owns in shadPS4's files
(userdata.py): the quit hotkeys. shadPS4's own window (Big Picture, shadPS4 settings under the games) stays for what
the Settings tab does not set. The window also reads the volume Bazzite remembers for shadPS4 and says when it is
muted (seen on the board). What the window says it also writes to the app's log (core's applog), shown in the Log
tab.

Packages (owner, 05-11-2026, as the Windows Portable Suite's shadPS4 Manager since 30-10-2026): a .pkg put in a game
folder is a row of its own in Your games, "PKG" or "PKG update", until it is unpacked (extract.py). Unpack takes the
chosen one, Unpack all every one, the games first; each update goes beside its game and replaces an older one there.
The packages unpacked whole are remembered (path, size and time), so they are no longer rows, and offered for
deletion in the keep window: a package takes as much room as its game."""

from __future__ import annotations

import re
import subprocess
import time
from html import escape
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, sound, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core import keep, renamed
from bc250_core.keep_dialog import KeepDialog
from bc250_core.platform import bin_home, private, xdg_open
from bc250_core.theme import GREEN, RED
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import (APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, controllers, emulator, extract, library,
               settings_page, shadnet, shortcuts, style, userdata)
from .games import MAX_DEPTH, Game, scan
from .settings_page import SettingsPage
from .shadnet_dialog import ShadNetDialog

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/shadps4/"
FOLDER_TIMEOUT = 60
SHADNET_WATCH_MS = 5000
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
RUNNING = "shadPS4 is running: close it first, it writes its own settings over the change when it closes."
STEAM_URL = "steam://open/games"        # Steam's library; Steam starts when it does not run
STEAM, GAME, SERIAL, VERSION, FOLDER = range(5)             # the table's columns
GAMES, SETTINGS, LOG = range(3)                             # the tabs
_NUMBERED = re.compile(r"\d+(\.\d+)*")


RUNNING_REMOVE = "shadPS4 is running: close it first, then remove the game."
UNPACKED_KEY = "packages/unpacked"      # the packages unpacked whole (path|size|time): no longer waiting rows
PROGRESS_MS = 500                       # how often the line under the tabs counts an unpacking package's files


def _stamp(path: Path) -> str:
    """A file as the app knows it again: path|size|time; "" for one that cannot be read."""
    try:
        info = path.stat()
    except OSError:
        return ""
    return f"{path}|{info.st_size}|{info.st_mtime_ns}"


class ShadSettings(SettingsStore):
    DEFAULTS: dict = {}


class MainWindow(QMainWindow):
    CONTROLLER_POLL = 3000                  # ms: how often the window looks for a controller

    def __init__(self, home: Path | None = None, shad_home: Path | None = None, steam_dir: Path | None = None,
                 run: Path | None = None, fetch: emulator.Download = emulator.download,
                 steam_closed=steam.with_steam_closed, steam_running=steam.steam_running,
                 newer_release=emulator.newer_release, shadnet_connect: shadnet.Connect = shadnet._connect,
                 shad_running=userdata.shadps4_running, covers_home: Path | None = None,
                 covers_get: covers.Get = covers._get, covers_key: Path | None = None,
                 log_path: Path | None = None, devices: Path = controllers.DEVICES, open_url=xdg_open,
                 sound_state: Path | None = None, user_home: Path | None = None,
                 drives: Callable[[], list[Path]] = library.removable_drives):
        """*home*: where the app installs shadPS4; *shad_home*: shadPS4's own folder; *steam_dir*: Steam's folder
        (None: looked up); *run*: the run wrapper the shortcuts start; *fetch*: the download; *steam_closed* and
        *steam_running*: closing Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a
        newer shadPS4; *shadnet_connect*: opens a connection to a shadNet server; *shad_running*: whether shadPS4
        runs (its files are not written then); *covers_home*, *covers_get* and *covers_key*: where the covers are
        kept, how SteamGridDB is asked and the suite's key file (tests never touch the real ones); *log_path*: the
        app's log file, as the Log tab shows it (__main__ set it up); *devices*: the kernel's list of input
        devices, for the controller state; *open_url*: opens a URL on the desktop (the Steam link); *sound_state*:
        WirePlumber's file with the volume the desktop remembers for shadPS4 (tests pass their own); *user_home*: the home folder with the app's own game
        folder, Games/PS4 (library.fixed); *drives*: the removable drives looked at for one."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.shad_home = shad_home or userdata.shadps4_home()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.user_home = user_home or Path.home()
        self.drives = drives
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.shadnet_connect = shadnet_connect
        self.shad_running = shad_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.log_path = log_path or applog.log_file(APP_ID)
        self.devices = devices
        self.open_url = open_url
        self.sound_state = sound_state or sound.stream_properties()
        self.sound: tuple[float, bool] | None = None    # (volume, muted) Bazzite remembers for shadPS4; None: unknown
        self._sound_said = False                        # said once while it stays off
        self._pin_noted = False                         # another version installed than the app brings: logged once
        self.controllers: list[str] | None = None       # the controllers last seen; None before the first look
        self.log = applog.logger(APP_ID)
        self.shadnet_check = UpdateChecker(self)        # whether the shadNet server answers, off the GUI thread
        self.shadnet_check.finished.connect(self._server_checked)
        self.shadnet_watch = QTimer(self)               # while shadPS4 runs: its log says whether it signed in
        self.shadnet_watch.setInterval(SHADNET_WATCH_MS)
        self.shadnet_watch.timeout.connect(self._watch_shadnet)
        self._shad_was_running = False
        self._newer_release = newer_release
        self.newer: ReleaseInfo | None = None           # shadPS4's newest stable, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.settings = ShadSettings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread: a download or Steam
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.moved: dict[str, str] = {}               # a game found again under another name: its file in Steam
        self._moved_said: set[str] = set()
        self.no_logo: set[str] = set()                # games in Steam whose shortcut has no logo yet
        self.old_tags: set[str] = set()               # games in Steam whose shortcut has the tags of an older name
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""
        self.config: dict = {}
        self.users: list[userdata.User] = []
        self.folders: list[Path] = []
        self.waiting: list[extract.Package] = []        # the packages in the game folders still to unpack
        self.unpacking = ("", (0, 0))                   # while packages unpack: which one, and its files done / all
        self.unpacked_whole: list[extract.Package] = []  # the last Unpack's packages without a missing file
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self._show_unpacking)

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        # The states on the right of the title row, ending at the middle of the last pill below them (owner,
        # 24-10-2026): a spacer of half that pill's width after them, set whenever the window's size changes.
        self.pill = StatusText()
        header.add_action(self.pill)
        self.shadnet_pill = StatusText()                # shadNet Online, Offline or Off
        header.add_action(self.shadnet_pill)
        self.controller = StatusText()                  # beside them: whether a controller is connected
        header.add_action(self.controller)
        self.states_spacer = QWidget()
        self.states_spacer.setFixedSize(0, 1)
        header.add_action(self.states_spacer)
        self.controller_timer = QTimer(self)
        self.controller_timer.setInterval(self.CONTROLLER_POLL)
        self.controller_timer.timeout.connect(self.show_controller)
        self.controller_timer.start()
        self.refresh_pill = style.action_pill("Refresh", "Click to refresh", "Read the state again and look for games")
        self.refresh_pill.clicked.connect(self.refresh)
        self.emulator_box = MetricBox("shadPS4 version", style.BLUE)
        self.games_box = MetricBox("Your games", style.BLUE)
        self.steam_box = MetricBox("Available in Steam", style.BLUE)
        self.time_box = MetricBox("Play time", style.BLUE)      # all games together, as shadPS4 counts it
        # The header's pills spread over the window's width in equal parts, as the action pills below (owner,
        # 24-10-2026). (The System modules box went: the System modules line below says how many there are.)
        self.header_pills = [self.refresh_pill, self.emulator_box, self.games_box, self.steam_box, self.time_box]
        for box in self.header_pills:
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.add_second(box, 1)
        self.intro = hint_label(
            "PS4 games on the system with the shadPS4 emulator. The app installs the shadPS4 release it was tried "
            "with, finds your games (or unpacks them from .pkg files) and puts them in Steam, so a game starts "
            "straight away, also from Steam's Big Picture Mode. Games, saves and system modules come from your own "
            "PS4; the app never downloads them. " + style.link(self, emulator.RELEASE_PAGE, "shadPS4's release notes")
            + " · " + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)   # its lines count in the minimum

        # What there is to do, as pills the size of the header's, spread over the window's width (owner,
        # 24-10-2026): what it is for in large type (shadPS4, Games, shadNet), what the pill does under it. The games
        # and the system modules are put in the app's own folder, Games/PS4 (owner, 03-11-2026: fixed folders, no
        # folder choosing); a package is still chosen for Extract PKG.
        self.install_pill = style.action_pill("shadPS4", "Install", f"Download shadPS4 {emulator.VERSION} from "
                                                                    f"GitHub (about {emulator.SIZE_MB} MB) and "
                                                                    "check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("shadPS4", "Uninstall", "Remove the installed shadPS4; its own folder "
                                                                     "(saves, settings, system modules) stays")
        self.remove_pill.clicked.connect(self.on_remove)
        self.package_pill = style.action_pill("Games", "Install", "Choose a package file (.pkg: a game, its update "
                                                                  "or add-on content); Extract PKG unpacks it into "
                                                                  "a game folder, in the layout shadPS4 loads")
        self.package_pill.clicked.connect(lambda: self.open_extract())
        self.extract_dialog = None                      # the Extract PKG window while it is open
        self.account_pill = style.action_pill("shadNet", "Account", "Your shadNet account: create one, try it, and "
                                                                    "have shadPS4 sign in with it")
        self.account_pill.clicked.connect(self.on_shadnet)
        self.actions = [self.install_pill, self.remove_pill, self.package_pill, self.account_pill]
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for pill in self.actions:                       # each a sixth of the width, whatever the window's
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(pill, 1)

        grid = QGridLayout()        # the state of each: shadPS4, the system modules, the game folders, shadNet
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self.emulator_state, self.modules_state, self.folders_state, self.shadnet_state = (self._state_label()
                                                                                           for _ in range(4))
        self.folders_state.setOpenExternalLinks(False)  # a folder's name is a link that takes it out
        for row, (name, state) in enumerate((("shadPS4", self.emulator_state),
                                             ("Sys modules", self.modules_state),
                                             ("Game folders", self.folders_state), ("shadNet", self.shadnet_state))):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label, row, 0)
            grid.addWidget(state, row, 1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["In Steam", "Game title", "Id", "Version", "Folder"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(column, mode)
        self.table.itemChanged.connect(lambda _item: self._update_buttons())

        self.shad_button = QPushButton("shadPS4 settings")
        self.shad_button.setToolTip("Open shadPS4's own window (Big Picture) for what the app does not set: the "
                                    "controller's buttons, a game's own settings, its game list")
        self.shad_button.clicked.connect(self.on_open_shadps4)
        self.remove_game_button = QPushButton("Remove game…")
        self.remove_game_button.setToolTip("Delete the chosen game from the disk: a window lists what would go, and "
                                           "you untick what to keep; nothing is deleted before you confirm")
        self.remove_game_button.clicked.connect(self.on_remove_game)
        self.covers_button = QPushButton("Steam artwork…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Steam "
                                      "gives each game its cover from SteamGridDB in Steam; the wide picture, the "
                                      "banner and the logo stay the game's own")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Steam", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        self.steam_hint = hint_label(f"Tick a game to put it in Steam. A game is started from "
                                     f"{style.link(self, STEAM_URL, 'Steam')}.")
        self.steam_hint.setOpenExternalLinks(False)      # the app opens Steam itself (open_steam)
        self.steam_hint.linkActivated.connect(lambda _url: self.open_steam())
        self.unpack_button = QPushButton("Unpack")
        self.unpack_button.setToolTip("Unpack the chosen package (a PKG row) into its game folder")
        self.unpack_button.clicked.connect(self.on_unpack)
        self.unpack_all_button = QPushButton("Unpack all")
        self.unpack_all_button.setToolTip("Unpack every package that waits, one after the other: the games first, "
                                          "then their updates")
        self.unpack_all_button.clicked.connect(self.on_unpack_all)
        buttons.addWidget(self.steam_hint, 1)
        buttons.addWidget(self.unpack_button)
        buttons.addWidget(self.unpack_all_button)
        buttons.addWidget(self.shad_button)
        buttons.addWidget(self.remove_game_button)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)
        games_page = QWidget()
        games = QVBoxLayout(games_page)
        games.setContentsMargins(0, 8, 0, 0)
        games.addWidget(self.table, 1)
        games.addLayout(buttons)

        self.settings_page = SettingsPage(self.shad_home, self.shad_running, self.log)
        self.settings_page.sound_path = self.sound_state
        self.settings_page.sound_changed.connect(self.show_sound)
        self.output = Terminal()
        self.output.setPlaceholderText("What the app did, with the time, appears here.")
        self.output.set_text(applog.tail(self.log_path))
        log_page = QWidget()
        log = QVBoxLayout(log_page)
        log.setContentsMargins(0, 8, 0, 0)
        log.addWidget(hint_label(f"Everything the app said and did, newest last, and each game started from Steam; "
                                 f"the same lines are in {escape(private(self.log_path))}, which turns over at 1 MB."))
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
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · shadPS4 {emulator.VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)

        self.setAcceptDrops(True)                       # a .pkg dropped on the window opens Extract PKG
        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()
        self.release_check.start(self._newer_release)

    @staticmethod
    def _state_label() -> QLabel:
        label = WrappedLabel()                  # its lines count in the window's minimum height
        # Its links take a click too: without the second flag a click on one did nothing (owner, 24-10-2026).
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        self.version = emulator.installed_version(self.home)
        self.config = userdata.read_config(self.shad_home)
        self.folders = library.fixed(self.user_home, self.drives)
        self.sync_folders()
        self.sync_modules()
        self.modules = userdata.check_modules(userdata.modules_folder(self.shad_home, self.config))
        self.users = userdata.read_users(self.shad_home)
        self.prepare_shadps4()
        self.games = scan(self.folders)
        done = self.unpacked_packages()
        self.waiting = [p for p in extract.waiting(self.folders, self.unpacked()) if _stamp(p.path) not in done]
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_logo = {str(g.eboot) for g in self.games if str(g.eboot) in self.in_steam and
                            shortcuts.logo_missing(self.steam_dir, g, self.in_steam[str(g.eboot)], self.run_path)}
            self.old_tags = shortcuts.old_tags(self.steam_dir) if self.steam_dir else set()
            self.no_cover = ({str(g.eboot) for g in self.games if str(g.eboot) in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_logo, self.old_tags, self.no_cover = {}, set(), set(), set()
        # A game renamed or moved after it was put in Steam keeps its mark (owner, 03-11-2026, from the Windows
        # Portable Suite's managers, 01-11-2026; core's renamed): known by its code, else its file's size.
        found = {str(g.eboot): renamed.identity(g.title_id, g.eboot) for g in self.games}
        known = renamed.load(self.settings.qsettings)
        self.moved = renamed.follow(known, found, self.in_steam)
        renamed.remember(self.settings.qsettings, known, found, self.in_steam)
        self._show_state()
        self._fill_table()
        if self.moved and set(self.moved) != self._moved_said:
            self._moved_said = set(self.moved)
            titles = [g.title for g in self.games if str(g.eboot) in self.moved]
            self.say(f"Found again under a new name or in another folder, with its Steam mark: {', '.join(titles)}. "
                     "Update Steam brings the shortcut in Steam up to date.")
        self.settings_page.load()
        self.show_controller()
        self.show_sound()

    def prepare_shadps4(self) -> None:
        """shadPS4's files brought to what the app owns: the quit hotkeys in input_config/global.ini, which shadPS4
        reads when a game starts (so it may run meanwhile); what was added goes to the log."""
        try:
            added = userdata.add_quit_bindings(self.shad_home)
        except OSError as error:
            self.note(f"shadPS4's quit hotkeys could not be written: {error}", ok=False)
            return
        if added:
            self.note("shadPS4 set up: Share + Options (Back + Start) and Ctrl+Shift+End open its quit window.")

    def show_sound(self) -> None:
        """The volume Bazzite remembers for shadPS4 (muted or turned down, a game plays without a sound): in the
        Settings tab's Sound box, and said once while it stays off."""
        self.sound = sound.stream_sound(settings_page.STREAM, self.sound_state)
        text, off = self.settings_page.show_sound(self.sound)
        if off and not self._sound_said:
            self.say(text, ok=False)
        self._sound_said = off

    def show_controller(self) -> None:
        """The controller state beside the title: a game started from Steam reads the controller that is there
        when it starts, so the window says when none is (switched off, asleep, not paired)."""
        found = controllers.connected(self.devices)
        if found == self.controllers:
            return
        self.controllers = found
        if found:
            self.controller.set_status("Controller connected" if len(found) == 1 else f"{len(found)} controllers",
                                       "ok", "Connected: " + ", ".join(found) + ". A game started from Steam "
                                       "reads it; Share + Options together open shadPS4's quit window in the "
                                       "game.")
        else:
            self.controller.set_status("No controller", "warn",
                                       "No controller is connected: switch it on, or press its PS button to wake "
                                       "it, before starting a game from Steam. Without one, shadPS4 plays with the "
                                       "keyboard only.")

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

    def sync_folders(self) -> None:
        """shadPS4's own game folders (config.json) made the app's (owner, 03-11-2026), so shadPS4's own window lists
        the games too; not while shadPS4 runs, and nothing written while they match."""
        if userdata.game_folders(self.config) == self.folders or self.shad_running():
            return
        try:
            userdata.set_game_folders(self.shad_home, self.folders)
        except userdata.UserDataError as error:
            self.say(f"shadPS4's game folders were not set: {error}", ok=False)
            return
        self.config = userdata.read_config(self.shad_home)

    def sync_modules(self) -> None:
        """The system modules put in Games/PS4/Modules copied into shadPS4's module folder, only what is new or
        changed (owner, 03-11-2026: the app takes care of them); shadPS4 reads them when a game asks for one."""
        try:
            copied = userdata.sync_modules(library.modules_home(self.user_home),
                                           userdata.modules_folder(self.shad_home, self.config))
        except OSError as error:
            self.say(f"The system modules were not taken from {private(library.modules_home(self.user_home))}: "
                     f"{error}", ok=False)
            return
        if copied:
            self.say(f"{len(copied)} system module(s) taken from {private(library.modules_home(self.user_home))} "
                     "into shadPS4's module folder.")

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(f"Not installed. Install downloads shadPS4 {pinned}, the release pinned "
                                        "for this version of the app, and checks it before unpacking. The "
                                        "app says when a newer shadPS4 is out.")
            self.emulator_box.set_value("—")
        else:                                   # the version alone (owner, 24-10-2026), the advice in the tip
            self.emulator_state.setText(f"<b>{escape(self.version)}</b>")
            # The box is not wide enough for a nightly build's name (date and commit) from before the channel went.
            self.emulator_box.set_value(self.version if _NUMBERED.fullmatch(self.version) else "other")
            if self.version != pinned and not self._pin_noted:
                self.note(f"shadPS4 {self.version} is installed; this version of the app brings {pinned}: Install "
                          "puts it in.")
                self._pin_noted = True
        tip = f"shadPS4 {pinned}, pinned for this version of the app"
        if self.version and self.version != pinned:
            tip = f"shadPS4 {self.version} is installed; this version of the app brings {pinned}: Install puts it in."
        if self.newer is not None:              # in the tip and the log, so the line stays the version (owner)
            tip += (f"\nshadPS4 {self.newer.version} is out ({self.newer.published}). A later version of this app "
                    f"may pin it: {self.newer.url}")
        self.emulator_state.setToolTip(tip)

        m = self.modules                        # Ok in green or Missing sys modules in red (owner, 24-10-2026)
        needed = len(userdata.NEEDED)
        if m.complete:
            self.modules_state.setText(f"<b style='color:{GREEN};'>Ok</b>")
        else:
            self.modules_state.setText(f"<b style='color:{RED};'>Missing sys modules</b>")
        tip = (f"{len(m.needed)} of the {needed} modules shadPS4 cannot do without are in its module folder: "
               f"{m.folder}")
        if m.missing:
            tip += ("\nMany games run without them; a game that needs a missing one does not start. Put those of your "
                    f"own PS4 in {private(library.modules_home(self.user_home))}: the app copies them in. Missing: "
                    + ", ".join(m.missing))
        self.modules_state.setToolTip(tip)

        # The app's own folders (owner, 03-11-2026): the home folder's, and a removable drive's when it has one.
        where = ", ".join(f"<b>{escape(private(f))}</b>" for f in self.folders)
        self.folders_state.setText(f"{where}: put your games there, each in a folder of its own (with eboot.bin); "
                                   "a package (.pkg) put there waits under Your games for Unpack. A USB drive or an "
                                   "SD card with a Games/PS4 folder on it is looked in too.")
        self.folders_state.setToolTip("\n".join(private(f) for f in self.folders)
                                      + f"\n{len(self.games)} game(s) found, up to {MAX_DEPTH} folders deep.")
        self._show_shadnet()
        self.games_box.set_value(str(len(self.games)))
        found = {str(g.eboot) for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))
        self._show_play_time()

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install shadPS4 first.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Add the folder with your games.")
        elif not m.complete:
            self.pill.set_status("Modules missing", "warn", "Some games need system modules from your own PS4.")
        else:
            self.pill.set_status("Ready", "ok", "shadPS4 is installed and games were found.")

    def _show_play_time(self) -> None:
        """The time spent in all games together, as shadPS4 counts it (its play_time.txt); per game in the tip."""
        times = userdata.play_times(self.shad_home)
        total = sum(seconds for seconds, _ in times.values())
        if not total:
            self.time_box.set_value("—", "shadPS4 counts the time spent in each game; none yet.")
            return
        titles = {g.title_id: g.title for g in self.games if g.title_id}
        lines = [f"{titles.get(serial, serial)}: {userdata.played(seconds)}"
                 + (f", last played {time.strftime('%d-%m-%Y %H:%M', time.localtime(last))}" if last else "")
                 for serial, (seconds, last) in sorted(times.items(), key=lambda t: -t[1][0]) if seconds]
        self.time_box.set_value(userdata.played(total), "The time spent in each game, as shadPS4 counts it:\n"
                                + "\n".join(lines))

    def _show_shadnet(self) -> None:
        """The nickname that signs in alone (owner, 24-10-2026), the rest in the tooltip."""
        signing_in = self._signing_in()
        server = userdata.shadnet_server(self.config)
        if not self.users:
            self.shadnet_state.setText("—")
            self.shadnet_state.setToolTip("shadPS4 has not run yet: start it once (shadPS4 settings), then set up "
                                          "your account with shadNet Account.")
        elif signing_in:
            self.shadnet_state.setText(", ".join(f"<b>{escape(u.npid)}</b>" for u in signing_in))
            self.shadnet_state.setToolTip("\n".join(f"{u.npid} ({u.name}) signs in to {server} when a game starts."
                                                     for u in signing_in))
        else:
            self.shadnet_state.setText("Off")
            self.shadnet_state.setToolTip("shadPS4's online service, for online trophies, friends and online play in "
                                          "the games it supports: shadNet Account sets it up.")
        self._show_shadnet_pill()

    def _signing_in(self) -> list[userdata.User]:
        """The users shadPS4 signs in with when a game starts."""
        return [u for u in self.users if u.shadnet and u.npid] if userdata.shadnet_on(self.config) else []

    def _show_shadnet_pill(self) -> None:
        """shadNet Online, Offline or Off. While shadPS4 runs, from its log: whether it signed in. Otherwise
        whether the server answers (without signing in, as shadPS4's own probe), so that it can sign in."""
        names = ", ".join(u.npid for u in self._signing_in())
        if not names:
            self.shadnet_watch.stop()
            self.shadnet_pill.set_status("shadNet Off", "neutral", "shadNet is off: set it up with shadNet Account.")
            return
        self.shadnet_watch.start()
        server = userdata.shadnet_server(self.config)
        self._shad_was_running = self.shad_running()
        if self._shad_was_running:
            state, detail = shadnet.session(self.shad_home / "log")
            if state == "online":
                self.shadnet_pill.set_status("shadNet Online", "ok", f"shadPS4 is signed in to {server} as {detail}.")
            elif state == "offline":
                self.shadnet_pill.set_status("shadNet Offline", "bad", f"{detail}.")
            else:
                self.shadnet_pill.set_status("shadNet …", "neutral",
                                             f"shadPS4 runs; it signs in as {names} when a game starts.")
            return
        try:
            target = shadnet.parse_server(server)
        except shadnet.ShadNetError as error:
            self.shadnet_pill.set_status("shadNet Offline", "bad", str(error))
            return
        connect = self.shadnet_connect

        def job() -> tuple[bool, str]:
            try:
                shadnet.server_answers(target, connect)
            except shadnet.ShadNetError as error:
                return False, f"{error} shadPS4 cannot sign in now."
            return True, f"{target} answers: shadPS4 signs in as {names} when a game starts."
        if self.shadnet_check.start(job) and self.shadnet_pill.kind not in ("ok", "bad"):
            self.shadnet_pill.set_status("shadNet …", "neutral", f"Asking {target}…")

    def _server_checked(self, result: tuple[bool, str]) -> None:
        if self._shad_was_running or not self._signing_in():
            return                                      # shadPS4's own session says more, or shadNet is off now
        ok, detail = result
        self.shadnet_pill.set_status("shadNet Online" if ok else "shadNet Offline", "ok" if ok else "bad", detail)

    def _watch_shadnet(self) -> None:
        """While shadPS4 runs, and once when it has ended (then the server again)."""
        if self.shad_running() or self._shad_was_running:
            self._show_shadnet_pill()

    def _release_found(self, release: ReleaseInfo | None) -> None:
        self.newer = release
        if release is not None:
            self._show_state()
            self._update_buttons()
            self.note(f"shadPS4 {release.version} is out ({release.published}); a later version of this app may pin "
                      f"it: {release.url}")

    def chosen(self) -> Game | None:
        """The game whose row is selected."""
        rows = self.table.selectionModel().selectedRows()
        return self.games[rows[0].row()] if rows and rows[0].row() < len(self.games) else None

    def chosen_package(self) -> extract.Package | None:
        """The package whose row is selected (the rows after the games)."""
        rows = self.table.selectionModel().selectedRows()
        index = rows[0].row() - len(self.games) if rows else -1
        return self.waiting[index] if 0 <= index < len(self.waiting) else None

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games) + len(self.waiting))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if str(game.eboot) in self.in_steam or str(game.eboot) in self.moved
                              else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam" if str(game.eboot) in self.in_steam else
                           f"Found again under a new name: in Steam as {self.in_steam.get(self.moved[str(game.eboot)], '?')}; "
                           "Update Steam brings the shortcut up to date" if str(game.eboot) in self.moved else "Not in Steam")
            self.table.setItem(row, STEAM, box)
            for column, text in ((GAME, game.title), (SERIAL, game.title_id), (VERSION, game.version),
                                 (FOLDER, game.folder.name or str(game.folder))):
                self.table.setItem(row, column, QTableWidgetItem(text))
            self.table.item(row, FOLDER).setToolTip(str(game.folder))     # the folder's name; the path as the tip
        unpacked = self.unpacked()
        for row, package in enumerate(self.waiting, len(self.games)):
            folder, game = extract.place(package, unpacked)
            kind = "PKG update" if package.category == "gp" and game is not None else "PKG"
            tip = (f"{package.path}\nWaits to be unpacked into {folder}"
                   + (", beside its game, which shadPS4 lays it over" if game is not None else "")
                   + ": Unpack or Unpack all.")
            box = QTableWidgetItem(kind)                # no tick: a package is not in Steam
            box.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, STEAM, box)
            for column, text in ((GAME, package.title or package.path.stem), (SERIAL, package.title_id),
                                 (VERSION, package.version), (FOLDER, package.path.name)):
                self.table.setItem(row, column, QTableWidgetItem(text))
            for column in range(self.table.columnCount()):
                self.table.item(row, column).setToolTip(tip)
        self.table.blockSignals(False)
        self._update_buttons()

    def ticked(self) -> list[Game]:
        return [g for row, g in enumerate(self.games)
                if self.table.item(row, STEAM).checkState() == Qt.CheckState.Checked]

    def steam_plan(self) -> tuple[list[Game], list[Game]]:
        """(games to add or bring up to date, games to take out): the ticked ones in, the others out, and the
        shortcuts of games no longer found out too."""
        add = self.ticked()
        found = {str(g.eboot) for g in self.games}
        remove = [g for g in self.games if str(g.eboot) in self.in_steam and g not in add]
        remove += [Game(Path(eboot), name) for eboot, name in self.in_steam.items() if eboot not in found]
        return add, remove

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        installed = bool(self.version)
        self.refresh_pill.setEnabled(idle)
        self.install_pill.setEnabled(idle and self.version != emulator.VERSION)
        self.remove_pill.setEnabled(idle and installed)
        self.package_pill.setEnabled(idle)
        self.account_pill.setEnabled(idle)
        self.shad_button.setEnabled(idle and installed)
        self.covers_button.setEnabled(idle)
        self.remove_game_button.setEnabled(idle and self.chosen() is not None)
        self.unpack_button.setVisible(bool(self.waiting))
        self.unpack_all_button.setVisible(bool(self.waiting))
        self.unpack_button.setEnabled(idle and self.chosen_package() is not None)
        self.unpack_all_button.setEnabled(idle)
        add, remove = self.steam_plan()
        stale = self.no_logo | self.old_tags | self.no_cover
        named = shortcuts.names(add)        # a name in Steam that differs (one from before the prefix) is renamed
        changed = bool(remove) or any(self.in_steam.get(str(g.eboot)) != named[g.eboot] or str(g.eboot) in stale
                                      for g in add)
        self.steam_button.setEnabled(idle and changed and self.steam_dir is not None and not steam.game_mode())
        if self.steam_dir is None:
            self.steam_button.setToolTip("Steam was never started on this system: start it once first")
        elif steam.game_mode():
            self.steam_button.setToolTip("In Game Mode (a handheld's Steam session) Steam is the session itself: "
                                         "change it in Desktop Mode")
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
        self.progress_timer.stop()
        self.refresh()
        self.say(message, ok)
        if self.unpacked_whole:
            QTimer.singleShot(0, self._packages_unpacked)       # after the line says what was done

    def on_install(self) -> None:
        if not self._ask("Install", f"Download shadPS4 {emulator.VERSION} from GitHub (about {emulator.SIZE_MB} MB)?"
                                    "\n\nIt is checked against the SHA-256 pinned by this app before it is "
                                    f"unpacked into {self.home}."):
            return
        home, fetch = self.home, self.fetch

        def job() -> tuple[bool, str]:
            try:
                return True, emulator.install(home, fetch)
            except (emulator.EmulatorError, OSError) as error:
                return False, f"shadPS4 was not installed: {error}"
        self._start(f"Downloading shadPS4 {emulator.VERSION}…", job)

    def on_remove(self) -> None:
        text = "Remove the installed shadPS4?\n\nIts own folder, with your saves, settings and system modules, stays."
        if self.in_steam:
            text += "\nThe games in Steam no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.refresh()
            self.say("shadPS4 was removed.")

    def open_extract(self, pkg: str | list[str] | None = None) -> None:
        """The Extract PKG window, with *pkg* loaded (several: the first loaded, the rest queued); when it is open
        already, they go into it."""
        pkgs = [pkg] if isinstance(pkg, str) else list(pkg or [])
        if self.extract_dialog is not None:
            if pkgs:
                self.extract_dialog.open_pkgs(pkgs)
            self.extract_dialog.raise_()
            self.extract_dialog.activateWindow()
            return
        try:
            from .extract_dialog import ExtractDialog
        except ImportError as error:                    # cryptography missing: an install from before it
            self.say(f"Extract PKG needs the cryptography package ({error}): install {APP_NAME} again through the "
                     "portal.", ok=False)
            return
        self.extract_dialog = ExtractDialog(self.settings, self.folders, self, pkgs)
        try:
            self.extract_dialog.exec()
            extracted = self.extract_dialog.extracted
        finally:
            self.extract_dialog = None
        if extracted:
            self.refresh()
            self.note("Extract PKG extracted a package; the games were looked for again.")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt override)
        if any(url.toLocalFile().lower().endswith(".pkg") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt override)
        pkgs = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile().lower().endswith(".pkg")]
        if pkgs:
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.open_extract(pkgs))      # after the drop has ended

    def shadps4_command(self, *args: str) -> list[str]:
        """The installed shadPS4 through the run wrapper (from the app folder when it is not installed yet)."""
        run = self.run_path if self.run_path.is_file() else ROOT / shortcuts.RUN_NAME
        return [str(run), *args]

    def on_shadnet(self) -> None:
        self.refresh()
        dialog = ShadNetDialog(self.shad_home, self.config, self.users, self, self.shadnet_connect)
        if dialog.exec():
            self.refresh()
            self.say("shadNet settings saved in shadPS4's own files.")

    def open_steam(self) -> None:
        """The Steam link: Steam's library on the desktop (Steam starts when it does not run)."""
        if self.open_url(STEAM_URL):
            self.note("Steam was opened.")
        else:
            self.say("Steam could not be opened: xdg-open is missing.", ok=False)

    def on_open_shadps4(self) -> None:
        command = self.shadps4_command("-b")
        if QProcess.startDetached(command[0], command[1:])[0]:
            self.note("shadPS4's own window was opened.")
        else:
            self.say(f"shadPS4 could not be started: {command[0]} did not run.", ok=False)

    def on_remove_game(self) -> None:
        """Remove game… (owner, 03-11-2026, from the Windows Portable Suite's managers: before deleting anything, let
        the user decide what to keep): a window lists what of the chosen game would go, a row each with its size,
        every row ticked; unticking keeps it, Delete marked deletes the rows still ticked (read-only files too) off
        the window's thread, its Steam shortcut through Steam, and Cancel deletes nothing. The saves, the play time and the package
        stay."""
        game = self.chosen()
        if game is None:
            return
        if self.shad_running():
            self.say(RUNNING_REMOVE, ok=False)
            return
        items, why = library.removal_items(game, self.folders, self.games, str(game.eboot) in self.in_steam)
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

    # --- Packages ---------------------------------------------------------------------------------------------

    def unpacked(self) -> dict[str, Path]:
        """Each game's folder by its title ID, a game without its update before one with it in it."""
        ordered = sorted((g for g in self.games if g.title_id), key=lambda g: not g.patched)
        return {g.title_id: g.folder for g in ordered}

    def unpacked_packages(self) -> set[str]:
        """The packages unpacked whole (path|size|time): a kept one is no longer a waiting row while it is the same
        file (an update unpacked as a game of its own would be offered again)."""
        stored = self.settings.qsettings.value(UNPACKED_KEY, [])
        stored = [stored] if isinstance(stored, str) else list(stored or [])
        return {s for s in stored if s}

    def remember_unpacked(self, paths: list[Path]) -> None:
        """The packages just unpacked whole kept, and those deleted or changed since forgotten."""
        if not paths and not self.settings.qsettings.contains(UNPACKED_KEY):
            return
        still = {s for s in self.unpacked_packages() if _stamp(Path(s.rsplit("|", 2)[0])) == s}
        stamps = still | {stamp for stamp in map(_stamp, paths) if stamp}
        self.settings.qsettings.setValue(UNPACKED_KEY, sorted(stamps))

    def on_unpack(self) -> None:
        package = self.chosen_package()
        if package is not None:
            self.unpack_packages([package])

    def on_unpack_all(self) -> None:
        self.unpack_packages(list(self.waiting))

    def unpack_packages(self, packages: list[extract.Package]) -> None:
        """Unpack or Unpack all: one after the other off the window's thread, the games first, each update beside
        its game (an older one there replaced), the files counted on the line under the tabs. An update whose game
        still waits as a package waits for it, unless that game is unpacked in the same go."""
        if self.worker.running:
            return
        todo = sorted(packages, key=lambda p: extract.ORDER[p.category])
        if not todo:
            return
        unpacked = self.unpacked()
        games = {p.title_id for p in todo if p.category == "gd"}
        waiting_games = {p.title_id for p in self.waiting if p.category == "gd"}
        alone = next((p for p in todo if p.category == "gp" and p.title_id not in unpacked
                      and p.title_id in waiting_games and p.title_id not in games), None)
        if alone is not None:                           # its game first, or the update takes the game's folder
            self.say(f"{alone.title or alone.title_id} is an update: unpack its game first, or Unpack all unpacks "
                     "both.", ok=False)
            return
        log = self.log

        def progress(done: int, total: int) -> None:
            self.unpacking = (self.unpacking[0], (done, total))     # read by _show_unpacking on the window's thread

        def job() -> tuple[bool, str]:
            done: list[str] = []
            whole: list[extract.Package] = []
            failed: list[str] = []
            for n, package in enumerate(todo, 1):
                what = package.title or package.title_id or package.path.name
                self.unpacking = (f"Unpacking {n} of {len(todo)}: {what}…" if len(todo) > 1 else
                                  f"Unpacking {what}…", (0, 0))
                folder, game = extract.place(package, unpacked)
                log.info(f"Unpack: {package.path} ({package.title_id}, {package.kind}) into {folder}.")
                try:
                    final, written, missing = extract.unpack(package, folder.parent, game is not None and
                                                             extract.has_entries(folder), progress, log.info,
                                                             beside=game)
                except extract.ExtractError as error:
                    failed.append(f"{what} ({error})")
                    continue
                if missing:
                    failed.append(f"{what} ({missing} of {written + missing} file(s) missing, {extract.ERRORS} in "
                                  f"{final.name} names them; the package stays)")
                    continue
                if package.category == "gd":
                    unpacked[package.title_id] = final
                done.append(what)
                whole.append(package)
            self.unpacked_whole = whole
            text = (f"{done[0]} is unpacked." if len(todo) == 1 and done else
                    f"{len(done)} of {len(todo)} package(s) unpacked.")
            if failed:
                text += " Not done: " + "; ".join(failed) + "."
            return not failed, text
        self.unpacked_whole = []
        self.unpacking = ("Unpacking…", (0, 0))
        self._start(f"Unpacking {len(todo)} package(s)…" if len(todo) > 1 else
                    f"Unpacking {todo[0].title or todo[0].path.name}…", job)
        self.progress_timer.start()

    def _show_unpacking(self) -> None:
        """While packages unpack: which one, and its files done (a large game takes minutes)."""
        if not self.worker.running:
            self.progress_timer.stop()
            return
        stage, (done, total) = self.unpacking
        self.running.setText(stage + (f" {done} of {total} files." if total else ""))

    def _packages_unpacked(self) -> None:
        """After Unpack: the packages unpacked whole remembered, and offered for deletion (a package takes as much
        room as its game; the user decides what to keep, owner 01-11-2026)."""
        whole, self.unpacked_whole = self.unpacked_whole, []
        if not whole:
            return
        self.remember_unpacked([package.path for package in whole])
        self.refresh()
        items = [keep.Item(f"path:{package.path}", f"{package.path.name} ({package.title or package.title_id})",
                           (package.path,)) for package in whole]
        if KeepDialog("Delete the packages?", items, self,
                      lead="The games are unpacked; their packages are not needed to play now. Untick what you "
                           "want to keep. Nothing is deleted before you press Delete marked.").exec() \
                != QDialog.DialogCode.Accepted:
            self.note("The packages were kept.")
            return
        failed = keep.delete([path for item in keep.chosen(items) for path in item.paths])
        self.refresh()
        self.say(f"Packages deleted.{' Not deleted: ' + ', '.join(failed) + '.' if failed else ''}", not failed)

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.say(f"The shortcuts run {self.run_path}, which is not there: install {APP_NAME} through the "
                     "portal first.", ok=False)
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.say("Install shadPS4 first: the games in Steam start it.", ok=False)
            return
        text = f"{len(add)} game(s) in Steam" + (f", {len(remove)} taken out." if remove else ".")
        if self.steam_running():
            text += "\n\nSteam closes for it and starts again in the background."
        if not self._ask("Steam", text):
            return
        folder, closed, run, existing = self.steam_dir, self.steam_closed, self.run_path, self.in_steam
        key, home, get = covers.read_key(self.covers_key), self.covers_home, self.covers_get

        def job() -> tuple[bool, str]:
            # The covers first, off the GUI thread; the artwork is drawn here too, on QImage only.
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
                missing = [g.title for g in add if str(g.eboot) not in found]
                if missing:
                    extra.append(f"Read back from Steam's file, {len(add) - len(missing)} of the {len(add)} game(s) "
                                 f"are there: not {', '.join(missing)}.")
            again = " Steam was closed for it and starts again in the background." if restarted else ""
            return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in the library"
                                              f"{f'; {len(remove)} taken out' if remove else ''}.{again}", *extra])
        self._start("Looking up covers and changing Steam's shortcuts…" if key else "Changing Steam's shortcuts…",
                    job)

    def on_covers(self) -> None:
        """Asks for the suite's SteamGridDB API key; empty turns the lookup off (the covers kept stay in use)."""
        if covers.edit_key(self, self.covers_key, "Update Steam"):
            self.refresh()
            self.say("The SteamGridDB key was changed." if covers.read_key(self.covers_key) else
                     "The SteamGridDB key was taken out; the covers kept stay in use.")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        QTimer.singleShot(0, self.place_states)         # once the pills below have their new width

    def place_states(self) -> None:
        """The states end at the middle of the last header pill: the spacer after them is half its width."""
        self.states_spacer.setFixedWidth(max(0, self.time_box.width() // 2))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.worker.running and not self._ask("Close", "A download or a change to Steam is still running. "
                                                          "Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.release_check.stop()
        self.shadnet_watch.stop()
        self.shadnet_check.stop()
        self.controller_timer.stop()
        self.settings_page.unmuting.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
