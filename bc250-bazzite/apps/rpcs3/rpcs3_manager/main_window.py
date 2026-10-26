# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window, built as PCSX2 Manager's (owner, 24-10-2026: the manager that works is the pattern for the
others): the header with the Refresh pill and the state boxes, a row of action pills (Install and Uninstall for
RPCS3, Install for the firmware, Install and Add folder for the games) in place of the three numbered steps with
buttons, the state of each (RPCS3, the firmware, the disc games, the PKG games) in a line, then three tabs: the
games found, each with a box for Steam and how it fills the screen; RPCS3's settings (settings_page.py); and the
app's log. Downloading RPCS3, asking
GitHub for a newer one and changing Steam's files run off the GUI thread; nothing here needs root. The look is the
app's own blue (style.py). Steam artwork… takes the suite's SteamGridDB API key, with which Update Steam looks up
the cover for each game first (core's covers).

The app has no Play button: a game is started from Steam. While RPCS3 is installed and not running, the window
keeps what the app owns in RPCS3's files (userdata.py): its welcome dialog and update check off, player 1 on the
first controller. RPCS3's own window is opened for what RPCS3 does only there: the firmware (--installfw) and
RPCS3's settings (RPCS3 settings, under the games). The packages RPCS3 installs without its window (--headless
--installpkg, one run per file, the window's job meanwhile; owner, 24-10-2026), and the result is read from
RPCS3's log. The window also reads the volume Bazzite remembers for RPCS3 and says when it is muted (found on
the board). What the window says it also writes to the app's log (core's applog), shown in the Log tab."""

from __future__ import annotations

import subprocess
import time
from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QBrush, QCloseEvent, QColor, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                             QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QTableWidget,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, sound, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import bin_home, xdg_open
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, controllers, emulator, shortcuts, style, userdata
from .games import Game, installed, scan
from . import settings_page
from .settings_page import SettingsPage

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/rpcs3/"
WATCH_MS = 2000
WATCH_LIMIT = 300                       # checks, so 10 minutes: RPCS3's own window installs the firmware
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
NO_SFB = "PS3_DISC.SFB is missing or damaged in this disc game's folder: RPCS3 does not start it without"
RUNNING = "RPCS3 is running: close it first, it writes its own settings over the change when it closes."
RUNNING_INSTALL = "RPCS3 is running: close it first; packages are installed while RPCS3 is closed."
STEAM_URL = "steam://open/games"        # Steam's library; Steam starts when it does not run
STEAM, GAME, SERIAL, VERSION, FOLDER, SCREEN = range(6)     # the table's columns (the screen last; owner)
GAMES, SETTINGS, LOG = range(3)                             # the tabs


def _packages_in(hdd0_game: Path) -> tuple[set[str], set[str]]:
    """(the installed games, the licenses) in RPCS3's folder: compared before and after an install."""
    return ({str(g.eboot) for g in installed(hdd0_game)},
            {p.name for p in userdata.licenses(hdd0_game.parent)})


def install_message(report: userdata.InstallReport, new_games: int, new_licenses: int, folder: str,
                    log_path: Path) -> tuple[bool, str]:
    """What to say after an install, from RPCS3's log (the titles) and what came into RPCS3's folders (the counts,
    when the log says nothing of them)."""
    def named(items: list[tuple[str, str]]) -> str:
        return ", ".join(f"{title} ({serial})" if serial else title for title, serial in items)
    parts = []
    if report.installed:
        parts.append(f"{len(report.installed)} game(s) installed in RPCS3: {named(report.installed)}")
    elif new_games:
        parts.append(f"{new_games} game(s) installed in RPCS3")
    copied = len(report.copied) or new_licenses
    if copied:
        parts.append(f"{copied} license(s) copied into RPCS3")
    if report.failed:
        parts.append(f"{len(report.failed)} package(s) RPCS3 could not install: {named(report.failed)}")
    if report.invalid:
        parts.append(f"{report.invalid} file(s) that are no PS3 package")
    if report.not_copied:
        parts.append(f"{len(report.not_copied)} license(s) RPCS3 could not copy: " + ", ".join(report.not_copied))
    if not parts:
        return False, f"RPCS3 installed nothing from {folder}. RPCS3's log: {log_path}"
    text = "; ".join(parts) + "."
    if report.problems:
        return False, f"{text} RPCS3's log: {log_path}"
    return True, text


class RpcsSettings(SettingsStore):
    DEFAULTS: dict = {"folders": [],            # the game folders chosen in the app
                      "pads_for": []}           # the controllers (the kernel's names) the pad file was written for


class MainWindow(QMainWindow):
    CONTROLLER_POLL = 3000                  # ms: how often the window looks for a controller

    def __init__(self, home: Path | None = None, rpcs3_home: Path | None = None, steam_dir: Path | None = None,
                 run: Path | None = None, fetch: emulator.Download = emulator.download,
                 steam_closed=steam.with_steam_closed, steam_running=steam.steam_running,
                 newer_release=emulator.newer_release, covers_home: Path | None = None,
                 covers_get: covers.Get = covers._get, covers_key: Path | None = None,
                 log_path: Path | None = None, devices: Path = controllers.DEVICES,
                 rpcs3_running=userdata.rpcs3_running, sdl_names=controllers.sdl_names, open_url=xdg_open,
                 rpcs3_log: Path | None = None, sound_state: Path | None = None):
        """*home*: where the app installs RPCS3; *rpcs3_home*: RPCS3's own folder; *steam_dir*: Steam's folder
        (None: looked up); *run*: the run wrapper the shortcuts start; *fetch*: the download; *steam_closed* and
        *steam_running*: closing Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a
        newer RPCS3; *covers_home*, *covers_get* and *covers_key*: where the covers are kept, how SteamGridDB is asked
        and the suite's key file (tests never touch the real ones); *log_path*: the app's log file, as the Log tab
        shows it (__main__ set it up); *devices*: the kernel's list of input devices, for the controller state;
        *rpcs3_running*: whether RPCS3 runs (its files are not written then); *sdl_names*: the controllers as SDL
        names them, for RPCS3's pad file; *open_url*: opens a URL on the desktop (the Steam link); *rpcs3_log*:
        RPCS3's own log, read for what a headless install did; *sound_state*: WirePlumber's file with the volume
        the desktop remembers for RPCS3 (tests pass their own)."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.rpcs3_home = rpcs3_home or userdata.rpcs3_home()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.log_path = log_path or applog.log_file(APP_ID)
        self.devices = devices
        self.rpcs3_running = rpcs3_running
        self.sdl_names = sdl_names
        self.open_url = open_url
        self.rpcs3_log = rpcs3_log or userdata.rpcs3_log()
        self.sound_state = sound_state or sound.stream_properties()
        self.sound: tuple[float, bool] | None = None    # (volume, muted) Bazzite remembers for RPCS3; None: unknown
        self._sound_said = False                        # said once while it stays off
        self._pin_noted = False                         # another build installed than the app brings: logged once
        self.controllers: list[str] | None = None       # the controllers last seen; None before the first look
        self.log = applog.logger(APP_ID)
        self._newer_release = newer_release
        self.newer: ReleaseInfo | None = None           # RPCS3's newest landmark, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.firmware_watch = QTimer(self)              # while RPCS3 installs the firmware in its own window
        self.firmware_watch.setInterval(WATCH_MS)
        self.firmware_watch.timeout.connect(self._watch_firmware)
        self._firmware_checks = 0
        self._firmware_before = ""
        self.settings = RpcsSettings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread: a download, an
        #                                              install of packages or Steam
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""
        self.replaced = False                       # RPCS3 updated itself to a build the app was not tried with
        self.firmware = ""
        self.folders: list[Path] = []

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        # The states on the right of the title row, ending at the middle of the last pill below them (owner,
        # 24-10-2026): a spacer of half that pill's width after them, set whenever the window's size changes.
        self.pill = StatusText()
        header.add_action(self.pill)
        self.controller = StatusText()                  # beside it: whether a controller is connected
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
        self.emulator_box = MetricBox("RPCS3 version", style.BLUE)
        self.games_box = MetricBox("Your games", style.BLUE)
        self.steam_box = MetricBox("Available in Steam", style.BLUE)
        self.time_box = MetricBox("Play time", style.BLUE)      # all games together, as RPCS3 counts it
        # The header's pills spread over the window's width in equal parts, as the action pills below (owner,
        # 24-10-2026). (The Firmware box went: the Firmware line below says which version.)
        self.header_pills = [self.refresh_pill, self.emulator_box, self.games_box, self.steam_box, self.time_box]
        for box in self.header_pills:
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.add_second(box, 1)
        self.intro = hint_label(
            "PS3 games on the BC-250 with the RPCS3 emulator. The app installs the RPCS3 build it was tried with, "
            "takes the PS3's firmware, finds your games and puts them in Steam, so a game starts straight away, also "
            "from Steam's Big Picture Mode. Games and the PS3's firmware come from you; the app never downloads "
            "them. " + style.link(self, emulator.RELEASE_PAGE, "RPCS3's release notes") + " · "
            + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)       # its lines count in the minimum

        # What there is to do, as pills the size of the header's, spread over the window's width (owner,
        # 24-10-2026): what it is for in large type (RPCS3, Firmware, Games), what the pill does under it (Install,
        # Uninstall, Add folder, Remove folder).
        self.install_pill = style.action_pill("RPCS3", "Install", f"Download RPCS3 {emulator.VERSION} from GitHub "
                                                                  f"(about {emulator.SIZE_MB} MB) and check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("RPCS3", "Uninstall", "Remove the installed RPCS3; its own folder "
                                                                   "(firmware, saves, settings, installed games) "
                                                                   "stays")
        self.remove_pill.clicked.connect(self.on_remove)
        self.firmware_pill = style.action_pill("Firmware", "Install", "Choose the PS3UPDAT.PUP you downloaded; "
                                                                      "RPCS3 installs it in its own window")
        self.firmware_pill.clicked.connect(self.on_install_firmware)
        self.package_pill = style.action_pill("Games", "Install", "Choose the folder with your .pkg files (and "
                                                                  "the .rap license of a PSN game); RPCS3 installs "
                                                                  "them, without opening its window")
        self.package_pill.clicked.connect(self.on_install_packages)
        self.folder_pill = style.action_pill("Games", "Add folder", "Add a folder with your disc games (each with "
                                                                    "PS3_GAME and PS3_DISC.SFB)")
        self.folder_pill.clicked.connect(self.on_add_folder)
        self.actions = [self.install_pill, self.remove_pill, self.firmware_pill, self.package_pill, self.folder_pill]
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for pill in self.actions:                       # each a fifth of the width, whatever the window's
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(pill, 1)

        grid = QGridLayout()        # the state of each: RPCS3, the firmware, the disc games, the PKG games (owner)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self.emulator_state, self.firmware_state, self.disc_state, self.pkg_state = (self._state_label()
                                                                                     for _ in range(4))
        self.disc_state.setOpenExternalLinks(False)     # a folder's name is a link that takes it out
        self.disc_state.linkActivated.connect(self.on_forget_folder)
        for row, (name, state) in enumerate((("RPCS3", self.emulator_state), ("Firmware", self.firmware_state),
                                             ("Disc games", self.disc_state), ("PKG games", self.pkg_state))):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label, row, 0)
            grid.addWidget(state, row, 1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["In Steam", "Game title", "Id", "Version", "Folder", "Screen setting"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.ResizeToContents)):
            head.setSectionResizeMode(column, mode)
        self.table.itemChanged.connect(lambda _item: self._update_buttons())

        self.rpcs3_button = QPushButton("RPCS3 settings")
        self.rpcs3_button.setToolTip("Open RPCS3's own window for what the app does not set yet: its settings, "
                                     "the controllers (Pads) and game updates (File > Install Packages)")
        self.rpcs3_button.clicked.connect(self.on_open_rpcs3)
        self.covers_button = QPushButton("Steam artwork…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Steam "
                                      "gives each game its cover from SteamGridDB in Steam; the wide picture, the "
                                      "banner and the logo stay the game's own")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Steam", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        self.steam_hint = hint_label("Tick a game to put it in Steam; Screen setting sets how it fills the screen. "
                                     f"A game is started from {style.link(self, STEAM_URL, 'Steam')}.")
        self.steam_hint.setOpenExternalLinks(False)      # the app opens Steam itself (open_steam)
        self.steam_hint.linkActivated.connect(lambda _url: self.open_steam())
        buttons.addWidget(self.steam_hint, 1)
        buttons.addWidget(self.rpcs3_button)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)
        games_page = QWidget()
        games = QVBoxLayout(games_page)
        games.setContentsMargins(0, 8, 0, 0)
        games.addWidget(self.table, 1)
        games.addLayout(buttons)

        self.settings_page = SettingsPage(self.rpcs3_home, self.rpcs3_running, self.log)
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
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · RPCS3 {emulator.VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()
        self.release_check.start(self._newer_release)

    @staticmethod
    def _state_label() -> QLabel:
        label = WrappedLabel()                  # its lines count in the window's minimum height
        # Its links take a click too: without the second flag a click on one did nothing (owner, 24-10-2026, in
        # shadPS4 Manager's window, built the same way).
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        self.version = emulator.installed_version(self.home)
        self.replaced = bool(self.version) and emulator.replaced(self.home)
        vfs = userdata.read_map(self.rpcs3_home / "vfs.yml")
        self.dev_flash = userdata.drive(self.rpcs3_home, vfs, "/dev_flash/")
        self.hdd0_game = userdata.drive(self.rpcs3_home, vfs, "/dev_hdd0/") / "game"
        self.firmware = userdata.firmware_version(self.dev_flash)
        self.known = list(userdata.known_games(self.rpcs3_home).values())
        self.folders = [Path(f) for f in self.settings.get("folders") if f]
        self.games = scan(self.folders, self.hdd0_game, self.known)
        self.prepare_rpcs3()
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_cover = ({str(g.eboot) for g in self.games if str(g.eboot) in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_cover = {}, set()
        self._show_state()
        self._fill_table()
        self.settings_page.load()
        self.show_controller()
        self.show_sound()

    def show_sound(self) -> None:
        """The volume Bazzite remembers for RPCS3 (muted or turned down, a game plays without a sound): in the
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
                                       "reads it; Share + Options together open RPCS3's menu in the game, with "
                                       "Exit Game in it. Switched off or asleep during a game (its idle timer, "
                                       "its battery), this RPCS3 build does not pick it up again when it comes "
                                       "back: quit the game and start it again.")
            self.prepare_pads()
        else:
            self.controller.set_status("No controller", "warn",
                                       "No controller is connected: switch it on, or press its PS button to wake "
                                       "it, before starting a game from Steam. Without one, RPCS3 plays with the "
                                       "keyboard only.")

    def prepare_rpcs3(self) -> bool:
        """RPCS3's files brought to what the app owns (its GUI settings; the pad file follows the controllers,
        prepare_pads), while RPCS3 is installed and does not run; what changed goes to the log. Whether RPCS3's
        files may be written now."""
        if not self.version or self.rpcs3_running():
            return False
        try:
            done = userdata.prepare_gui(self.rpcs3_home)
        except OSError as error:
            self.say(f"RPCS3's settings could not be written: {error}", ok=False)
            return False
        if done:
            self.say(f"RPCS3 set up: {', '.join(done)}.")
        if self.controllers:
            self.prepare_pads()
        return True

    def prepare_pads(self) -> None:
        """Player 1 (and 2) on the controllers connected, in RPCS3's pad file, while the app may write it (RPCS3
        installed and not running, the file not RPCS3's own): the controllers as SDL names them, asked once per
        change of the controllers connected (the kernel's names)."""
        if not self.controllers or not self.version or self.rpcs3_running():
            return
        if not userdata.pads_ours(self.rpcs3_home):
            return
        if (self.settings.get("pads_for") == self.controllers
                and userdata.pad_device(self.rpcs3_home)):           # written for these already
            return
        names = self.sdl_names()
        if names is None:                   # no SDL3 on the system: the kernel's names, which may differ from SDL's
            names = list(self.controllers)
            how = " (as the kernel names it; SDL3 was not found to ask)"
        else:
            how = ""
        devices = userdata.pad_devices(names)
        if not devices:
            return
        try:
            written = userdata.write_pads(self.rpcs3_home, devices)
        except OSError as error:
            self.say(f"RPCS3's pad settings could not be written: {error}", ok=False)
            return
        self.settings.set("pads_for", list(self.controllers))
        if written:
            players = "; ".join(f"player {n} on {device}" for n, device in enumerate(devices, 1))
            self.say(f"RPCS3 set up: {players}{how}.")

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
            self.emulator_state.setText(f"Not installed. Install downloads RPCS3 {pinned}, the build this version "
                                        "of the app was tried with, and checks it before installing it. The app "
                                        "says when a newer RPCS3 is out.")
            self.emulator_box.set_value("—")
        elif self.version != pinned:        # the version alone here too (owner, 24-10-2026), the advice in the
            self.emulator_state.setText(f"<b>{escape(self.version)}</b>")    # tip and the log once
            self.emulator_box.set_value(self.version.split("-")[0])         # the landmark: the box is not wide
            if not self._pin_noted:                                          # enough for the build
                self.note(f"RPCS3 {self.version} is installed; this version of the app brings {pinned}: Install "
                          "puts it in.")
                self._pin_noted = True
        elif self.replaced:
            self.emulator_state.setText("RPCS3 updated itself in its own window to a build this version of the app "
                                        f"was not tried with. <b>Install</b> puts back {pinned}.")
            self.emulator_box.set_value("other")
        else:                                   # the version alone (owner, 24-10-2026), the build in the tip
            self.emulator_state.setText(f"<b>{emulator.LANDMARK}</b>")
            self.emulator_box.set_value(emulator.LANDMARK)
        tip = f"RPCS3 {pinned}, the build this version of the app was tried with"
        if self.version and self.version != pinned and not self.replaced:
            tip = f"RPCS3 {self.version} is installed; this version of the app brings {pinned}: Install puts it in."
        if self.newer is not None:              # in the tip and the log, so the line stays the version (owner)
            tip += (f"\nRPCS3 {self.newer.version} is out ({self.newer.published}). A later version of this app "
                    f"brings it, once it has been tried on the board: {self.newer.url}")
        self.emulator_state.setToolTip(tip)
        self.emulator_state.setOpenExternalLinks(True)

        page = style.link(self, userdata.FIRMWARE_PAGE, "PlayStation's firmware page")
        if self.firmware:
            self.firmware_state.setText(f"<b>{escape(self.firmware)}</b>")
        else:
            self.firmware_state.setText("No firmware yet. RPCS3 needs the PS3's firmware to start any game: download "
                                        f"PS3UPDAT.PUP from {page}, then pick it with Firmware Install; RPCS3 "
                                        "installs it in its own window.")
        self.firmware_state.setToolTip(f"PS3 firmware {self.firmware or 'none'} in RPCS3's firmware folder: "
                                       f"{self.dev_flash}")
        self.firmware_state.setOpenExternalLinks(True)

        discs = [g for g in self.games if g.disc]
        pkgs = [g for g in self.games if not g.disc]
        if self.folders:                        # the folders' names alone (owner, 24-10-2026), each a link that
            self.disc_state.setText(", ".join(    # takes the folder out; the paths and the count in the tip
                f"<b>{style.link(self, f'forget:{n}', escape(f.name or str(f)))}</b>"
                for n, f in enumerate(self.folders)))
            self.disc_state.setToolTip("\n".join(str(f) for f in self.folders)
                                       + f"\n{len(discs)} disc game(s) found. Click a folder to stop looking "
                                       "for games in it; its games stay where they are.")
        elif discs:                             # none chosen here, but RPCS3 knows some (its games.yml)
            self.disc_state.setText(f"{len(discs)} disc game(s) RPCS3 knows. Add folder takes the folder with your "
                                    "disc games (each in a folder of its own, with PS3_GAME and PS3_DISC.SFB).")
            self.disc_state.setToolTip("")
        else:
            self.disc_state.setText("None yet: Add folder takes the folder with your disc games (each in a folder of "
                                    "its own, with PS3_GAME and PS3_DISC.SFB).")
            self.disc_state.setToolTip("")
        # RPCS3's games folder by its path within RPCS3's own folder (dev_hdd0/game/; the whole path when it is
        # elsewhere) while a game is installed in it, "—" while none is (owner, 24-10-2026); the count and what
        # Install takes in the tip.
        if pkgs:
            self.pkg_state.setText(f"<b>{escape(self._games_folder_name())}</b>")
        else:
            self.pkg_state.setText("—")
        self.pkg_state.setToolTip(f"{len(pkgs)} game(s) installed in RPCS3's games folder: {self.hdd0_game}\n"
                                  "Install takes the folder with your .pkg files (a PSN game also needs its .rap "
                                  "license beside them); RPCS3 installs them without opening its window.")
        self.games_box.set_value(str(len(self.games)))
        found = {str(g.eboot) for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))
        self._show_play_time()

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install RPCS3 first.")
        elif not self.firmware:
            self.pill.set_status("No firmware", "warn", "RPCS3 needs the PS3's firmware to start a game.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Add the folder with your games.")
        else:
            self.pill.set_status("Ready", "ok", "RPCS3 and its firmware are installed and games were found.")

    def _games_folder_name(self) -> str:
        try:
            return f"{self.hdd0_game.relative_to(self.rpcs3_home).as_posix()}/"
        except ValueError:                      # kept elsewhere (RPCS3's Virtual File System settings)
            return str(self.hdd0_game)

    def _show_play_time(self) -> None:
        """The time spent in all games together, as RPCS3 counts it (its persistent_settings.dat); per game in the
        tip."""
        times = userdata.play_times(self.rpcs3_home)
        total = sum(seconds for seconds, _ in times.values())
        if not total:
            self.time_box.set_value("—", "RPCS3 counts the time spent in each game; none yet.")
            return
        titles = {g.title_id: g.title for g in self.games if g.title_id}
        lines = [f"{titles.get(serial, serial)}: {userdata.played(seconds)}"
                 + (f", last played {time.strftime('%d-%m-%Y %H:%M', time.localtime(last))}" if last else "")
                 for serial, (seconds, last) in sorted(times.items(), key=lambda t: -t[1][0])]
        self.time_box.set_value(userdata.played(total), "The time spent in each game, as RPCS3 counts it:\n"
                                + "\n".join(lines))

    def _release_found(self, release: ReleaseInfo | None) -> None:
        self.newer = release
        if release is not None:
            self._show_state()
            self._update_buttons()
            self.note(f"RPCS3 {release.version} is out ({release.published}); a later version of this app brings "
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
            folder = self.table.item(row, FOLDER)           # the folder's name; the whole path as the tip
            folder.setToolTip(str(game.folder))
            if not game.startable:
                folder.setForeground(QBrush(QColor("#c62828")))
                folder.setToolTip(f"{NO_SFB} it.\n{game.folder}")
            self.table.setCellWidget(row, SCREEN, self._screen_box(game))
        self.table.blockSignals(False)
        self._update_buttons()

    def _screen_box(self, game: Game) -> QComboBox:
        """How the game fills the screen: the PS3's picture for a wide screen, for a 4:3 one, or stretched to fill
        the window; kept in the game's own settings in RPCS3 (owner, 24-10-2026: as PCSX2 Manager's)."""
        box = QComboBox()
        for key, text in userdata.SCREENS.items():
            box.addItem(text, key)
        if not game.title_id:
            box.setEnabled(False)
            box.setToolTip("Without an Id in its PARAM.SFO the game has no settings of its own in RPCS3")
            return box
        current = userdata.read_screen(userdata.game_config(self.rpcs3_home, game.title_id))
        box.setCurrentIndex(max(box.findData(current), 0))
        box.setToolTip("16:9: the PS3's picture for a wide screen, RPCS3's default. 4:3: the picture for a 4:3 "
                       "screen, with borders on a wide one. Fill screen: the picture stretched to fill the window.")
        box.currentIndexChanged.connect(lambda _index, g=game, b=box: self.set_screen(g, b.currentData()))
        return box

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
        installed_ = bool(self.version)
        self.refresh_pill.setEnabled(idle)
        self.install_pill.setEnabled(idle and (self.version != emulator.VERSION or self.replaced))
        self.remove_pill.setEnabled(idle and installed_)
        self.firmware_pill.setEnabled(idle and installed_)
        self.package_pill.setEnabled(idle and installed_)
        self.folder_pill.setEnabled(idle)
        self.rpcs3_button.setEnabled(idle and installed_)
        self.covers_button.setEnabled(idle)
        add, remove = self.steam_plan()
        named = shortcuts.names(add)        # a name in Steam that differs (one from before the prefix) is renamed
        changed = bool(remove) or any(self.in_steam.get(str(g.eboot)) != named[g.eboot]
                                      or str(g.eboot) in self.no_cover for g in add)
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
        if not self._ask("Install", f"Download RPCS3 {emulator.VERSION} from GitHub (about {emulator.SIZE_MB} MB)?"
                                    "\n\nIt is checked against the SHA-256 this app was tried with before it is "
                                    f"installed in {self.home}."):
            return
        home, fetch = self.home, self.fetch

        def job() -> tuple[bool, str]:
            try:
                return True, emulator.install(home, fetch)
            except (emulator.EmulatorError, OSError) as error:
                return False, f"RPCS3 was not installed: {error}"
        self._start(f"Downloading RPCS3 {emulator.VERSION}…", job)

    def on_remove(self) -> None:
        text = ("Remove the installed RPCS3?\n\nIts own folder, with the firmware, your saves, settings and installed "
                "games, stays.")
        if self.in_steam:
            text += "\nThe games in Steam no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.refresh()
            self.say("RPCS3 was removed.")

    def on_install_firmware(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, window_title("Install the PS3 firmware"), str(Path.home()),
                                              "PS3 firmware (*.PUP *.pup);;All files (*)")
        if name:
            self.install_firmware(Path(name))

    def install_firmware(self, pup: Path) -> None:
        """Through RPCS3 itself (--installfw): it shows its progress in its own window. The state follows when the
        firmware's version changes."""
        self.prepare_rpcs3()                    # RPCS3's window opens: its welcome dialog off first
        command = self.rpcs3_command("--installfw", str(pup))
        if not QProcess.startDetached(command[0], command[1:])[0]:
            self.say(f"RPCS3 could not be started: {command[0]} did not run.", ok=False)
            return
        self.say(f"RPCS3 installs {pup.name} in its own window. Close RPCS3 when it is done.")
        self._firmware_before = self.firmware
        self._firmware_checks = 0
        self.firmware_watch.start()

    def _watch_firmware(self) -> None:
        self._firmware_checks += 1
        now = userdata.firmware_version(self.dev_flash)
        if now and now != self._firmware_before:
            self.firmware_watch.stop()
            self._job_done((True, f"PS3 firmware {now} is installed."))
        elif self._firmware_checks >= WATCH_LIMIT:
            self.firmware_watch.stop()

    def on_install_packages(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, window_title("Install packages from a folder"),
                                                  str(Path.home()))
        if folder:
            self.install_packages(Path(folder))

    def install_packages(self, folder: Path) -> None:
        """Through RPCS3 itself, without its window (--headless --installpkg; owner, 24-10-2026), once per file:
        the licenses (.rap, .edat) first, which RPCS3 copies into its exdata, then the packages in
        userdata.install_order (the games and DLC, then the updates: an update needs its game installed), each
        into RPCS3's dev_hdd0/game. It runs as the window's job, off the GUI thread. RPCS3's exit code says
        nothing of the outcome (this build ends a headless run with an error of its own once the work is done),
        so each run's result is read from RPCS3's log, and the games and licenses that came are counted."""
        pkgs, licenses = userdata.packages(folder)
        if not pkgs and not licenses:
            self.say(f"No .pkg, .rap or .edat file in {folder.name or folder}.", ok=False)
            return
        if self.rpcs3_running():
            self.say(RUNNING_INSTALL, ok=False)
            return
        self.prepare_rpcs3()
        files = [*licenses, *(info.path for info in userdata.install_order(pkgs))]
        commands = [self.rpcs3_command("--headless", "--installpkg", str(f)) for f in files]
        what = " and ".join(part for part in (f"{len(pkgs)} package(s)" if pkgs else "",
                                              f"{len(licenses)} license(s)" if licenses else "") if part)
        name, hdd0, log_path = folder.name or str(folder), self.hdd0_game, self.rpcs3_log
        before = _packages_in(hdd0)

        def job() -> tuple[bool, str]:
            report = userdata.InstallReport()
            for command in commands:
                try:
                    subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=False)
                except OSError as error:
                    return False, f"RPCS3 could not be started: {error}"
                report.extend(userdata.read_install_report(log_path))
            games, copied = _packages_in(hdd0)
            return install_message(report, len(games - before[0]), len(copied - before[1]), name, log_path)
        self._start(f"RPCS3 installs {what} from {name}, without its window… RPCS3 starts once per file, and a "
                    "large package takes minutes.", job)

    def set_screen(self, game: Game, screen: str) -> None:
        if self.rpcs3_running():
            self.say(RUNNING, ok=False)
            self._fill_table()
            return
        try:
            userdata.write_screen(userdata.game_config(self.rpcs3_home, game.title_id), screen)
        except OSError as error:
            self.say(f"{game.title}'s screen was not changed: {error}", ok=False)
            return
        self.say(f"{game.title}: {userdata.SCREENS[screen]}.")

    def open_steam(self) -> None:
        """The Steam link: Steam's library on the desktop (Steam starts when it does not run)."""
        if self.open_url(STEAM_URL):
            self.note("Steam was opened.")
        else:
            self.say("Steam could not be opened: xdg-open is missing.", ok=False)

    def on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, window_title("Add a game folder"), str(Path.home()))
        if folder:
            self.add_folder(Path(folder))

    def add_folder(self, folder: Path) -> None:
        folders = [str(f) for f in self.folders]
        if str(folder) not in folders:
            self.settings.set("folders", folders + [str(folder)])
        self.refresh()
        found = scan([folder])
        self.say(f"{folder.name or folder} is a game folder now: {len(found)} game(s) in it.")

    def on_forget_folder(self, url: str) -> None:
        """A folder's name in the Disc games line was clicked ("forget:<n>"): asked first."""
        try:
            folder = self.folders[int(url.partition(":")[2])]
        except (ValueError, IndexError):
            return
        if self._ask("Remove a game folder", f"Stop looking for games in {folder}?\n\nIts games stay where they "
                                             "are."):
            self.forget_folder(folder)

    def forget_folder(self, folder: Path) -> None:
        self.settings.set("folders", [str(f) for f in self.folders if f != folder])
        self.refresh()
        self.say(f"{folder.name or folder} is no longer a game folder; its games stay where they are.")

    def rpcs3_command(self, *args: str) -> list[str]:
        """The installed RPCS3 through the run wrapper (from the app folder when it is not installed yet)."""
        run = self.run_path if self.run_path.is_file() else ROOT / shortcuts.RUN_NAME
        return [str(run), *args]

    def on_open_rpcs3(self) -> None:
        self.prepare_rpcs3()                    # RPCS3's window opens: its welcome dialog off first
        command = self.rpcs3_command()
        if QProcess.startDetached(command[0], command[1:])[0]:
            self.note("RPCS3's own window was opened.")
        else:
            self.say(f"RPCS3 could not be started: {command[0]} did not run.", ok=False)

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.say(f"The shortcuts run {self.run_path}, which is not there: install {APP_NAME} through the "
                     "portal first.", ok=False)
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.say("Install RPCS3 first: the games in Steam start it.", ok=False)
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
        if self.worker.running and not self._ask("Close", "A download, an install of packages or a change to "
                                                          "Steam is still running. Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.release_check.stop()
        self.firmware_watch.stop()
        self.controller_timer.stop()
        self.settings_page.unmuting.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
