# SPDX-License-Identifier: GPL-3.0-or-later
"""Games page: every Steam game on this PC, each looked through in the background for an AMD FSR 3.1 DLL, with Run
with HelixSR (install when needed, then start the game through Steam). The page shows and asks; the main window
does the file work. GameScanner, at the bottom, is the thread that looks through the game folders."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .backend import GameScan, is_steam_tool, scan_game
from .pages import _item, _table
from .style import accent_button
from .widgets import STATE_COLORS, hint_label, page_header


class GamesPage(QWidget):
    rescan_requested = pyqtSignal()
    run_requested = pyqtSignal(object)              # GameScan
    deploy_page_requested = pyqtSignal(object)      # Path of the game folder

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.scans: dict[Path, GameScan | None] = {}    # None: not looked through yet
        self.checking: set[Path] = set()                # being looked through (again)
        self.rows: list[Path] = []
        self.payload_ready = False
        layout = QVBoxLayout(self)
        header, _ = page_header("Games")
        rescan = QPushButton("Rescan")
        rescan.setToolTip("Read the Steam libraries again and look through every game.")
        rescan.clicked.connect(self.rescan_requested)
        header.addWidget(rescan)
        layout.addLayout(header)
        layout.addWidget(hint_label(
            "Every Steam game on this PC. HelixSR goes in place of a game's AMD FSR 3.1 DLL, so only the games that "
            "ship one can use it: they come first, the others are grayed out. <b>Run with HelixSR</b> (or a "
            "double-click) puts HelixSR in when it is not there yet, again after a game update put the game's own "
            "DLL back, or when the payload has a newer build, then starts the game through Steam. Choose <b>AMD "
            "FSR</b> in the game's graphics settings."))
        self.table = _table(["Game", "HelixSR", "FSR 3.1 DLL", "Folder"])
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._run_clicked())
        layout.addWidget(self.table, 1)
        self.info = hint_label("No Steam library found on this PC.")
        layout.addWidget(self.info)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_deploy = QPushButton("Open on Deploy page")
        self.open_deploy.setToolTip("Pick the DLL yourself, or use the OptiScaler folder, on the Deploy page.")
        self.open_deploy.clicked.connect(self._deploy_page_clicked)
        buttons.addWidget(self.open_deploy)
        self.run = accent_button("Run with HelixSR", "Install HelixSR where needed, then start the game through Steam.")
        self.run.clicked.connect(self._run_clicked)
        buttons.addWidget(self.run)
        layout.addLayout(buttons)
        self._update_buttons()

    # ---------------------------------------------------------------- data in
    def set_games(self, games: list[Path]) -> None:
        games = [game for game in games if not is_steam_tool(game)]
        self.scans = {game: None for game in games}
        self.checking = set(games)
        self._render()

    def set_checking(self, games: list[Path]) -> None:
        """*games* are looked through again; until then they keep their last result."""
        self.checking |= {game for game in games if game in self.scans}
        self._render()

    def show_scan(self, scan: GameScan) -> None:
        if scan.folder in self.scans:
            self.scans[scan.folder] = scan
            self.checking.discard(scan.folder)
            self._render()

    def set_payload_ready(self, ready: bool) -> None:
        self.payload_ready = ready
        self._update_buttons()

    # ---------------------------------------------------------------- state
    def selected(self) -> GameScan | None:
        game = self._selected_row()
        return self.scans.get(game) if game is not None else None

    def _selected_row(self) -> Path | None:
        """The selected game, also while it has not been looked through yet."""
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        row = rows.pop()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def _render(self) -> None:
        current = self._selected_row()
        order = lambda game: (0 if (s := self.scans[game]) is not None and s.usable else 1 if s is None else 2,
                              game.name.lower())
        self.rows = sorted(self.scans, key=order)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row, game in enumerate(self.rows):
            scan = self.scans[game]
            kind, state = ("neutral", "checking…") if game in self.checking else scan.state()
            if scan is not None and scan.dlls:
                dlls = ", ".join(str(d.path.relative_to(game)) for d in scan.targets())
            else:
                dlls = "—"
            items = (_item(game.name), _item(state), _item(dlls), _item(str(game)))
            usable = scan is not None and scan.usable
            for column, item in enumerate(items):
                if not usable:                  # grayed out: no Run, but the Deploy page (OptiScaler) is open to it
                    item.setForeground(self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
                self.table.setItem(row, column, item)
            if usable:
                items[1].setForeground(QColor("white"))
                items[1].setBackground(QColor(STATE_COLORS[kind]))
            if game == current:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        usable = sum(1 for s in self.scans.values() if s is not None and s.usable)
        if not self.scans:
            self.info.setText("No Steam library found on this PC.")
        elif self.checking:
            self.info.setText("Looking through {0} of {1} games…".format(len(self.scans) - len(self.checking),
                                                                        len(self.scans)))
        else:
            self.info.setText("{0} of {1} games ship AMD FSR 3.1. Games that only offer DLSS, XeSS or FSR 2 need "
                              "OptiScaler: Open on Deploy page.".format(usable, len(self.scans)))
        self._update_buttons()

    def _update_buttons(self) -> None:
        scan = self.selected()
        self.open_deploy.setEnabled(scan is not None or self._selected_row() is not None)
        busy = scan is not None and scan.folder in self.checking
        self.run.setEnabled(scan is not None and scan.usable and bool(scan.app_id) and self.payload_ready and not busy)
        self.run.setToolTip("Import a complete payload first (Setup page)." if not self.payload_ready else
                            "Select a game with an FSR 3.1 DLL in the list." if scan is None else
                            "Looking through the game's folder…" if busy else
                            "Not a Steam game: start it yourself." if not scan.app_id else
                            "Install HelixSR where needed, then start {0} through Steam.".format(scan.folder.name))

    def _run_clicked(self) -> None:
        scan = self.selected()
        if scan is not None and self.run.isEnabled():
            self.run_requested.emit(scan)

    def _deploy_page_clicked(self) -> None:
        game = self._selected_row()
        if game is not None:
            self.deploy_page_requested.emit(game)


class GameScanner(QThread):
    """Looks through game folders one by one; scanned(GameScan) arrives on the GUI thread for each."""

    scanned = pyqtSignal(object)

    def __init__(self, games: list[tuple[Path, str]], payload_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.games, self.payload_dir = games, payload_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        for folder, app_id in self.games:
            if self._cancel:
                return
            try:
                scan = scan_game(folder, self.payload_dir, app_id, cancelled=lambda: self._cancel)
            except OSError:
                scan = GameScan(folder, [], app_id)
            if not self._cancel:
                self.scanned.emit(scan)
