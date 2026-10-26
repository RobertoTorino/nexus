# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: Vita3K itself, the PS Vita firmware and the games as three steps with their state and buttons,
then the games Vita3K has installed, each with a box for Game Mode. Downloading Vita3K, asking GitHub for a newer
one, installing the firmware or a package through Vita3K and changing Steam's files run off the GUI thread; nothing
here needs root. The look is the app's own blue (style.py)."""

from __future__ import annotations

import shlex
import subprocess
import time
from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, covers, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import bin_home
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts, style, userdata
from .games import Game, installed, names

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/vita3k/"
INSTALL_WATCH_MS = 2000
INSTALL_WATCH_LIMIT = 300               # checks, so 10 minutes: Vita3K's own window does the installing
INSTALL_TIMEOUT = 900                   # seconds for Vita3K to install a firmware file or a package without a window
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"


class MainWindow(QMainWindow):
    def __init__(self, home: Path | None = None, vita3k_config: Path | None = None, steam_dir: Path | None = None,
                 run: Path | None = None, fetch: emulator.Download = emulator.download,
                 steam_closed=steam.with_steam_closed, steam_running=steam.steam_running,
                 newer_release=emulator.newer_release, covers_home: Path | None = None,
                 covers_get: covers.Get = covers._get, covers_key: Path | None = None):
        """*home*: where the app installs Vita3K; *vita3k_config*: Vita3K's settings folder (its config.yml says
        where its storage is); *steam_dir*: Steam's folder (None: looked up); *run*: the run wrapper the shortcuts
        start; *fetch*: the download; *steam_closed* and *steam_running*: closing Steam for a change and asking
        whether it runs; *newer_release*: asks GitHub for a newer Vita3K; *covers_home*, *covers_get* and
        *covers_key*: where the covers are kept, how SteamGridDB is asked and the suite's key file (tests never touch
        the real ones)."""
        super().__init__()
        self.resize(980, 760)
        self.home = home or emulator.emulator_home()
        self.vita3k_config = vita3k_config or userdata.config_dir()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.newer: ReleaseInfo | None = None           # Vita3K's newest build, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.install_watch = QTimer(self)               # while Vita3K installs a game in its own window
        self.install_watch.setInterval(INSTALL_WATCH_MS)
        self.install_watch.timeout.connect(self._watch_install)
        self._install_checks = 0
        self._names_before: set[str] = set()
        self.settings = SettingsStore(INFO, self)    # the window's size only
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
        self.pill = StatusText()
        header.add_state(self.pill)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the state again and look for games")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.emulator_box = MetricBox("Vita3K", style.BLUE)
        self.firmware_box = MetricBox("Firmware", style.BLUE)
        self.games_box = MetricBox("Games", style.BLUE)
        self.steam_box = MetricBox("In Game Mode", style.BLUE)
        for box in (self.emulator_box, self.firmware_box, self.games_box, self.steam_box):
            header.add_second(box)
        intro = hint_label(
            "PS Vita games on the BC-250 with the Vita3K emulator. The app installs the Vita3K build it was tried "
            "with, installs the firmware and your games through it and puts the games in Steam, so they start from "
            "Game Mode. Games and the PS Vita's firmware come from you; the app never downloads them. "
            + style.link(self, MANUAL_URL, "Manual"))

        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.emulator_state, self.firmware_state, self.games_state = (self._state_label() for _ in range(3))
        self.install_button = style.primary_button("Install", f"Download Vita3K build {emulator.VERSION} from GitHub "
                                                              f"(about {emulator.SIZE_MB} MB) and check it")
        self.install_button.clicked.connect(self.on_install)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Remove the installed Vita3K; its own folders (firmware, games, saves, "
                                      "settings) stay")
        self.remove_button.clicked.connect(self.on_remove)
        self.firmware_button = QPushButton("Install firmware…")
        self.firmware_button.setToolTip("Choose a PSP2UPDAT.PUP you downloaded: the firmware, its font package or the "
                                        "preinstalled apps; Vita3K installs it")
        self.firmware_button.clicked.connect(self.on_install_firmware)
        self.game_button = QPushButton("Install game…")
        self.game_button.setToolTip("Install one of your own games in Vita3K: a .vpk or .zip, a .pkg with its zRIF "
                                    "license key, or a dumped game folder")
        menu = QMenu(self.game_button)
        menu.addAction("From a file (.vpk, .zip, .pkg)…", self.on_install_game_file)
        menu.addAction("From a dumped folder…", self.on_install_game_folder)
        self.game_button.setMenu(menu)
        rows = [("Vita3K", self.emulator_state, [self.install_button, self.remove_button]),
                ("Firmware", self.firmware_state, [self.firmware_button]),
                ("Games", self.games_state, [self.game_button])]
        centre = Qt.AlignmentFlag.AlignVCenter
        for row, (name, state, buttons) in enumerate(rows):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            for text in (label, state):
                text.setAlignment(Qt.AlignmentFlag.AlignLeft | centre)
            grid.addWidget(style.step_badge(row + 1), row, 0, centre)
            grid.addWidget(label, row, 1)
            grid.addWidget(state, row, 2)
            for column, button in zip((4, 3), reversed(buttons)):
                grid.addWidget(button, row, column, centre)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Game Mode", "Game", "ID", "Version", "Folder"])
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
        self.table.doubleClicked.connect(lambda _index: self.on_play())

        self.play_button = QPushButton("Play")
        self.play_button.setToolTip("Start the chosen game alone in Vita3K, here on the desktop")
        self.play_button.clicked.connect(self.on_play)
        self.vita3k_button = QPushButton("Vita3K settings")
        self.vita3k_button.setToolTip("Open Vita3K's own window: its settings, controls and game list")
        self.vita3k_button.clicked.connect(self.on_open_vita3k)
        self.covers_button = QPushButton("Covers…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Game Mode "
                                      "gives each game a cover from SteamGridDB in Steam's library")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Game Mode", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.vita3k_button)
        buttons.addStretch(1)
        buttons.addWidget(self.covers_button)
        buttons.addWidget(self.steam_button)

        self.running = QLabel()
        self.running.setStyleSheet("font-weight:600;")
        self.running.setWordWrap(True)
        self.output = Terminal()
        self.output.setPlaceholderText("Messages appear here.")
        self.output.setMaximumHeight(120)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(intro)
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(self.table, 1)
        lay.addLayout(buttons)
        lay.addWidget(self.running)
        lay.addWidget(self.output)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · Vita3K build {emulator.VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)
        # As in shadPS4 Manager: the buttons of the steps the size of the widest, in two columns on the
        # right. Sized here, in the window, so their size includes the style sheet's padding.
        steps = [b for _, _, buttons in rows for b in buttons]
        for button in steps:
            button.ensurePolished()
        width = max(b.sizeHint().width() for b in steps)
        height = max(b.sizeHint().height() for b in steps)
        for row in range(len(rows)):
            grid.setRowMinimumHeight(row, height)
        for button in steps:
            button.setFixedSize(width, height)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()
        self.release_check.start(newer_release)

    @staticmethod
    def _state_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        self.version = emulator.installed_version(self.home)
        self.replaced = bool(self.version) and emulator.replaced(self.home)
        self.vita_fs = userdata.storage(self.vita3k_config)
        self.firmware = userdata.firmware(self.vita_fs)
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

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(f"Not installed. Install downloads Vita3K build {pinned}, the build this "
                                        "version of the app was tried with, and checks it before installing it.")
            self.emulator_box.set_value("—")
        elif self.version != pinned:
            self.emulator_state.setText(f"Vita3K build {escape(self.version)} is installed; this version of the app "
                                        f"brings build {pinned}: <b>install it</b> to use it.")
            self.emulator_box.set_value(self.version)
        elif self.replaced:
            self.emulator_state.setText("Vita3K updated itself to a build this version of the app was not tried "
                                        f"with. <b>Install</b> puts back build {pinned}.")
            self.emulator_box.set_value("other")
        else:
            self.emulator_state.setText(f"Vita3K build {pinned} ({emulator.SEMVER}) is installed. "
                                        + style.link(self, emulator.RELEASE_PAGE, "What is in it"))
            self.emulator_box.set_value(pinned)
        if self.newer is not None:
            self.emulator_state.setText(
                self.emulator_state.text() + f"<br>Vita3K build {escape(self.newer.version)} is out "
                f"({escape(self.newer.published)}). A later version of this app brings a newer build, once it has "
                "been tried on the board. " + style.link(self, self.newer.url, "What is new"))
        self.emulator_state.setOpenExternalLinks(True)

        fw = self.firmware
        official = style.link(self, userdata.FIRMWARE_PAGE, "here")
        fonts = style.link(self, userdata.FONTS_URL, "here")
        preinstall = style.link(self, userdata.PREINSTALL_URL, "here")
        lines = ["System software: " + ("installed" if fw.system else
                                         f"<b>not installed</b>: download it {official} (official page)"),
                 "Font package: " + ("installed" if fw.fonts else
                                      f"<b>not installed</b>: download it {fonts} (Sony's file)"),
                 "Preinstalled apps (optional): " + ("installed" if fw.preinstalled else
                                                      f"not installed: download them {preinstall} (Sony's file)")]
        tail = (f"In <code>{escape(str(self.vita_fs))}</code>." if fw.ready else
                "Vita3K needs the firmware and its font package to start most games: press Install firmware for "
                "each file.")
        self.firmware_state.setText("<br>".join(lines) + "<br>" + tail)
        self.firmware_state.setOpenExternalLinks(True)
        self.firmware_box.set_value("Ready" if fw.ready else "Partly" if fw.system or fw.fonts else "—")

        if self.games:
            self.games_state.setText(f"{len(self.games)} installed in Vita3K's storage, "
                                     f"<code>{escape(str(self.vita_fs))}</code>.")
        else:
            self.games_state.setText("None installed yet. Install game takes your own dumps: a .vpk or .zip, a .pkg "
                                     "with its zRIF license key, or a dumped game folder.")
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

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.games))
        for row, game in enumerate(self.games):
            box = QTableWidgetItem()
            box.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            box.setCheckState(Qt.CheckState.Checked if game.name in self.in_steam else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam for Game Mode" if game.name in self.in_steam else "Not in Steam")
            self.table.setItem(row, 0, box)
            for column, text in enumerate((game.title, game.title_id, game.version, str(game.folder)), start=1):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.blockSignals(False)
        self._update_buttons()

    def ticked(self) -> list[Game]:
        return [g for row, g in enumerate(self.games)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def chosen(self) -> Game | None:
        rows = self.table.selectionModel().selectedRows()
        return self.games[rows[0].row()] if rows else None

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
        self.refresh_button.setEnabled(idle)
        self.install_button.setEnabled(idle and (self.version != emulator.VERSION or self.replaced))
        self.remove_button.setEnabled(idle and installed_)
        self.firmware_button.setEnabled(idle and installed_)
        self.game_button.setEnabled(idle and installed_)
        self.play_button.setEnabled(idle and installed_ and self.chosen() is not None)
        self.vita3k_button.setEnabled(idle and installed_)
        self.covers_button.setEnabled(idle)
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
            self.running.setText(text)
            self._update_buttons()

    def _job_done(self, result: tuple[bool, str]) -> None:
        ok, message = result
        self.running.setText(message)
        self.output.appendPlainText(message)
        self.refresh()
        if not ok:
            self.running.setStyleSheet("font-weight:600;color:#c62828;")
        else:
            self.running.setStyleSheet("font-weight:600;")

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
            text += "\nThe games in Game Mode no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.output.appendPlainText("Vita3K was removed.")
            self.refresh()

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

    def on_install_firmware(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, window_title("Install the PS Vita firmware"), str(Path.home()),
                                              "PS Vita firmware (*.PUP *.pup);;All files (*)")
        if name:
            self.install_firmware(Path(name))

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
        name, _ = QFileDialog.getOpenFileName(self, window_title("Install a game"), str(Path.home()),
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
        folder = QFileDialog.getExistingDirectory(self, window_title("Install a dumped game"), str(Path.home()))
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
            self.running.setText(f"Vita3K could not be started: {command[0]} did not run.")
            return
        self.running.setStyleSheet("font-weight:600;")
        self.running.setText(f"Vita3K installs {path.name} and then starts it in its own window.")
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

    def on_play(self) -> None:
        game = self.chosen()
        if game is None or not self.version:
            return
        command = self.vita3k_command(*shlex.split(shortcuts.launch_options(game)))
        if QProcess.startDetached(command[0], command[1:])[0]:
            self.running.setText(f"Started {game.title}.")
        else:
            self.running.setText(f"{game.title} could not be started: {command[0]} did not run.")

    def on_open_vita3k(self) -> None:
        command = self.vita3k_command()
        if not QProcess.startDetached(command[0], command[1:])[0]:
            self.running.setText(f"Vita3K could not be started: {command[0]} did not run.")

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.running.setText(f"The shortcuts run {self.run_path}, which is not there: install "
                                 f"{APP_NAME} through the portal first.")
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.running.setText("Install Vita3K first: the games in Game Mode start it.")
            return
        text = f"{len(add)} game(s) in Game Mode" + (f", {len(remove)} taken out." if remove else ".")
        if self.steam_running():
            text += "\n\nSteam closes for it and starts again in the background."
        if not self._ask("Game Mode", text):
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
        if covers.edit_key(self, self.covers_key):
            self.refresh()

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
