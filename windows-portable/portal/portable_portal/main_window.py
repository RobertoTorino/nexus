# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the categories as tabs (LB, RB), the tab's apps as two rows of four tiles, the strip under them with
the focused app and its pills (A Install or Open, Y Update), a banner on the tabs' line while a newer portal is out
(Y updates the portal then, owner 01-11-2026), X for the app's details (and Remove there), Menu for
the Settings page (the portal's own update and the settings), B back, View to exit (core's buttons, owner 29-10-2026), RT
Steam's library where Steam is installed (owner, 30-10-2026: out of the game managers, into the portal). An install downloads the app's release in the
background, checks it and runs its install.ps1 in a PowerShell window; the portal waits for that window's exit
status. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePath

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget

from bc250_core import applog, chip, portable, power, sound_output, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import expand, launch_in_terminal, make_shortcut, private, start_menu
from bc250_core.portable import AMBER, DIM, KEYBOARD, MENU, VIEW, Card, Legend, PortableHeader, PortableWindow, px
from bc250_core.updates import UpdateChecker

from . import ACTION_SOUND, APP_ICONS, APP_ID, APP_NAME, INTRO_SOUND, SUITE, __version__, operating_mode
from . import weather
from .clock import ZONE_NAMES, read as read_clock, save as save_clock
from .intro import INTRO_MS, Intro, play
from .manifest import CATEGORIES, AppEntry
from .portal_update import PortalUpdate, short
from .sources import Records, SourceError, Sources, downloaded, fetch_release, is_installed
from .widgets import AppPane, Count, DetailsPane, ModePane, PageMarker, PlacePane, SuitePane, Tabs, UpdateBanner

STATUS_MS = 2_000               # the header: the CPU and GPU live (owner, 30-10-2026), the battery and the time
EXIT_QUESTION = "Do you really want to exit the portal?"
EXIT_ANSWERS = [(VIEW, "Yes, exit the portal"), ("B", "No, stay")]   # the legend while it is asked
POLL_MS = 1000                  # how often the portal looks for the installer window's exit status
CONFIRM_MS = 5000               # Remove, and View's exit question, wait this long for the answer
PROGRESS_MS = 500               # how often a download's size is shown (owner, 28-10-2026: 94 MB looked like a hang)
RECHECK_MS = 60 * 60 * 1000     # the portal's own update looked for again this often while it runs (owner's roadmap,
RECHECK_AFTER_S = 15 * 60       # 04-11-2026), and when it becomes active again with the last check this old
HELPER_POLL_MS = 500            # how often the Operating Mode page looks for the helper's answer
HELPER_ANSWER_S = 15            # the helper's answer to a mode, at most (PowerShell starts as SYSTEM, ASUS WMI)
HELPER_INSTALL_S = 180          # its install or removal, with Windows' prompt answered first
TILE_W, TILE_H, GAP = 293, 176, 14      # the mock-up's tiles: two rows of four
COLUMNS, PER_PAGE = 4, 8          # a tab's page of tiles; a tab with more apps has more pages
TAB_KEY = "window/tab"          # the settings: the tab shown last
SOUND_OFF_KEY = "look/sound_off"   # the suite's: when Sound was switched off (time.time()), on again after a restart
SOUND_MS = 2_000                # how often the portal reads where Windows plays the sound (5 ms a read on the Ally X)
NOTICE_MS = 8_000               # how long a Windows notification shows
STEAM_MISSING = "Steam is not installed on this device: install it from store.steampowered.com, then RT opens it."
ONE_SCREEN = "There is one screen: attach a TV or a monitor, then LT moves the portal to it."
DISPLAY_SWITCH = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "DisplaySwitch.exe"   # Win + P
NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
# Windows' display setup as Win + P names it (owner, 07-11-2026): what each row says once it is set
PC_SCREEN = "/internal"
ON_HANDHELD = ("PC screen only: Windows shows its picture on the handheld's screen only, and plays the sound on its "
               "speakers.")
ON_BOTH = ("Duplicate: Windows shows the same picture on both screens, XBOX mode too; the sound goes to the second "
           "screen. PC screen only switches back.")
ON_EXTEND = ("Extend: Windows uses both screens, the second one beside the handheld's; XBOX mode stays on the main "
             "screen. PC screen only switches back.")
ON_SECOND = ("Second screen only: Windows shows its picture on the second screen only, XBOX mode, the games and the "
             "sound too. PC screen only switches back.")
# Back on the handheld's screen after the portal and after a restart (owner, 07-11-2026: it kept the last one set): a
# shortcut in the user's Startup folder sets PC screen only at the next sign-in, while another one is set here
STARTUP_LINK = "Windows Portable Suite - PC screen only.lnk"
SETTLE_MS = 4000                # Windows' display switch settles in this time: then the portal starts again, sized
SWITCHED_MODE = ("XBOX mode or the desktop, as Win + F11 switches: the same row switches back. Coming back to XBOX "
                 "mode, Windows may ask to restart for better performance.")


def press_win_f11() -> None:
    """Win + F11, Windows' own switch between XBOX mode and the desktop (no command does it: Microsoft documents the
    keys, Game Bar and Task View), pressed as the keyboard would. OSError off Windows."""
    if sys.platform != "win32":
        raise OSError("Win + F11 is Windows'")
    import ctypes
    user32 = ctypes.windll.user32
    win, f11, up = 0x5B, 0x7A, 0x0002               # VK_LWIN, VK_F11, KEYEVENTF_KEYUP
    for key, flags in ((win, 0), (f11, 0), (f11, up), (win, up)):
        user32.keybd_event(key, 0, flags, 0)


def switch_display(mode: str) -> None:
    """Windows' display setup as Win + P sets it, with DisplaySwitch.exe: /external (the second screen only),
    /internal (the handheld's only), /clone, /extend. OSError when it does not start."""
    subprocess.Popen([str(DISPLAY_SWITCH), mode], creationflags=NO_WINDOW if sys.platform == "win32" else 0)
# With a second screen, the legend's left end (owner, 31-10-2026: "Switch monitor: [] + Shift + < or >", with icons)
SCREEN_KEYS = (portable.SCREEN_ICON, (portable.WINDOWS_KEY, "+", "Shift", "+", "←", "→"))   # two screens drawn
TURBO_COLOR = "#ff1f1f"         # the Turbo letter in the header: a hard red, extra bold (owner, 31-10-2026)
BANNER = "UPDATE AVAILABLE, PRESS Y TO UPDATE"      # on the tabs' line (owner, 01-11-2026)
INTRO_BANNER = "PORTAL UPDATE AVAILABLE"            # on the intro, when the check answers in time
WAIT_UPDATE = "The portal's update starts once the download or install has finished."
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
                 exe: str = "", build: str | None = None, exit_dir: Path | None = None, intro_ms: int = INTRO_MS,
                 wallpaper: Path | None = portable.WALLPAPER,
                 steam_here: Callable[[], bool] = steam.installed, open_steam: Callable[[str], None] = steam.open_url,
                 chip_parts: Callable[[], list[str]] | None = None,
                 modes: Callable[[], operating_mode.PowerApi | None] = operating_mode.power_api,
                 helper: Callable[[], operating_mode.Helper] = operating_mode.Helper,
                 player: Callable[[Path | None], None] = play,
                 display: Callable[[str], None] = switch_display,
                 xbox_mode: Callable[[], None] = press_win_f11,
                 weather_fetch: weather.Fetch | None = None, startup: Path | None = None,
                 shortcut: Callable[..., None] = make_shortcut, booted: Callable[[], float] | None = None,
                 sound_kind: Callable[[], str | None] = sound_output.default_kind,
                 notify: Callable[[str], None] | None = None):
        """*build*: the sha256 of the zip this portal was installed from (build.sha256), "" when not known, None
        from a checkout: a new build of the same version is offered when its sha256 differs. *intro_ms*: how long
        the intro plays when the window starts (0: none). *wallpaper*: the picture behind the page, darkened (None:
        the plain background); on or off for the whole suite (Settings). *steam_here*: whether Steam is installed; *open_steam*: hands a steam:// address to Steam (its library). *chip_parts*: the CPU's and the GPU's load and temperature for the
        status line (default core's chip.py, AMD's driver opened once). *modes*: Windows' power API on the ROG XBOX
        Ally X, None elsewhere: the operating mode's letter before the battery and its page; *helper*: the Operating
        Mode helper that writes its watts (the Ally X only). *player*: plays a .wav, the intro's and each controller
        action's (default winsound; tests pass a fake). *display*: sets Windows' display setup (switch_display). *xbox_mode*: switches between XBOX mode and the desktop
        (press_win_f11). *weather_fetch*: reads Open-Meteo (url -> decoded JSON) for the Location page and the weather
        at the top (weather.fetch_json); None: no lookups (the tests). *startup*: the user's Startup folder, where
        STARTUP_LINK goes (default the Start menu's); *shortcut*: writes a .lnk (core's make_shortcut); *booted*: when
        Windows started, as time.time() counts (default boot_time). *sound_kind*: the kind of Windows' default sound
        output (core's sound_output.default_kind); *notify*: shows a line as a Windows notification (default
        windows_notice; tests pass a fake)."""
        old = QSettings()                              # portal 1.6.0 kept the switch in portal.ini: the suite's now
        if old.contains(WALLPAPER_KEY) and portable.look_settings(SUITE).value(portable.LOOK_KEY) is None:
            portable.set_wallpaper_on(SUITE, str(old.value(WALLPAPER_KEY)).lower() != "false")
        old.remove(WALLPAPER_KEY)
        super().__init__(gamepad, suite=SUITE, wallpaper=wallpaper)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.entries, self.sources, self.records = entries, sources, records
        self.steam_here, self.open_steam = steam_here, open_steam
        self.startup = startup if startup is not None else start_menu() / "Startup"
        self.shortcut, self.booted = shortcut, booted or boot_time
        self.sound_back()                               # before the intro, which plays it
        self.portal_check, self.battery, self.launch, self.terminal = portal_check, battery, launch, terminal
        self.player = player                            # plays a .wav (the intro's player, winsound)
        self.display = display                          # Windows' display setup (DisplaySwitch.exe)
        self.xbox_mode = xbox_mode                      # Win + F11
        self.sensors: chip.Temperatures | None = None
        if chip_parts is None:                          # ADL opened once, read every STATUS_MS
            self.sensors, cpu_load = chip.Temperatures(), chip.CpuLoad()
            chip_parts = self.read_chip(self.sensors, cpu_load)
        self.chip_parts = chip_parts
        self.modes = modes()                            # the Ally X's operating mode (owner, 31-10-2026)
        self.mode_marker = (lambda: operating_mode.marker(self.modes)) if self.modes is not None else (lambda: "")
        self.mode_message = ""                          # the last mode set, on its page
        self.helper = helper() if self.modes is not None else None
        self.helper_wait: tuple | None = None           # waiting for the helper: ("result", mode, since, until) or
        self.helper_timer = QTimer(self)                # ("install", installed, until)
        self.helper_timer.setInterval(HELPER_POLL_MS)
        self.helper_timer.timeout.connect(self._check_helper)
        self.exe = exe                                  # the installed portal's program, for a restart; "" from a checkout
        self.build = build
        self.exit_dir = exit_dir or Path(tempfile.gettempdir())
        self.intro: Intro | None = None
        self.settings = QSettings()
        self.by_key = {entry.key: entry for entry in entries}
        self.current_key = ""
        self.job: tuple[AppEntry, str] | None = None    # being downloaded
        self.pending: Pending | None = None             # installing in its PowerShell window
        self.update: PortalUpdate | None = None
        self.checking = False
        self.checked_at: float | None = None            # time.monotonic() of the last check of the portal's update
        self.quiet_check = False                        # a check again of its own: an error keeps what was known
        self.confirm_key = ""                           # Remove pressed once on this app
        self.close_asked = False                        # View pressed once: the exit question asked
        self.message = ""                               # the last outcome, under the focused app
        self.message_key = ""

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(10))
        self.tabs = Tabs([(key, name) for key, name in CATEGORIES.items()
                          if any(entry.category == key for entry in entries)])
        tabs_line = QHBoxLayout()
        tabs_line.setContentsMargins(0, 0, 0, 0)
        tabs_line.addWidget(self.tabs, 1)
        self.count = Count()                            # how many apps are installed, of all (owner, 07-11-2026)
        tabs_line.addWidget(self.count, 0, Qt.AlignmentFlag.AlignVCenter)
        tabs_line.addSpacing(px(16))
        self.banner = UpdateBanner()                    # while a newer portal is out
        self.banner.pressed.connect(self.portal_update_action)
        tabs_line.addWidget(self.banner, 0, Qt.AlignmentFlag.AlignVCenter)
        page.addLayout(tabs_line)
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
        self.page = 0                                   # the tab's page that shows
        self.page_marker = PageMarker()
        self.page_marker.pressed.connect(lambda: self.turn_page(1, wrap=True))
        apps.addWidget(self.page_marker, 0, Qt.AlignmentFlag.AlignRight)
        apps.addStretch()
        self.app_pane = AppPane()
        apps.addWidget(self.app_pane)
        self.details_pane = DetailsPane()
        self.suite_pane = SuitePane()
        self.mode_pane = ModePane()
        self.place_pane = PlacePane()
        for widget in (self.apps_page, self.details_pane, self.suite_pane, self.mode_pane, self.place_pane):
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
        self.suite_pane.mode.activated.connect(self.show_modes)
        self.suite_pane.screen_row.activated.connect(self.next_screen)
        self.suite_pane.handheld.activated.connect(lambda: self.play_on(PC_SCREEN, ON_HANDHELD, "PC screen only"))
        self.suite_pane.both.activated.connect(lambda: self.play_on("/clone", ON_BOTH, "Duplicate"))
        self.suite_pane.extend.activated.connect(lambda: self.play_on("/extend", ON_EXTEND, "Extend"))
        self.suite_pane.tv.activated.connect(lambda: self.play_on("/external", ON_SECOND, "Second screen only"))
        self.suite_pane.xbox_mode.activated.connect(self.switch_xbox_mode)
        self.suite_pane.hours.activated.connect(lambda: self.change_clock(twelve_hour=not self.clock.twelve_hour))
        self.suite_pane.seconds.activated.connect(lambda: self.change_clock(seconds=not self.clock.seconds))
        self.suite_pane.zone.activated.connect(
            lambda: self.change_clock(zone="utc" if self.clock.zone == "cet" else "cet"))
        self.suite_pane.place.activated.connect(self.show_place)
        for index, row in enumerate(self.place_pane.rows):
            row.activated.connect(lambda index=index: self.pick_place(index))
        self.place_pane.off.activated.connect(lambda: self.pick_place(None))
        self.place_pane.field.returnPressed.connect(self.search_place)
        for letter, row in self.mode_pane.rows.items():
            row.activated.connect(lambda letter=letter: self.set_mode(letter))
        self.mode_pane.helper.activated.connect(self.helper_action)
        self.tabs.changed.connect(self.show_tab)
        self.bind("accept", self.a_action)
        self.bind("x", self.show_details)
        self.bind("y", self.y_action)
        self.bind("previous", lambda: self.tabs.step(-1))
        self.bind("next", lambda: self.tabs.step(1))
        self.bind("menu", self.show_suite)
        self.bind("rt", self.steam_action)
        self.bind("lt", self.screen_action)
        self.back.connect(self.on_back)
        app = QGuiApplication.instance()
        if app is not None:                             # a TV attached or taken away: LT and the Screen row follow
            app.screenAdded.connect(self.screens_changed)
            app.screenRemoved.connect(self.screens_changed)

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
        # Where Windows plays the sound, said on every change (owner, 07-11-2026: a TV switched to another input kept
        # it, and it moved to the handheld only when the screen turned off): by kind, never a device's name
        self.sound_kind = sound_kind
        self.notify = notify or self.windows_notice
        self.sound_where: str | None = None
        self.sound_read = False                         # read once: a change after that is said
        self.sound_failed = False                       # Core Audio did not answer: logged once
        self.tray: QSystemTrayIcon | None = None
        self.tray_timer = QTimer(self)                  # the icon goes once the last notification has shown
        self.tray_timer.setSingleShot(True)
        self.tray_timer.setInterval(NOTICE_MS)
        self.tray_timer.timeout.connect(self.hide_tray)
        self.sound_timer = QTimer(self)
        self.sound_timer.setInterval(SOUND_MS)
        self.sound_timer.timeout.connect(self.watch_sound)
        # The clock and the weather at the top, as the Settings page sets them (owner, 06-11-2026)
        self.clock = read_clock(SUITE)
        self.place = weather.place(SUITE)
        self.weather_now: weather.Weather | None = None
        self.weather_fetch = weather_fetch
        self.weather_checker = UpdateChecker(self)      # the weather off the window's thread
        self.weather_checker.finished.connect(self._weather_in)
        self.search_checker = UpdateChecker(self)       # a place search
        self.search_checker.finished.connect(self._places_found)
        self.weather_timer = QTimer(self)
        self.weather_timer.setInterval(weather.EVERY_MS)
        self.weather_timer.timeout.connect(self.look_weather)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.recheck_timer = QTimer(self)
        self.recheck_timer.setInterval(RECHECK_MS)
        self.recheck_timer.timeout.connect(lambda: self.check_portal(quiet=True))
        if intro_ms > 0:                                # over the window before it shows: its first frame is dark
            self.intro = Intro(self, intro_ms, sound=INTRO_SOUND if portable.sound_on(SUITE) else None,
                               player=player)
            self.intro.finished.connect(self._intro_done)
            self.intro.cover()

    def start(self) -> None:
        """After the window is shown: the intro, the controller, the status line, the last tab, and the portal's own
        update checked once in the background."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start(self.status_ms())
        self.look_weather()
        self.weather_timer.start()
        last = str(self.settings.value(TAB_KEY, ""))
        if last in self.tabs.keys and last != self.tabs.current:
            self.tabs.select(last)
        else:
            self.show_tab(self.tabs.current)
        self.check_portal()
        self.recheck_timer.start()
        self.watch_sound()
        self.sound_timer.start()
        self.startup_done()
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
        if self.isActiveWindow() and portable.sound_on(SUITE):
            self.player(ACTION_SOUND)                   # every controller action (owner, 05-11-2026), as the BC250
        super().on_action(action)                       # portal: the portal only, never during the intro

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

    def mode_name(self) -> str:
        """The Operating mode row's state: "" off the Ally X, the active mode's name, or Other (a plan or a power mode
        of none of them)."""
        if self.modes is None:
            return ""
        mode = operating_mode.active(self.modes)
        return mode.name if mode else "Other"

    def show_modes(self) -> None:
        """The Settings page's Operating mode row: the Operating Mode page, the focus on the active mode."""
        if self.modes is None:
            return
        self.mode_message = ""
        self.stack.setCurrentWidget(self.mode_pane)
        self.fill_modes()
        self.update_legend()
        mode = operating_mode.active(self.modes)
        self.mode_pane.rows[mode.letter if mode else operating_mode.MODES[0].letter].setFocus()

    def fill_modes(self) -> None:
        """Each mode's watts for the power source the device is on now (a device without a battery: the charger's)."""
        if self.modes is None:
            return
        state = self.battery()
        charger = state is None or state[1]
        active = operating_mode.active(self.modes)
        helper = "" if self.helper is None else "Installed" if self.helper.installed() else "Install"
        self.mode_pane.fill("On the charger" if charger else "On battery",
                            [(mode.letter, operating_mode.watts_text(mode.charger if charger else mode.battery),
                              mode is active) for mode in operating_mode.MODES], self.mode_message, helper)

    def set_mode(self, letter: str) -> None:
        """A on a mode's row: its power plan and Windows' power mode, set as the user, then the helper asked for the
        whole mode with its watts (when it is installed); said on the page, in the header's letter and in the log."""
        if self.modes is None:
            return
        mode = operating_mode.BY_LETTER[letter]
        if not operating_mode.apply(mode, self.modes):
            self.mode_message = f"{mode.name} not set: Windows did not take its power plan or power mode."
            self.log.error(f"Operating mode {mode.name} not set: Windows refused its power plan or power mode.")
        elif self.helper is None or not self.helper.installed():
            self.mode_message = (f"{mode.name} set: its power plan and power mode. The watts stay as Armoury Crate set "
                                 "them until the helper is installed (Watt limits).")
            self.log.info(f"Operating mode: {mode.name} (its power plan and power mode; no helper for the watts).")
        else:
            since, _ = self.helper.result()
            error = self.helper.request(mode)
            if error:
                self.mode_message = f"{mode.name} set, but not its watts: {error}."
                self.log.error(f"Operating mode {mode.name}: the helper was not asked: {error}.")
            else:
                self.mode_message = f"{mode.name} set; its watts are being written…"
                self.log.info(f"Operating mode: {mode.name}, the helper asked for its watts.")
                self.wait_helper(("result", mode, since), HELPER_ANSWER_S)
        self.fill_modes()
        self.update_status()

    def helper_action(self) -> None:
        """A on the Watt limits row: the helper installed, or removed when it is, with Windows' administrator prompt."""
        if self.helper is None:
            return
        remove = self.helper.installed()
        error = self.helper.install(remove)
        if error:
            self.mode_message = f"The helper was not {'removed' if remove else 'installed'}: {error}."
            self.log.info(f"Operating Mode helper not {'removed' if remove else 'installed'}: {error}.")
        else:
            self.mode_message = f"{'Removing' if remove else 'Installing'} the helper: answer Windows' prompt…"
            self.log.info(f"Operating Mode helper: {'removal' if remove else 'install'} started.")
            self.wait_helper(("install", not remove), HELPER_INSTALL_S)
        self.fill_modes()

    def wait_helper(self, what: tuple, seconds: float) -> None:
        self.helper_wait = (*what, time.monotonic() + seconds)
        self.helper_timer.start()

    def _check_helper(self) -> None:
        """While the helper is waited for: its result after a mode was asked for, or its install or removal done."""
        if self.helper_wait is None or self.helper is None:
            self.helper_timer.stop()
            return
        *what, until = self.helper_wait
        late = time.monotonic() > until
        if what[0] == "result":
            mode, since = what[1], what[2]
            when, outcome = self.helper.result()
            if when > since and outcome is not None and outcome.letter == mode.letter:
                if outcome.ok:
                    self.mode_message = f"{mode.name} set, with its watts: {outcome.text}."
                    self.log.info(f"Operating mode: {mode.name}, the helper wrote {outcome.text}.")
                else:
                    self.mode_message = f"{mode.name} set, but not its watts: {outcome.text}."
                    self.log.error(f"Operating mode {mode.name}: the helper failed: {outcome.text}.")
            elif late:
                self.mode_message = f"{mode.name} set; the helper did not answer, so its watts may not be written."
                self.log.error(f"Operating mode {mode.name}: no answer from the helper.")
            else:
                return
        else:
            installed = what[1]
            if self.helper.installed() == installed:
                self.mode_message = ("The helper is installed: a mode set here sets its watts too." if installed
                                     else "The helper is removed: Armoury Crate sets the watts again.")
                self.log.info(f"Operating Mode helper {'installed' if installed else 'removed'}.")
            elif late:
                self.mode_message = f"The helper was not {'installed' if installed else 'removed'}."
                self.log.info(self.mode_message)
            else:
                return
        self.helper_wait = None
        self.helper_timer.stop()
        self.fill_modes()
        self.update_status()

    def toggle_sound(self) -> None:
        """The Settings page's Sound row: the portal's intro sound on or off for the suite (owner, 29-10-2026), kept for
        the next start until Windows restarts (sound_back)."""
        on = not portable.sound_on(SUITE)
        portable.set_sound_on(SUITE, on)
        settings = portable.look_settings(SUITE)
        if on:
            settings.remove(SOUND_OFF_KEY)
        else:
            settings.setValue(SOUND_OFF_KEY, time.time())
        settings.sync()
        self.suite_pane.set_sound(on)
        self.log.info(f"Sound {'on' if on else 'off'}, for the suite.")

    def sound_back(self) -> None:
        """Sound on again after Windows restarted (owner, 07-11-2026: "on reboot it should return to default"): Off
        holds from its switch until the next start of Windows; one switched off before that time, or by a portal that
        did not keep the time, is on again."""
        settings = portable.look_settings(SUITE)
        if portable.sound_on(SUITE):
            return
        try:
            off = float(settings.value(SOUND_OFF_KEY, 0))
        except (TypeError, ValueError):
            off = 0.0
        if off >= self.booted():
            return
        portable.set_sound_on(SUITE, True)
        settings.remove(SOUND_OFF_KEY)
        settings.sync()
        self.log.info("Sound on again: it was switched off before Windows started.")

    def watch_sound(self) -> None:
        """Where Windows plays the sound, read every SOUND_MS: a change is said in a Windows notification, seen
        whatever is in front (owner, 07-11-2026: on every change), and logged. The first read only notes it."""
        try:
            kind = self.sound_kind()
        except OSError as exc:
            if not self.sound_failed:
                self.sound_failed = True
                self.log.warning(f"Where Windows plays the sound is not known: {exc}")
            return
        self.sound_failed = False
        if self.sound_read and kind == self.sound_where:
            return
        changed, self.sound_where, self.sound_read = self.sound_read, kind, True
        line = (f"Sound plays on: {sound_output.label(kind)}" if kind is not None
                else "Windows has no sound output now.")
        self.log.info(line)
        if changed:
            self.notify(line)

    def windows_notice(self, line: str) -> None:
        """*line* as a Windows notification from the portal's icon in the taskbar's corner, which goes again once
        the notification has shown."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(APP_NAME)
        self.tray.show()
        self.tray.showMessage(APP_NAME, line, QSystemTrayIcon.MessageIcon.Information, NOTICE_MS)
        self.tray_timer.start()

    def hide_tray(self) -> None:
        if self.tray is not None:
            self.tray.hide()

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
        # temperature (owner, 30-10-2026: two lines, one was wider than the screen), the Ally X's operating mode
        # (S, P, T or W, owner 31-10-2026) and the battery, last
        parts = self.clock.parts()
        place = weather.text(self.place, self.weather_now)
        if place:
            parts.insert(0, place)                      # the place and its weather before the date
        if self.status_timer.isActive():
            self.status_timer.start(self.status_ms())   # with seconds, on each second
        if self.update_available():
            parts.append(f"Suite {self.update.release.version} available")
        marker = self.mode_marker()
        self.header.set_status(parts, [*self.chip_parts(), (marker, TURBO_COLOR) if marker == "T" else marker,
                                       power.text(self.battery())])
        if self.stack.currentWidget() is self.mode_pane:  # the watts follow the charger
            self.fill_modes()

    def status_ms(self) -> int:
        """The time to the header's next look: just past the next second when the clock shows seconds (a timer of a
        second drifts, and a second would be skipped), else STATUS_MS."""
        if not self.clock.seconds:
            return STATUS_MS
        return 1000 - int(time.time() * 1000) % 1000 + 20

    def change_clock(self, **changes: object) -> None:
        """A Clock, Seconds or Time zone row: the clock at the top changes at once, and the choice is kept."""
        self.clock = replace(self.clock, **changes)
        save_clock(SUITE, self.clock)
        self.show_clock_rows()
        self.update_status()
        self.log.info(f"Clock: {'12' if self.clock.twelve_hour else '24'} hours, seconds "
                      f"{'on' if self.clock.seconds else 'off'}, {ZONE_NAMES[self.clock.zone]}.")

    def show_clock_rows(self) -> None:
        self.suite_pane.set_clock(self.clock.twelve_hour, self.clock.seconds, ZONE_NAMES[self.clock.zone])
        self.suite_pane.set_place(self.place.name if self.place else "")

    def look_weather(self) -> None:
        """The place's weather from Open-Meteo, off the window's thread; the last one stays while it is looked up."""
        if self.place is None or self.weather_fetch is None or self.weather_checker.running:
            return
        place, fetch = self.place, self.weather_fetch

        def job() -> tuple[weather.Place, object]:
            try:
                return place, weather.current(place, fetch)
            except (OSError, ValueError) as error:
                return place, error
        self.weather_checker.start(job)

    def _weather_in(self, result: object) -> None:
        place, outcome = result                         # type: ignore[misc]
        if place != self.place:                         # the place changed meanwhile
            return
        if isinstance(outcome, weather.Weather):
            self.weather_now = outcome
            self.update_status()
        else:
            self.log.warning(f"The weather at {place.name} could not be read: {outcome}")

    def show_place(self) -> None:
        """The Location page: the field with the place's name, A searches."""
        pane = self.place_pane
        self.stack.setCurrentWidget(pane)
        pane.field.setText(self.place.name if self.place else "")
        pane.show_places([])
        pane.status.setText(f"Now: {self.place.label}." if self.place else "Now: Off, no weather.")
        pane.field.setFocus()
        pane.field.selectAll()
        self.update_legend()

    def search_place(self) -> None:
        pane = self.place_pane
        name = pane.field.text().strip()
        if len(name) < 2:
            pane.status.setText("Type at least two letters of the place's name, then A.")
            return
        if self.weather_fetch is None or self.search_checker.running:
            return
        fetch = self.weather_fetch

        def job() -> object:
            try:
                return weather.search(name, fetch)
            except (OSError, ValueError) as error:
                return error
        pane.status.setText(f"Searching for {name}…")
        self.search_checker.start(job)

    def _places_found(self, result: object) -> None:
        pane = self.place_pane
        if not isinstance(result, list):
            pane.status.setText(f"Open-Meteo could not be reached: {result}. Try again with A.")
            return
        pane.show_places(result)
        if result:
            pane.rows[0].setFocus()
            pane.status.setText("The d-pad picks a place, A takes it; Y goes back to the name.")
        else:
            pane.status.setText("No place by that name: try another spelling, then A.")
        self.update_legend()

    def place_toggle(self) -> None:
        """Y on the Location page: from the field to the list (the matches, then Off), and back to the field for
        another name; the d-pad stays in a text field (core's move_focus)."""
        pane = self.place_pane
        if pane.field.hasFocus():
            next(row for row in [*pane.rows, pane.off] if row.isVisible()).setFocus()
        else:
            pane.field.setFocus()
            pane.field.selectAll()
        self.update_legend()

    def pick_place(self, index: int | None) -> None:
        """A on a match (or on Off): the suite's place, its weather looked up at once; back to Settings."""
        chosen = self.place_pane.places[index] if index is not None and index < len(self.place_pane.places) else None
        weather.set_place(SUITE, chosen)
        self.place, self.weather_now = chosen, None
        self.log.info(f"Location: {chosen.label if chosen else 'Off'}.")
        self.look_weather()
        self.update_status()
        self.show_suite(self.suite_pane.place)

    def tab_entries(self, category: str) -> list[AppEntry]:
        return [entry for entry in self.entries if entry.category == category]

    def pages(self) -> int:
        return max(1, -(-len(self.tab_entries(self.tabs.current)) // PER_PAGE))

    def show_tab(self, category: str, page: int = 0, focus: int = 0) -> None:
        """The tab's *page* of tiles (the first when a tab is picked), the focus on its tile at *focus* (the last
        one when there are fewer)."""
        for tile in self.tiles.values():
            self.grid.removeWidget(tile)
            tile.hide()
        entries = self.tab_entries(category)
        self.page = min(page, max(0, (len(entries) - 1) // PER_PAGE))
        shown = entries[self.page * PER_PAGE:(self.page + 1) * PER_PAGE]
        for i, entry in enumerate(shown):
            tile = self.tiles[entry.key]
            self.grid.addWidget(tile, i // COLUMNS, i % COLUMNS, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            tile.show()
        self.page_marker.set_page(self.page, self.pages())
        self.settings.setValue(TAB_KEY, category)
        self.stack.setCurrentWidget(self.apps_page)
        self.refresh()
        if shown:
            key = shown[min(focus, len(shown) - 1)].key
            self.tiles[key].setFocus()
            self.show_app(key)
        self.update_legend()

    def turn_page(self, step: int, row: int = 0, wrap: bool = False) -> bool:
        """The tab's next (*step* 1) or previous (-1) page, the focus on *row*'s first tile going forward and its
        last going back (the d-pad past the tiles' edge); with *wrap*, from the last page to the first (a tap on the
        page marker). Whether the page turned."""
        pages = self.pages()
        page = (self.page + step) % pages if wrap else self.page + step
        if pages < 2 or not 0 <= page < pages:
            return False
        self.show_tab(self.tabs.current, page, row * COLUMNS + (COLUMNS - 1 if step < 0 else 0))
        return True

    def move_focus(self, direction: str) -> QWidget | None:
        """The d-pad as everywhere, and past the tiles' left or right edge to the tab's previous or next page."""
        before = QGuiApplication.focusObject()
        moved = super().move_focus(direction)
        if moved is before and direction in ("left", "right") and self.stack.currentWidget() is self.apps_page:
            tile = next((i for i, (key, card) in enumerate(self.page_tiles()) if card is before), None)
            if tile is not None and self.turn_page(1 if direction == "right" else -1, tile // COLUMNS):
                return QGuiApplication.focusObject()
        return moved

    def page_tiles(self) -> list[tuple[str, Card]]:
        """The tiles of the page that shows, in order."""
        entries = self.tab_entries(self.tabs.current)[self.page * PER_PAGE:(self.page + 1) * PER_PAGE]
        return [(entry.key, self.tiles[entry.key]) for entry in entries]

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

    def show_suite(self, focus: QWidget | None = None) -> None:
        """Menu: the Settings page, the focus on *focus* (default its first row); on it, and on the Operating Mode
        page, Menu shows what the page's settings do (its information icon)."""
        if focus is None and self.stack.currentWidget() in (self.suite_pane, self.mode_pane):
            self.show_info()
            return
        self.stack.setCurrentWidget(self.suite_pane)
        self.show_wallpaper_rows()
        self.suite_pane.set_sound(portable.sound_on(SUITE))
        self.suite_pane.set_mode(self.mode_name())
        self.suite_pane.set_screen(self.screen_name())
        self.show_clock_rows()
        self.update_legend()
        self.refresh()
        (focus or self.suite_pane.wallpaper).setFocus()

    def update_legend(self) -> None:
        """The page's buttons, LT Screen with a second screen (and the keyboard's Win + Shift + an arrow at the
        left), RT Steam where Steam is installed, R3 the touch keyboard, then core's B Back (on Details and Suite, and from the strip to its
        tile) and View Exit; while the exit question is asked, its answers."""
        if not hasattr(self, "legend") or not hasattr(self, "stack"):
            return
        self.show_banner()
        screens = len(QGuiApplication.screens()) > 1
        triggers = [*([("LT", "Screen")] if screens else []), *([("RT", "Steam")] if self.steam_here() else []),
                    KEYBOARD]                       # R3 and a keyboard drawn: Windows' touch keyboard (owner)
        keys = SCREEN_KEYS if screens and not self.close_asked else None
        if self.close_asked:
            self.legend.set_items(EXIT_ANSWERS)
        elif self.stack.currentWidget() is self.apps_page:
            pane = self.app_pane
            other = "Update suite" if self.update_available() else pane.other      # the portal first
            self.legend.set_items([*([("A", pane.main)] if pane.main else []), ("X", "Details"),
                                   *([("Y", other)] if other else []), (MENU, "Settings"), *triggers,
                                   *self.common_items()], keys)
        elif self.stack.currentWidget() is self.details_pane:
            pane = self.details_pane
            self.legend.set_items([*([("A", pane.open)] if pane.open else []),
                                   *([("Y", pane.remove)] if pane.remove else []), *triggers,
                                   *self.common_items(True)], keys)
        elif self.stack.currentWidget() is self.mode_pane:
            self.legend.set_items([("A", "Set"), *triggers, *self.common_items(True)], keys)
        elif self.stack.currentWidget() is self.place_pane:
            typing = self.place_pane.field.hasFocus()
            self.legend.set_items([("A", "Search" if typing else "Take"), ("Y", "To the list" if typing else "Search"),
                                   *triggers, *self.common_items(True)], keys)
        else:
            self.legend.set_items([("A", "Change"), *([("Y", self.suite_pane.action)] if self.suite_pane.action
                                                      else []), *triggers, *self.common_items(True)], keys)

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
        """View: the portal asks first, then closes on a second View (owner, 05-11-2026: every time, not only while
        a download or an install runs), Windows' display setup back to PC screen only when another one was set here
        (owner, 07-11-2026)."""
        if not self.close_asked:
            self.ask_close()
            return
        self.screen_back()
        self.close()

    def on_back(self) -> None:
        """B goes back (owner, 29-10-2026): Details and Suite to the tiles, Operating Mode to Settings, the strip's pills
        to their tile; on a tile it does nothing (View exits). While the exit question is asked, B is its No."""
        if self.close_asked:
            self._confirm_over()
            return
        if self.stack.currentWidget() is self.apps_page:
            self.go_back()
            return
        if self.stack.currentWidget() is self.mode_pane:
            self.show_suite(self.suite_pane.mode)
            return
        if self.stack.currentWidget() is self.place_pane:
            self.show_suite(self.suite_pane.place)
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
        self.count.set_count(sum(is_installed(entry) for entry in self.entries), len(self.entries))
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
        elif self.stack.currentWidget() is self.place_pane:
            self.search_place()                         # A in the field

    def y_action(self) -> None:
        if self.stack.currentWidget() is self.details_pane:
            self.remove_action(self.current_key)
        elif self.stack.currentWidget() is self.apps_page and self.update_available():
            self.portal_update_action()
        elif self.stack.currentWidget() is self.apps_page:
            self.update_action(self.current_key)
        elif self.stack.currentWidget() is self.suite_pane:
            self.suite_action()
        elif self.stack.currentWidget() is self.place_pane:
            self.place_toggle()

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
        """View asks first (owner, 05-11-2026: "Do you really want to exit the Portal?"): a second View within
        CONFIRM_MS exits, B or the time running out stays. While a download or an install runs the question says what
        exiting does to it (owner, 28-10-2026): the download is dropped, and an installer that ends after the portal
        is not recorded."""
        self.close_asked = True
        self.confirm_timer.start()
        text = EXIT_QUESTION
        if self.job is not None:
            text += " The download stops."
        elif self.pending is not None:
            text += " The installer finishes in its window, unrecorded."
        self.say(self.current_key, text)
        self.update_legend()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.close_asked:
            self.close_asked = False
            if self.message.startswith(EXIT_QUESTION):
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
        # The app may take the front, also the one already open that this start only asks to show itself (owner,
        # 07-11-2026: an open app stayed behind the portal)
        portable.allow_foreground()
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
                    and (power_version(release.version) > power_version(__version__) or self.new_build()))

    def new_build(self) -> bool:
        """The newest release is this portal's version built again (owner, 31-10-2026: a device kept a draft the
        device test turned down, and the version alone never offered the release that replaced it): its zip's
        sha256 is not the one this portal was installed from, or that one is not known."""
        update = self.update
        return bool(update is not None and self.build is not None and update.sha256
                    and power_version(update.release.version) == power_version(__version__)
                    and update.sha256 != self.build)

    def check_portal(self, quiet: bool = False) -> None:
        """The portal's own update looked for in the background: at the start, on Check again, and *quiet* again of
        its own (recheck_portal)."""
        if self.portal_check is None or self.checking or self.worker.busy:
            return
        self.checking, self.quiet_check = True, quiet
        self.fill_suite()
        self._run(self.portal_check, self._portal_checked)

    def recheck_portal(self) -> None:
        """Not only at the start (owner's roadmap, 04-11-2026): when the portal becomes active again (back from a
        game or an app) once the last check is RECHECK_AFTER_S old, which keeps it well within GitHub's limit for a
        device that is not signed in; and every RECHECK_MS (recheck_timer)."""
        if self.checked_at is None or time.monotonic() - self.checked_at >= RECHECK_AFTER_S:
            self.check_portal(quiet=True)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self.intro is None:
            self.recheck_portal()
        super().changeEvent(event)

    def _portal_checked(self, result: object) -> None:
        self.checking = False
        self.checked_at = time.monotonic()
        if isinstance(result, PortalUpdate) and result.release.error and self.quiet_check and self.update_available():
            # Offline for a moment: the update found before stays offered
            self.log.info(f"Portal update check again: {result.release.error}; the update found before stays.")
        elif isinstance(result, PortalUpdate):
            self.update = result
            if result.release.error:
                self.log.info(f"Portal update check: {result.release.error}")
            else:
                self.log.info(f"Portal update check: newest {result.release.tag or 'none'}.")
        if self.intro is not None and self.update_available():
            self.intro.set_banner(INTRO_BANNER)
        self.refresh()

    def show_banner(self) -> None:
        """The banner on the tabs' line: while a newer portal is out, on the tiles and the Settings page, where Y
        updates it (Y removes an app on Details); while it downloads, how far it is; else none (owner, 01-11-2026)."""
        portal_job = self.job is not None and self.job[0].key == ""
        text = (f"DOWNLOADING THE UPDATE…{self.downloaded_text()}" if portal_job
                else BANNER if self.update_available() else "")
        self.banner.setText(text)
        self.banner.setVisible(bool(text) and self.stack.currentWidget() in (self.apps_page, self.suite_pane))

    def portal_update_action(self) -> None:
        """Y on the tiles, or a tap on the banner, while a newer portal is out: its download and install; while an
        app is downloaded or installed, the line under the app says it waits."""
        if not self.update_available():
            return
        if self.job is not None or self.pending is not None:
            if not (self.job is not None and self.job[0].key == ""):
                self.say(self.current_key, WAIT_UPDATE)
            return
        self.install_portal_update()

    def fill_suite(self) -> None:
        # This portal's version is the line under the title; the app by app changes are in the information (owner,
        # 01-11-2026: their lines ran over each other)
        rows: list[tuple[str, str]] = []
        status, action, brings = "", "Check again", ""
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
                elif self.new_build():
                    newest += ": a new build of this version"
                rows.append(("Newest release", newest))
                if self.update_available():
                    summary = self.update.summary()
                    rows.append(("It brings", summary or "the portal itself"))
                    action = f"Update to {release.version}"
                    brings = self.update.details()
        if self.job is not None and self.job[0].key == "":
            status, action = f"Downloading the portal…{self.downloaded_text()}", ""
        if self.message_key == "" and self.message:
            status = self.message
        self.suite_pane.fill(APP_NAME, f"{__version__}, the portal of the suite", rows, status, action, brings)

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

    # The screen it is on (owner, 31-10-2026): core's PortableWindow starts it again on a screen of another size

    def screen_name(self) -> str:
        """The Screen row's state: "" with one screen, else the name of the screen the portal is on."""
        if len(QGuiApplication.screens()) < 2 or self.screen() is None:
            return ""
        return portable.screen_label(self.screen())

    def next_screen(self) -> None:
        """A on the Screen row: the portal on the next screen, started again there once nothing is being installed."""
        screens = QGuiApplication.screens()
        if len(screens) < 2:
            return
        names = [screen.name() for screen in screens]
        here = self.screen().name() if self.screen() is not None else ""
        target = screens[(names.index(here) + 1) % len(screens)] if here in names else screens[0]
        self.log.info(f"Moving to the screen {portable.screen_label(target)}.")
        self.move_to(target)

    def screen_action(self) -> None:
        """LT (or a tap on LT Screen): the next screen, as the Screen row's A; with one screen the line under the app
        says so."""
        if len(QGuiApplication.screens()) < 2:
            self.say(self.current_key, ONE_SCREEN)
            self.refresh()
            return
        self.next_screen()

    def switch_xbox_mode(self) -> None:
        """The Settings page's XBOX mode ↔ Desktop row (owner, 05-11-2026: "a button to start XBOX mode and to quit
        it"): Win + F11, which switches either way; Windows asks its own question about a restart for performance."""
        try:
            self.xbox_mode()
        except OSError as exc:
            self.say("", f"XBOX mode was not switched: {exc.strerror or exc}")
            self.log.error(f"Win + F11 not pressed: {exc}")
        else:
            self.say("", SWITCHED_MODE)
            self.log.info("XBOX mode or the desktop: Win + F11 pressed.")
        self.refresh()

    def play_on(self, mode: str, said: str, where: str) -> None:
        """The Settings page's PC screen only (/internal), Duplicate (/clone), Extend (/extend) and Second screen only
        (/external), as Win + P names them (owner, 05-11-2026 and 07-11-2026): XBOX mode runs on Windows' main screen
        only and leaves the other one empty, so Windows' display setup is switched as Win + P does, for everything on
        the handheld; said on the page and in the log. Any but PC screen only puts STARTUP_LINK in place, which sets
        PC screen only at the next sign-in; PC screen only takes it away."""
        try:
            self.display(mode)
        except OSError as exc:
            self.say("", f"Windows' display setting did not change: {exc.strerror or exc}")
            self.log.error(f"DisplaySwitch {mode} failed: {exc}")
        else:
            self.say("", said)
            self.log.info(f"{where}: DisplaySwitch {mode}.")
            self.reset_at_sign_in(mode != PC_SCREEN)
            # Windows moves the window to its new main screen but the portal keeps the sizes of the one before (owner,
            # 05-11-2026: the TV cut the legend off): once the switch has settled it starts again there, as LT does
            QTimer.singleShot(SETTLE_MS, lambda: self.move_to(QGuiApplication.primaryScreen()))
        self.refresh()

    def startup_link(self) -> Path:
        return self.startup / STARTUP_LINK

    def reset_at_sign_in(self, on: bool) -> None:
        """STARTUP_LINK in the user's Startup folder (*on*), or taken away: DisplaySwitch.exe /internal at the next
        sign-in, so a restart comes back on the handheld's screen."""
        link = self.startup_link()
        try:
            if on and not link.is_file():
                self.shortcut(link, DISPLAY_SWITCH, PC_SCREEN, description="PC screen only at the next sign-in: the "
                              "Windows Portable Suite's portal set another screen")
                self.log.info("PC screen only at the next sign-in: the Startup folder's shortcut is in place.")
            elif not on and link.is_file():
                link.unlink()
                self.log.info("The Startup folder's PC screen only shortcut is taken away.")
        except (OSError, RuntimeError) as exc:
            self.log.error(f"The Startup folder's PC screen only shortcut: {exc}")

    def startup_done(self) -> None:
        """At the start: STARTUP_LINK from before Windows' last start has done its work at the sign-in (the screen is
        the handheld's again), so it goes; one put in place since stays, for the next restart."""
        link = self.startup_link()
        try:
            if link.is_file() and link.stat().st_mtime < self.booted():
                link.unlink()
                self.log.info("PC screen only was set at the sign-in; the Startup folder's shortcut is taken away.")
        except OSError as exc:
            self.log.error(f"The Startup folder's PC screen only shortcut: {exc}")

    def screen_back(self) -> None:
        """Exiting the portal: PC screen only again when another one was set here (STARTUP_LINK is in place)."""
        if not self.startup_link().is_file():
            return
        try:
            self.display(PC_SCREEN)
        except OSError as exc:
            self.log.error(f"DisplaySwitch {PC_SCREEN} on exit failed: {exc}")
            return
        self.log.info(f"Exit: PC screen only again (DisplaySwitch {PC_SCREEN}).")
        self.reset_at_sign_in(False)

    def screens_changed(self, _screen=None) -> None:
        self.update_legend()
        if self.stack.currentWidget() is self.suite_pane:
            self.suite_pane.set_screen(self.screen_name())

    def screen_moved(self, screen) -> None:
        """Moved to another screen by the keyboard (Win + Shift + an arrow) without starting again (a screen of the
        same size): the Screen row says the screen it is on now, PC screen or Other screen (owner, 01-11-2026)."""
        super().screen_moved(screen)
        self.screens_changed()

    def can_restart(self) -> bool:
        return self.job is None and self.pending is None

    def waiting_to_move(self) -> None:
        self.say(self.current_key, "The portal moves to the other screen once the download or install has finished.")
        self.refresh()

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.recheck_timer.stop()
        self.progress_timer.stop()
        self.status_timer.stop()
        self.sound_timer.stop()
        self.tray_timer.stop()
        self.hide_tray()
        if self.sensors is not None:
            self.sensors.close()
            self.sensors = None
        super().closeEvent(event)


def boot_time() -> float:
    """When Windows started, as time.time() counts: now less GetTickCount64's milliseconds; 0 off Windows."""
    if sys.platform != "win32":
        return 0.0
    import ctypes
    ticks = ctypes.windll.kernel32.GetTickCount64
    ticks.restype = ctypes.c_ulonglong
    return time.time() - ticks() / 1000


def power_version(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return ()
