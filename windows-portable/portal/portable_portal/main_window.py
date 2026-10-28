# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the categories as tabs (LB, RB), the tab's apps as two rows of four tiles, the strip under them with
the focused app and its pills (A Install or Open, Y Update), X for the app's details (and Remove there), Start or
View for the Suite page (the portal's own update), B to close. An install downloads the app's release in the
background, checks it and runs its install.ps1 in a PowerShell window; the portal waits for that window's exit
status. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

import datetime
import shlex
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGridLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import expand, launch_in_terminal
from bc250_core.portable import AMBER, DIM, Card, Legend, PortableHeader, PortableWindow, px

from . import APP_ICONS, APP_ID, APP_NAME, __version__
from .manifest import CATEGORIES, AppEntry
from .portal_update import PortalUpdate, short
from .sources import Records, SourceError, Sources, fetch_release, is_installed
from .widgets import AppPane, DetailsPane, SuitePane, Tabs

STATUS_MS = 30_000              # the header's battery and time
POLL_MS = 1000                  # how often the portal looks for the installer window's exit status
CONFIRM_MS = 5000               # Remove asks for a second press within this
TILE_W, TILE_H, GAP = 293, 176, 14      # the mock-up's tiles: two rows of four
COLUMNS, PER_PAGE = 4, 8
TAB_KEY = "window/tab"          # the settings: the tab shown last
MENU = "☰"                  # the Menu button as the Ally shows it (SDL's start; owner, 28-10-2026: not "Menu")
APPS_LEGEND = (("X", "Details"), (MENU, "Suite"), ("B", "Close"))


@dataclass
class Pending:
    entry: AppEntry
    action: str                 # "install" | "uninstall"
    exit_file: Path
    tag: str


def ps_quote(text: str | PurePath) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def ps_line(folder: PurePath, commands: Sequence[str]) -> str:
    """Into the extracted release and its commands in order, stopping at the first that fails (a command's own
    exit status is not an error to PowerShell, so each is checked)."""
    steps = [f"Set-Location -LiteralPath {ps_quote(folder)}"]
    for command in commands:
        steps += [command, 'if ($LASTEXITCODE -ne 0) { throw "ended with exit status $LASTEXITCODE" }']
    return "; ".join(steps)


def launch_argv(command: str) -> list[str]:
    """A manifest's launch command as argv: the program (with %VARIABLES%) and its arguments, Windows quoting."""
    parts = shlex.split(command, posix=False)
    argv = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]
    argv[0] = str(expand(argv[0]))
    return argv


def start_app(argv: list[str]) -> None:
    """The app, detached from the portal: closing the portal leaves it running."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(argv, cwd=Path(argv[0]).parent, creationflags=flags, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def restart_line(folder: PurePath, exe: str) -> str:
    """The portal's own update, run after this portal has ended (its program folder is replaced): the release's
    install.ps1, then the new portal."""
    steps = [f"Wait-Process -Id {subprocess.os.getpid()} -ErrorAction SilentlyContinue",
             f"Set-Location -LiteralPath {ps_quote(folder)}",
             "powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1",
             'if ($LASTEXITCODE -ne 0) { throw "install.ps1 ended with exit status $LASTEXITCODE" }']
    if exe:
        steps.append(f"Start-Process -FilePath {ps_quote(exe)}")
    return "; ".join(steps)


class _Worker(QObject):
    """One job at a time off the window's thread; its result (or the error) arrives on the window's."""

    done = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.busy = False

    def run(self, job: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return True

    def _run(self, job: Callable[[], object]) -> None:
        try:
            result = job()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            result = error
        self.busy = False
        self.done.emit(result)


class MainWindow(PortableWindow):
    def __init__(self, entries: list[AppEntry], sources: Sources, records: Records,
                 portal_check: Callable[[], PortalUpdate] | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 launch: Callable[[list[str]], None] = start_app,
                 terminal: Callable[..., None] = launch_in_terminal, icons: Path = APP_ICONS,
                 exe: str = "", exit_dir: Path | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.entries, self.sources, self.records = entries, sources, records
        self.portal_check, self.battery, self.launch, self.terminal = portal_check, battery, launch, terminal
        self.exe = exe                                  # the installed portal's program, for a restart; "" from a checkout
        self.exit_dir = exit_dir or Path(tempfile.gettempdir())
        self.settings = QSettings()
        self.by_key = {entry.key: entry for entry in entries}
        self.current_key = ""
        self.job: tuple[AppEntry, str] | None = None    # being downloaded
        self.pending: Pending | None = None             # installing in its PowerShell window
        self.update: PortalUpdate | None = None
        self.checking = False
        self.confirm_key = ""                           # Remove pressed once on this app
        self.message = ""                               # the last outcome, under the focused app
        self.message_key = ""

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(10))
        self.tabs = Tabs([(key, name) for key, name in CATEGORIES.items()
                          if any(entry.category == key for entry in entries)])
        page.addWidget(self.tabs)
        page.addSpacing(px(10))
        self.stack = QStackedWidget()
        self.apps_page = QWidget()
        apps = QVBoxLayout(self.apps_page)
        apps.setContentsMargins(0, 0, 0, 0)
        apps.setSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(GAP))
        self.grid.setVerticalSpacing(px(GAP))
        self.grid.setColumnStretch(COLUMNS, 1)
        for row in range(PER_PAGE // COLUMNS):          # two rows of tiles, also when a tab fills one
            self.grid.setRowMinimumHeight(row, px(TILE_H))
        apps.addLayout(self.grid)
        apps.addStretch()
        self.app_pane = AppPane()
        apps.addWidget(self.app_pane)
        self.details_pane = DetailsPane()
        self.suite_pane = SuitePane()
        for widget in (self.apps_page, self.details_pane, self.suite_pane):
            self.stack.addWidget(widget)
        page.addWidget(self.stack, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)

        self.tiles: dict[str, Card] = {}
        for entry in entries:
            tile = Card(entry.short or short(entry.name), "", icon=QPixmap(str(icons / f"{entry.key}.webp")))
            tile.setFixedSize(px(TILE_W), px(TILE_H))
            tile.hide()
            tile.focused.connect(lambda key=entry.key: self.show_app(key))
            tile.activated.connect(lambda key=entry.key: self.main_action(key))
            self.tiles[entry.key] = tile
        self.app_pane.main.activated.connect(lambda: self.main_action(self.current_key))
        self.app_pane.other.activated.connect(lambda: self.update_action(self.current_key))
        self.details_pane.open.activated.connect(lambda: self.open_app(self.current_key))
        self.details_pane.remove.activated.connect(lambda: self.remove_action(self.current_key))
        self.suite_pane.action.activated.connect(self.suite_action)
        self.tabs.changed.connect(self.show_tab)
        self.bind("x", self.show_details)
        self.bind("y", self.y_action)
        self.bind("previous", lambda: self.tabs.step(-1))
        self.bind("next", lambda: self.tabs.step(1))
        self.bind("menu", self.show_suite)
        self.bind("view", self.show_suite)
        self.back.connect(self.on_back)

        self.worker = _Worker()
        self.worker.done.connect(self._worker_done)
        self._on_done: Callable[[object], None] | None = None
        self.poll = QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self._check_pending)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the last tab, and the portal's own update
        checked once in the background."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        last = str(self.settings.value(TAB_KEY, ""))
        if last in self.tabs.keys and last != self.tabs.current:
            self.tabs.select(last)
        else:
            self.show_tab(self.tabs.current)
        self.check_portal()

    # The pages

    def update_status(self) -> None:
        parts = [power.text(self.battery()), datetime.datetime.now().strftime("%H:%M")]
        if self.update_available():
            parts.append(f"Suite {self.update.release.version} available")
        self.header.set_status(parts)

    def tab_entries(self, category: str) -> list[AppEntry]:
        return [entry for entry in self.entries if entry.category == category][:PER_PAGE]

    def show_tab(self, category: str) -> None:
        for tile in self.tiles.values():
            self.grid.removeWidget(tile)
            tile.hide()
        shown = self.tab_entries(category)
        for i, entry in enumerate(shown):
            tile = self.tiles[entry.key]
            self.grid.addWidget(tile, i // COLUMNS, i % COLUMNS, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            tile.show()
        self.settings.setValue(TAB_KEY, category)
        self.stack.setCurrentWidget(self.apps_page)
        self.refresh()
        if shown:
            self.tiles[shown[0].key].setFocus()
            self.show_app(shown[0].key)
        self.legend.set_items(APPS_LEGEND)

    def show_app(self, key: str) -> None:
        if key not in self.by_key:
            return
        self.current_key = key
        self.refresh()

    def show_details(self) -> None:
        if self.stack.currentWidget() is not self.apps_page or self.current_key not in self.by_key:
            return
        self.stack.setCurrentWidget(self.details_pane)
        self.legend.set_items([("B", "Back")])
        self.refresh()
        focus = self.details_pane.open if self.details_pane.open.isVisible() else self.details_pane.remove
        focus.setFocus()

    def show_suite(self) -> None:
        if self.stack.currentWidget() is self.suite_pane:
            return
        self.stack.setCurrentWidget(self.suite_pane)
        self.legend.set_items([("B", "Back")])
        self.refresh()
        self.suite_pane.action.setFocus()

    def on_back(self) -> None:
        if self.stack.currentWidget() is self.apps_page:
            self.close()
            return
        self.stack.setCurrentWidget(self.apps_page)
        self.legend.set_items(APPS_LEGEND)
        self._confirm_over()
        if self.current_key in self.tiles and self.tiles[self.current_key].isVisible():
            self.tiles[self.current_key].setFocus()
        self.refresh()

    # What each app's tile and pane say

    def busy_text(self, key: str) -> str:
        if self.job is not None and self.job[0].key == key:
            return "Downloading…" if self.job[1] == "install" else "Preparing…"
        if self.pending is not None and self.pending.entry.key == key:
            return "Installing…" if self.pending.action == "install" else "Removing…"
        return ""

    def state(self, entry: AppEntry) -> tuple[str, str, str, str]:
        """The tile's status (and its color), the main pill's text (A) and the other's (Y), by what is installed and
        what the portal recorded."""
        busy = self.busy_text(entry.key)
        if busy:
            return busy, AMBER, "", ""
        installed = is_installed(entry)
        record = self.records.get(entry.key)
        if entry.withdrawn:
            return ("Withdrawn" if installed else "Not available"), DIM, "", ""
        if not installed:
            return "Not installed", DIM, "Install", ""
        if record == entry.tag:
            return f"Installed {entry.version}", DIM, "Open", ""
        if record:
            return f"Update {entry.version}", AMBER, "Open", "Update"
        return "Installed, version unknown", AMBER, "Open", "Reinstall"

    def refresh(self) -> None:
        busy = self.job is not None or self.pending is not None
        for entry in self.entries:
            status, color, _, _ = self.state(entry)
            self.tiles[entry.key].set_text(status, color)
        entry = self.by_key.get(self.current_key)
        if entry is None:
            self.app_pane.fill("", "", "", "", "", "")
        else:
            status, _, main, other = self.state(entry)
            record = self.records.get(entry.key)
            installed = f"Installed {record.rsplit('-v', 1)[1]}" if record else \
                ("Installed, version unknown" if is_installed(entry) else "Not installed")
            message = self.message if self.message_key == entry.key else ""
            self.app_pane.fill(entry.name, f"{installed}; this portal has {entry.version}", entry.summary,
                               message or (status if status.endswith("…") else ""), "" if busy else main,
                               "" if busy else other)
            can_remove = is_installed(entry) and not busy
            self.details_pane.fill(entry.name, entry.summary, self.detail_rows(entry), message, main == "Open",
                                   can_remove, "Press again to remove" if self.confirm_key == entry.key else "Remove")
        self.fill_suite()
        self.update_status()

    def detail_rows(self, entry: AppEntry) -> list[tuple[str, str]]:
        record = self.records.get(entry.key)
        installed = ("not installed" if not is_installed(entry) else f"{record.rsplit('-v', 1)[1]} ({record})"
                     if record else "installed, version unknown: Reinstall records it")
        rows = [("Installed", installed), ("This portal pins", entry.tag),
                ("Category", CATEGORIES.get(entry.category, entry.category)),
                ("Program", str(expand(entry.detect[0])) if entry.detect else "")]
        if entry.withdrawn:
            rows.append(("Withdrawn", entry.withdrawn))
        return rows

    # A, Y and the details

    def main_action(self, key: str) -> None:
        entry = self.by_key.get(key)
        if entry is None or self.stack.currentWidget() is not self.apps_page:
            return
        _, _, main, _ = self.state(entry)
        if main == "Install":
            self._start(entry, "install")
        elif main == "Open":
            self.open_app(key)

    def update_action(self, key: str) -> None:
        entry = self.by_key.get(key)
        if entry is not None and self.state(entry)[3]:
            self._start(entry, "install")

    def y_action(self) -> None:
        if self.stack.currentWidget() is self.details_pane:
            self.remove_action(self.current_key)
        elif self.stack.currentWidget() is self.apps_page:
            self.update_action(self.current_key)

    def remove_action(self, key: str) -> None:
        """Remove asks for a second press (no dialog on a handheld): the pill says so for a few seconds."""
        entry = self.by_key.get(key)
        if entry is None or not is_installed(entry) or self.job is not None or self.pending is not None:
            return
        if self.confirm_key != key:
            self.confirm_key = key
            self.confirm_timer.start()
            self.refresh()
            return
        self._confirm_over()
        self._start(entry, "uninstall")

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.confirm_key:
            self.confirm_key = ""
            self.refresh()

    def open_app(self, key: str) -> None:
        entry = self.by_key.get(key)
        if entry is None or not entry.launch or not is_installed(entry):
            return
        label, command = entry.launch[0]
        try:
            self.launch(launch_argv(command))
        except OSError as exc:
            self.say(key, f"{entry.name} could not be started: {exc}")
            self.log.error(f"{entry.name} could not be started: {exc}")
            return
        self.log.info(f"Opened {entry.name} ({label}).")

    def say(self, key: str, text: str) -> None:
        self.message, self.message_key = text, key
        self.refresh()

    # Installing and removing: the release in the background, then its installer in a PowerShell window

    def _start(self, entry: AppEntry, action: str) -> None:
        if self.job is not None or self.pending is not None:
            return
        self.job = (entry, action)
        self.message = ""
        self.refresh()
        self._run(lambda: self.sources.prepare(entry), self._prepared)

    def _run(self, job: Callable[[], object], then: Callable[[object], None]) -> None:
        self._on_done = then
        self.worker.run(job)

    def _worker_done(self, result: object) -> None:
        then, self._on_done = self._on_done, None
        if then is not None:
            then(result)

    def _prepared(self, result: object) -> None:
        entry, action = self.job or (None, "")
        self.job = None
        if entry is None:
            return
        if isinstance(result, Exception):
            self.say(entry.key, f"{entry.name} could not be prepared: {result}")
            self.log.error(f"{entry.name} could not be prepared: {result}")
            return
        folder = Path(result)
        commands = entry.install if action == "install" else entry.uninstall
        exit_file = self.exit_dir / f"{APP_ID}-{entry.key}-{uuid.uuid4().hex}.exit"
        try:
            self.terminal(ps_line(folder, commands), exit_file=exit_file, keep_open="on_error")
        except (RuntimeError, OSError) as exc:
            self.say(entry.key, f"The installer could not be started: {exc}")
            self.log.error(f"The installer of {entry.name} could not be started: {exc}")
            return
        self.pending = Pending(entry, action, exit_file, entry.tag)
        self.log.info(f"{action.capitalize()} of {entry.name} started from {folder}.")
        self.poll.start()
        self.refresh()

    def _check_pending(self) -> None:
        pending = self.pending
        if pending is None:
            self.poll.stop()
            return
        try:
            status = pending.exit_file.read_text(encoding="utf-8").strip()
        except OSError:
            return                                      # still running
        self.poll.stop()
        self.pending = None
        pending.exit_file.unlink(missing_ok=True)
        entry = pending.entry
        ok = status == "0"
        if ok and pending.action == "install":
            self.records.set(entry.key, pending.tag)
            self.sources.prune(entry)                   # an update: the previous release's folder goes
            self.say(entry.key, f"{entry.name} {entry.version} is installed.")
        elif ok:
            self.records.remove(entry.key)
            self.sources.forget(entry)
            self.say(entry.key, f"{entry.name} is removed.")
        else:
            self.say(entry.key, f"The {pending.action} of {entry.name} ended with exit status {status or '?'}: "
                                "its window shows what happened.")
        self.log.info(f"{pending.action.capitalize()} of {entry.name}: exit status {status or '?'}.")
        if self.stack.currentWidget() is self.details_pane and not is_installed(entry):
            self.on_back()

    # The portal's own update (the Suite page)

    def update_available(self) -> bool:
        release = self.update.release if self.update is not None else None
        return bool(release and release.tag and not release.error
                    and power_version(release.version) > power_version(__version__))

    def check_portal(self) -> None:
        if self.portal_check is None or self.checking or self.worker.busy:
            return
        self.checking = True
        self.fill_suite()
        self._run(self.portal_check, self._portal_checked)

    def _portal_checked(self, result: object) -> None:
        self.checking = False
        if isinstance(result, PortalUpdate):
            self.update = result
            if result.release.error:
                self.log.info(f"Portal update check: {result.release.error}")
            else:
                self.log.info(f"Portal update check: newest {result.release.tag or 'none'}.")
        self.refresh()

    def fill_suite(self) -> None:
        rows: list[tuple[str, str]] = [("This portal", __version__)]
        status, action = "", "Check again"
        if self.checking:
            status = "Looking for a newer release…"
            action = ""
        elif self.update is not None:
            release = self.update.release
            if release.error:
                rows.append(("Newest release", f"not known: {release.error}"))
            else:
                rows.append(("Newest release", f"{release.version}" + (f", {release.published}" if release.published
                                                                       else "")))
                if self.update_available():
                    summary = self.update.summary()
                    rows.append(("It brings", summary or "the portal itself"))
                    if self.update.details():
                        rows.append(("", self.update.details()))
                    action = f"Update to {release.version}"
        if self.job is not None and self.job[0].key == "":
            status, action = "Downloading the portal…", ""
        if self.message_key == "" and self.message:
            status = self.message
        self.suite_pane.fill(APP_NAME, f"{__version__}, the portal of the suite", rows, status, action)

    def suite_action(self) -> None:
        if self.update_available() and self.job is None and self.pending is None:
            self.install_portal_update()
        else:
            self.check_portal()

    def install_portal_update(self) -> None:
        """Download and install the newer portal: its release checked like an app's, its install.ps1 run after this
        portal has ended, then the new portal started (owner, 28-10-2026: no browser on the handheld)."""
        release = self.update.release
        tag, download = release.tag, self.sources.download
        if download is None:
            return
        work = self.sources.work.parent / "portal-update"
        self.job = (AppEntry(key="", name=APP_NAME, summary="", tag=tag), "install")
        self.message = ""
        self.refresh()
        self._run(lambda: fetch_release(download, self.sources.repo_url, tag, f"{tag}.zip", work),
                  self._portal_fetched)

    def _portal_fetched(self, result: object) -> None:
        self.job = None
        if isinstance(result, Exception):
            self.say("", f"The portal could not be prepared: {result}")
            self.log.error(f"The portal update could not be prepared: {result}")
            return
        try:
            self.terminal(restart_line(Path(result), self.exe), keep_open="on_error")
        except (RuntimeError, OSError) as exc:
            self.say("", f"The portal's installer could not be started: {exc}")
            return
        self.log.info(f"Portal update started from {result}; closing.")
        self.close()

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.status_timer.stop()
        super().closeEvent(event)


def power_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return ()
