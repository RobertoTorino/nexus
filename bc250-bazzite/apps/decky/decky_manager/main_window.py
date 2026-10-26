# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window: Decky Loader itself, its service, Steam's switch for it and the /home/deck link as rows with their
state and buttons, then the plugins Decky has. The download and the release check run off the GUI thread; the steps
that need root go through pkexec (privileged.py, loader.py). The look is the gaming apps' blue (style.py)."""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from bc250_core import SUITE_MANUAL_URL, steam, window_title
from bc250_core import __version__ as CORE_VERSION
from bc250_core.platform import xdg_open
from bc250_core.settings import SettingsStore
from bc250_core.updates import ReleaseInfo, UpdateChecker, latest_release, version_tuple
from bc250_core.widgets import AppHeader, MetricBox, StatusText, TextDialog, Terminal, hint_label

from . import APP_ID, APP_NAME, INFO, LOGO_PATH, __version__, loader, privileged, state, style

MANUAL_URL = f"{SUITE_MANUAL_URL}apps/decky/"
GAME_MODE_TIP = "In Game Mode there is no password dialog: do this in Desktop Mode"
AFTER_STEAM = ("Decky appears in the Quick Access menu of Game Mode and Big Picture Mode (the … button, or Ctrl + 2) "
               "once Steam starts again.")

Root = Callable[[list[str]], privileged.Result]
Latest = Callable[[], ReleaseInfo]


def _latest() -> ReleaseInfo:
    return latest_release(loader.REPO, user_agent=f"{APP_ID}/{__version__}")


class DeckySettings(SettingsStore):
    DEFAULTS: dict = {}


class MainWindow(QMainWindow):
    def __init__(self, paths: loader.Paths | None = None, steam_dirs: list[Path] | None = None,
                 run: state.Command = state.command, root: Root = privileged.run,
                 fetch: state.Download = state.download, latest: Latest = _latest,
                 download_dir: Path | None = None):
        """*paths*: Decky's files (your home's, /etc's); *steam_dirs*: the Steam folders for Steam's switch (None:
        looked up); *run*: the commands that read the service; *root*: the root part through pkexec; *fetch*: the
        download; *latest*: the release check (tests never touch the real ones)."""
        super().__init__()
        self.resize(940, 720)
        self.paths = paths or loader.Paths(Path.home())
        self.steam_dirs = steam_dirs if steam_dirs is not None else state.steam_folders()
        self.run = run
        self.root = root
        self.fetch = fetch
        self.latest = latest
        self.download_dir = download_dir or state.download_folder()
        self.settings = DeckySettings(INFO, self)
        self.worker = UpdateChecker(self)           # the download, off the GUI thread
        self.worker.finished.connect(self._downloaded)
        self.checker = UpdateChecker(self)          # the check for a newer Decky release
        self.checker.finished.connect(self._checked)
        self.release = ReleaseInfo()
        self.version = ""
        self.service = state.Service(False, "unknown", "unknown")
        self.plugins: list[state.Plugin] = []

        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.pill = StatusText()
        header.add_state(self.pill)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Read the state again")
        self.refresh_button.clicked.connect(self.refresh)
        header.add_action(self.refresh_button)
        self.decky_box = MetricBox("Decky Loader", style.BLUE)
        self.service_box = MetricBox("Service", style.BLUE)
        self.steam_box = MetricBox("Steam switch", style.BLUE)
        self.plugins_box = MetricBox("Plugins", style.BLUE)
        for box in (self.decky_box, self.service_box, self.steam_box, self.plugins_box):
            header.add_second(box)
        intro = hint_label(
            "Decky Loader adds plugins to Steam's Game Mode and Big Picture Mode: its menu is in the Quick Access menu "
            "(the … button, or Ctrl + 2). "
            "The app installs the Decky release it was tried with, runs it as a system service and shows its "
            "plugins; you install and set up plugins in Game Mode. "
            + style.link(self, MANUAL_URL, "Manual"))
        intro.setOpenExternalLinks(True)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.decky_state, self.service_state, self.steam_state, self.deck_state = (self._state_label()
                                                                                  for _ in range(4))
        self.install_button = style.primary_button("Install", f"Download Decky Loader {loader.VERSION} from GitHub "
                                                       f"(about {loader.SIZE_MB} MB), check it and start it")
        self.install_button.clicked.connect(self.on_install)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Stop Decky Loader and remove it; its plugins stay unless you choose otherwise")
        self.remove_button.clicked.connect(self.on_remove)
        self.restart_button = QPushButton("Restart")
        self.restart_button.setToolTip("Restart Decky's service, as Decky's own Reload does")
        self.restart_button.clicked.connect(self.on_restart)
        self.log_button = QPushButton("Log")
        self.log_button.setToolTip("Decky's log from the system journal")
        self.log_button.clicked.connect(self.on_log)
        self.steam_button = QPushButton("Switch on")
        self.steam_button.clicked.connect(self.on_steam_switch)
        self.deck_button = QPushButton("Link")
        self.deck_button.clicked.connect(self.on_deck_link)
        rows = [("Decky Loader", self.decky_state, [self.install_button, self.remove_button]),
                ("Service", self.service_state, [self.restart_button, self.log_button]),
                ("Steam", self.steam_state, [self.steam_button]),
                ("/home/deck", self.deck_state, [self.deck_button])]
        centre = Qt.AlignmentFlag.AlignVCenter
        for row, (name, text, buttons) in enumerate(rows):
            label = QLabel(name)
            label.setStyleSheet("font-weight:700;")
            for widget in (label, text):
                widget.setAlignment(Qt.AlignmentFlag.AlignLeft | centre)
            grid.addWidget(label, row, 0)
            grid.addWidget(text, row, 1)
            for column, button in zip((3, 2), reversed(buttons)):
                grid.addWidget(button, row, column, centre)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Plugin", "Version", "Author", "State", "Folder"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(column, mode)
        self.plugins_hint = hint_label("Plugins are installed, switched off and removed in Game Mode, in Decky's "
                                       "store and settings. The list shows what is in the plugins folder.")
        self.folder_button = QPushButton("Open plugins folder")
        self.folder_button.clicked.connect(self.open_plugins_folder)
        plugin_row = QHBoxLayout()
        plugin_row.addWidget(self.plugins_hint, 1)
        plugin_row.addWidget(self.folder_button)

        self.running = QLabel()
        self.running.setStyleSheet("font-weight:600;")
        self.running.setWordWrap(True)
        self.output = Terminal()
        self.output.setPlaceholderText("Messages appear here.")
        self.output.setMaximumHeight(110)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(intro)
        lay.addSpacing(6)
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(self.table, 1)
        lay.addLayout(plugin_row)
        lay.addWidget(self.running)
        lay.addWidget(self.output)
        version = QLabel(f"{APP_NAME} {__version__} · core {CORE_VERSION} · Decky Loader {loader.VERSION}")
        version.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(version, 0, Qt.AlignmentFlag.AlignRight)
        self.setCentralWidget(central)
        style.apply(self)
        # The row buttons the size of the widest, in two columns on the right, as in shadPS4 Manager. Sized
        # here, in the window, so their size includes the style sheet's padding.
        buttons = [b for _, _, row_buttons in rows for b in row_buttons]
        for button in buttons:
            button.ensurePolished()
        width = max(b.sizeHint().width() for b in buttons)
        height = max(b.sizeHint().height() for b in buttons)
        for button in buttons:
            button.setFixedSize(width, height)

        geometry = self.settings.window_state("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh()
        self.checker.start(self.latest)

    @staticmethod
    def _state_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        return label

    # --- State ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        self.version = state.installed_version(self.paths)
        self.service = state.service(self.paths, self.run)
        self.plugins = state.plugins(self.paths)
        self.cef = state.cef_enabled(self.steam_dirs)
        self.deck = loader.deck_state(self.paths.home, self.paths.deck)
        self._show_state()
        self._fill_table()
        self._update_buttons()

    def _decky_text(self) -> str:
        pinned = loader.VERSION
        notes = f"<a href='{loader.RELEASE_PAGE}'>Release notes</a>"
        if not self.version:
            text = (f"Not installed. Install downloads Decky Loader {pinned}, the release this version of the app was "
                    "tried with, checks it and starts it as a system service.")
        elif self.version == "unknown":
            text = (f"Installed, of an unknown version (no version file). Install puts {pinned} in its place, "
                    "with your plugins kept.")
        elif self.version == pinned:
            text = f"Decky Loader {pinned} is installed. {notes}"
        elif version_tuple(self.version) > version_tuple(pinned):
            text = (f"Decky Loader {escape(self.version)} is installed: Decky updated itself, past the {pinned} "
                    "this version of the app was tried with. It stays as it is.")
        else:
            text = (f"Decky Loader {escape(self.version)} is installed; this version of the app brings {pinned}: "
                    "<b>install it</b> to use it.")
        latest = self.release.version
        newest = max(filter(None, [self.version if self.version != "unknown" else "", pinned]), key=version_tuple)
        if latest and version_tuple(latest) > version_tuple(newest):
            text += (f"<br>Decky Loader {escape(latest)} is out ({escape(self.release.published)}); a version of "
                     "the app that was tried with it will bring it.")
        return text

    def _show_state(self) -> None:
        self.decky_state.setText(self._decky_text())
        self.decky_box.set_value(self.version or "—")

        s = self.service
        if not s.unit:
            self.service_state.setText("No service: Decky starts once it is installed.")
            self.service_box.set_value("—")
        else:
            boot = "starts at boot" if s.at_boot else f"<b>does not start at boot</b> ({escape(s.enabled)})"
            if s.running:
                self.service_state.setText(f"Running as root; {boot}.")
            elif s.active == "activating":
                self.service_state.setText(f"Starting; {boot}.")
            else:
                self.service_state.setText(f"<b>Not running</b> ({escape(s.active)}); {boot}. Restart starts it; "
                                           "Log shows why it stopped.")
            self.service_box.set_value("Running" if s.running else s.active.capitalize())

        if not self.steam_dirs:
            self.steam_state.setText("Steam was never started here: start it once, then press Refresh.")
            self.steam_box.set_value("—")
        elif self.cef:
            self.steam_state.setText("Steam lets Decky in (its remote debugging is on). " + AFTER_STEAM)
            self.steam_box.set_value("On")
        else:
            self.steam_state.setText("Steam does not let Decky in: its remote debugging is off. Install switches it "
                                     "on; so does Switch on.")
            self.steam_box.set_value("Off")

        home = escape(str(self.paths.home))
        deck = escape(str(self.paths.deck))
        self.deck_state.setText({
            "own": f"Your home is {deck}: plugins written for the Steam Deck find it as they are.",
            "linked": f"{deck} points to your home ({home}), for plugins written for the Steam Deck.",
            "missing": (f"Not there. Some plugins written for the Steam Deck look in {deck} only; Link points it to "
                        f"your home ({home}), as Bazzite's ujust setup-decky does."),
            "elsewhere": f"{deck} is a link to another folder; the app leaves it as it is.",
            "taken": f"{deck} is a folder of its own (another user's home); the app leaves it as it is.",
        }[self.deck])

        on = sum(not p.disabled for p in self.plugins)
        self.plugins_box.set_value(str(len(self.plugins)), f"{on} switched on" if self.plugins else "")

        if not self.version:
            self.pill.set_status("Not installed", "warn", "Install Decky Loader first.")
        elif not s.unit:
            self.pill.set_status("No service", "bad", "Decky is there without its service: Install sets it up.")
        elif not s.running:
            self.pill.set_status("Not running", "bad", "Decky's service does not run: see Log.")
        elif self.steam_dirs and not self.cef:
            self.pill.set_status("Steam switch off", "warn", "Switch Steam's remote debugging on for Decky.")
        else:
            self.pill.set_status("Ready", "ok", "Decky Loader runs. " + AFTER_STEAM)

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.plugins))
        for row, plugin in enumerate(self.plugins):
            texts = (plugin.name, plugin.version, plugin.author, "Off" if plugin.disabled else "On",
                     str(plugin.folder))
            for column, text in enumerate(texts):
                self.table.setItem(row, column, QTableWidgetItem(text))

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        game_mode = steam.game_mode()
        installed = bool(self.version)
        current = self.version == loader.VERSION and self.service.unit and self.service.at_boot
        root = idle and not game_mode
        self.refresh_button.setEnabled(idle)
        self.install_button.setEnabled(root and not current)
        self.install_button.setText("Update" if installed and self.version != "unknown"
                                    and version_tuple(self.version) < version_tuple(loader.VERSION) else "Install")
        self.remove_button.setEnabled(root and (installed or self.service.unit))
        self.restart_button.setEnabled(root and self.service.unit)
        self.log_button.setEnabled(self.service.unit)
        self.steam_button.setText("Switch off" if self.cef else "Switch on")
        self.steam_button.setEnabled(idle and bool(self.steam_dirs))
        self.steam_button.setToolTip("Decky does not load while it is off" if self.cef else
                                     "Let Decky into Steam: Steam's remote debugging, from its next start")
        self.deck_button.setText("Unlink" if self.deck == "linked" else "Link")
        self.deck_button.setEnabled(root and self.deck in ("linked", "missing"))
        self.deck_button.setToolTip(f"{self.paths.deck} as a link to your home folder (needs your password)")
        self.folder_button.setEnabled(self.paths.plugins.is_dir())
        for button in (self.install_button, self.remove_button, self.restart_button, self.deck_button):
            if game_mode:
                button.setToolTip(GAME_MODE_TIP)

    # --- Actions ----------------------------------------------------------------------------------------------

    def _ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, window_title(title), text)
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_remove(self) -> tuple[bool, bool]:
        """(remove, also the plugins and their settings)."""
        box = QMessageBox(QMessageBox.Icon.Question, window_title("Remove"),
                          "Stop Decky Loader and remove it?\n\nSteam's switch for it goes off too"
                          + (f", and {self.paths.deck} is no longer linked." if self.deck == "linked" else "."),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        wipe = QCheckBox(f"Also remove the plugins and their settings ({self.paths.homebrew})")
        box.setCheckBox(wipe)
        return box.exec() == QMessageBox.StandardButton.Yes, wipe.isChecked()

    def _report(self, ok: bool, message: str) -> None:
        self.running.setText(message)
        self.running.setStyleSheet("font-weight:600;" if ok else "font-weight:600;color:#c62828;")
        self.output.appendPlainText(message)

    def _root(self, args: list[str], then: str = "") -> bool:
        """A step as root; *then* is added to the message when it worked."""
        result = self.root(args)
        self._report(result.ok, f"{result.message} {then}".strip() if result.ok else result.message)
        self.refresh()
        return result.ok

    def on_install(self) -> None:
        if not self._ask("Install", f"Download Decky Loader {loader.VERSION} from GitHub (about {loader.SIZE_MB} MB) "
                                    "and start it?\n\nIt is checked against the SHA-256 this app was tried with, "
                                    f"goes in {self.paths.services} and runs as root from a system service. Your "
                                    "password is asked for that."):
            return
        folder, fetch = self.download_dir, self.fetch

        def job() -> tuple[bool, str, Path | None]:
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / loader.ASSET
            try:
                fetch(loader.URL, dest, None)
                if loader.sha256(dest.read_bytes()) != loader.SHA256:
                    dest.unlink(missing_ok=True)
                    return False, (f"The download is not Decky Loader {loader.VERSION} as this app was tried with "
                                   "(its SHA-256 differs); nothing was installed."), None
            except OSError as error:            # urllib's errors included
                dest.unlink(missing_ok=True)
                reason = str(getattr(error, "reason", error))
                return False, f"The download failed: {reason}.", None
            return True, "", dest
        if self.worker.start(job):
            self.running.setText(f"Downloading Decky Loader {loader.VERSION}…")
            self.running.setStyleSheet("font-weight:600;")
            self._update_buttons()

    def _downloaded(self, result: tuple[bool, str, Path | None]) -> None:
        ok, message, path = result
        if not ok or path is None:
            self._report(False, message)
            self._update_buttons()
            return
        try:
            state.enable_cef(self.steam_dirs)
            self._root(["install", str(path)], AFTER_STEAM)
        except OSError as error:
            self._report(False, f"Steam's switch for Decky was not changed: {error}")
        finally:
            path.unlink(missing_ok=True)

    def on_remove(self) -> None:
        proceed, wipe = self._confirm_remove()
        if not proceed:
            return
        args = ["remove"] + (["--wipe"] if wipe else []) + (["--unlink"] if self.deck == "linked" else [])
        if self._root(args):
            state.disable_cef(self.steam_dirs)
            self.refresh()

    def on_restart(self) -> None:
        self._root(["restart"])

    def on_log(self) -> None:
        TextDialog("Decky Loader log", state.journal(self.run) or "The journal has no lines from Decky.", self).exec()

    def on_steam_switch(self) -> None:
        try:
            if self.cef:
                state.disable_cef(self.steam_dirs)
                self._report(True, "Steam's remote debugging is off from Steam's next start: Decky no longer loads.")
            else:
                state.enable_cef(self.steam_dirs)
                self._report(True, "Steam's remote debugging is on from Steam's next start. " + AFTER_STEAM)
        except OSError as error:
            self._report(False, f"Steam's switch was not changed: {error}")
        self.refresh()

    def on_deck_link(self) -> None:
        if self.deck == "linked":
            if self._ask("/home/deck", f"Remove the link {self.paths.deck}? Plugins that look there no longer find "
                                       "their files."):
                self._root(["unlink"])
        elif self._ask("/home/deck", f"Point {self.paths.deck} to your home ({self.paths.home})?\n\nFor plugins "
                                     "written for the Steam Deck that look there only. Your password is asked."):
            self._root(["link"])

    def open_plugins_folder(self) -> None:
        if not xdg_open(self.paths.plugins):
            self.output.appendPlainText(f"The plugins are in {self.paths.plugins}")

    def _checked(self, release: ReleaseInfo) -> None:
        self.release = release
        self._show_state()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if self.worker.running and not self._ask("Close", "The download is still running. Close anyway?"):
            event.ignore()
            return
        self.worker.stop()
        self.checker.stop()
        self.settings.set_window_state("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)
