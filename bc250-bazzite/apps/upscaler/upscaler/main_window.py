# SPDX-License-Identifier: GPL-3.0-or-later
"""Main window: logo and metric boxes on top, navigation on the left, pages on the right. All file work
(backend.py) happens here, with confirmations and status-bar messages."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from bc250_core import steam

from . import APP_ID, APP_NAME, DEPLOYMENTS_FILE, DISPLAY_NAME, LOGO_PATH, PAYLOAD_DIR, __version__, plain_tooltip
from . import backend, upstream
from .acquire import (
    DLSS_DLL, FALLBACK_VERSION, HELIXSR_DATA_DIR, WORK_DIR, DlssFinder, SetupOutcome, SetupRequest, SetupWorker,
    UpdateChecker, UpdateStatus, latest_work_release, pinned_dlss_sha, version_tuple,
)
from .backend import MODE_FOLDER, MODE_REPLACE, Deployment, DeploymentStore, GameDll, GameScan, HelixError
from .games_page import GamesPage, GameScanner
from .help import HelpView
from .pages import POLL_MS, DeployPage, IniPage, OverviewPage
from .setup_page import SetupPage
from .style import COPPER, CYAN, TEAL
from .widgets import ORANGE, RED, ClickableLogo, MetricBox, header_font


class MainWindow(QMainWindow):
    def __init__(self, payload_dir: Path = PAYLOAD_DIR, deployments_file: Path = DEPLOYMENTS_FILE,
                 work_dir: Path = WORK_DIR, helix_data: Path = HELIXSR_DATA_DIR, check_updates: bool | None = None):
        super().__init__()
        self.payload_dir = payload_dir
        self.work_dir = work_dir
        self.helix_data = helix_data
        self.store = DeploymentStore(deployments_file)
        self.settings = QSettings(APP_ID, APP_ID)
        self.libraries: list[Path] = []
        self.app_ids: dict[Path, str] = {}              # Steam game folder -> AppID
        self._game_scanner: GameScanner | None = None
        self._scan_pending: list[Path] = []
        self.updates: dict[str, UpdateStatus] = {}
        self._setup_worker: SetupWorker | None = None
        self._dlss_finder: DlssFinder | None = None
        self.update_checker = UpdateChecker(self)
        self.update_checker.finished.connect(self._updates_checked)
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1080, 760)

        central = QWidget()
        root = QVBoxLayout(central)
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = ClickableLogo(str(LOGO_PATH), 96)
        logo.setCursor(Qt.CursorShape.ArrowCursor)
        header.addWidget(logo)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        title = QLabel(f"{APP_NAME}  <span style='color:#9aa0a6; font-size:14px;'>v{__version__}</span>")
        title.setStyleSheet(header_font() + "font-size:24px; font-weight:800;")
        header_right.addWidget(title)
        boxes = QHBoxLayout()
        boxes.setSpacing(8)
        self.box_payload = MetricBox("HelixSR payload", COPPER, centred=True)
        self.box_network = MetricBox("Network files", TEAL, centred=True)
        self.box_deployed = MetricBox("Deployments", COPPER, centred=True)
        self.box_games = MetricBox("Steam games", TEAL, centred=True)
        for box in (self.box_payload, self.box_network, self.box_deployed, self.box_games):
            boxes.addWidget(box, 1)
        header_right.addLayout(boxes)
        header.addLayout(header_right, 1)
        root.addLayout(header)

        main = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        self.nav.setStyleSheet(
            "QListWidget { outline:0; }"
            "QListWidget::item { padding:6px; margin:2px 4px; border:2px solid transparent; border-radius:6px; }"
            "QListWidget::item:hover { border-color:palette(mid); }"
            "QListWidget::item:selected { background:transparent; color:palette(text);"
            f" border-color:{CYAN}; }}")
        self.stack = QStackedWidget()
        main.addWidget(self.nav)
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)
        self.setCentralWidget(central)

        self.overview = OverviewPage(payload_dir)
        self.overview.import_folder_requested.connect(self._import_folder)
        self.overview.import_zip_requested.connect(self._import_zip)
        self.overview.open_payload_requested.connect(lambda: self._open_folder(self.payload_dir))
        self.overview.open_folder_requested.connect(self._open_folder)
        self.overview.refresh_requested.connect(self.refresh)
        self.overview.remove_requested.connect(self._remove_deployment)
        self.overview.forget_requested.connect(self._forget)
        self.overview.setup_requested.connect(lambda: self.nav.setCurrentRow(self.page_rows[self.setup_page]))
        self.setup_page = SetupPage()
        self.setup_page.check_requested.connect(self.check_for_updates)
        self.setup_page.start_requested.connect(self._start_setup)
        self.setup_page.cancel_requested.connect(self._cancel_setup)
        self.setup_page.browse_dlss_requested.connect(self._browse_dlss)
        self.setup_page.find_dlss_requested.connect(self._find_dlss)
        self.setup_page.open_work_requested.connect(lambda: self._open_folder(self.work_dir))
        self.setup_page.import_requested.connect(self._import)
        self.setup_page.auto_check_changed.connect(lambda on: self.settings.setValue("updates/check_on_start", on))
        self.setup_page.set_fallback(self.settings.value("setup/fallback", False, type=bool))
        self.setup_page.fallback_changed.connect(lambda on: self.settings.setValue("setup/fallback", on))
        self.games_page = GamesPage()
        self.games_page.rescan_requested.connect(self._scan_steam)
        self.games_page.run_requested.connect(self._run_game)
        self.games_page.deploy_page_requested.connect(self._open_on_deploy_page)
        self.overview.update_requested.connect(self._update_older)
        self.deploy_page = DeployPage()
        self.deploy_page.browse_requested.connect(self._browse_game)
        self.deploy_page.browse_folder_requested.connect(self._browse_folder)
        self.deploy_page.browse_second_requested.connect(self._browse_second)
        self.deploy_page.browse_exe_requested.connect(self._browse_exe)
        self.deploy_page.scan_requested.connect(self._scan)
        self.deploy_page.deploy_requested.connect(self._deploy)
        self.deploy_page.remove_requested.connect(self._remove_from_deploy_page)
        self.deploy_page.copy_requested.connect(self._copy)
        self.ini_page = IniPage()
        self.ini_page.save_default_requested.connect(self._save_ini_default)
        self.ini_page.apply_requested.connect(self._write_ini_to)
        self.help_page = HelpView(str(payload_dir), str(self.store.path), str(work_dir))
        self.page_rows: dict[QWidget, int] = {}
        for name, page in (("Overview", self.overview), ("Setup", self.setup_page),
                           ("Games", self.games_page), ("Deploy", self.deploy_page), ("helixsr.ini", self.ini_page),
                           ("Help", self.help_page)):
            self.nav.addItem(name)
            self.page_rows[page] = self.nav.count() - 1
            if page in (self.deploy_page, self.ini_page):
                # Taller than a small window: scroll instead of squeezing the hints and boxes to one line.
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(page)
                page = scroll
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._bold_nav_item)

        self.statusBar().showMessage("Ready")
        self._load_ini_page()
        self._scan_steam()
        self.refresh()
        self._restore_window_state()
        built = latest_work_release(self.work_dir)
        if built is not None and backend.payload_status(backend.payload_folder(built)).network_ready:
            self.setup_page.set_built(built)
        auto = self.settings.value("updates/check_on_start", True, type=bool) if check_updates is None else check_updates
        self.setup_page.set_auto_check(bool(auto))
        if auto:
            self.check_for_updates()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # ------------------------------------------------------------ window state
    def _restore_window_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        try:
            row = int(self.settings.value("window/page", 0))
        except (TypeError, ValueError):
            row = 0
        self.nav.setCurrentRow(row if 0 <= row < self.nav.count() else 0)
        last_game = self.settings.value("deploy/last_game", "")
        if last_game and Path(last_game).is_dir():
            self.deploy_page.set_game_path(Path(last_game))

    def _bold_nav_item(self, row: int) -> None:
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            font = item.font()
            font.setBold(index == row)
            item.setFont(font)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._setup_worker is not None and self._setup_worker.isRunning():
            if QMessageBox.question(self, "Setup running",
                                 "The HelixSR setup is still running. Cancel it and quit?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._setup_worker.cancel()
            self._setup_worker.wait(15000)
        if self._dlss_finder is not None:
            self._dlss_finder.cancel()
            self._dlss_finder.wait(5000)
        if self._game_scanner is not None:
            self._scan_pending = []
            self._game_scanner.cancel()
            self._game_scanner.wait(5000)
        self.update_checker.stop()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/page", self.nav.currentRow())
        game = self.deploy_page.game_dir()
        self.settings.setValue("deploy/last_game", str(game) if game else "")
        super().closeEvent(event)

    # ------------------------------------------------------------ refresh
    def refresh(self) -> None:
        status = backend.payload_status(self.payload_dir)
        self.overview.show_payload(status)
        self.overview.show_deployments(self.store.items, self.payload_dir)
        self.deploy_page.set_payload_ready(status.ready, status.optiscaler)
        self.games_page.set_payload_ready(status.ready)
        self.ini_page.set_deployments(self.store.items)
        self.ini_page.set_helixsr_version(status.version)

        self.box_payload.set_value(status.version or ("Imported" if status.dll else "Missing"),
                                   plain_tooltip(str(self.payload_dir)))
        self.box_payload.set_colour(COPPER if status.dll else RED)
        self.box_network.set_value("Ready" if status.network_ready else "Missing",
                                   "helixsr_weights.bin and helixsr_kernels.pak from helixsr-setup.sh")
        self.box_network.set_colour(TEAL if status.network_ready else ORANGE)
        states = [backend.deployment_state(d, self.payload_dir)[0] for d in self.store.items]
        in_place = states.count("ok")
        self.box_deployed.set_value(f"{in_place} / {len(states)}" if states else "0",
                                    "HelixSR in place / known deployments")
        self.box_games.set_value(str(len(self.deploy_page.games)),
                                 plain_tooltip("\n".join(str(p) for p in self.libraries) or "No Steam library found"))

    def _scan_steam(self) -> None:
        self.libraries = backend.steam_libraries()
        games = backend.steam_games(self.libraries)
        self.app_ids = backend.steam_app_ids(self.libraries)
        self.deploy_page.set_games(games)
        self.games_page.set_games(games)
        self._scan_games(games)

    # ------------------------------------------------------------ games page
    def _scan_games(self, games: list[Path]) -> None:
        """Look through *games* in the background; while a scan runs, they wait for the next one."""
        games = [g for g in games if g in self.games_page.scans]
        if not games:
            return
        self.games_page.set_checking(games)
        if self._game_scanner is not None:
            self._scan_pending += [g for g in games if g not in self._scan_pending]
            return
        scanner = GameScanner([(g, self.app_ids.get(g, "")) for g in games], self.payload_dir, self)
        scanner.scanned.connect(self.games_page.show_scan)
        scanner.finished.connect(self._games_scanned)
        self._game_scanner = scanner
        scanner.start()

    def _games_scanned(self) -> None:
        scanner, self._game_scanner = self._game_scanner, None
        if scanner is not None:
            scanner.wait()
            scanner.deleteLater()
        pending, self._scan_pending = self._scan_pending, []
        self._scan_games(pending)

    def _game_of(self, location: Path) -> Path | None:
        """The Steam game folder *location* is in, if any."""
        return next((g for g in self.games_page.scans if location == g or g in location.parents), None)

    def _rescan_game_of(self, location: Path) -> None:
        game = self._game_of(location)
        if game is not None:
            self._scan_games([game])

    def _open_on_deploy_page(self, game: Path) -> None:
        self.nav.setCurrentRow(self.page_rows[self.deploy_page])
        self.deploy_page.set_game_path(game)

    def _run_game(self, scan: GameScan) -> None:
        """Run with HelixSR: HelixSR goes in where it is missing, older or replaced by the game's own DLL, then
        Steam starts the game. Nothing changes while the game runs."""
        name = self._game_name(scan.folder)
        if backend.game_running(scan.app_id):
            QMessageBox.information(self, "Run with HelixSR", ("{0} is running. Close it first: HelixSR goes in "
                                                              "before the game starts.").format(name))
            return
        targets = [d for d in scan.targets() if not d.matches_payload]
        fresh = [d for d in targets if not d.deployed]
        if fresh and QMessageBox.question(
                self, "Run with HelixSR",
                "Put HelixSR in place of\n{paths}\n\nThe game's file is kept as .original.dll; Remove puts it "
                "back.".format(paths="\n".join(str(d.path) for d in fresh))) != QMessageBox.StandardButton.Yes:
            return
        version = backend.payload_status(self.payload_dir).version
        try:
            for dll in targets:
                dep = Deployment(str(dll.path), MODE_REPLACE, name)
                backend.update_deployment(dep, self.payload_dir)
                self.store.record(dll.path, MODE_REPLACE, name, version)
        except (HelixError, OSError) as exc:
            QMessageBox.critical(self, "Deploy failed", str(exc))
            self.refresh()
            self._scan_games([scan.folder])
            return
        self.refresh()
        self._scan_games([scan.folder])
        try:
            subprocess.Popen(["xdg-open", f"steam://rungameid/{scan.app_id}"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            QMessageBox.warning(self, "Could not start the game", "steam://rungameid/{0}\n{1}".format(scan.app_id, exc))
            return
        self.statusBar().showMessage(("HelixSR put into {0} DLL(s); starting {1} through Steam. Choose AMD FSR in the "
                                      "game.").format(len(targets), name) if targets else
                                     "Starting {0} through Steam with HelixSR.".format(name), 10000)

    # ------------------------------------------------------------ update older deployments
    def _update_older(self, ask: bool = False) -> None:
        """Update older games: the payload's HelixSR into every deployment with an older build or with the game's own
        DLL back. *ask*: after a build, only when there are such deployments, and the user agrees."""
        deps = [d for d in self.store.items if backend.needs_update(d, self.payload_dir)]
        if not deps or not backend.payload_status(self.payload_dir).ready:
            return
        if ask and QMessageBox.question(
                self, "Update older games",
                "{0} game(s) still have an older HelixSR or the game's own DLL:\n{1}\n\nPut the new build in now? "
                "Their helixsr.ini is kept.".format(len(deps), "\n".join(d.game for d in deps))) \
                != QMessageBox.StandardButton.Yes:
            return
        version = backend.payload_status(self.payload_dir).version
        done, skipped = [], []
        for dep in deps:
            game = self._game_of(dep.location)
            if game is not None and self.app_ids.get(game) and backend.game_running(self.app_ids[game]):
                skipped.append("{0}: running, close it first".format(dep.game))
                continue
            try:
                backend.update_deployment(dep, self.payload_dir)
            except (HelixError, OSError) as exc:
                skipped.append("{0}: {1}".format(dep.game, exc))
                continue
            self.store.record(dep.location, dep.mode, dep.game, version)
            done.append(dep)
        self.refresh()
        self._scan_games([g for g in (self._game_of(d.location) for d in done) if g is not None])
        if skipped:
            QMessageBox.warning(self, "Update older games", "Updated {0} of {1}. Not updated:\n{2}".format(
                len(done), len(deps), "\n".join(skipped)))
        else:
            self.statusBar().showMessage("HelixSR {0} put into {1} game(s).".format(version, len(done)), 8000)

    def _load_ini_page(self) -> None:
        template = backend.ini_template(self.payload_dir)
        self.ini_page.load(backend.parse_ini(template), template)

    # ------------------------------------------------------------ payload
    def _import_folder(self) -> None:
        start = self.settings.value("import/last_dir", str(Path.home() / "Downloads"))
        source = QFileDialog.getExistingDirectory(self, "Extracted HelixSR release folder", start)
        if source:
            self._import(Path(source))

    def _import_zip(self) -> None:
        start = self.settings.value("import/last_dir", str(Path.home() / "Downloads"))
        source, _ = QFileDialog.getOpenFileName(self, "HelixSR release zip", start, "Zip archives (*.zip)")
        if source:
            self._import(Path(source))

    def _import(self, source: Path) -> None:
        self.settings.setValue("import/last_dir", str(source.parent if source.is_file() else source))
        try:
            result = backend.import_payload(source, self.payload_dir)
        except (HelixError, OSError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self._load_ini_page()
        self.refresh()
        text = "Imported {0} file(s): {1}.".format(len(result.copied), ", ".join(result.copied))
        if result.missing:
            text += ("\n\nStill missing: {0}. Run helixsr-setup.sh in the extracted "
                     "release folder, then import that folder.").format(", ".join(result.missing))
            QMessageBox.warning(self, "Payload incomplete", text)
        else:
            self.statusBar().showMessage(text, 8000)

    def _save_ini_default(self, text: str) -> None:
        try:
            self.payload_dir.mkdir(parents=True, exist_ok=True)
            (self.payload_dir / backend.INI).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Could not write", str(exc))
            return
        self.ini_page.template = text
        self.refresh()
        self.statusBar().showMessage("Saved {0}".format(self.payload_dir / backend.INI), 6000)

    # ------------------------------------------------------------ deploy page
    def _browse_game(self) -> None:
        start = self.deploy_page.game_path.text() or (str(self.libraries[0] / "common") if self.libraries
                                                      else str(Path.home()))
        path = QFileDialog.getExistingDirectory(self, "Game folder", start)
        if path:
            self.deploy_page.set_game_path(Path(path))

    def _browse_folder(self) -> None:
        start = self.deploy_page.folder_path.text() or self.deploy_page.game_path.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Folder for HelixSR (OptiScaler)", start)
        if path:
            self.deploy_page.set_folder_path(Path(path))

    def _browse_second(self) -> None:
        start = self.deploy_page.second_path.text() or self.deploy_page.game_path.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Second FidelityFX upscaler DLL (e.g. AMD's with FSR 4)", start,
                                              "DLL files (*.dll)")
        if path:
            self.deploy_page.set_second_upscaler(Path(path))

    def _browse_exe(self) -> None:
        start = self.deploy_page.exe_path.text() or self.deploy_page.game_path.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "The folder of the game's .exe", start)
        if path:
            self.deploy_page.set_exe_folder(Path(path))

    def _scan(self, game_dir: Path) -> None:
        if not game_dir.is_dir():
            self.deploy_page.show_found([], game_dir, "{0} is not a folder.".format(game_dir))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            found = backend.find_game_dlls(game_dir, self.payload_dir)
            self.deploy_page.set_exe_folder(backend.find_exe_folder(game_dir))
        except OSError as exc:
            found = []
            self.deploy_page.show_found([], game_dir, "Could not scan {0}: {1}".format(game_dir, exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.deploy_page.show_found(found, game_dir)

    def _game_name(self, path: Path) -> str:
        return backend.game_name(path, self.libraries)

    def _deploy(self, info: GameDll | None, mode: str, folder: Path | None, write_ini: bool,
                second: Path | None = None, exe_dir: Path | None = None) -> None:
        if write_ini and not self.ini_page.valid():
            QMessageBox.warning(self, "helixsr.ini", ("The helixsr.ini page has invalid values; fix them or untick "
                                                      "writing the ini."))
            return
        ini_text = self.ini_page.text() if write_ini else None
        version = backend.payload_status(self.payload_dir).version
        try:
            if mode == MODE_REPLACE:
                if info is None:
                    return
                if not info.deployed and QMessageBox.question(
                        self, "Deploy HelixSR",
                        "Rename\n{path}\nto {original} and put HelixSR in its place?".format(
                            path=info.path, original=info.original.name)) \
                        != QMessageBox.StandardButton.Yes:
                    return
                written = backend.deploy(info.path, self.payload_dir, ini_text)
                location = info.path
            else:
                if folder is None:
                    return
                if exe_dir is not None and backend.optiscaler_record(folder) is None and QMessageBox.question(
                        self, "Install OptiScaler",
                        ("Put OptiScaler into\n{exe_dir}\nnext to the game's .exe, pointed at HelixSR in\n{folder}?"
                         "\n\nA file of the game it replaces is kept in {backup}; Remove puts it back. The game's "
                         "Steam launch options get the WINEDLLOVERRIDES that Proton needs to load it; Remove takes "
                         "that out again.").format(
                                    exe_dir=exe_dir, folder=folder, backup=folder / backend.OPTISCALER_BACKUP)) \
                        != QMessageBox.StandardButton.Yes:
                    return
                written = backend.deploy_folder(folder, self.payload_dir, ini_text, second)
                if exe_dir is not None:
                    written += backend.install_optiscaler(exe_dir, folder, self.payload_dir)
                location = folder
        except (HelixError, OSError) as exc:
            QMessageBox.critical(self, "Deploy failed", str(exc))
            return
        game_dir = self.deploy_page.game_dir()
        self.store.record(location, mode, self._game_name(game_dir or location), version)
        self.refresh()
        if game_dir:
            self._scan(game_dir)
        self._rescan_game_of(location)
        self.statusBar().showMessage("HelixSR deployed: {0} file(s) written to {1}".format(
            len(written), location.parent if mode == MODE_REPLACE else location), 8000)
        if mode == MODE_FOLDER:
            record = backend.optiscaler_record(folder)
            launch = self._set_launch_options(folder, game_dir) if exe_dir is not None and record else ""
            text = (("HelixSR is in\n{folder}\nand OptiScaler, as {name}, in\n{exe_dir}\n\n{launch}Start the game and "
                     "select DLSS. OptiScaler's menu (Insert) shows FSR HelixSR.").format(
                                folder=folder, name=record["optiscaler"], exe_dir=record["exe_dir"], launch=launch)
                    if exe_dir is not None and record else
                    ("HelixSR is in\n{folder}\n\nNow point OptiScaler at it: the OptiScaler.ini lines "
                     "on the Deploy page (Copy button) go into the game's OptiScaler.ini.").format(folder=folder))
            QMessageBox.information(self, "HelixSR folder ready",
                                    text
                                    + (
                                        "\n\n" + (
                                            "The second upscaler is in the folder as {0}; OptiScaler's FFX Upscaler menu "
                                            "lists its upscalers after HelixSR.").format(backend.SECOND_UPSCALER_DLL)
                                       if second is not None else ""))

    def _remove_from_deploy_page(self, info: GameDll | None, mode: str, folder: Path | None) -> None:
        if mode == MODE_REPLACE and info is not None:
            self._remove(info.path, MODE_REPLACE)
        elif mode == MODE_FOLDER and folder is not None:
            self._remove(folder, MODE_FOLDER)

    def _remove_deployment(self, dep: Deployment) -> None:
        self._remove(dep.location, dep.mode)

    def _remove(self, location: Path, mode: str) -> None:
        what = ("Delete HelixSR's files next to\n{0}\nand rename the game's .original.dll back?".format(location)
                if mode == MODE_REPLACE else "Delete HelixSR's files in\n{0}?".format(location))
        if QMessageBox.question(self, "Remove HelixSR", what) != QMessageBox.StandardButton.Yes:
            return
        launch = (backend.optiscaler_record(location) or {}).get("launch", []) if mode == MODE_FOLDER else []
        try:
            removed = (backend.remove(location, self.payload_dir) if mode == MODE_REPLACE
                       else backend.remove_folder(location, self.payload_dir))
        except (HelixError, OSError) as exc:
            QMessageBox.critical(self, "Remove failed", str(exc))
            return
        self.store.forget(location)
        self.refresh()
        game_dir = self.deploy_page.game_dir()
        if game_dir:
            self._scan(game_dir)
        self._rescan_game_of(location)
        self.statusBar().showMessage("Removed {0} file(s); HelixSR is gone from {1}".format(
            len(removed), location.parent if mode == MODE_REPLACE else location), 8000)
        if launch:
            self._restore_launch_options(launch)

    # ------------------------------------------------------------------------------------ Steam launch options
    def _app_id(self, game_dir: Path | None) -> str:
        if game_dir is None:
            return ""
        ids = {folder.resolve(): app_id for folder, app_id in backend.steam_app_ids(self.libraries).items()}
        return ids.get(game_dir.resolve(), "")

    def _write_launch_options(self, changes: list[tuple[Path, str, str]], why: str) -> str | None:
        """Writes (config, AppID, value) with Steam closed, as Steam writes localconfig.vdf again when it exits: a
        running Steam is closed after asking and started again. In Game Mode Steam is the session and stays. Returns
        None when written, else why not."""
        if steam.game_mode():
            return "In Game Mode Steam is the session itself and stays open."
        if steam.steam_running() and QMessageBox.question(
                self, "Steam launch options",
                ("{0}\n\nSteam is running and writes its settings again when it closes, so it has to close for this. "
                 "Close Steam now and start it again afterwards?").format(why)) != QMessageBox.StandardButton.Yes:
            return "Steam stayed open."

        def change() -> None:
            for config, app_id, value in changes:
                backend.set_launch_options(config, app_id, value)

        def wait(seconds: float) -> None:
            QApplication.processEvents()
            time.sleep(seconds)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            steam.with_steam_closed(change, running=steam.steam_running, sleep=wait)
        except (steam.SteamError, HelixError, OSError) as exc:
            return str(exc)
        finally:
            QApplication.restoreOverrideCursor()
        return None

    def _set_launch_options(self, folder: Path, game_dir: Path | None) -> str:
        """Under Proton OptiScaler only loads with WINEDLLOVERRIDES in the game's launch options: set for every
        Steam user and kept in OptiScaler's record for Remove. Returns a paragraph for the message after Deploy, ""
        for a game outside Steam."""
        record = backend.optiscaler_record(folder) or {}
        name, app_id, root = record.get("optiscaler", ""), self._app_id(game_dir), steam.find_steam()
        if not name.lower().endswith(".dll") or not app_id or root is None:
            return ""
        try:
            plan = [(config, before, backend.with_override(before, name)) for config in backend.launch_configs(root)
                    for before in [backend.launch_options(config, app_id)]]
        except (HelixError, OSError) as exc:
            plan, problem = [], str(exc)
        else:
            problem = None if plan else "Steam has no users on this system yet."
        line = plan[0][2] if plan else backend.with_override("", name)
        changed = [(config, before, after) for config, before, after in plan if before != after]
        if problem is None and not changed:
            return "The game's Steam launch options already load it:\n{0}\n\n".format(line)
        if problem is None:
            problem = self._write_launch_options([(c, app_id, a) for c, _, a in changed], "Set the Steam launch options of {0} to\n{1}".format(
                self._game_name(game_dir), line))
        if problem is None:
            backend.record_launch_options(folder, app_id, changed)
            return "The game's Steam launch options are now:\n{0}\n\n".format(line)
        self._copy(line)
        return ("The game's Steam launch options were not changed: {0} Set them in the game's Properties in Steam "
                "(copied to the clipboard):\n{1}\n\n").format(problem, line)

    def _restore_launch_options(self, entries: list[dict]) -> None:
        """After Remove: the launch options Deploy set go back to what they were, where the user did not change
        them since."""
        restores = backend.launch_restores(entries)
        if not restores:
            return
        problem = self._write_launch_options(restores, "Put the game's Steam launch options back to what they were "
                                                       "before OptiScaler?")
        if problem is not None:
            QMessageBox.information(self, "Steam launch options", (
                "The game's Steam launch options were not changed: {0} Take WINEDLLOVERRIDES out of them in the "
                "game's Properties in Steam; without OptiScaler it does nothing.").format(problem))

    def _forget(self, dep: Deployment) -> None:
        self.store.forget(dep.location)
        self.refresh()

    def _write_ini_to(self, dep: Deployment, text: str) -> None:
        target = dep.folder / backend.INI
        if not dep.folder.is_dir():
            QMessageBox.warning(self, "Folder gone", "{0} does not exist any more.".format(dep.folder))
            return
        try:
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Could not write", str(exc))
            return
        self.refresh()
        self.statusBar().showMessage("Wrote {0}".format(target), 6000)

    # ------------------------------------------------------------ updates
    def check_for_updates(self) -> None:
        if self.update_checker.start(backend.payload_status(self.payload_dir).version):
            self.setup_page.set_checking(True)

    def _updates_checked(self, statuses: dict) -> None:
        self.updates = statuses
        self.setup_page.set_checking(False)
        self.setup_page.show_updates(statuses)
        helix = statuses.get("helixsr")
        if helix is None:
            return
        self._publish_update(helix)
        if helix.latest.error:
            self.overview.show_update("", "neutral")
            self.statusBar().showMessage("Update check: {0}".format(helix.latest.error), 8000)
        elif helix.update_available and self.setup_page.fallback() and \
                version_tuple(helix.installed) == version_tuple(FALLBACK_VERSION):
            self.overview.show_update(("HelixSR {version} is out ({published}); the payload has {installed}, "
                                       "the fallback picked on the Setup page.").format(
                                              version=helix.latest.version, published=helix.latest.published,
                                              installed=helix.installed), "info")
        elif helix.update_available:
            self.overview.show_update(("HelixSR {version} is out ({published}); the payload "
                                       "has {installed}. Get HelixSR… updates it.").format(
                                              version=helix.latest.version, published=helix.latest.published,
                                              installed=helix.installed), "warn")
        elif not helix.installed and helix.latest.version:
            self.overview.show_update("Latest HelixSR release: {version} ({published}).".format(
                version=helix.latest.version, published=helix.latest.published), "info")
        elif helix.unsupported:
            self.overview.show_update(("HelixSR {version} is out; this app does not support it yet and stays on "
                                       "{installed}.").format(version=helix.unsupported,
                                                              installed=helix.installed), "info")
        else:
            self.overview.show_update("", "ok")

    def _publish_update(self, helix: UpdateStatus) -> None:
        """For the portal's notice: a newer HelixSR that Get HelixSR… installs, or none. Not when the check failed
        (the last answer stands), nor when the payload is the fallback picked on the Setup page."""
        if helix.latest.error or not helix.latest.version:
            return
        on_fallback = self.setup_page.fallback() and version_tuple(helix.installed) == version_tuple(FALLBACK_VERSION)
        updates = [upstream.Outside("HelixSR", helix.installed, helix.latest.version, helix.latest.published,
                                    helix.latest.url, "Get HelixSR… on the Setup page updates it.")] \
            if helix.update_available and not on_fallback else []
        upstream.publish("upscaler", updates)

    # ------------------------------------------------------------ setup (download + build)
    def _start_setup(self, dlss_file: Path | None) -> None:
        if self._setup_worker is not None:
            return
        if dlss_file is not None and not dlss_file.is_file():
            QMessageBox.warning(self, DLSS_DLL, "{0} does not exist.".format(dlss_file))
            return
        fallback = self.setup_page.fallback()
        helix = self.updates.get("helixsr")
        release = helix.latest if helix is not None and helix.latest.asset_url and not fallback else None
        wanted = FALLBACK_VERSION if fallback else release.version if release is not None else ""
        status = backend.payload_status(self.payload_dir)
        if status.ready and wanted and version_tuple(status.version) == version_tuple(wanted) and QMessageBox.question(
                self, "Payload is current",
                ("The payload already has HelixSR {version} with its network files. "
                 "Download and build again anyway?").format(
                            version=status.version or "(unknown version)")) != QMessageBox.StandardButton.Yes:
            self.setup_page.set_stage(("Nothing to do: the payload already has HelixSR {version} "
                                       "with its network files. Use Deploy to install it into a game.").format(
                                          version=status.version or ""))
            self.statusBar().showMessage("Payload is already current.", 6000)
            return
        request = SetupRequest(release, self.work_dir, self.helix_data, dlss_file, fallback=fallback)
        worker = SetupWorker(request, self)
        worker.log.connect(self.setup_page.append)
        worker.stage.connect(self.setup_page.set_stage)
        worker.progress.connect(self.setup_page.set_progress)
        worker.finished_with.connect(self._setup_finished)
        self._setup_worker = worker
        self.setup_page.set_running(True)
        self.statusBar().showMessage("HelixSR setup running…")
        worker.start()

    def _cancel_setup(self) -> None:
        if self._setup_worker is not None:
            self._setup_worker.cancel()
            self.setup_page.set_stage("Cancelling…")

    def _setup_finished(self, outcome: SetupOutcome) -> None:
        worker, self._setup_worker = self._setup_worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.setup_page.set_stage(outcome.message)
        self.setup_page.set_built(outcome.release_dir if outcome.ok else None)
        self.setup_page.set_running(False)
        if not outcome.ok:
            self.statusBar().showMessage("HelixSR setup failed: {0}".format(outcome.message.splitlines()[0]),
                                         10000)
            if outcome.message != "Cancelled.":
                QMessageBox.critical(self, "HelixSR setup failed", outcome.message)
            return
        self.statusBar().showMessage("{message} ({seconds:.0f} s)".format(
            message=outcome.message, seconds=outcome.seconds), 10000)
        self._import(outcome.release_dir)
        self._scan_games(list(self.games_page.scans))
        self._update_older(ask=True)
        self.check_for_updates()

    def _browse_dlss(self) -> None:
        start = self.setup_page.dlss_path.text() or (str(self.libraries[0] / "common") if self.libraries
                                                    else str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, "NVIDIA {0} (310.7.0)".format(DLSS_DLL), start,
                                        f"{DLSS_DLL} ({DLSS_DLL})")
        if path:
            self.setup_page.dlss_path.setText(path)

    def _find_dlss(self) -> None:
        if self._dlss_finder is not None or not self.libraries:
            if not self.libraries:
                self.setup_page.append("No Steam library found on this PC.")
            return
        self.setup_page.find_dlss.setEnabled(False)
        self.setup_page.append("Looking for {dll} in {libraries} …".format(
            dll=DLSS_DLL, libraries=", ".join(str(p) for p in self.libraries)))
        finder = DlssFinder(self.libraries, pinned_dlss_sha(latest_work_release(self.work_dir)), self)
        finder.found.connect(self._dlss_found)
        self._dlss_finder = finder
        finder.start()

    def _dlss_found(self, paths: list) -> None:
        finder, self._dlss_finder = self._dlss_finder, None
        if finder is not None:
            finder.wait()
            finder.deleteLater()
        self.setup_page.set_dlss_candidates([Path(p) for p in paths])

    # ------------------------------------------------------------ misc
    def _copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Copied to the clipboard", 4000)

    def _open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open", f"{folder}\n{exc}")
