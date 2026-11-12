# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window, built as RPCS3 Manager's (owner, 07-11-2026: RPCS3 Manager's design is every manager's): the header
with the Refresh pill and the state boxes, a row of action pills (Install and Uninstall for Vita3K, Install for the
games), the state of each (Vita3K, the PS Vita firmware, the games) in a line, then three tabs: the games Vita3K has
installed, each with a box for Steam; Vita3K's settings (core's settings_page over vita3k_settings); and the app's
log. Downloading Vita3K, asking GitHub for a newer one, installing the firmware or a package through Vita3K and
changing Steam's files run off the GUI thread; nothing here needs root. The look is the app's own blue (style.py).

A game runs from Steam: the last tab, Start game, starts the chosen one there (owner, 12-11-2026). Vita3K's own window
(Vita3K settings, under the games) stays for what the Settings tab does not set. What the window says it also writes to
the app's log (core's applog), shown in the Log tab."""

from __future__ import annotations

import subprocess
import time
from html import escape
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                             QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core import keep
from bc250_core.action_tab import ActionTab
from bc250_core.keep_dialog import KeepDialog
from bc250_core.platform import bin_home, private, xdg_open
from bc250_core.settings import SettingsStore
from bc250_core.settings_page import SettingsPage
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, InfoButton, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import (APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, library, shortcuts, style, userdata,
               vita3k_settings)
from .games import Game, installed, names

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/vita3k/"
INSTALL_WATCH_MS = 2000
INSTALL_WATCH_LIMIT = 300               # checks, so 10 minutes: Vita3K's own window does the installing
INSTALL_TIMEOUT = 900                   # seconds for Vita3K to install a firmware file or a package without a window
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
START_TIP = "Start the game chosen under Your games through Steam, as its shortcut in Steam does"
STEAM_URL = "steam://open/games"        # Steam's library; Steam starts when it does not run
STEAM, GAME, SERIAL, VERSION, FOLDER = range(5)             # the table's columns
GAMES, SETTINGS, LOG = range(3)                             # the tabs
# The emulator's line: the state alone, the same words in every manager (owner, 07-11-2026); the version and the
# advice are in its tip.
NOT_INSTALLED = "Not installed.<br>Install it with the Install button."
INSTALLED = "Installed.<br>Uninstall with the Uninstall button."

RUNNING_REMOVE = "Vita3K is running: close it first, then remove the game."


class Vita3kSettings(SettingsStore):
    DEFAULTS: dict = {"firmware_given": []}     # the PUPs in Games/Vita/Firmware given to Vita3K (library.file_key)


def _with_info(state: QLabel, info: InfoButton) -> QWidget:
    """A state line with its info symbol right after it, at the top of its first line. The line is short, so it
    keeps to one line: wrapped, it took the narrowest width beside the symbol."""
    state.setWordWrap(False)
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(state)
    layout.addWidget(info, 0, Qt.AlignmentFlag.AlignTop)
    layout.addStretch(1)
    return row


class MainWindow(QMainWindow):
    def __init__(self, home: Path | None = None, vita3k_config: Path | None = None, steam_dir: Path | None = None,
                 run: Path | None = None, fetch: emulator.Download = emulator.download,
                 steam_closed=steam.with_steam_closed, steam_running=steam.steam_running,
                 newer_release=emulator.newer_release, covers_home: Path | None = None,
                 covers_get: covers.Get = covers._get, covers_key: Path | None = None,
                 vita3k_running=emulator.running, user_home: Path | None = None,
                 drives: Callable[[], list[Path]] = library.removable_drives, log_path: Path | None = None,
                 open_url=xdg_open):
        """*home*: where the app installs Vita3K; *vita3k_config*: Vita3K's settings folder (its config.yml says
        where its storage is); *steam_dir*: Steam's folder (None: looked up); *run*: the run wrapper the shortcuts
        start; *fetch*: the download; *steam_closed* and *steam_running*: closing Steam for a change and asking
        whether it runs; *newer_release*: asks GitHub for a newer Vita3K; *covers_home*, *covers_get* and
        *covers_key*: where the covers are kept, how SteamGridDB is asked and the suite's key file (tests never touch
        the real ones); *vita3k_running*: whether Vita3K runs (its settings are left alone then); *user_home*: the
        home folder with the app's own folder, Games/Vita (library.fixed); *drives*: the removable drives looked at
        for one; *log_path*: the app's log file, as the Log tab shows it (__main__ set it up); *open_url*: opens a
        URL on the desktop (the Steam link)."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.vita3k_config = vita3k_config or userdata.config_dir()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.user_home = user_home or Path.home()
        self.drives = drives
        self.folders: list[Path] = []
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.vita3k_running = vita3k_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.log_path = log_path or applog.log_file(APP_ID)
        self.open_url = open_url
        self.log = applog.logger(APP_ID)
        self._pin_noted = False                         # another build installed than the app brings: logged once
        self.newer: ReleaseInfo | None = None           # Vita3K's newest build, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.install_watch = QTimer(self)               # while Vita3K installs a game in its own window
        self.install_watch.setInterval(INSTALL_WATCH_MS)
        self.install_watch.timeout.connect(self._watch_install)
        self._install_checks = 0
        self._names_before: set[str] = set()
        self.settings = Vita3kSettings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""
        self.replaced = False                       # the AppImage updated itself to a build the app was not tried with
        self.vita_fs = userdata.default_storage()
        self.firmware = userdata.Firmware(False, False, False)

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
        self.emulator_box = MetricBox("Vita3K version", style.BLUE)
        self.firmware_box = MetricBox("Firmware", style.BLUE)
        self.games_box = MetricBox("Your games", style.BLUE)
        self.steam_box = MetricBox("Available in Steam", style.BLUE)
        # The header's pills spread over the window's width in equal parts, as the action pills below.
        self.header_pills = [self.refresh_pill, self.emulator_box, self.firmware_box, self.games_box, self.steam_box]
        for box in self.header_pills:
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.add_second(box, 1)
        self.intro = hint_label(
            "PS Vita games on the BC-250 with the Vita3K emulator. The app installs the Vita3K build it was tried "
            "with, installs the firmware and your games through it and puts the games in Steam, so a game starts "
            "straight away, also from Steam's Big Picture Mode. Games and the PS Vita's firmware come from you; the "
            "app never downloads them. " + style.link(self, emulator.RELEASE_PAGE, "Vita3K's release notes") + " · "
            + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)       # its lines count in the minimum

        # What there is to do, as pills the size of the header's, spread over the window's width: what it is for in
        # large type (Vita3K, Games), what the pill does under it (Install, Uninstall). Games Install opens the menu
        # of what to install from.
        self.install_pill = style.action_pill("Vita3K", "Install", f"Download Vita3K build {emulator.VERSION} from "
                                                                   f"GitHub (about {emulator.SIZE_MB} MB) and check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("Vita3K", "Uninstall", "Remove the installed Vita3K; its own folders "
                                                                    "(firmware, games, saves, settings) stay")
        self.remove_pill.clicked.connect(self.on_remove)
        self.game_pill = style.action_pill("Games", "Install", "Install one of your own games in Vita3K: a .vpk or "
                                                               ".zip, a .pkg with its zRIF license key, or a dumped "
                                                               "game folder")
        self.game_menu = QMenu(self)
        self.game_menu.addAction("From a file (.vpk, .zip, .pkg)…", self.on_install_game_file)
        self.game_menu.addAction("From a dumped folder…", self.on_install_game_folder)
        self.game_pill.clicked.connect(
            lambda: self.game_menu.popup(self.game_pill.mapToGlobal(self.game_pill.rect().bottomLeft())))
        self.actions = [self.install_pill, self.remove_pill, self.game_pill]
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for pill in self.actions:                       # each a third of the width, whatever the window's
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(pill, 1)

        grid = QGridLayout()        # the state of each: Vita3K, the firmware, the game folder
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self.emulator_state, self.firmware_state, self.folders_state = (self._state_label() for _ in range(3))
        # The firmware's parts and the game folders by name; where the firmware comes from and what goes in the
        # folders behind an info symbol each (owner, 12-11-2026).
        self.firmware_info = InfoButton("", "About the firmware")
        self.folders_info = InfoButton("", "About the game folder")
        infos = {self.firmware_state: self.firmware_info, self.folders_state: self.folders_info}
        for row, (name, state) in enumerate((("Vita3K", self.emulator_state), ("Firmware", self.firmware_state),
                                             ("Game folder", self.folders_state))):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label, row, 0)
            grid.addWidget(_with_info(state, infos[state]) if state in infos else state, row, 1)

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
        self.table.itemSelectionChanged.connect(self._update_buttons)

        self.vita3k_button = QPushButton("Vita3K settings")
        self.vita3k_button.setToolTip("Open Vita3K's own window for what the Settings tab does not set: its other "
                                      "settings, the controls and its game list")
        self.vita3k_button.clicked.connect(self.on_open_vita3k)
        self.remove_game_button = QPushButton("Remove game…")
        self.remove_game_button.setToolTip("Delete the chosen game from the disk: a window lists what would go, and "
                                           "you untick what to keep; nothing is deleted before you confirm")
        self.remove_game_button.clicked.connect(self.on_remove_game)
        self.covers_button = QPushButton("Steam artwork…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Steam "
                                      "gives each game a cover from SteamGridDB in Steam's library")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Steam", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        self.steam_hint = hint_label(f"Tick a game to put it in Steam. A game is started from "
                                     f"{style.link(self, STEAM_URL, 'Steam')}.")
        self.steam_hint.setOpenExternalLinks(False)      # the app opens Steam itself (open_steam)
        self.steam_hint.linkActivated.connect(lambda _url: self.open_steam())
        buttons.addWidget(self.steam_hint, 1)
        buttons.addWidget(self.vita3k_button)
        buttons.addWidget(self.remove_game_button)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)
        games_page = QWidget()
        games = QVBoxLayout(games_page)
        games.setContentsMargins(0, 8, 0, 0)
        games.addWidget(self.table, 1)
        games.addLayout(buttons)

        self.settings_page = SettingsPage("Vita3K", vita3k_settings.SETTINGS,
                                          lambda: vita3k_settings.read_settings(self.vita3k_config),
                                          lambda setting, value: vita3k_settings.write_setting(self.vita3k_config,
                                                                                               setting, value),
                                          self.vita3k_running, log=self.log)
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
        # Start game (owner, 12-11-2026): the last tab is a button, which starts the chosen game in Steam
        self.start_tab = ActionTab(self.tabs, "Start game", START_TIP, self.on_start_game)

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
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · Vita3K build {emulator.VERSION}")
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
        self.replaced = bool(self.version) and emulator.replaced(self.home)
        self.prepare_vita3k()
        self.folders = library.fixed(self.user_home, self.drives)
        self.vita_fs = userdata.storage(self.vita3k_config)
        self.firmware = userdata.firmware(self.vita_fs)
        self.sync_firmware()
        self.games = installed(self.vita_fs)
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_cover = ({g.name for g in self.games if g.name in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_cover = {}, set()
        self._show_state()
        self._fill_table()
        self.settings_page.load()

    def prepare_vita3k(self) -> None:
        """The lines of config.yml the app owns (userdata.prepare), once Vita3K is installed and while it does not
        run; what changed goes to the log."""
        if not self.version or self.vita3k_running():
            return
        try:
            done = userdata.prepare(self.vita3k_config)
        except OSError as exc:
            self.note(f"Vita3K's settings could not be written: {exc}", ok=False)
            return
        if done:
            self.note("Vita3K set up: " + ", ".join(done) + ".")

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
            tip = (f"Install downloads Vita3K build {pinned}, the build this version of the app was tried with, and "
                   "checks it before installing it.")
        else:
            self.emulator_state.setText(INSTALLED)
            if self.version != pinned:
                self.emulator_box.set_value(self.version)
                tip = (f"Vita3K build {self.version} is installed; this version of the app brings build {pinned}: "
                       "Install puts it in.")
                if not self._pin_noted:
                    self.note(tip)
                    self._pin_noted = True
            elif self.replaced:
                self.emulator_box.set_value("other")
                tip = ("Vita3K updated itself to a build this version of the app was not tried with. Install puts "
                       f"back build {pinned}.")
            else:
                self.emulator_box.set_value(pinned)
                tip = f"Vita3K build {pinned} ({emulator.SEMVER}), the build this version of the app was tried with"
        if self.newer is not None:
            tip += (f"\nVita3K build {self.newer.version} is out ({self.newer.published}). A later version of this "
                    f"app brings a newer build, once it has been tried on the board: {self.newer.url}")
        self.emulator_state.setToolTip(tip)

        fw = self.firmware                      # the state of each part; where it comes from: the info symbol
        official = style.link(self, userdata.FIRMWARE_PAGE, "here")
        fonts = style.link(self, userdata.FONTS_URL, "here")
        preinstall = style.link(self, userdata.PREINSTALL_URL, "here")
        lines = ["Installed" if fw.ready else "Not installed"]
        lines += [f"{part}: {'installed' if there else 'not installed'}"
                  for part, there in (("System software", fw.system), ("Font package", fw.fonts),
                                      ("Preinstalled apps", fw.preinstalled))]
        self.firmware_state.setText("<br>".join(lines))
        self.firmware_info.set_text("Drop your own firmware and font package in "
                                    f"{escape(private(library.firmware_home(self.user_home)))}. System software can "
                                    f"be downloaded from its official page {official}. Font package can be "
                                    f"downloaded from {fonts}. Preinstalled apps can be downloaded {preinstall}.")
        self.firmware_state.setToolTip("Vita3K needs the system software and the font package to start most games; "
                                       "the preinstalled apps are optional. The app gives the PSP2UPDAT.PUP files to "
                                       f"Vita3K, which installs them in {private(self.vita_fs)}.")
        self.firmware_box.set_value("Ready" if fw.ready else "Partly" if fw.system or fw.fonts else "—")

        # The app's own folders (owner, 03-11-2026): the home folder's, and a removable drive's when it has one.
        where = ", ".join(f"<b>{escape(private(f))}</b>" for f in self.folders)
        self.folders_state.setText(where)
        self.folders_info.set_text(f"Drop your games in {escape(private(self.user_home / library.GAMES_HOME))}, .vpk, "
                                   ".zip, .pkg, zRIF license key, or drop a game folder there.")
        self.folders_state.setToolTip("\n".join(private(f) for f in self.folders)
                                      + f"\n{len(self.games)} game(s) installed in Vita3K's storage, "
                                      f"{private(self.vita_fs)}.")
        self.games_box.set_value(str(len(self.games)))
        found = {g.name for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install Vita3K first.")
        elif not fw.ready:
            self.pill.set_status("No firmware", "warn", "Vita3K needs the PS Vita's firmware and its font package.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Install one of your games.")
        else:
            self.pill.set_status("Ready", "ok", "Vita3K and its firmware are installed and games were found.")

    def _release_found(self, release: ReleaseInfo | None) -> None:
        self.newer = release
        if release is not None:
            self._show_state()
            self.note(f"Vita3K build {release.version} is out ({release.published}); a later version of this app "
                      f"brings a newer build, once it has been tried on the board: {release.url}")

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if game.name in self.in_steam else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam" if game.name in self.in_steam else "Not in Steam")
            self.table.setItem(row, STEAM, box)
            for column, text in ((GAME, game.title), (SERIAL, game.title_id), (VERSION, game.version),
                                 (FOLDER, str(game.folder))):
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
        shortcuts of games no longer installed out too."""
        add = self.ticked()
        found = {g.name for g in self.games}
        remove = [g for g in self.games if g.name in self.in_steam and g not in add]
        remove += [Game(Path(name), title) for name, title in self.in_steam.items() if name not in found]
        return add, remove

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        installed_ = bool(self.version)
        self.refresh_pill.setEnabled(idle)
        self.install_pill.setEnabled(idle and (self.version != emulator.VERSION or self.replaced))
        self.remove_pill.setEnabled(idle and installed_)
        self.game_pill.setEnabled(idle and installed_)
        self.vita3k_button.setEnabled(idle and installed_)
        self.covers_button.setEnabled(idle)
        self.remove_game_button.setEnabled(idle and self.chosen() is not None)
        add, remove = self.steam_plan()
        named = shortcuts.names(add)
        changed = bool(remove) or any(self.in_steam.get(g.name) != named[g.name] or g.name in self.no_cover
                                      for g in add)
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
        if not self._ask("Install", f"Download Vita3K build {emulator.VERSION} from GitHub (about "
                                    f"{emulator.SIZE_MB} MB)?\n\nIt is checked against the SHA-256 this app was tried "
                                    f"with before it is installed in {self.home}."):
            return
        home, fetch = self.home, self.fetch

        def job() -> tuple[bool, str]:
            try:
                return True, emulator.install(home, fetch)
            except (emulator.EmulatorError, OSError) as error:
                return False, f"Vita3K was not installed: {error}"
        self._start(f"Downloading Vita3K build {emulator.VERSION}…", job)

    def on_remove(self) -> None:
        text = ("Remove the installed Vita3K?\n\nIts own folders, with the firmware, your games, saves and settings, "
                "stay.")
        if self.in_steam:
            text += "\nThe games in Steam no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.refresh()
            self.say("Vita3K was removed.")

    def vita3k_command(self, *args: str) -> list[str]:
        """The installed Vita3K through the run wrapper (from the app folder when it is not installed yet)."""
        run = self.run_path if self.run_path.is_file() else ROOT / shortcuts.RUN_NAME
        return [str(run), *args]

    def _run_vita3k(self, args: list[str], done) -> None:
        """Vita3K without a window (it installs and quits), in the worker; *done*(exit code, last line it printed)
        says what happened."""
        command = self.vita3k_command(*args)

        def job() -> tuple[bool, str]:
            try:
                result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                        timeout=INSTALL_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as error:
                return False, f"Vita3K could not do it: {error}"
            lines = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
            return done(result.returncode, lines[-1] if lines else "")
        self._start("Vita3K is installing it…", job)

    def sync_firmware(self) -> None:
        """The PS Vita's firmware files put in Games/Vita/Firmware given to Vita3K by itself (owner, 03-11-2026,
        from the Windows Portable Suite's Vita3K Manager: firmware taken in automatically), the largest first, one
        after the other (the next one when the window reads the state again, after the install), once Vita3K is
        installed and while it does not run; each file once while it stays the same (its place, size and time in
        the settings), one Vita3K could not use too; a file replaced is given again. The files stay."""
        if not self.version or self.vita3k_running() or self.worker.running:
            return
        given = list(self.settings.get("firmware_given"))
        for pup in library.firmware_files(self.user_home):
            key = library.file_key(pup)
            if not key or key in given:
                continue
            self.settings.set("firmware_given", [*given, key])
            self.note(f"Firmware file found in {private(library.firmware_home(self.user_home))}: {private(pup)} is "
                      "given to Vita3K.")
            self.install_firmware(pup)
            return

    def install_firmware(self, pup: Path) -> None:
        """Through Vita3K itself (--firmware), which installs it and quits; the parts it wrote are named. Vita3K
        also quits as after an install on a file it could not use, so what it wrote is what tells."""
        vita_fs, start = self.vita_fs, time.time() - 1      # a second's room for the file system's clock

        def done(code: int, last: str) -> tuple[bool, str]:
            wrote = userdata.firmware_written(vita_fs, start)
            parts = [part for part, written in (("the system software", wrote.system),
                                                ("the font package", wrote.fonts),
                                                ("the preinstalled apps", wrote.preinstalled)) if written]
            if parts:
                named = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
                return True, f"{pup.name}: {named} installed."
            if code == 0:
                return False, (f"Vita3K did not install {pup.name}: nothing of the firmware was written. Is it one "
                               "of the PS Vita's PSP2UPDAT.PUP files?")
            return False, f"Vita3K did not install {pup.name}" + (f": {last}" if last else ".")
        self._run_vita3k(["--firmware", str(pup)], done)

    def on_install_game_file(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, window_title("Install a game"),
                                              str(self.folders[0] if self.folders else Path.home()),
                                              "PS Vita games (*.vpk *.zip *.pkg);;All files (*)")
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() == ".pkg":
            zrif, ok = QInputDialog.getText(self, window_title("The game's license"),
                                            f"The zRIF licence key of {path.name} (it starts with KO5i):",
                                            QLineEdit.EchoMode.Normal)
            if ok and zrif.strip():
                self.install_package(path, zrif.strip())
        else:
            self.install_game(path)

    def on_install_game_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, window_title("Install a dumped game"),
                                                  str(self.folders[0] if self.folders else Path.home()))
        if folder:
            self.install_game(Path(folder))

    def install_package(self, pkg: Path, zrif: str) -> None:
        """A .pkg with its zRIF through Vita3K (--pkg, --zrif), which installs it and quits."""
        before, vita_fs = names(self.vita_fs), self.vita_fs

        def done(code: int, last: str) -> tuple[bool, str]:
            new = sorted(names(vita_fs) - before)
            if new:
                return True, f"{pkg.name} is installed: {', '.join(new)}."
            if code == 0:
                return True, (f"Vita3K installed {pkg.name}; no new game came with it (an update goes to ux0/patch, "
                              "extra content to ux0/addcont).")
            return False, f"Vita3K did not install {pkg.name}" + (f": {last}" if last else ".")
        self._run_vita3k(["--pkg", str(pkg), "--zrif", zrif], done)

    def install_game(self, path: Path) -> None:
        """A .vpk, .zip or dumped folder through Vita3K, which installs it and then starts it in its own window.
        The list follows when a new game is in ux0/app."""
        command = self.vita3k_command(str(path))
        if not QProcess.startDetached(command[0], command[1:])[0]:
            self.say(f"Vita3K could not be started: {command[0]} did not run.", ok=False)
            return
        self.say(f"Vita3K installs {path.name} and then starts it in its own window.")
        self._names_before = names(self.vita_fs)
        self._install_checks = 0
        self.install_watch.start()

    def _watch_install(self) -> None:
        self._install_checks += 1
        new = sorted(names(self.vita_fs) - self._names_before)
        if new:
            self.install_watch.stop()
            self._job_done((True, f"Installed in Vita3K: {', '.join(new)}."))
        elif self._install_checks >= INSTALL_WATCH_LIMIT:
            self.install_watch.stop()

    def on_open_vita3k(self) -> None:
        command = self.vita3k_command()
        if QProcess.startDetached(command[0], command[1:])[0]:
            self.note("Vita3K's own window was opened.")
        else:
            self.say(f"Vita3K could not be started: {command[0]} did not run.", ok=False)

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
        the window's thread, its Steam shortcut through Steam, and Cancel deletes nothing. The saves
        stay."""
        game = self.chosen()
        if game is None:
            return
        if self.vita3k_running():
            self.say(RUNNING_REMOVE, ok=False)
            return
        items, why = library.removal_items(game, self.vita_fs, game.name in self.in_steam)
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

    def on_start_game(self) -> None:
        """The Start game tab (owner, 12-11-2026): the chosen game started through Steam, as its shortcut there
        starts it (steam://rungameid/ with the shortcut's number; Steam starts first when it does not run)."""
        game = self.chosen()
        if game is None:
            self.say("Choose a game under Your games first: Start game starts the chosen one in Steam.", ok=False)
            return
        if self.worker.running:
            self.say("Wait until what runs now has finished, then start the game.", ok=False)
            return
        number = (steam.shortcut_number(self.steam_dir, shortcuts.for_game(game))
                  if self.steam_dir is not None and game.name in self.in_steam else None)
        if number is None:
            self.say(f"{game.title} is not in Steam yet: tick it and press Update Steam first.", ok=False)
            return
        if self.open_url(steam.play_url(number)):
            self.say(f"Steam starts {game.title}.")
        else:
            self.say(f"{game.title} could not be started: xdg-open is missing.", ok=False)

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.say(f"The shortcuts run {self.run_path}, which is not there: install {APP_NAME} through the "
                     "portal first.", ok=False)
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.say("Install Vita3K first: the games in Steam start it.", ok=False)
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
                missing = [g.title for g in add if g.name not in found]
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
        """The state ends at the middle of the last header pill: the spacer after it is half its width."""
        self.states_spacer.setFixedWidth(max(0, self.steam_box.width() // 2))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.worker.running and not self._ask("Close", "A download, an install or a change to Steam is still "
                                                          "running. Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.release_check.stop()
        self.install_watch.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
