# SPDX-License-Identifier: GPL-3.0-or-later
"""The dashboard's window: the suite chosen in the header, the tiles (the Nexus apps of the checkout, then the
suite's tours and icons and Close issues), Test local apps (the suite's portal and apps from the checkout, and the
wikis), and what happened below. A click on an app's tile starts it with its run script, in its own session, and
says where its log is; a click on a tool's tile opens its dialog on the chosen suite. A tile is greyed out where it
does not run here: Nexus Demo Recorder on Windows, a suite's tours where its scripts need the other system, the
icons for a suite whose apps take no category icons. Test local apps and Close issues came from Nexus Release
Tool's Test on this board (owner, 04-11-2026: the release tool is the release, the dashboard the place for working
on a suite)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QRectF, QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QListView, QListWidget,
                             QListWidgetItem, QMainWindow, QMessageBox, QVBoxLayout, QWidget)

from bc250_core.instance import server_name
from bc250_core.theme import ORANGE
from bc250_core.widgets import AppHeader, InfoButton, Terminal, hint_label

from . import APP_ID, APP_NAME, CHECKOUT, LOGO_PATH, __version__
from . import local
from .checkout import DevApp, dev_apps, here, start, suite_name, suites
from .icons import IconsDialog, has_category_icons
from .issues import IssuesDialog, close_commands, fetch_open_issues, gh_program
from .tours import RECORD_APP_TOUR, RECORD_TOUR, AppsTourDialog, PortalTourDialog

SUITE_KEY = "suite"                     # the chosen suite, in the settings
ICON_PX = 64
BADGE_PX = 26                           # the warning in the corner of an app's icon that changes the board
# Each local app's output, a log per app (the Nexus apps' logs are in checkout.LOG_DIR)
LOCAL_LOG_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP_ID / "local"
ABOUT = ("One door to the tools for working on the suites. The first tiles are the Nexus apps of this checkout, "
         "each a window of its own that keeps running when the dashboard closes: Nexus Release Tool (a release's "
         "versions, CHANGELOG entries, pins and the board checks), Nexus Installer Tests (a suite's installer tests "
         "one at a time), Nexus Demo Recorder (a portal installation recorded with OBS, Linux) and Nexus Sound Lab (short "
         "sound effects for the windows, made from sliders and saved as WAV).\n\n"
         "The other tiles work on the suite chosen in the header: Portal video tour and Apps video tour record the "
         "suite's tours from this checkout (its tools/record-tour.sh and record-app-tour.sh), Convert icons makes "
         "a category's icons from your images (tools/sync_icons.py). Close issues is the repository's: it lists "
         "the open issues on GitHub and closes the ones you tick. A tile is greyed out where it does not run on "
         "this system or for this suite.\n\n"
         "Test local apps, below the tiles: the suite's portal and apps as they are in this checkout, to try them "
         "before their release, then the suite's wiki and the Nexus page served from the checkout.")
LOCAL_ABOUT = (
    "Click an app to start it from this checkout, to try it before its release: <code>python -m</code> with this "
    "venv and the checkout's core, as <code>run.sh</code> starts an app. An app that changes how the board runs "
    "(an orange <b>!</b> on its icon) asks first; it uses the scripts in the checkout. Each app writes its output "
    f"to <code>{LOCAL_LOG_DIR}</code>; when it stops with an error, the end of that log shows below. The suite's "
    "portal is the first icon; when a portal is already open it warns instead, as a second one would only show the "
    "open one. The last icons are the suite's wiki and the Nexus page: each is served with <code>mkdocs "
    "serve</code> on a port of its own and opens in the browser with its design panel; it rebuilds on every save. "
    "With <b>Wikis on the network</b> they are served for the other devices too, on ports of their own; the "
    "addresses show below.")


def board_badge(icon: QIcon) -> QIcon:
    """*icon* with a warning in its lower right corner: the app changes how the board runs. On the icon, not in the
    label, so a name that wraps never pushes it out of the grid's cell."""
    pixmap = QPixmap(ICON_PX, ICON_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    icon.paint(painter, 0, 0, ICON_PX, ICON_PX)
    corner = QRectF(ICON_PX - BADGE_PX, ICON_PX - BADGE_PX, BADGE_PX, BADGE_PX)
    painter.setPen(QPen(QColor("white"), 2))
    painter.setBrush(QColor(ORANGE))
    painter.drawEllipse(corner.adjusted(1, 1, -1, -1))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(BADGE_PX - 8)
    painter.setFont(font)
    painter.drawText(corner, Qt.AlignmentFlag.AlignCenter, "!")
    painter.end()
    return QIcon(pixmap)


def instance_running(app_id: str) -> bool:
    """Whether *app_id* is open for this user: something listens on its instance socket (core's instance.py). It only
    connects and lets go, so the open window is not asked to show itself."""
    connection = QLocalSocket()
    connection.connectToServer(server_name(app_id))
    found = connection.waitForConnected(500)
    connection.abort()
    return found


def answers(url: str) -> bool:
    """True when something listens at the host and port of *url* (a local server that is up)."""
    address = QUrl(url)
    try:
        with socket.create_connection((address.host(), address.port(80)), timeout=0.2):
            return True
    except OSError:
        return False


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def log_tail(log: Path, lines: int = 20) -> str:
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def start_local(command: list[str], env: dict[str, str], cwd: Path, log: Path) -> subprocess.Popen:
    """Starts a local app in its own session, so it keeps running when this window closes; its output goes to *log*."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as out:
        return subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True)
LOGO_ICON = LOGO_PATH


class Tile:
    """One tile: an app of dev/ or a tool of the suite, with why it is greyed out when it is."""

    def __init__(self, key: str, name: str, icon: Path | None, tooltip: str, app: DevApp | None = None,
                 off: str = ""):
        self.key, self.name, self.icon, self.tooltip, self.app, self.off = key, name, icon, tooltip, app, off


class MainWindow(QMainWindow):
    def __init__(self, root: Path = CHECKOUT, settings: QSettings | None = None, suite: str | None = None,
                 starter=start, open_file=None, start_local=start_local, issues_source=fetch_open_issues):
        """*settings* keeps the chosen suite (None: this session only); *suite* opens that suite (a folder name);
        *starter* starts a dev app (checkout.start); *open_file* opens a video (the system's player); *start_local*
        starts an app or a wiki under Test local apps; *issues_source* reads the open GitHub issues for Close
        issues."""
        super().__init__()
        self.root = root
        self.settings = settings
        self.starter = starter
        self.start_local = start_local
        self.issues_source = issues_source
        self.open_file = open_file or (lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        self.setWindowTitle(APP_NAME)
        self.resize(900, 820)
        self.suites = suites(root)
        remembered = str(settings.value(SUITE_KEY, "")) if settings is not None else ""
        self.suite = suite if suite in self.suites else remembered if remembered in self.suites else \
            self.suites[0] if self.suites else None
        self.apps = dev_apps(root)

        central = QWidget()
        layout = QVBoxLayout(central)
        header = AppHeader(LOGO_ICON, APP_NAME, __version__)
        header.add_action(InfoButton(ABOUT, "What this app does"))
        self.suite_box = QComboBox()
        for name in self.suites:
            self.suite_box.addItem(suite_name(root, name), name)
        self.suite_box.setToolTip("The suite the tours and the icons work on; the Nexus apps are every suite's")
        if self.suite is not None:
            self.suite_box.setCurrentIndex(self.suites.index(self.suite))
        self.suite_box.currentIndexChanged.connect(lambda index: self.choose_suite(self.suite_box.itemData(index)))
        header.add_second(QLabel("Suite:"))
        header.add_second(self.suite_box)
        header.add_second(hint_label("Click a tile: an app opens in a window of its own, a tool on the suite."), 1)
        layout.addLayout(header)

        self.tiles = QListWidget()
        self.tiles.setViewMode(QListView.ViewMode.IconMode)
        self.tiles.setIconSize(QSize(ICON_PX, ICON_PX))
        self.tiles.setGridSize(QSize(150, 120))
        self.tiles.setResizeMode(QListView.ResizeMode.Adjust)
        self.tiles.setMovement(QListView.Movement.Static)
        self.tiles.setWordWrap(True)
        self.tiles.itemClicked.connect(lambda item: self.click(item.data(Qt.ItemDataRole.UserRole)))
        self.tiles.setMinimumHeight(2 * 120 + 12)      # two rows of tiles, the window's width or less
        layout.addWidget(self.tiles)

        local_title = QLabel("Test local apps")
        local_title.setStyleSheet("font-weight:700;")
        self.network_box = QCheckBox("Wikis on the network")
        self.network_box.setToolTip("Serve the wikis on every address of this computer, on ports of their own, so "
                                    "the other devices on the network (a handheld, a laptop, the TV) open them too; "
                                    "their addresses show below once a wiki started")
        self.network_box.toggled.connect(lambda _on: self.fill_local())
        local_row = QHBoxLayout()
        local_row.addWidget(local_title)
        local_row.addWidget(InfoButton(LOCAL_ABOUT, "Test local apps"))
        local_row.addWidget(hint_label("Click an app to start it from this checkout, to try it before its release; "
                                       "the last icons serve the wikis."), 1)
        local_row.addWidget(self.network_box)
        layout.addLayout(local_row)
        self.local_apps = QListWidget()
        self.local_apps.setViewMode(QListView.ViewMode.IconMode)
        self.local_apps.setIconSize(QSize(ICON_PX, ICON_PX))
        self.local_apps.setGridSize(QSize(150, 120))
        self.local_apps.setResizeMode(QListView.ResizeMode.Adjust)
        self.local_apps.setMovement(QListView.Movement.Static)
        self.local_apps.setWordWrap(True)
        self.local_apps.itemClicked.connect(lambda item: self.run_local(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.local_apps, 3)
        self.running: list[tuple[local.Launch, subprocess.Popen, Path]] = []
        self.waiting: list[str] = []            # servers started, whose page opens once they answer
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.poll)
        self.closing: list[list[str]] = []      # the gh issue close commands still to run
        self.closer: QProcess | None = None

        self.output = Terminal()
        self.output.setMaximumBlockCount(2000)
        layout.addWidget(self.output, 1)
        self.setCentralWidget(central)
        self.fill()

    # --- the suite and the tiles ------------------------------------------------------------------------------
    @property
    def suite_dir(self) -> Path | None:
        return self.root / self.suite if self.suite else None

    def choose_suite(self, name: str | None) -> None:
        if not name or name == self.suite:
            return
        self.suite = name
        if self.settings is not None:
            self.settings.setValue(SUITE_KEY, name)
        self.fill()

    def tile_list(self) -> list[Tile]:
        """The tiles in their order: the Nexus apps, then the suite's tools; each with why it is off, when it is."""
        found = []
        for app in self.apps:
            off = "" if app.runs_here else f"{app.name} runs on Linux (OBS and the desktop portal)."
            found.append(Tile(app.key, app.name, app.icon, f"{app.name} {app.version}: {app.script.name} in "
                              f"{app.folder}", app, off))
        suite = self.suite_dir
        if suite is None:
            off_tours = off_icons = "No suite in the checkout."
        else:
            system = "Windows" if sys.platform == "win32" else "Linux"
            off_tours = ("" if here(self.root, self.suite) and (suite / RECORD_TOUR).is_file()
                         else f"{self.suite}'s tours are not recorded on {system}.")
            off_icons = "" if has_category_icons(suite) else f"{self.suite}'s apps take no category icons."
        found += [
            Tile("portal-tour", "Portal video tour", LOGO_ICON, "Record the portal's video tour from this checkout: "
                 "about two minutes, with music, at 1080p or 4K, and the copy on the wiki's Portal Tour page if "
                 "you like", off=off_tours),
            Tile("apps-tour", "Apps video tour", LOGO_ICON, "Record a short video tour of each app you tick, from "
                 "this checkout: about 40 seconds each, with music, at 1080p or 4K", off=off_tours or (
                     "" if (suite / RECORD_APP_TOUR).is_file() else f"{self.suite} has no record-app-tour.sh.")),
            Tile("icons", "Convert icons", LOGO_ICON, "Make a category's icons from new images, and their copies "
                 "in the suite's apps", off=off_icons),
            Tile("issues", "Close issues", LOGO_ICON, "The open issues on GitHub, such as the weekly Upstream "
                 "review: tick the ones that are handled, and Run closes them (gh issue close)"),
        ]
        return found

    def fill(self) -> None:
        self.tiles.clear()
        for tile in self.tile_list():
            item = QListWidgetItem(QIcon(str(tile.icon)) if tile.icon else QIcon(), tile.name)
            item.setData(Qt.ItemDataRole.UserRole, tile)
            item.setToolTip(tile.off or tile.tooltip)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            if tile.off:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.tiles.addItem(item)
        self.fill_local()

    def fill_local(self) -> None:
        """The icons under Test local apps: the suite's portal, its apps and the wikis, from the checkout."""
        self.local_apps.clear()
        if self.suite is None:
            return
        for target in local.targets(self.root, self.suite, self.network_box.isChecked()):
            icon = QIcon(str(target.icon)) if target.icon else QIcon()
            item = QListWidgetItem(board_badge(icon) if target.changes_board else icon, target.label)
            item.setData(Qt.ItemDataRole.UserRole, target)
            item.setToolTip(("\u26a0 Changes how the board runs: it asks first.\n" if target.changes_board else "") +
                            " ".join(("python -m", target.module, *target.args)) + f" in {target.folder}" +
                            (f"\nopens {target.url}" if target.url else ""))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.local_apps.addItem(item)

    # --- a click ----------------------------------------------------------------------------------------------
    def click(self, tile: Tile) -> None:
        if tile.off:
            self.output.appendPlainText(tile.off)
            return
        if tile.app is not None:
            self.run(tile.app)
        elif tile.key == "portal-tour":
            PortalTourDialog(self.suite_dir, self.open_file, self).exec()
        elif tile.key == "apps-tour":
            AppsTourDialog(self.suite_dir, self.open_file, self).exec()
        elif tile.key == "icons":
            IconsDialog(self.root, self.suite, self).exec()
        elif tile.key == "issues":
            dialog = IssuesDialog(self, self.issues_source)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.close_issues(dialog.numbers(), dialog.comment.text())

    def run(self, app: DevApp) -> None:
        """Starts *app* in a window of its own; the suite goes along where the app takes one."""
        args = ("--suite", self.suite) if app.key in ("nrt", "itests") and self.suite else ()
        try:
            self.starter(app, args)
        except OSError as exc:
            self.output.appendPlainText(f"{app.name}: could not start ({exc})")
            return
        self.output.appendPlainText(f"{app.name} {app.version} started from {app.folder} (log: {app.log})")

    # --- Test local apps --------------------------------------------------------------------------------------
    def run_local(self, target: local.Launch) -> None:
        if target.changes_board and QMessageBox.question(
                self, "Local app test",
                f"{target.name} changes how the board runs. Like every app of the suite it is software-only and "
                f"reversible; started from the checkout it uses the scripts in {target.folder}.\n\nStart it?") \
                != QMessageBox.StandardButton.Yes:
            return
        if target.app_id and instance_running(target.app_id):
            QMessageBox.warning(
                self, "Local app test",
                f"{target.name} is already open (the installed one, or one started here).\n\nA second one never "
                "opens: starting it again only brings the open window to the front, so the checkout would not be "
                f"tested. Close {target.name} first, then click its icon again.")
            return
        if target.url and answers(target.url):
            # Already up (started here or before): mkdocs would only fail on the taken port.
            open_url(target.url)
            self.output.appendPlainText(f"{target.label} is already running: opened {target.url}" +
                                        (f"\n{target.note}" if target.note else ""))
            return
        command, env = local.launch_command(self.root, target)
        log = LOCAL_LOG_DIR / target.log_name
        try:
            process = self.start_local(command, env, target.folder, log)
        except OSError as exc:
            self.output.appendPlainText(f"{target.label}: could not start ({exc})")
            return
        self.running.append((target, process, log))
        if target.url:
            self.waiting.append(target.url)
        self.timer.start()
        self.output.appendPlainText(f"{target.label} started from {target.folder} (log: {log})" +
                                    (f"; {target.url} opens once it is up" if target.url else "") +
                                    (f"\n{target.note}" if target.note else ""))

    def poll(self) -> None:
        for entry in list(self.running):
            target, process, log = entry
            code = process.poll()
            if code is None:
                if target.url in self.waiting and answers(target.url):
                    self.waiting.remove(target.url)
                    open_url(target.url)
                continue
            self.running.remove(entry)
            if target.url in self.waiting:
                self.waiting.remove(target.url)
            if code == 0:
                self.output.appendPlainText(f"{target.label} closed.")
            else:
                tail = log_tail(log)
                self.output.appendPlainText(f"{target.label} stopped with exit code {code}" +
                                            (f"; the end of {log}:\n{tail}" if tail else "."))
        if not self.running:
            self.timer.stop()

    # --- Close issues -----------------------------------------------------------------------------------------
    def close_issues(self, numbers: list[int], comment: str) -> None:
        """gh issue close for each ticked issue, one after the other, their output below."""
        if not numbers:
            return
        if self.closer is not None:
            self.output.appendPlainText("Close issues: the issues ticked before are still being closed.")
            return
        gh = gh_program()
        if not gh:
            self.output.appendPlainText("Close issues: gh (the GitHub CLI) is not installed; nothing was closed.")
            return
        self.closing = close_commands(numbers, comment, gh)
        self._close_next()

    def _close_next(self) -> None:
        if not self.closing:
            self.closer = None
            return
        command = self.closing.pop(0)
        self.output.appendPlainText("$ " + " ".join(["gh", *command[1:]]))
        self.closer = QProcess(self)
        self.closer.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.closer.readyReadStandardOutput.connect(self._closer_output)
        self.closer.finished.connect(self._closed)
        self.closer.errorOccurred.connect(       # gh did not start: no finished signal follows
            lambda error: error == QProcess.ProcessError.FailedToStart and self._closed(-1, None))
        self.closer.start(command[0], command[1:])

    def _closer_output(self) -> None:
        if self.closer is not None:
            text = bytes(self.closer.readAllStandardOutput()).decode(errors="replace").rstrip("\n")
            if text:
                self.output.appendPlainText(text)

    def _closed(self, code: int, _status) -> None:
        if self.closer is None:
            return
        self._closer_output()
        closer, self.closer = self.closer, None
        closer.deleteLater()
        if code != 0:
            self.output.appendPlainText(f"gh stopped with exit code {code}; the issues after it stay open.")
            self.closing = []
            return
        self._close_next()

    def closeEvent(self, event) -> None:
        if self.closer is not None:                     # a close under way: finished, not cut off
            self.closer.waitForFinished(10000)
        super().closeEvent(event)
