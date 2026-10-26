# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: the header with Refresh and the state boxes, a row of action pills (Install and Remove for
PCSX2 and for a BIOS, Add folder and Remove folder for the games; owner, 24-10-2026: pills in place of the three
numbered steps with buttons), the state of each (PCSX2, the BIOS, the game folders) in a line, then four tabs: the
games found, each with a box for Steam and how it fills the screen; PCSX2's settings (settings_page.py); the
memory cards (memcard_page.py); and the app's log. Downloading PCSX2, asking GitHub for a newer one and changing
Steam's files run off the GUI thread; nothing here needs root. The look is the app's own blue (style.py). Steam
artwork… takes the suite's SteamGridDB API key, with which Update Steam looks up the pictures for each game first
(core's covers).

Everything about PCSX2 is done here (owner, 24-10-2026): the app never opens PCSX2's own window and has no Play
button, a game is started from Steam. While PCSX2 is installed and not running, the window keeps PCSX2's settings
at what the app owns (pcsx2_settings.py), so a game started from Steam goes straight into the game. What the
window says it also writes to the app's log (core's applog), shown in the Log tab; PCSX2's last run (the game, the
play time, the controller, from PCSX2's own log) goes there too, once, when the window next looks."""

from __future__ import annotations

import time
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QResizeEvent
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy,
                             QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, applog, covers, sound, steam, upstream, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import bin_home
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, WrappedLabel, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__, catalogue, controllers, emulator, memcards
from . import pcsx2_settings
from . import shortcuts, style, userdata
from .games import Game, scan
from .memcard_page import MemcardPage
from . import settings_page
from .settings_page import SettingsPage

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/pcsx2/"
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
KINDS = {"iso": "ISO", "chd": "CHD", "cso": "CSO", "zso": "ZSO", "gz": "GZ"}
RUNNING = "PCSX2 is running: close it first, it would write its own settings over the change."
STEAM, GAME, SERIAL, KIND, FILE, SCREEN = range(6)          # the table's columns (the screen last; owner)
GAMES, SETTINGS, MEMCARDS, LOG = range(4)                   # the tabs


class Pcsx2Settings(SettingsStore):
    DEFAULTS: dict = {"folders": [],            # the game folders chosen in the app
                      "session_logged": ""}     # PCSX2's log as last written into the app's log (its time)


class MainWindow(QMainWindow):
    CONTROLLER_POLL = 3000                  # ms: how often the window looks for a controller

    def __init__(self, home: Path | None = None, pcsx2_home: Path | None = None, steam_dir: Path | None = None,
                 run: Path | None = None, fetch: emulator.Download = emulator.download,
                 steam_closed=steam.with_steam_closed, steam_running=steam.steam_running,
                 newer_release=emulator.newer_release, pcsx2_running=memcards.pcsx2_running,
                 covers_home: Path | None = None, covers_get: covers.Get = covers._get,
                 covers_key: Path | None = None, log_path: Path | None = None,
                 devices: Path = controllers.DEVICES, sound_state: Path | None = None):
        """*home*: where the app installs PCSX2; *pcsx2_home*: PCSX2's own folder; *steam_dir*: Steam's folder
        (None: looked up); *run*: the run wrapper the shortcuts start; *fetch*: the download; *steam_closed* and
        *steam_running*: closing Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a
        newer stable; *pcsx2_running*: whether PCSX2 runs (its settings are not written then); *covers_home*,
        *covers_get* and *covers_key*: where the SteamGridDB pictures are kept, how SteamGridDB is asked and the
        suite's key file (tests never touch the real ones); *log_path*: the app's log file, as the Log tab shows
        it (__main__ set it up); *devices*: the kernel's list of input devices, for the controller state;
        *sound_state*: WirePlumber's file with the volume the desktop remembers for PCSX2 (tests pass their own)."""
        super().__init__()
        self.resize(980, 800)
        self.home = home or emulator.emulator_home()
        self.pcsx2_home = pcsx2_home or userdata.pcsx2_home()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.pcsx2_running = pcsx2_running
        self.log_path = log_path or applog.log_file(APP_ID)
        self.devices = devices
        self.sound_state = sound_state or sound.stream_properties()
        self.sound: tuple[float, bool] | None = None    # (volume, muted) Bazzite remembers for PCSX2; None: unknown
        self._sound_said = False                        # said once while it stays off
        self.controllers: list[str] | None = None       # the controllers last seen; None before the first look
        self.log = applog.logger(APP_ID)
        self._newer_release = newer_release
        self.newer: ReleaseInfo | None = None           # PCSX2's newest stable, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.settings = Pcsx2Settings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread: a download or Steam
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""
        self.replaced = False                       # PCSX2 updated itself to a build the app was not tried with
        self.bios: list[Path] = []
        self.folders: list[Path] = []
        self.catalogue_dir = emulator.appimage(self.home).parent    # PCSX2's titles and patches, beside its AppImage

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
        self.emulator_box = MetricBox("PCSX2 version", style.BLUE)
        self.games_box = MetricBox("Your games", style.BLUE)
        self.steam_box = MetricBox("Available in Steam", style.BLUE)
        self.time_box = MetricBox("Play time", style.BLUE)      # all games together, as PCSX2 counts it
        # The header's pills spread over the window's width in equal parts, as the action pills below (owner,
        # 24-10-2026). (The BIOS box went: the BIOS line below says which dump.)
        self.header_pills = [self.refresh_pill, self.emulator_box, self.games_box, self.steam_box, self.time_box]
        for box in self.header_pills:
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.add_second(box, 1)
        self.intro = hint_label(
            "PS2 games on the BC-250 with the PCSX2 emulator. The app installs the PCSX2 release it was tried with and "
            "sets it up, finds your games and puts them in Steam, so a game starts straight away, also from Steam's "
            "Big Picture Mode. Everything about PCSX2 is set here; PCSX2's own window is not needed. Games and the "
            "PS2's BIOS come from you; the app never downloads them. "
            + style.link(self, emulator.RELEASE_PAGE, "PCSX2's release notes") + " · "
            + style.link(self, MANUAL_URL, "Wiki"), follow_height=True)       # its lines count in the minimum

        # What there is to do, as pills the size of the header's, spread over the window's width (owner,
        # 24-10-2026): what it is for in large type (PCSX2, BIOS, Games), what the pill does under it (Install,
        # Uninstall, Add folder, Remove folder).
        self.install_pill = style.action_pill("PCSX2", "Install", f"Download PCSX2 {emulator.VERSION} from GitHub "
                                                                  f"(about {emulator.SIZE_MB} MB) and check it")
        self.install_pill.clicked.connect(self.on_install)
        self.remove_pill = style.action_pill("PCSX2", "Uninstall", "Remove the installed PCSX2; its own folder "
                                                                   "(BIOS, memory cards, settings) stays")
        self.remove_pill.clicked.connect(self.on_remove)
        self.bios_pill = style.action_pill("BIOS", "Install", "Choose your BIOS dump (.bin): the app copies it into "
                                                              "PCSX2's BIOS folder and PCSX2 uses it")
        self.bios_pill.clicked.connect(self.on_choose_bios)
        self.bios_remove_pill = style.action_pill("BIOS", "Uninstall", "Take a BIOS dump out of PCSX2's BIOS "
                                                                       "folder, with the files beside it; your own "
                                                                       "copy stays")
        self.bios_remove_pill.clicked.connect(self.on_remove_bios)
        self.folder_pill = style.action_pill("Games", "Add folder", "Add a folder with your games (ISO, CHD, CSO, "
                                                                    "ZSO or GZ images)")
        self.folder_pill.clicked.connect(self.on_add_folder)
        self.forget_pill = style.action_pill("Games", "Remove folder", "Stop looking for games in one of the "
                                                                       "folders; the games stay where they are")
        self.forget_pill.clicked.connect(self.on_forget_folder)
        self.actions = [self.install_pill, self.remove_pill, self.bios_pill, self.bios_remove_pill,
                        self.folder_pill, self.forget_pill]
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for pill in self.actions:                       # each a sixth of the width, whatever the window's
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            actions.addWidget(pill, 1)

        grid = QGridLayout()                            # the state of each: PCSX2, the BIOS, the game folders
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        self.emulator_state, self.bios_state, self.folders_state = (self._state_label() for _ in range(3))
        for row, (name, state) in enumerate((("PCSX2", self.emulator_state), ("BIOS", self.bios_state),
                                             ("Game folders", self.folders_state))):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label, row, 0)
            grid.addWidget(state, row, 1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["In Steam", "Game title", "Id", "Type", "File name",
                                              "Screen setting"])
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

        self.covers_button = QPushButton("Steam artwork…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Steam "
                                      "gives each game its cover, banner and logo from SteamGridDB in Steam")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Steam", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        buttons.addWidget(hint_label("Tick a game to put it in Steam; Screen setting sets how it fills the screen. "
                                     "A game is started from Steam."), 1)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)
        games_page = QWidget()
        games = QVBoxLayout(games_page)
        games.setContentsMargins(0, 8, 0, 0)
        games.addWidget(self.table, 1)
        games.addLayout(buttons)

        self.settings_page = SettingsPage(self.pcsx2_home, self.pcsx2_running, self.log)
        self.settings_page.sound_path = self.sound_state
        self.settings_page.sound_changed.connect(self.show_sound)
        self.memcard_page = MemcardPage(self.pcsx2_home, self.pcsx2_running, self.log)
        self.output = Terminal()
        self.output.setPlaceholderText("What the app did, with the time, appears here.")
        self.output.set_text(applog.tail(self.log_path))
        log_page = QWidget()
        log = QVBoxLayout(log_page)
        log.setContentsMargins(0, 8, 0, 0)
        log.addWidget(hint_label(f"Everything the app said and did, newest last, and each game started from Steam "
                                 f"with what PCSX2 logged about the run; the same lines are in "
                                 f"{escape(str(self.log_path))}, which turns over at 1 MB."))
        log.addWidget(self.output, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(games_page, "Your games")
        self.tabs.addTab(self.settings_page, "Settings")
        self.tabs.addTab(self.memcard_page, "Memory cards")
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
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · PCSX2 {emulator.VERSION}")
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
        self.catalogue_dir = emulator.appimage(self.home).parent
        if self.version and catalogue.missing(self.catalogue_dir):     # a PCSX2 installed before the app took it out
            emulator.take_catalogue(self.home)
        self.bios_dir = userdata.bios_dir(self.pcsx2_home)
        self.bios = userdata.bios_files(self.bios_dir)
        self.folders = [Path(f) for f in self.settings.get("folders") if f]
        titles = catalogue.titles(self.catalogue_dir)
        self.games = scan(self.folders, titles)
        self.prepare_pcsx2()
        self.log_session(titles)
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_cover = ({str(g.file) for g in self.games if str(g.file) in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_cover = {}, set()
        self._show_state()
        self._fill_table()
        self.settings_page.load()
        self.memcard_page.load()
        self.show_controller()
        self.show_sound()

    def show_sound(self) -> None:
        """The volume Bazzite remembers for PCSX2 (muted or turned down, a game plays without a sound; owner,
        24-10-2026, as RPCS3 Manager's): in the Settings tab's Sound box, and said once while it stays off."""
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
                                       "reads it; Select + Start together quit the game.")
        else:
            self.controller.set_status("No controller", "warn",
                                       "No controller is connected: switch it on, or press its PS button to wake "
                                       "it, before starting a game from Steam. Without one, PCSX2 plays with the "
                                       "keyboard only and Select + Start cannot quit the game.")

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

    def log_session(self, titles: dict[str, str]) -> None:
        """PCSX2's last run, as its own log tells it, into the app's log once: the game (named as the catalog
        names it), how long it was played, until when, and with which controller. PCSX2 writes its log over at
        every start, so a run is lost when another follows before the window looks."""
        session = userdata.last_session(self.pcsx2_home)
        if session is None or not session.serial:               # no log, or no game in that run
            return
        mark = f"{session.ended:.6f}"
        if self.settings.get("session_logged") == mark:
            return
        self.settings.set("session_logged", mark)
        game = f"{titles[session.serial]} ({session.serial})" if session.serial in titles else session.serial
        length = userdata.played(session.seconds) if session.counted else f"about {userdata.played(session.seconds)}"
        until = time.strftime(applog.DATE, time.localtime(session.ended))
        pads = session.controllers
        with_ = (f"with the controller {pads[0]}" if len(pads) == 1 else
                 f"with the controllers {' and '.join(pads)}" if pads else "without a controller")
        self.note(f"{game} was played for {length} in PCSX2 {session.version or '?'}, until {until}, {with_}.")

    def prepare_pcsx2(self) -> bool:
        """PCSX2's settings brought to what the app owns, while PCSX2 is installed and does not run; what changed goes
        to the log. Whether they are as the app wants them."""
        if not self.version or self.pcsx2_running():
            return False
        try:
            done = pcsx2_settings.prepare(self.pcsx2_home)
        except OSError as error:
            self.say(f"PCSX2's settings could not be written: {error}", ok=False)
            return False
        if done:
            self.say(f"PCSX2 set up: {', '.join(done)}.")
        return True

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(f"Not installed. Install downloads PCSX2 {pinned}, the stable release this "
                                        "version of the app was tried with, checks it and sets it up. The app says "
                                        "when a newer stable release is out.")
            self.emulator_box.set_value("—")
        elif self.version != pinned:
            self.emulator_state.setText(f"PCSX2 {escape(self.version)} is installed; this version of the app "
                                        f"brings {pinned}: <b>install it</b> to use it.")
            self.emulator_box.set_value(self.version)
        elif self.replaced:
            self.emulator_state.setText("PCSX2 updated itself in its own window to a build this version of the app "
                                        f"was not tried with. <b>Install</b> puts back {pinned}.")
            self.emulator_box.set_value("other")
        else:
            self.emulator_state.setText(f"PCSX2 {pinned} is installed.")
            self.emulator_box.set_value(pinned)
        if self.newer is not None:
            self.emulator_state.setText(
                self.emulator_state.text() + f"<br>PCSX2 {escape(self.newer.version)} is out "
                f"({escape(self.newer.published)}). A later version of this app brings it, once it has been tried "
                "on the board. " + style.link(self, self.newer.url, "What is new"))
        self.emulator_state.setOpenExternalLinks(True)

        page = style.link(self, userdata.BIOS_HELP_URL, "PCSX2's BIOS page")
        chosen = pcsx2_settings.chosen_bios(self.pcsx2_home)
        if self.bios:
            used = chosen if chosen in {p.name for p in self.bios} else self.bios[0].name
            others = [p.name for p in self.bios if p.name != used]
            self.bios_state.setText(f"PCSX2 uses <b>{escape(used)}</b>"
                                    + (f"; also there: {escape(', '.join(others))}." if others else "."))
        else:
            self.bios_state.setText("No BIOS yet. PCSX2 needs the PS2's BIOS to start any game: dump it from your "
                                    f"own console ({page} says how), then pick the .bin with BIOS Install.")
        self.bios_state.setToolTip(f"PCSX2's BIOS folder: {self.bios_dir}")
        self.bios_state.setOpenExternalLinks(True)

        if self.folders:
            self.folders_state.setText(", ".join(f"<b>{escape(f.name or str(f))}</b>" for f in self.folders) + ".")
            self.folders_state.setToolTip("\n".join(str(f) for f in self.folders))
        else:
            self.folders_state.setText("None yet: add the folder with your games (ISO, CHD, CSO, ZSO or GZ images).")
            self.folders_state.setToolTip("")
        self.games_box.set_value(str(len(self.games)))
        found = {str(g.file) for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))
        self._show_play_time()

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install PCSX2 first.")
        elif not self.bios:
            self.pill.set_status("No BIOS", "warn", "PCSX2 needs the PS2's BIOS to start a game.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Add the folder with your games.")
        else:
            self.pill.set_status("Ready", "ok", "PCSX2 and a BIOS are installed and games were found.")
        # For the portal's notice: the release is pinned (a newer one comes with a new version of the app), so the
        # app has no update of its own to announce; a notice from before is cleared.
        upstream.publish("pcsx2", [])

    def _show_play_time(self) -> None:
        """The time spent in all games together, as PCSX2 counts it (its playtime.dat); per game in the tip."""
        times = userdata.play_times(self.pcsx2_home)
        total = sum(seconds for seconds, _ in times.values())
        if not total:
            self.time_box.set_value("—", "PCSX2 counts the time spent in each game; none yet.")
            return
        titles = {g.serial: g.title for g in self.games if g.serial}
        lines = [f"{titles.get(serial, serial)}: {userdata.played(seconds)}, last played "
                 f"{time.strftime('%d-%m-%Y %H:%M', time.localtime(last))}"
                 for serial, (seconds, last) in sorted(times.items(), key=lambda t: -t[1][0]) if seconds]
        self.time_box.set_value(userdata.played(total), "The time spent in each game, as PCSX2 counts it:\n"
                                + "\n".join(lines))

    def _release_found(self, result: ReleaseInfo | None) -> None:
        self.newer = result
        if result is not None:
            self._show_state()
            self._update_buttons()

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if str(game.file) in self.in_steam else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam" if str(game.file) in self.in_steam else "Not in Steam")
            self.table.setItem(row, STEAM, box)
            kind = KINDS.get(game.kind, game.kind)
            for column, text in ((GAME, game.title), (SERIAL, game.serial), (KIND, kind), (FILE, game.file.name)):
                self.table.setItem(row, column, QTableWidgetItem(text))
            self.table.item(row, FILE).setToolTip(str(game.file))
            if game.kind != "iso":
                self.table.item(row, KIND).setToolTip("A compressed image is not looked into: the name is the "
                                                      "file's and there is no Id. PCSX2 plays it the same.")
            self.table.setCellWidget(row, SCREEN, self._screen_box(game))
        self.table.blockSignals(False)
        self._update_buttons()

    def _screen_box(self, game: Game) -> QComboBox:
        """How the game fills the screen: as it is, PCSX2's widescreen patch (when PCSX2 has one for it) or
        stretched; kept in the game's own settings in PCSX2."""
        box = QComboBox()
        if not game.crc:
            box.addItem(pcsx2_settings.SCREENS[pcsx2_settings.ORIGINAL], pcsx2_settings.ORIGINAL)
            box.setEnabled(False)
            box.setToolTip("A compressed image is not looked into, so its own settings in PCSX2 are not known")
            return box
        current = pcsx2_settings.read_screen(pcsx2_settings.game_settings(self.pcsx2_home, game.serial, game.crc))
        widescreen = catalogue.has_widescreen(self.catalogue_dir, game.serial, game.crc)
        for key, text in pcsx2_settings.SCREENS.items():
            if key != pcsx2_settings.WIDESCREEN or widescreen or current == key:
                box.addItem(text, key)
        box.setCurrentIndex(max(box.findData(current), 0))
        box.setToolTip("Original: the PS2's picture, with borders on a wide screen. "
                       + ("Widescreen: PCSX2's widescreen patch for this game. " if widescreen else
                          "PCSX2 has no widescreen patch for this game. ")
                       + "Fill screen: the picture stretched to fill the screen.")
        box.currentIndexChanged.connect(lambda _index, g=game, b=box: self.set_screen(g, b.currentData()))
        return box

    def ticked(self) -> list[Game]:
        return [g for row, g in enumerate(self.games)
                if self.table.item(row, STEAM).checkState() == Qt.CheckState.Checked]

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
        self.install_pill.setEnabled(idle and (self.version != emulator.VERSION or self.replaced))
        self.remove_pill.setEnabled(idle and installed_)
        self.bios_pill.setEnabled(idle)
        self.bios_remove_pill.setEnabled(idle and bool(self.bios))
        self.folder_pill.setEnabled(idle)
        self.forget_pill.setEnabled(idle and bool(self.folders))
        self.covers_button.setEnabled(idle)
        add, remove = self.steam_plan()
        named = shortcuts.names(add)        # a name in Steam that differs (one from before the prefix) is renamed
        changed = bool(remove) or any(self.in_steam.get(str(g.file)) != named[g.file] or str(g.file) in self.no_cover
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
        if not self._ask("Install", f"Download PCSX2 {emulator.VERSION} from GitHub (about {emulator.SIZE_MB} MB)?"
                                    "\n\nIt is checked against the SHA-256 this app was tried with before it is "
                                    f"installed in {self.home}."):
            return
        home, fetch = self.home, self.fetch

        def job() -> tuple[bool, str]:
            try:
                return True, emulator.install(home, fetch)
            except (emulator.EmulatorError, OSError) as error:
                return False, f"PCSX2 was not installed: {error}"
        self._start(f"Downloading PCSX2 {emulator.VERSION}…", job)

    def on_remove(self) -> None:
        text = ("Remove the installed PCSX2?\n\nIts own folder, with the BIOS, your memory cards, saves and "
                "settings, stays.")
        if self.in_steam:
            text += "\nThe games in Steam no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.refresh()
            self.say("PCSX2 was removed.")

    def on_choose_bios(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, window_title("Choose your BIOS dump"), str(Path.home()),
                                              "PS2 BIOS dumps (*.bin *.BIN *.rom *.ROM);;All files (*)")
        if path:
            self.choose_bios(Path(path))

    def choose_bios(self, dump: Path) -> None:
        """Copies the dump, with the files beside it, into PCSX2's bios folder and makes it the one PCSX2 uses."""
        if self.pcsx2_running():
            self.say(RUNNING, ok=False)
            return
        try:
            placed = userdata.copy_bios(dump, self.bios_dir)
            pcsx2_settings.choose_bios(self.pcsx2_home, placed.name)
        except OSError as error:
            self.say(f"The BIOS was not taken: {error}", ok=False)
            return
        self.refresh()
        self.say(f"PCSX2 uses {placed.name} now.")

    def on_remove_bios(self) -> None:
        names = [p.name for p in self.bios]
        if not names:
            return
        name, ok = QInputDialog.getItem(self, window_title("Remove a BIOS"), "Take out of PCSX2's BIOS folder:",
                                        names, 0, False)
        if ok and name and self._ask("Remove a BIOS", f"Remove {name} from PCSX2's BIOS folder, with the files "
                                                      "beside it under the same name?\n\nThe dump you chose it "
                                                      "from stays where it is."):
            self.remove_bios(self.bios_dir / name)

    def remove_bios(self, dump: Path) -> None:
        """Takes the dump out of PCSX2's bios folder with its files; PCSX2 then uses another one, when there is."""
        if self.pcsx2_running():
            self.say(RUNNING, ok=False)
            return
        try:
            removed = userdata.remove_bios(dump)
        except OSError as error:
            self.say(f"{dump.name} was not removed: {error}", ok=False)
            return
        self.refresh()
        others = [p.name for p in self.bios]
        uses = f"PCSX2 uses {others[0]} now." if others else "PCSX2 has no BIOS now."
        self.say(f"{', '.join(removed) or dump.name} removed from PCSX2's BIOS folder. {uses}")

    def set_screen(self, game: Game, screen: str) -> None:
        if self.pcsx2_running():
            self.say(RUNNING, ok=False)
            self._fill_table()
            return
        try:
            pcsx2_settings.write_screen(pcsx2_settings.game_settings(self.pcsx2_home, game.serial, game.crc), screen)
        except OSError as error:
            self.say(f"{game.title}'s screen was not changed: {error}", ok=False)
            return
        self.say(f"{game.title}: {pcsx2_settings.SCREENS[screen].lower()}.")

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

    def on_forget_folder(self) -> None:
        folders = [str(f) for f in self.folders]
        if not folders:
            return
        folder, ok = QInputDialog.getItem(self, window_title("Remove a game folder"),
                                          "Stop looking for games in:", folders, 0, False)
        if ok and folder:
            self.forget_folder(Path(folder))

    def forget_folder(self, folder: Path) -> None:
        self.settings.set("folders", [str(f) for f in self.folders if f != folder])
        self.refresh()
        self.say(f"{folder.name or folder} is no longer a game folder; its games stay where they are.")

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.say(f"The shortcuts run {self.run_path}, which is not there: install {APP_NAME} through the "
                     "portal first.", ok=False)
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.say("Install PCSX2 first: the games in Steam start it.", ok=False)
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
        """Asks for the suite's SteamGridDB API key; empty turns the lookup off (the pictures kept stay in use)."""
        if covers.edit_key(self, self.covers_key, "Update Steam"):
            self.refresh()
            self.say("The SteamGridDB key was changed." if covers.read_key(self.covers_key) else
                     "The SteamGridDB key was taken out; the pictures kept stay in use.")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        QTimer.singleShot(0, self.place_states)         # once the pills below have their new width

    def place_states(self) -> None:
        """The states end at the middle of the last header pill: the spacer after them is half its width."""
        self.states_spacer.setFixedWidth(max(0, self.time_box.width() // 2))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        busy = self.worker.running or self.memcard_page.worker.running
        if busy and not self._ask("Close", "A download, a change to Steam or a change to a memory card is still "
                                           "running. Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.release_check.stop()
        self.memcard_page.stop()
        self.controller_timer.stop()
        self.settings_page.unmuting.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
