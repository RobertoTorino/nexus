# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: Xenia itself and the game folders as two steps with their state and buttons, then the games found,
each with a box for Game Mode. Downloading Xenia, asking GitHub for a newer one and changing Steam's files run off
the GUI thread; nothing here needs root. The look is the app's own blue (style.py). Covers… takes the suite's
SteamGridDB API key, with which Update Game Mode looks up each game's pictures first (core's covers)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from bc250_core import SUITE_MANUAL_URL, covers, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import bin_home
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, Terminal, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, emulator, shortcuts, style
from .games import Game, scan

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/xenia/"
STEAM_TIP = "Add the ticked games to Steam and take out the others; Steam closes for it and starts again"
KINDS = {"iso": "ISO", "xex": "XEX", "zar": "ZAR", "god": "Games on Demand", "xbla": "Arcade"}


class XeniaSettings(SettingsStore):
    DEFAULTS: dict = {"folders": []}            # the game folders chosen in the app


class MainWindow(QMainWindow):
    def __init__(self, home: Path | None = None, steam_dir: Path | None = None, run: Path | None = None,
                 fetch: emulator.Download = emulator.download, steam_closed=steam.with_steam_closed,
                 steam_running=steam.steam_running, newer_release=emulator.newer_release,
                 covers_home: Path | None = None, covers_get: covers.Get = covers._get, covers_key: Path | None = None):
        """*home*: where the app installs Xenia; *steam_dir*: Steam's folder (None: looked up); *run*: the run
        wrapper the shortcuts start; *fetch*: the download of Xenia; *steam_closed* and *steam_running*: closing
        Steam for a change and asking whether it runs; *newer_release*: asks GitHub for a newer Xenia;
        *covers_home*, *covers_get* and *covers_key*: where the pictures from SteamGridDB are kept, how SteamGridDB
        is asked and the suite's key file (tests never touch the real ones)."""
        super().__init__()
        self.resize(980, 680)
        self.home = home or emulator.emulator_home()
        self.steam_dir = steam_dir if steam_dir is not None else steam.find_steam()
        self.run_path = run or bin_home() / shortcuts.RUN_NAME
        self.fetch = fetch
        self.steam_closed = steam_closed
        self.steam_running = steam_running
        self.covers_home = covers_home or covers.covers_home(APP_ID)
        self.covers_get = covers_get
        self.covers_key = covers_key
        self.newer: ReleaseInfo | None = None           # Xenia's newest release, when newer than the pinned one
        self.release_check = UpdateChecker(self)        # apart from the worker: it runs while the window opens
        self.release_check.finished.connect(self._release_found)
        self.settings = XeniaSettings(INFO, self)
        self.worker = UpdateChecker(self)            # one job at a time off the GUI thread: a download or Steam
        self.worker.finished.connect(self._job_done)
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.no_cover: set[str] = set()               # games in Steam not yet looked up on SteamGridDB, with a key
        self.version = ""                               # the installed Xenia, "" when none is
        self.folders: list[Path] = []

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.pill = StatusText()
        header.add_state(self.pill)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the state again and look for games")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.emulator_box = MetricBox("Xenia", style.BLUE)
        self.games_box = MetricBox("Games", style.BLUE)
        self.steam_box = MetricBox("In Game Mode", style.BLUE)
        for box in (self.emulator_box, self.games_box, self.steam_box):
            header.add_second(box)
        intro = hint_label(
            "Xbox 360 games on the BC-250 with the Xenia emulator (Xenia Canary, experimental on Linux). The app "
            "installs a tested Xenia build, finds your games and puts them in Steam, so they start from Game Mode. "
            "Games come from your own discs and console; the app never downloads them. "
            + style.link(self, MANUAL_URL, "Manual"))

        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.emulator_state, self.folders_state = (self._state_label() for _ in range(2))
        self.install_button = style.primary_button("Install", f"Download Xenia {emulator.VERSION} from GitHub and "
                                                              "check it")
        self.install_button.clicked.connect(self.on_install)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Remove the installed Xenia; its settings, saves and installed content stay")
        self.remove_button.clicked.connect(self.on_remove)
        self.folder_button = QPushButton("Add folder…")
        self.folder_button.setToolTip("Add a folder with your games (ISO images, unpacked discs with a default.xex, "
                                      ".zar archives, Games on Demand and Arcade packages)")
        self.folder_button.clicked.connect(self.on_add_folder)
        self.forget_button = QPushButton("Remove folder…")
        self.forget_button.setToolTip("Stop looking for games in one of the folders; the games stay where they are")
        self.forget_button.clicked.connect(self.on_forget_folder)
        rows = [("Xenia", self.emulator_state, [self.install_button, self.remove_button]),
                ("Game folders", self.folders_state, [self.folder_button, self.forget_button])]
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
        self.table.setHorizontalHeaderLabels(["Game Mode", "Game", "Title ID", "Kind", "File"])
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
        self.play_button.setToolTip("Start the chosen game in Xenia, here on the desktop")
        self.play_button.clicked.connect(self.on_play)
        self.xenia_button = QPushButton("Xenia settings")
        self.xenia_button.setToolTip("Open Xenia's own window: its settings, profiles and installed content")
        self.xenia_button.clicked.connect(self.on_open_xenia)
        self.covers_button = QPushButton("Covers…")
        self.covers_button.setToolTip("The SteamGridDB API key, one for the whole suite: with it, Update Game Mode "
                                      "gives each game its cover, banner and logo from SteamGridDB in Steam")
        self.covers_button.clicked.connect(self.on_covers)
        self.steam_button = style.primary_button("Update Game Mode", STEAM_TIP)
        self.steam_button.clicked.connect(self.on_update_steam)
        buttons = QHBoxLayout()
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.xenia_button)
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
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION}")
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
        self.folders = [Path(f) for f in self.settings.get("folders") if f]
        self.games = scan(self.folders)
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir else {}
            self.no_cover = ({str(g.file) for g in self.games if str(g.file) in self.in_steam
                              and not covers.known(self.covers_home, shortcuts.cover_name(g))}
                             if covers.read_key(self.covers_key) else set())
        except OSError:
            self.in_steam, self.no_cover = {}, set()
        self._show_state()
        self._fill_table()

    def _show_state(self) -> None:
        pinned = emulator.VERSION
        if not self.version:
            self.emulator_state.setText(f"Not installed. Install downloads Xenia {pinned}, the build this version "
                                        "of the app was tried with, and checks it before installing it.")
            self.emulator_box.set_value("—")
        elif self.version != pinned:
            self.emulator_state.setText(f"Xenia {escape(self.version)} is installed; this version of the app brings "
                                        f"{pinned}: <b>install it</b> to use it.")
            self.emulator_box.set_value(self.version)
        else:
            self.emulator_state.setText(f"Xenia {pinned} is installed: Xenia Canary, experimental on Linux, so "
                                        "not every game starts. "
                                        + style.link(self, emulator.RELEASE_PAGE, "What is in it"))
            self.emulator_box.set_value(pinned)
        if self.newer is not None:
            self.emulator_state.setText(
                self.emulator_state.text() + f"<br>Xenia {escape(self.newer.version)} is out "
                f"({escape(self.newer.published)}). A later version of this app brings it, once it has been tried "
                "on the board. " + style.link(self, self.newer.url, "What is new"))
        self.emulator_state.setOpenExternalLinks(True)

        if self.folders:
            self.folders_state.setText("<br>".join(f"<code>{escape(str(f))}</code>" for f in self.folders))
        else:
            self.folders_state.setText("None yet: add the folder with your games (ISO images, unpacked discs, .zar "
                                       "archives, Games on Demand and Arcade packages).")
        self.games_box.set_value(str(len(self.games)))
        found = {str(g.file) for g in self.games}
        self.steam_box.set_value(str(len(found & set(self.in_steam))))

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install Xenia first.")
        elif not self.games:
            self.pill.set_status("No games", "neutral", "Add the folder with your games.")
        else:
            self.pill.set_status("Ready", "ok", "Xenia is installed and games were found.")

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
            box.setCheckState(Qt.CheckState.Checked if str(game.file) in self.in_steam else Qt.CheckState.Unchecked)
            box.setToolTip("In Steam for Game Mode" if str(game.file) in self.in_steam else "Not in Steam")
            self.table.setItem(row, 0, box)
            kind = KINDS.get(game.kind, game.kind)
            for column, text in enumerate((game.title, game.title_id, kind, str(game.file)), start=1):
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
        shortcuts of games no longer found out too."""
        add = self.ticked()
        found = {str(g.file) for g in self.games}
        remove = [g for g in self.games if str(g.file) in self.in_steam and g not in add]
        remove += [Game(Path(file), name) for file, name in self.in_steam.items() if file not in found]
        return add, remove

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        installed_ = bool(self.version)
        self.refresh_button.setEnabled(idle)
        self.install_button.setEnabled(idle and self.version != emulator.VERSION)
        self.remove_button.setEnabled(idle and installed_)
        self.folder_button.setEnabled(idle)
        self.forget_button.setEnabled(idle and bool(self.folders))
        self.play_button.setEnabled(idle and installed_ and self.chosen() is not None)
        self.covers_button.setEnabled(idle)
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
            text += "\nThe games in Game Mode no longer start until it is installed again."
        if self._ask("Remove", text):
            emulator.remove(self.home)
            self.output.appendPlainText("Xenia was removed.")
            self.refresh()

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
        self.running.setStyleSheet("font-weight:600;")
        self.running.setText(f"{folder} is a game folder now: {len(found)} game(s) in it.")

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
        self.running.setStyleSheet("font-weight:600;")
        self.running.setText(f"{folder} is no longer a game folder; its games stay where they are.")

    def xenia_command(self, *args: str) -> list[str]:
        """Xenia through the run wrapper (from the app folder when it is not installed yet)."""
        run = self.run_path if self.run_path.is_file() else ROOT / shortcuts.RUN_NAME
        return [str(run), *args]

    def on_play(self) -> None:
        game = self.chosen()
        if game is None or not self.version:
            return
        command = self.xenia_command(str(game.file))
        if QProcess.startDetached(command[0], command[1:], str(game.folder))[0]:
            self.running.setText(f"Started {game.title}.")
        else:
            self.running.setText(f"{game.title} could not be started: {command[0]} did not run.")

    def on_open_xenia(self) -> None:
        command = self.xenia_command()
        if not QProcess.startDetached(command[0], command[1:])[0]:
            self.running.setText(f"Xenia could not be started: {command[0]} did not run.")

    def on_update_steam(self) -> None:
        if self.steam_dir is None:
            return
        if not self.run_path.is_file():
            self.running.setText(f"The shortcuts run {self.run_path}, which is not there: install "
                                 f"{APP_NAME} through the portal first.")
            return
        add, remove = self.steam_plan()
        if add and not self.version:
            self.running.setText("Install Xenia first: the games in Game Mode start it.")
            return
        text = f"{len(add)} game(s) in Game Mode" + (f", {len(remove)} taken out." if remove else ".")
        if self.steam_running():
            text += "\n\nSteam closes for it and starts again in the background."
        if not self._ask("Game Mode", text):
            return
        folder, closed, run, existing = self.steam_dir, self.steam_closed, self.run_path, self.in_steam
        key, home, get = covers.read_key(self.covers_key), self.covers_home, self.covers_get

        def job() -> tuple[bool, str]:
            # The pictures first, off the GUI thread; the artwork is drawn here too, on QImage only.
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
        if covers.edit_key(self, self.covers_key):
            self.refresh()

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
