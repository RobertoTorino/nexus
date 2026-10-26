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
tab."""

from __future__ import annotations

import re
import subprocess
import time
from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, sound, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import bin_home, xdg_open
from bc250_core.theme import GREEN, RED
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import (APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, controllers, emulator, settings_page, shadnet,
               shortcuts, style, userdata)
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
                 sound_state: Path | None = None):
        """*home*: where the app installs shadPS4; *shad_home*: shadPS4's own folder; *steam_dir*: Steam's folder
        (None: looked up); *run*: the run wrapper the shortcuts start; *fetch*: the download; *steam_closed* and
        *steam_running*: closing Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a
        newer shadPS4; *shadnet_connect*: opens a connection to a shadNet server; *shad_running*: whether shadPS4
        runs (its files are not written then); *covers_home*, *covers_get* and *covers_key*: where the covers are
        kept, how SteamGridDB is asked and the suite's key file (tests never touch the real ones); *log_path*: the
        app's log file, as the Log tab shows it (__main__ set it up); *devices*: the kernel's list of input
        devices, for the controller state; *open_url*: opens a URL on the desktop (the Steam link); *sound_state*:
        WirePlumber's file with the volume the desktop remembers for shadPS4 (tests pass their own)."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.shad_home = shad_home or userdata.shadps4_home()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
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
        self.no_logo: set[str] = set()                # games in Steam whose shortcut has no logo yet
        self.old_tags: set[str] = set()               # games in Steam whose shortcut has the tags of an older name
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""
        self.config: dict = {}
        self.users: list[userdata.User] = []
        self.folders: list[Path] = []

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
            "PS4 games on the BC-250 with the shadPS4 emulator. The app installs the shadPS4 release it was tried "
            "with, finds your games (or unpacks them from .pkg files) and puts them in Steam, so a game starts "
            "straight away, also from Steam's Big Picture Mode. Games, saves and system modules come from your own "
            "PS4; the app never downloads them. " + style.link(self, emulator.RELEASE_PAGE, "shadPS4's release notes")
            + " · " + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)   # its lines count in the minimum

        # What there is to do, as pills the size of the header's, spread over the window's width (owner,
        # 24-10-2026): what it is for in large type (shadPS4, Modules, Games, shadNet), what the pill does under it.
        self.install_pill = style.action_pill("shadPS4", "Install", f"Download shadPS4 {emulator.VERSION} from "
                                                                    f"GitHub (about {emulator.SIZE_MB} MB) and "
                                                                    "check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("shadPS4", "Uninstall", "Remove the installed shadPS4; its own folder "
                                                                     "(saves, settings, system modules) stays")
        self.remove_pill.clicked.connect(self.on_remove)
        self.modules_pill = style.action_pill("Modules", "Install", "Choose the folder with the system modules "
                                                                    "(.sprx) from your own PS4's firmware; the app "
                                                                    "copies them into shadPS4's module folder")
        self.modules_pill.clicked.connect(self.on_install_modules)
        self.package_pill = style.action_pill("Games", "Install", "Choose a package file (.pkg: a game, its update "
                                                                  "or add-on content); Extract PKG unpacks it into "
                                                                  "a game folder, in the layout shadPS4 loads")
        self.package_pill.clicked.connect(lambda: self.open_extract())
        self.extract_dialog = None                      # the Extract PKG window while it is open
        self.folder_pill = style.action_pill("Games", "Add folder", "Add a folder with your games (each in a folder "
                                                                    "of its own, with eboot.bin) to shadPS4's game "
                                                                    "folders")
        self.folder_pill.clicked.connect(self.on_add_folder)
        self.account_pill = style.action_pill("shadNet", "Account", "Your shadNet account: create one, try it, and "
                                                                    "have shadPS4 sign in with it")
        self.account_pill.clicked.connect(self.on_shadnet)
        self.actions = [self.install_pill, self.remove_pill, self.modules_pill, self.package_pill, self.folder_pill,
                        self.account_pill]                  # in the owner's order (24-10-2026)
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
        self.folders_state.linkActivated.connect(self.on_forget_folder)
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
        buttons.addWidget(self.steam_hint, 1)
        buttons.addWidget(self.shad_button)
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
                                 f"the same lines are in {escape(str(self.log_path))}, which turns over at 1 MB."))
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
        self.modules = userdata.check_modules(userdata.modules_folder(self.shad_home, self.config))
        self.folders = userdata.game_folders(self.config)
        self.users = userdata.read_users(self.shad_home)
        self.prepare_shadps4()
        self.games = scan(self.folders)
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
        self._show_state()
        self._fill_table()
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

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(f"Not installed. Install downloads shadPS4 {pinned}, the release this "
                                        "version of the app was tried with, and checks it before unpacking. The "
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
        tip = f"shadPS4 {pinned}, the release this version of the app was tried with"
        if self.version and self.version != pinned:
            tip = f"shadPS4 {self.version} is installed; this version of the app brings {pinned}: Install puts it in."
        if self.newer is not None:              # in the tip and the log, so the line stays the version (owner)
            tip += (f"\nshadPS4 {self.newer.version} is out ({self.newer.published}). A later version of this app "
                    f"brings it, once it has been tried on the board: {self.newer.url}")
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
            tip += ("\nMany games run without them; a game that needs a missing one does not start. Modules Install "
                    "takes those of your own PS4. Missing: " + ", ".join(m.missing))
        self.modules_state.setToolTip(tip)

        if self.folders:                        # the folders' names alone (owner, 24-10-2026), each a link that
            self.folders_state.setText(", ".join(  # takes the folder out; the paths and the count in the tip
                f"<b>{style.link(self, f'forget:{n}', escape(f.name or str(f)))}</b>"
                for n, f in enumerate(self.folders)))
            self.folders_state.setToolTip("\n".join(str(f) for f in self.folders)
                                          + f"\n{len(self.games)} game(s) found, up to {MAX_DEPTH} folders "
                                          "deep. Click a folder to stop looking for games in it; its games stay "
                                          "where they are.")
        elif not self.version:
            self.folders_state.setText("None yet: install shadPS4 first, then Add folder takes the folder with your "
                                       "games.")
            self.folders_state.setToolTip("")
        else:
            self.folders_state.setText("None yet: Add folder takes the folder with your games (each in a folder of "
                                       "its own, with eboot.bin); Games Install unpacks a package into one.")
            self.folders_state.setToolTip("")
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
            self.note(f"shadPS4 {release.version} is out ({release.published}); a later version of this app brings "
                      f"it, once it has been tried on the board: {release.url}")

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if str(game.eboot) in self.in_steam else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam" if str(game.eboot) in self.in_steam else "Not in Steam")
            self.table.setItem(row, STEAM, box)
            for column, text in ((GAME, game.title), (SERIAL, game.title_id), (VERSION, game.version),
                                 (FOLDER, game.folder.name or str(game.folder))):
                self.table.setItem(row, column, QTableWidgetItem(text))
            self.table.item(row, FOLDER).setToolTip(str(game.folder))     # the folder's name; the path as the tip
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
        self.modules_pill.setEnabled(idle)
        self.folder_pill.setEnabled(idle and installed)
        self.package_pill.setEnabled(idle)
        self.account_pill.setEnabled(idle)
        self.shad_button.setEnabled(idle and installed)
        self.covers_button.setEnabled(idle)
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
        ok, message = result
        self.refresh()
        self.say(message, ok)

    def on_install(self) -> None:
        if not self._ask("Install", f"Download shadPS4 {emulator.VERSION} from GitHub (about {emulator.SIZE_MB} MB)?"
                                    "\n\nIt is checked against the SHA-256 this app was tried with before it is "
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

    def on_install_modules(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, window_title("Install the system modules"),
                                                  str(Path.home()))
        if folder:
            self.install_modules(Path(folder))

    def install_modules(self, source: Path) -> None:
        """The .sprx files of *source* copied into shadPS4's module folder, which shadPS4 reads when a game asks
        for a module (so it may run meanwhile); the state follows at once."""
        target = self.modules.folder
        try:
            copied = userdata.install_modules(source, target)
        except OSError as error:
            self.say(f"The system modules were not copied: {error}", ok=False)
            return
        if not copied:
            self.say(f"No system module (.sprx) in {source.name or source}.", ok=False)
            return
        self.refresh()
        m = self.modules
        self.say(f"{len(copied)} system module(s) copied into shadPS4's module folder: {len(m.needed)} of the "
                 f"{len(userdata.NEEDED)} it cannot do without are there now.")

    def on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, window_title("Add a game folder"), str(Path.home()))
        if folder:
            self.add_folder(Path(folder))

    def add_folder(self, folder: Path) -> None:
        """Through shadPS4 itself (--add-game-folder), so its own window lists the games too."""
        try:
            done = subprocess.run(self.shadps4_command("--add-game-folder", str(folder)), capture_output=True,
                                  text=True, timeout=FOLDER_TIMEOUT, cwd=self.home)
            ok = done.returncode == 0
            message = "" if ok else \
                f"shadPS4 did not add {folder} (exit code {done.returncode}): {done.stderr.strip()[-300:]}"
        except (OSError, subprocess.SubprocessError) as error:
            ok, message = False, f"shadPS4 did not add {folder}: {error}"
        self.refresh()
        if ok:
            message = f"{folder.name or folder} is a game folder now: {len(scan([folder]))} game(s) in it."
        self.say(message, ok)

    def on_forget_folder(self, url: str) -> None:
        """A folder's name in the Game folders line was clicked ("forget:<n>"): asked first."""
        try:
            folder = self.folders[int(url.partition(":")[2])]
        except (ValueError, IndexError):
            return
        if self._ask("Remove a game folder", f"Stop looking for games in {folder}?\n\nIts games stay where they "
                                             "are."):
            self.forget_folder(folder)

    def forget_folder(self, folder: Path) -> None:
        """Out of shadPS4's game folders, as shadPS4's own Remove Folder does; not while shadPS4 runs."""
        if self.shad_running():
            self.say(RUNNING, ok=False)
            return
        try:
            userdata.remove_game_folder(self.shad_home, folder)
        except userdata.UserDataError as error:
            self.say(f"{folder.name or folder} was not taken out: {error}", ok=False)
            return
        self.refresh()
        self.say(f"{folder.name or folder} is no longer a game folder; its games stay where they are.")

    def open_extract(self, pkg: str | None = None) -> None:
        """The Extract PKG window, with *pkg* loaded; when it is open already, *pkg* goes into it."""
        if self.extract_dialog is not None:
            if pkg:
                self.extract_dialog.open_pkg(pkg)
            self.extract_dialog.raise_()
            self.extract_dialog.activateWindow()
            return
        try:
            from .extract_dialog import ExtractDialog
        except ImportError as error:                    # cryptography missing: an install from before it
            self.say(f"Extract PKG needs the cryptography package ({error}): install {APP_NAME} again through the "
                     "portal.", ok=False)
            return
        self.extract_dialog = ExtractDialog(self.settings, self.folders, self, pkg)
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
            QTimer.singleShot(0, lambda: self.open_extract(pkgs[0]))   # after the drop has ended

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
            try:
                restarted = closed(lambda: steam.write_shortcuts(folder, changes))
            except (steam.SteamError, steam.ShortcutError, OSError) as error:
                return False, "\n".join([*notes, f"Steam was not changed: {error}"])
            again = " Steam was closed for it and starts again in the background." if restarted else ""
            return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in the library"
                                              f"{f'; {len(remove)} taken out' if remove else ''}.{again}"])
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

