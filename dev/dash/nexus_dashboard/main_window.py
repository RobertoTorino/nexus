# SPDX-License-Identifier: GPL-3.0-or-later
"""The dashboard's window: the suite chosen in the header, the tiles (the Nexus apps of the checkout, then the
suite's tours and icons), and what happened below. A click on an app's tile starts it with its run script, in its
own session, and says where its log is; a click on a tool's tile opens its dialog on the chosen suite. A tile is
greyed out where it does not run here: Nexus Demo Recorder on Windows, a suite's tours where its scripts need the
other system, the icons for a suite whose apps take no category icons."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (QComboBox, QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow, QVBoxLayout,
                             QWidget)

from bc250_core.widgets import AppHeader, InfoButton, Terminal, hint_label

from . import APP_NAME, CHECKOUT, LOGO_PATH, __version__
from .checkout import DevApp, dev_apps, here, start, suite_name, suites
from .icons import IconsDialog, has_category_icons
from .tours import RECORD_APP_TOUR, RECORD_TOUR, AppsTourDialog, PortalTourDialog

SUITE_KEY = "suite"                     # the chosen suite, in the settings
ICON_PX = 64
ABOUT = ("One door to the tools for working on the suites. The first tiles are the Nexus apps of this checkout, "
         "each a window of its own that keeps running when the dashboard closes: Nexus Release Tool (a release's "
         "versions, CHANGELOG entries, pins and the board checks), Nexus Installer Tests (a suite's installer tests "
         "one at a time) and Nexus Demo Recorder (a portal installation recorded with OBS, Linux).\n\n"
         "The other tiles work on the suite chosen in the header: Portal video tour and Apps video tour record the "
         "suite's tours from this checkout (its tools/record-tour.sh and record-app-tour.sh), Convert icons makes "
         "a category's icons from your images (tools/sync_icons.py). A tile is greyed out where it does not run on "
         "this system or for this suite.")
LOGO_ICON = LOGO_PATH


class Tile:
    """One tile: an app of dev/ or a tool of the suite, with why it is greyed out when it is."""

    def __init__(self, key: str, name: str, icon: Path | None, tooltip: str, app: DevApp | None = None,
                 off: str = ""):
        self.key, self.name, self.icon, self.tooltip, self.app, self.off = key, name, icon, tooltip, app, off


class MainWindow(QMainWindow):
    def __init__(self, root: Path = CHECKOUT, settings: QSettings | None = None, suite: str | None = None,
                 starter=start, open_file=None):
        """*settings* keeps the chosen suite (None: this session only); *suite* opens that suite (a folder name);
        *starter* starts a dev app (checkout.start); *open_file* opens a video (the system's player)."""
        super().__init__()
        self.root = root
        self.settings = settings
        self.starter = starter
        self.open_file = open_file or (lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        self.setWindowTitle(APP_NAME)
        self.resize(760, 560)
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
        layout.addWidget(self.tiles, 2)
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

    def run(self, app: DevApp) -> None:
        """Starts *app* in a window of its own; the suite goes along where the app takes one."""
        args = ("--suite", self.suite) if app.key in ("nrt", "itests") and self.suite else ()
        try:
            self.starter(app, args)
        except OSError as exc:
            self.output.appendPlainText(f"{app.name}: could not start ({exc})")
            return
        self.output.appendPlainText(f"{app.name} {app.version} started from {app.folder} (log: {app.log})")
