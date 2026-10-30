# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the categories as tabs (LB, RB), the tab's apps as two rows of four tiles, the strip under them with
the focused app and its pills (A Install or Open, Y Update), X for the app's details (and Remove there), Menu for
the Settings page (the portal's own update and the settings), B back, View to exit (core's buttons, owner 29-10-2026), RT
Steam's library where Steam is installed (owner, 30-10-2026: out of the game managers, into the portal). An install downloads the app's release in the
background, checks it and runs its install.ps1 in a PowerShell window; the portal waits for that window's exit
status. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

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

from bc250_core import applog, chip, portable, power, steam, xbox
from bc250_core.gamepad import Gamepad
from bc250_core.platform import expand, launch_in_terminal, private
from bc250_core.portable import AMBER, DIM, MENU, VIEW, Card, Legend, PortableHeader, PortableWindow, px, status_clock

from . import APP_ICONS, APP_ID, APP_NAME, EXE_NAME, INTRO_SOUND, ROOT, SUITE, __version__, state_dir
from .intro import INTRO_MS, Intro
from .manifest import CATEGORIES, AppEntry
from .portal_update import PortalUpdate, short
from .sources import Records, SourceError, Sources, downloaded, fetch_release, is_installed
from .widgets import AppPane, DetailsPane, SuitePane, Tabs

STATUS_MS = 2_000               # the header: the CPU and GPU live (owner, 30-10-2026), the battery and the time
POLL_MS = 1000                  # how often the portal looks for the installer window's exit status
CONFIRM_MS = 5000               # Remove, and B while the portal is busy, ask for a second press within this
PROGRESS_MS = 500               # how often a download's size is shown (owner, 28-10-2026: 94 MB looked like a hang)
TILE_W, TILE_H, GAP = 293, 176, 14      # the mock-up's tiles: two rows of four
COLUMNS, PER_PAGE = 4, 8
TAB_KEY = "window/tab"          # the settings: the tab shown last
LOGO_PNG = ROOT / "images" / f"{APP_ID}-128.png"   # the suite's icon, its picture in the Xbox menu
STEAM_MISSING = "Steam is not installed on this device: install it from store.steampowered.com, then RT opens it."
WALLPAPER_KEY = "look/wallpaper"  # where portal 1.6.0 kept the wallpaper switch: now the suite's (core, suite.ini)


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
    install.ps1, then the new portal. The window starts in the portal's working directory, its program folder, which
    a process's working directory keeps from being replaced: Set-Location alone does not move the process, so
    [Environment]::CurrentDirectory moves it to the release folder too."""
    steps = [f"Wait-Process -Id {subprocess.os.getpid()} -ErrorAction SilentlyContinue",
             f"Set-Location -LiteralPath {ps_quote(folder)}",
             f"[Environment]::CurrentDirectory = {ps_quote(folder)}",
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
                 exe: str = "", exit_dir: Path | None = None, intro_ms: int = INTRO_MS,
                 wallpaper: Path | None = portable.WALLPAPER,
                 steam_here: Callable[[], bool] = steam.installed, open_steam: Callable[[str], None] = steam.open_url,
                 xbox_local: Path | None = None, xbox_closed: Callable[[Callable[[], None]], None] | None = None,
                 chip_parts: Callable[[], list[str]] | None = None):
        """*intro_ms*: how long the intro plays when the window starts (0: none). *wallpaper*: the picture behind
        the page, darkened (None: the plain background); on or off for the whole suite (Settings). *steam_here*:
        whether Steam is installed; *open_steam*: hands a steam:// address to Steam (its library). *xbox_local*:
        where the Xbox app's package folder is (default %LOCALAPPDATA%); *xbox_closed*: runs a change with the Xbox
        app closed (core's xbox.with_xbox_closed). *chip_parts*: the CPU's and the GPU's load and temperature for the
        status line (default core's chip.py, AMD's driver opened once)."""
        old = QSettings()                               # portal 1.6.0 kept the switch in portal.ini: the suite's now
        if old.contains(WALLPAPER_KEY) and portable.look_settings(SUITE).value(portable.LOOK_KEY) is None:
            portable.set_wallpaper_on(SUITE, str(old.value(WALLPAPER_KEY)).lower() != "false")
        old.remove(WALLPAPER_KEY)
        super().__init__(gamepad, suite=SUITE, wallpaper=wallpaper)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.entries, self.sources, self.records = entries, sources, records
        self.steam_here, self.open_steam = steam_here, open_steam
        self.xbox_local, self.xbox_closed = xbox_local, xbox_closed
        self.portal_check, self.battery, self.launch, self.terminal = portal_check, battery, launch, terminal
        self.sensors: chip.Temperatures | None = None
        if chip_parts is None:                          # ADL opened once, read every STATUS_MS
            self.sensors, cpu_load = chip.Temperatures(), chip.CpuLoad()
            chip_parts = self.read_chip(self.sensors, cpu_load)
        self.chip_parts = chip_parts
        self.exe = exe                                  # the installed portal's program, for a restart; "" from a checkout
        self.exit_dir = exit_dir or Path(tempfile.gettempdir())
        self.intro: Intro | None = None
        self.settings = QSettings()
        self.by_key = {entry.key: entry for entry in entries}
        self.current_key = ""
        self.job: tuple[AppEntry, str] | None = None    # being downloaded
        self.pending: Pending | None = None             # installing in its PowerShell window
        self.update: PortalUpdate | None = None
        self.checking = False
        self.confirm_key = ""                           # Remove pressed once on this app
        self.close_asked = False                        # View pressed once while a download or an install runs
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
        self.suite_pane.wallpaper.activated.connect(self.next_wallpaper)
        self.suite_pane.transparency.activated.connect(self.next_transparency)
        self.suite_pane.sound.activated.connect(self.toggle_sound)
        self.suite_pane.xbox.activated.connect(self.xbox_menu)
        self.tabs.changed.connect(self.show_tab)
        self.bind("accept", self.a_action)
        self.bind("x", self.show_details)
        self.bind("y", self.y_action)
        self.bind("previous", lambda: self.tabs.step(-1))
        self.bind("next", lambda: self.tabs.step(1))
        self.bind("menu", self.show_suite)
        self.bind("rt", self.steam_action)
        self.back.connect(self.on_back)

        self.worker = _Worker()
        self.download_at: Path | None = None            # the folder of the job's download, for its size
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.refresh)
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
        if intro_ms > 0:                                # over the window before it shows: its first frame is dark
            self.intro = Intro(self, intro_ms, sound=INTRO_SOUND if portable.sound_on(SUITE) else None)
            self.intro.finished.connect(self._intro_done)
            self.intro.cover()

    def start(self) -> None:
        """After the window is shown: the intro, the controller, the status line, the last tab, and the portal's own
        update checked once in the background."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        last = str(self.settings.value(TAB_KEY, ""))
        if last in self.tabs.keys and last != self.tabs.current:
            self.tabs.select(last)
        else:
            self.show_tab(self.tabs.current)
        self.check_portal()
        if self.intro is not None:
            self.intro.begin()

    def _intro_done(self) -> None:
        self.intro = None
        self.show_tab(self.tabs.current)                # the focus back on the tab's tile

    def on_action(self, action: str) -> None:
        if self.intro is not None:                      # any button skips the intro, and only that
            if self.isActiveWindow():
                self.intro.skip()
            return
        super().on_action(action)

    def wallpaper_choices(self) -> tuple[list[tuple[str, Path | None]], dict[str, str]]:
        """The Wallpaper row's choices in order, (name, picture): Off, Built-in (the suite's own), then each picture in
        the suite's wallpaper folder that can be one (owner, 30-10-2026); and the folder's others, each with why not."""
        usable, refused = portable.wallpapers(SUITE)
        return [("Off", None), ("Built-in", None), *((path.stem, path) for path in usable)], refused

    def wallpaper_name(self, choices: list[tuple[str, Path | None]]) -> str:
        """The choice shown now: Off, Built-in, or the chosen picture's name."""
        if not self.wallpaper_on:
            return "Off"
        picture = portable.wallpaper_picture(SUITE, None)
        return next((name for name, path in choices[2:] if path == picture), "Built-in")

    def show_wallpaper_rows(self) -> None:
        choices, refused = self.wallpaper_choices()
        self.suite_pane.set_wallpaper(self.wallpaper_name(choices), refused)
        veil = portable.wallpaper_veil(SUITE)
        self.suite_pane.set_transparency(veil if veil is not None else round(portable.SHADE * 100 / 255))

    def next_wallpaper(self) -> None:
        """The Settings page's Wallpaper row: the next choice, for every app of the suite (each at its next start; this
        window at once): Off, the suite's own picture, then each picture dropped in the suite's wallpaper folder."""
        choices, _ = self.wallpaper_choices()
        names = [name for name, _ in choices]
        name, picture = choices[(names.index(self.wallpaper_name(choices)) + 1) % len(choices)]
        if name == "Off":
            self.set_wallpaper(False)
        else:
            self.set_wallpaper_picture(picture)
            self.set_wallpaper(True)
        self.show_wallpaper_rows()
        self.log.info(f"Wallpaper: {name}, for the suite.")

    def next_transparency(self) -> None:
        """The Settings page's Transparency row: VEIL_STEP more of the background over the wallpaper, from VEIL_MAX
        back to 0 (owner, 30-10-2026: as the BC250 portal's transparency), for the suite."""
        veil = portable.wallpaper_veil(SUITE)
        now = veil if veil is not None else round(portable.SHADE * 100 / 255)
        percent = 0 if now >= portable.VEIL_MAX else (now // portable.VEIL_STEP + 1) * portable.VEIL_STEP
        self.set_wallpaper_veil(percent)
        self.show_wallpaper_rows()
        self.log.info(f"Wallpaper transparency {percent} %, for the suite.")

    def xbox_state(self) -> str:
        """The Xbox menu row's state: "" without the Xbox app, In the menu, or Add."""
        if not xbox.installed(self.xbox_local):
            return ""
        return "In the menu" if xbox.listed(self.program(), self.xbox_local) else "Add"

    def program(self) -> Path:
        """The installed portal, what the Xbox menu starts (never a checkout's Python)."""
        return state_dir() / "app" / f"{EXE_NAME}.exe"

    def xbox_menu(self) -> None:
        """The Settings page's Xbox menu row (owner, 30-10-2026): A puts the suite in the Xbox app's library, and A on
        In the menu takes it out again, the Xbox app closed for a moment either way (core's xbox.py); said on the row
        and in the log."""
        state = self.xbox_state()
        if not state:
            return
        adding = state == "Add"
        try:
            if adding:
                xbox.add(self.program(), APP_NAME, LOGO_PNG, local=self.xbox_local, closed=self.xbox_closed)
            else:
                xbox.remove(self.program(), local=self.xbox_local, closed=self.xbox_closed)
        except xbox.FormatError as exc:
            self.suite_pane.set_xbox(f"not {'added' if adding else 'removed'}, the Xbox app keeps its library otherwise")
            self.log.error(f"Not {'added to' if adding else 'removed from'} the Xbox menu: {exc}")
            return
        except OSError as exc:
            self.suite_pane.set_xbox(f"not {'added' if adding else 'removed'} ({exc.strerror or exc})")
            self.log.error(f"Not {'added to' if adding else 'removed from'} the Xbox menu: {exc}")
            return
        self.suite_pane.set_xbox(self.xbox_state())
        self.log.info(f"{'Added to' if adding else 'Removed from'} the Xbox menu (the Xbox app's library).")

    def toggle_sound(self) -> None:
        """The Settings page's Sound row: the portal's intro sound on or off for the suite (owner, 29-10-2026), kept for
        the next start."""
        on = not portable.sound_on(SUITE)
        portable.set_sound_on(SUITE, on)
        self.suite_pane.set_sound(on)
        self.log.info(f"Sound {'on' if on else 'off'}, for the suite.")

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self.intro is not None:
            self.intro.setGeometry(self.rect())

    # The pages

    @staticmethod
    def read_chip(sensors: chip.Temperatures, cpu_load: chip.CpuLoad) -> Callable[[], list[str]]:
        def read() -> list[str]:
            cpu_temp, gpu_temp = sensors.read()
            return chip.parts(cpu_load.read(), cpu_temp, sensors.gpu_load(), gpu_temp)
        return read

    def update_status(self) -> None:
        # The date and the time, and a portal update when there is one; under them the CPU's and the GPU's load and
        # temperature (owner, 30-10-2026: two lines, one was wider than the screen) and the battery, last
        parts = status_clock()
        if self.update_available():
            parts.append(f"Suite {self.update.release.version} available")
        self.header.set_status(parts, [*self.chip_parts(), power.text(self.battery())])

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
        self.update_legend()

    def show_app(self, key: str) -> None:
        if key not in self.by_key:
            return
        self.current_key = key
        self.refresh()

    def show_details(self) -> None:
        if self.stack.currentWidget() is not self.apps_page or self.current_key not in self.by_key:
            return
        self.stack.setCurrentWidget(self.details_pane)
        self.update_legend()
        self.refresh()

    def show_suite(self) -> None:
        """Menu: the Settings page; on it, Menu shows what the settings do (its information icon)."""
        if self.stack.currentWidget() is self.suite_pane:
            self.show_info()
            return
        self.stack.setCurrentWidget(self.suite_pane)
        self.show_wallpaper_rows()
        self.suite_pane.set_sound(portable.sound_on(SUITE))
        self.suite_pane.set_xbox(self.xbox_state())
        self.update_legend()
        self.refresh()
        self.suite_pane.wallpaper.setFocus()

    def update_legend(self) -> None:
        """The page's buttons, RT Steam where Steam is installed, then core's B Back (on Details and Suite, and from
        the strip to its tile) and View Exit app; while an exit is asked, only that."""
        if not hasattr(self, "legend") or not hasattr(self, "stack"):
            return
        steam_item = [("RT", "Steam")] if self.steam_here() else []
        if self.close_asked:
            self.legend.set_items([(VIEW, "Press again to exit")])
        elif self.stack.currentWidget() is self.apps_page:
            pane = self.app_pane
            self.legend.set_items([*([("A", pane.main)] if pane.main else []), ("X", "Details"),
                                   *([("Y", pane.other)] if pane.other else []), (MENU, "Settings"), *steam_item,
                                   *self.common_items()])
        elif self.stack.currentWidget() is self.details_pane:
            pane = self.details_pane
            self.legend.set_items([*([("A", pane.open)] if pane.open else []),
                                   *([("Y", pane.remove)] if pane.remove else []), *steam_item,
                                   *self.common_items(True)])
        else:
            self.legend.set_items([("A", "Change"), *([("Y", self.suite_pane.action)] if self.suite_pane.action
                                                      else []), *steam_item, *self.common_items(True)])

    def steam_action(self) -> None:
        """RT (or a tap on RT Steam): Steam's library in Big Picture, Steam started first when it does not run (owner,
        30-10-2026: the game managers' Open Steam, now the suite's). Without Steam the line under the app says so."""
        if not self.steam_here():
            self.say(self.current_key, STEAM_MISSING)
            self.refresh()
            return
        try:
            self.open_steam(steam.OPEN_URL)
        except OSError as exc:
            self.say(self.current_key, f"Steam could not be opened: {exc.strerror or exc}")
            self.log.error(f"Opening Steam ({steam.OPEN_URL}) failed: {exc}")
        else:
            self.say(self.current_key, "Opening Steam…")
            self.log.info("Opening Steam.")
        self.refresh()

    def exit_app(self) -> None:
        """View: the portal closes; while a download or an install runs it asks first."""
        if (self.job is not None or self.pending is not None) and not self.close_asked:
            self.ask_close()
            return
        self.close()

    def on_back(self) -> None:
        """B goes back (owner, 29-10-2026): Details and Suite to the tiles, the strip's pills to their tile; on a
        tile it does nothing (View exits)."""
        if self.stack.currentWidget() is self.apps_page:
            self.go_back()
            return
        self.stack.setCurrentWidget(self.apps_page)
        self.update_legend()
        self._confirm_over()
        if self.current_key in self.tiles and self.tiles[self.current_key].isVisible():
            self.tiles[self.current_key].setFocus()
        self.refresh()

    # What each app's tile and pane say

    def downloaded_text(self) -> str:
        """How much of the job's release has come in: " 40 MB", or "" before the first bytes."""
        if self.job is None or self.download_at is None:
            return ""
        entry = self.job[0]
        size = downloaded(self.download_at, entry.tag, entry.asset)
        return f" {size / 1_000_000:.0f} MB" if size else ""

    def busy_text(self, key: str) -> str:
        if self.job is not None and self.job[0].key == key:
            return f"Downloading…{self.downloaded_text()}" if self.job[1] == "install" else "Preparing…"
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
            status, color, _, other = self.state(entry)
            self.tiles[entry.key].set_text(status, color)
            self.tiles[entry.key].set_dot(other == "Update")       # an update is out (owner, 29-10-2026: a red dot)
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
        self.update_legend()                            # A's and Y's texts follow the app and its state

    def detail_rows(self, entry: AppEntry) -> list[tuple[str, str]]:
        record = self.records.get(entry.key)
        installed = ("not installed" if not is_installed(entry) else f"{record.rsplit('-v', 1)[1]} ({record})"
                     if record else "installed, version unknown: Reinstall records it")
        rows = [("Installed", installed), ("This portal pins", entry.tag),
                ("Category", CATEGORIES.get(entry.category, entry.category)),
                ("Program", private(expand(entry.detect[0])) if entry.detect else "")]       # never the user's name
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

    def a_action(self) -> None:
        """A away from a tile or a row (a tap on the legend's A, A on the Details page): the page's own A."""
        if self.stack.currentWidget() is self.details_pane:
            if self.details_pane.open:
                self.open_app(self.current_key)
        elif self.stack.currentWidget() is self.apps_page:
            self.main_action(self.current_key)

    def y_action(self) -> None:
        if self.stack.currentWidget() is self.details_pane:
            self.remove_action(self.current_key)
        elif self.stack.currentWidget() is self.apps_page:
            self.update_action(self.current_key)
        elif self.stack.currentWidget() is self.suite_pane:
            self.suite_action()

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

    def ask_close(self) -> None:
        """View while a download or an install runs asks first (owner, 28-10-2026): exiting drops the download, and
        an installer that ends after the portal is not recorded. A second View within CONFIRM_MS exits."""
        self.close_asked = True
        self.confirm_timer.start()
        if self.job is not None:
            text = "Press View again to exit the portal: the download stops."
        else:
            text = "Press View again to exit the portal: the installer finishes in its window, unrecorded."
        self.say(self.current_key, text)
        self.update_legend()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.close_asked:
            self.close_asked = False
            if self.message.startswith("Press View again"):
                self.message = ""
            self.update_legend()
            self.refresh()
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
        self.download_at = self.sources.work
        self.progress_timer.start()
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
        self.progress_timer.stop()
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

    # The portal's own update (the Settings page)

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
                newest = f"{release.version}" + (f", {release.published}" if release.published else "")
                if power_version(release.version) < power_version(__version__):
                    # This portal is out of no release yet (owner, 30-10-2026: a draft on its device test read as
                    # "the newest is 5.0.0" under 6.0.0)
                    newest += ": older than this portal, which is not published yet"
                rows.append(("Newest release", newest))
                if self.update_available():
                    summary = self.update.summary()
                    rows.append(("It brings", summary or "the portal itself"))
                    if self.update.details():
                        rows.append(("", self.update.details()))
                    action = f"Update to {release.version}"
        if self.job is not None and self.job[0].key == "":
            status, action = f"Downloading the portal…{self.downloaded_text()}", ""
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
        self.download_at = work
        self.progress_timer.start()
        self.refresh()
        self._run(lambda: fetch_release(download, self.sources.repo_url, tag, f"{tag}.zip", work),
                  self._portal_fetched)

    def _portal_fetched(self, result: object) -> None:
        self.job = None
        self.progress_timer.stop()
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
        self.progress_timer.stop()
        self.status_timer.stop()
        if self.sensors is not None:
            self.sensors.close()
            self.sensors = None
        super().closeEvent(event)


def power_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return ()
