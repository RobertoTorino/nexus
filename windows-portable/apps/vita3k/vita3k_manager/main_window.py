# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as RPCS3 Manager and shadPS4 Manager lay it out: the cards on the left
(Vita3K, Your games, Settings, Log: the BC250 suite's Vita3K Manager's parts, and the settings its Vita3K settings
button opened), what the focused one shows on the right, the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a pane to its card,
the browser a level up, a field's page to its pane), View exits the app and Menu shows the information of the pane
that shows.

The Vita3K pane: what is installed, the firmware's parts, the games and where, and when a newer build is out; A
Install until Vita3K is installed, Y Update when another build is there, X Remove Vita3K (a second press), LB
Firmware (the browser in Downloads, showing the .PUP files; A on one gives it to Vita3K, which installs it without
any window: --firmware) and RB Install a game (the browser showing the .vpk, .zip and .pkg files: A on a .vpk or .zip
gives it to Vita3K, X the open folder as a dumped game, which Vita3K installs and the app closes before the game
starts; A on a .pkg asks for its license key on a page of its own, then Vita3K installs it without any window: --pkg
--zrif). A press that cannot act now says why on the status line. Nothing downloads before A. The download, the
unpacking and Vita3K's installs run off the window's thread; the pane counts the megabytes. View (exit) while a job
runs asks first, as the portal does. What the app owns in Vita3K's config.yml (userdata.prepare: games full screen,
its welcome window and update check off) is set after an install, when the window opens and before each of Vita3K's
installs, while Vita3K does not run.

The Your games pane (panes.py, library.py): the games installed in Vita3K, played from Steam (owner, 29-10-2026); A
marks one for Steam, X plays one that is in Steam, through Steam (steam://rungameid), and on a device without Steam
starts Vita3K with it itself (owner, 30-10-2026: a fallback, as its shortcut would start it), Y Update Steam makes
Steam's shortcuts match the marks; RB Steam artwork keeps the SteamGridDB key; Steam's library is the portal's RT
Steam (owner, 30-10-2026: Open Steam moved there). The browser opens where the last one of its kind was left
(browse.remembered). The Log pane: Vita3K's folder and the newest lines of the app's log; A (or a
tap on the pane) shows the whole log in the pane.

The Settings pane: Vita3K's settings that matter on the handheld, in tabs (LB and RB: Picture, Speed, Sound,
System), a row each with its value; A steps to the next value and writes it into config.yml at once
(vita3k_settings), never while Vita3K runs."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, covers, platform, play, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)
from bc250_core.updates import ReleaseInfo

from . import APP_ID, APP_NAME, LOGO_PATH, __version__, emulator, library, shortcuts, userdata, vita3k_settings
from .games import Game, installed as installed_games, read_game
from .panes import BROWSE_INFO, GAMES_INFO, VITA3K_INFO, ZRIF_TEXT, FieldPane, KeyPane, ListPane, LogPane
from .vita3k_settings import TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and View (exit) while a job runs, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
CARD_HEIGHT = 100               # the cards and their gaps fit the column at 720 px high
ABOUT = ("Vita3K, the PS Vita emulator, installed for your own user: the firmware, your games, your saves and its "
         "settings stay in its folder.")
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
FIRMWARE, GAME = "firmware", "game"     # what the browser looks for, and browse.remembered's keys
RUNNING = "Vita3K is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install Vita3K first: the settings are in its folder."
NEEDS_VITA3K = "Install Vita3K first (the A button): it is Vita3K that installs the firmware and your games."
NO_FIRMWARE = ("Install the PS Vita's firmware and its font package first (the LB button on the Vita3K pane): "
               "without them most games do not start.")
BUSY = "Wait a moment: the app is still busy with the step before."
OPEN_A_FOLDER = "Open the game's folder first: the A button opens the one the focus is on, then the X button takes it."
NO_GAME = "Put the focus on a game first: the X button starts it."
ALL_SETTINGS = vita3k_settings.SETTINGS
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; Vita3K "
                  "reads the settings when a game starts. A game's own settings in Vita3K come before these.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


def content_message(written: list[tuple[str, str]], fs: Path, source: str) -> tuple[bool, str]:
    """What to say after Vita3K installed a game, an update or extra content: what came into its storage (titles from
    the games' param.sfo), or that nothing did."""
    if not written:
        return False, (f"Vita3K installed nothing from {source}: is it a PS Vita game (a .vpk, .zip or folder with "
                       "sce_sys\\param.sfo), not a Vitamin dump? Its log (portable\\vita3k.log in its folder) may say "
                       "why.")
    parts = []
    for what, title_id in written:
        game = read_game(fs / "ux0" / "app" / title_id) if what == "game" else None
        if game is not None:
            parts.append(f"{game.title} ({title_id})")
        else:
            parts.append(f"{'an ' if what == 'update' else ''}{what} for {title_id}")
    return True, f"Installed in Vita3K: {'; '.join(parts)}."


class _Worker(QObject):
    """Runs a job off the window's thread; done (the result, or the exception) and what it is doing (said) arrive on
    the window's."""

    done = pyqtSignal(object)
    said = pyqtSignal(str)

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


class SettingsPane(Pane):
    """The settings in tabs, as RPCS3 Manager's: LB and RB step through Picture, Speed, Sound and System, a tap picks
    one; a tab is a page of rows, "Renderer: Vulkan", and A on one steps to the next value (the window writes it). The
    information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("Vita3K's settings", TAB_INFO[TABS[0][0]])
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(4))
        self.tabs = Tabs([(key, name) for key, name, _group in TABS])
        self.column.addWidget(self.tabs)
        self.column.addSpacing(px(8))
        self.pages = QStackedWidget()
        self.pills: dict[str, Row] = {}
        self.first: dict[str, Row] = {}                 # a tab's first row
        for key, _name, group in TABS:
            page = QWidget()
            rows = QVBoxLayout(page)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(px(6))
            for setting in group:
                pill = Row(setting.label)
                self.pills[setting.key] = pill
                self.first.setdefault(key, pill)
                rows.addWidget(pill)
            rows.addStretch()
            self.pages.addWidget(page)
        self.column.addWidget(self.pages, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.tabs.changed.connect(self.show_tab)

    def show_tab(self, key: str) -> None:
        """The tab's page and its information; the focus, when it was on a row, moves to the page's first row."""
        keys = [k for k, _name, _group in TABS]
        inside = any(pill.hasFocus() for pill in self.pills.values())
        if inside:
            self.setFocus()                             # off the old page first: a row hidden with the focus would
        self.pages.setCurrentIndex(keys.index(key))     # hand it to a card, and that card's pane would show
        self.info.info = TAB_INFO[key]
        if inside:
            self.focus_first()

    def focus_first(self) -> None:
        self.first[self.tabs.current].setFocus()


class MainWindow(PortableWindow):
    release_found = pyqtSignal(object)                  # Vita3K's newest build, from the check's thread

    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, running: Callable[[Path], bool] = emulator.running,
                 run_quiet: Callable[..., int] = emulator.run_quiet,
                 install_content: Callable[..., bool] = emulator.install_content,
                 runtime_missing: Callable[[], list[str]] = emulator.runtime_missing,
                 newer_release: Callable[[], ReleaseInfo | None] = emulator.newer_release,
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, roots: Callable[[], list[Path]] = browse.drives,
                 settings: QSettings | None = None, play: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *run_quiet*: Vita3K installing
        a firmware file or a package without a window, *install_content*: Vita3K installing a .vpk, .zip or folder
        (tests pass their own); *runtime_missing*: the Visual C++ runtime's files that are missing; *newer_release*:
        asks GitHub for a newer Vita3K build; *user_home*: the user's folder (the browser's places); *roots*: every
        drive the browser offers; *settings*: the app's (its .ini, create_app's), where the browsers' last folders
        are kept; *play*: hands a steam:// address to Steam (a game); *start*: starts a program on its own (Vita3K
        with a game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running = install, running
        self.run_quiet, self.install_content = run_quiet, install_content
        self.runtime_missing = runtime_missing
        self.settings = settings if settings is not None else QSettings()
        self.play, self.start_program = play, start
        self.newer_release = newer_release
        self.newer: ReleaseInfo | None = None           # Vita3K's newest build, when newer than the pinned one
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…", a job's line
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed = steam_closed
        self._job = ""                                  # "install", "steam", "firmware", "content" or "package"
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.user_home, self.roots = user_home, roots
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.browser: browse.Browser | None = None      # the browser, while it shows
        self.browsing = FIRMWARE                        # what it looks for
        self.package: Path | None = None                # the .pkg whose license key the field's page asks for
        self.fs = userdata.vita_fs(self.home)
        self.firmware = userdata.Firmware(False, False, False)

        page = QVBoxLayout(self)
        page.setContentsMargins(*self.margins())
        self.header = PortableHeader(APP_NAME, __version__)
        page.addWidget(self.header)
        page.addSpacing(px(14))
        body = QHBoxLayout()
        column = QWidget()
        column.setFixedWidth(px(CARDS_WIDTH))
        cards = QVBoxLayout(column)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(px(12))
        self.vita3k_card = Card("Vita3K", "Install it, the PS Vita's firmware and your games.")
        self.games_card = Card("Your games", "Mark them for Steam, and play them.")
        self.settings_card = Card("Settings", "The picture, the speed, the sound and the system.")
        self.log_card = Card("Log", "Vita3K's folder, and this app's log.")
        for card in (self.vita3k_card, self.games_card, self.settings_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        heading = QHBoxLayout()
        heading.addWidget(text_label("Vita3K", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.vita3k_info = InfoPill("Vita3K", VITA3K_INFO)
        heading.addWidget(self.vita3k_info, 0, Qt.AlignmentFlag.AlignTop)
        self.pane.column.addLayout(heading)
        self.pane.column.addWidget(text_label(ABOUT, BODY + 1, color=DIM, wrap=True))
        self.pane.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.pane.column.addLayout(self.grid)
        self.pane.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.pane.column.addWidget(self.status)
        self.settings_pane = SettingsPane()
        self.games_pane = ListPane("Your games", "Your games", GAMES_INFO)
        self.browse_pane = ListPane("Choose a file", "Choosing a file", BROWSE_INFO)
        self.key_pane = KeyPane()
        self.zrif_pane = FieldPane()
        self.log_pane = LogPane()
        for pane in (self.pane, self.games_pane, self.settings_pane, self.log_pane, self.key_pane, self.zrif_pane,
                     self.browse_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.vita3k_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.log_pane: self.log_card,
                      self.key_pane: self.games_card, self.zrif_pane: self.vita3k_card,
                      self.browse_pane: self.vita3k_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.worker.said.connect(self._said)
        self.release_found.connect(self._release_found)
        self.vita3k_card.focused.connect(lambda: self.show_pane(self.pane))
        self.vita3k_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.mark_game)
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.confirm_key = False                        # Remove key pressed once
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("accept", self.a_action)
        self.bind("y", self.y_action)
        self.bind("x", self.x_action)
        self.bind("previous", self.lb_action)
        self.bind("next", self.rb_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(PROGRESS_MS)
        self.progress_timer.timeout.connect(self.refresh)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.read_vita3k()
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, Vita3K's config.yml brought to what the app
        owns, the focus on the Vita3K card, and GitHub asked for a newer build (off the window's thread)."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.read_vita3k()
        self.refresh()
        self.refresh_games()
        self.vita3k_card.setFocus()
        ask = self.newer_release
        threading.Thread(target=lambda: self.release_found.emit(ask()), daemon=True).start()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def read_vita3k(self) -> None:
        """The PS Vita's storage and the firmware's parts in it."""
        self.fs = userdata.vita_fs(self.home)
        self.firmware = userdata.firmware(self.fs)

    def prepare(self) -> bool:
        """config.yml's lines the app owns (userdata.prepare) set while Vita3K is installed and not running; whether
        its files may be written now."""
        if not emulator.installed(self.home) or self.running(self.home):
            return False
        try:
            done = userdata.prepare(self.home)
        except OSError as error:
            self.log.error(f"Vita3K's settings could not be written: {error}")
            return False
        if done:
            self.log.info(f"Vita3K set up: {', '.join(done)}.")
        return True

    def _release_found(self, release: object) -> None:
        self.newer = release if isinstance(release, ReleaseInfo) else None
        if self.newer is not None:
            self.log.info(f"Vita3K build {self.newer.version} is out ({self.newer.published}); this app brings "
                          f"{emulator.VERSION}.")
            self.refresh()

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy and self._job in ("firmware", "content", "package"):
            return self.stage, "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading Vita3K build {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if version != emulator.VERSION:
            return f"This app installs Vita3K build {emulator.VERSION}: the Y button updates it.", "", "Update"
        missing = self.runtime_missing()
        if missing:
            return (f"Vita3K needs Microsoft's Visual C++ runtime ({', '.join(missing)} missing in System32): "
                    "install vc_redist.x64.exe from Microsoft, then open the app again.", "", "")
        if not self.firmware.ready:
            return ("Vita3K needs the PS Vita's firmware and its font package to start most games: the LB button "
                    "takes each PSP2UPDAT.PUP you downloaded.", "", "")
        return "", "", ""

    def firmware_text(self) -> str:
        fw = self.firmware
        if fw.ready:
            return "installed" + (", with the preinstalled apps" if fw.preinstalled else "")
        parts = [part for part, there in (("system software", fw.system), ("font package", fw.fonts)) if not there]
        return f"no {' and no '.join(parts)}"

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        rows = [("Installed", f"build {version}" if version else "not installed"),
                ("This app installs", f"build {emulator.VERSION} ({emulator.SEMVER})")]
        if self.newer is not None:
            rows.append(("Newest build", f"{self.newer.version} ({self.newer.published}): a later version of this "
                                         "app brings it, once tried on the handheld"))
        rows += [("Firmware", self.firmware_text()), ("Games", str(len(self.games)))]
        return [*rows, ("Folder", wrappable(self.home))]

    def refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for r, (label, value) in enumerate(self.rows()):
            self.grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
            shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
            shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(shown, r, 1)
        self.grid.setColumnStretch(1, 1)
        status = self.state()[0]
        if self.confirm_remove:
            status = ("Press the X button again to remove Vita3K: its folder, with the firmware, your games and your "
                      "saves, stays.")
        self.status.setText(self.message or status)
        self.refresh_settings()
        self.update_legend()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        values = vita3k_settings.read_settings(self.home) if ready else {}
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(values[setting.key])}" if ready else setting.label)
        if not ready and not self.settings_pane.status.text():
            self.settings_pane.status.setText(NOT_INSTALLED)
        elif ready and self.settings_pane.status.text() == NOT_INSTALLED:
            self.settings_pane.status.setText("")

    def show_pane(self, pane: Pane) -> None:
        if pane is not self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
        self.panes.setCurrentWidget(pane)
        if pane is self.log_pane:
            self.refresh_log()
        self.update_legend()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows: its actions on the controller's buttons, A too (a tap on an entry does
        the same), then core's Menu Info, B Back (in a pane, and on the browser, a field's page and the whole log) and
        View Exit app. A press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []),
                     *([("X", "Press again" if self.confirm_remove else "Remove Vita3K")] if installed else []),
                     *([("Y", other)] if other else []),
                     *([("LB", "Firmware"), ("RB", "Install a game")] if installed else [])]
        elif pane is self.games_pane:
            items = [("A", "Steam mark"), *([("X", "Play")] if self.games_pane.list.focused() else []),
                     ("Y", "Update Steam"), ("RB", "Steam artwork")]
        elif pane is self.browse_pane:
            items = [("A", "Open")] + ([("X", "Install this folder")] if self.browsing == GAME else [])
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key")]
        elif pane is self.zrif_pane:
            items = [("A", "Install"), ("X", "Paste")]
        on_a_page = pane in (self.key_pane, self.zrif_pane, self.browse_pane) or self.log_pane.viewing
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games, which are in Steam (*in_steam* when given: what Update Steam read back, else Steam's file now),
        and the list."""
        self.games = installed_games(self.fs)
        if in_steam is not None:
            self.in_steam = in_steam
        else:
            try:
                self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir is not None else {}
            except OSError as error:
                self.in_steam = {}
                self.log.error(f"Steam's shortcuts could not be read: {error}")
        try:
            self.outdated = shortcuts.outdated(self.steam_dir) if self.steam_dir is not None else set()
        except OSError:
            self.outdated = set()
        found = {g.name for g in self.games}
        self.marked = {n for n in self.marked if n in found} | {n for n in self.in_steam if n in found
                                                                  and n not in self._unmarked}
        self.show_games()

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        in_steam = sum(1 for g in self.games if g.name in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) installed in Vita3K"
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        rows = [(g.name, self.game_text(g)) for g in self.games]
        if not rows:
            pane.status.setText(pane.status.text() or "No games yet: the RB button on the Vita3K pane installs "
                                                       "one of your games in Vita3K.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        mark = "✓ Steam" if game.name in self.marked else ""
        changed = ((game.name in self.marked) != (game.name in self.in_steam)
                   or game.name in self.marked and game.name in self.outdated)
        parts = (game.title, game.title_id, game.version, mark + (" (Update Steam)" if changed else ""))
        return "  ·  ".join(p for p in parts if p)

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {g.name for g in self.games}:
            return
        if key in self.marked:
            self.marked.discard(key)
            if key in self.in_steam:
                self._unmarked = self._unmarked | {key}
        else:
            self.marked.add(key)
            self._unmarked = self._unmarked - {key}
        self.show_games()
        self.games_pane.list.pills[key].setFocus()

    def update_steam(self) -> None:
        """Y Update Steam: the marked games in Steam, the others out, off the window's thread. Y always answers: a
        press that changes nothing says why on the status line."""
        if self.busy:
            if self._job != "steam":                    # Steam's own job says so on the line already
                self.games_pane.status.setText(BUSY)
            return
        if self.steam_dir is None:
            self.games_pane.status.setText(NO_STEAM)
            return
        if not library.pending(self.games, self.marked, self.in_steam, self.outdated):
            self.games_pane.status.setText(NOTHING_TO_CHANGE)
            return
        add, remove = library.plan(self.games, self.marked, self.in_steam)
        if add and not emulator.installed(self.home):
            self.games_pane.status.setText("Install Vita3K first (the Vita3K card): the games in Steam start it.")
            return
        if add and not self.firmware.ready:
            self.games_pane.status.setText(NO_FIRMWARE)
            return
        folder, closed, program, existing = self.steam_dir, self.steam_closed, emulator.program(self.home), self.in_steam
        key = covers.read_key(library.key_file())
        self.busy, self.message = True, ""
        self.games_pane.status.setText("Looking up covers and changing Steam's shortcuts…" if key else
                                       "Changing Steam's shortcuts…")
        self.log.info(f"Update Steam: {len(add)} in, {len(remove)} out.")
        self._job = "steam"
        self._steam_plan = (add, remove)
        self.worker.run(lambda: library.update_steam(folder, add, remove, program, LOGO_PATH, existing, closed, key))

    def play_game(self) -> None:
        """X on a game: started through Steam (owner, 29-10-2026), which starts Vita3K with it full screen as its
        shortcut says; Steam starts first when it does not run. A game not in Steam yet says how it gets there; on a
        device without Steam Vita3K starts it itself."""
        key = self.games_pane.list.focused()
        game = next((g for g in self.games if g.name == key), None)
        if game is None:
            self.games_pane.status.setText(NO_GAME)
            return
        if self.steam_dir is None:
            self.play_without_steam(game)
            return
        try:
            number = shortcuts.numbers(self.steam_dir).get(key) if self.steam_dir is not None else None
        except OSError as error:
            self.log.error(f"Steam's shortcuts could not be read: {error}")
            number = None
        if number is None:
            self.games_pane.status.setText(f"{game.title} is not in Steam yet: A marks it, then Y Update Steam puts "
                                           "it there.")
            return
        url = steam.play_url(number)
        try:
            self.play(url)
        except OSError as error:
            self.games_pane.status.setText(f"Steam could not be asked to start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} through Steam ({url}) failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in Steam… {play.QUIT_HINT}")
        self.log.info(f"Starting {game.title} in Steam ({url}).")

    def play_without_steam(self, game: Game) -> None:
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): the game in the app's play mode, as
        its Steam shortcut would start it (core's play: View and Menu held quit it), outside the app's bundle
        (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install Vita3K first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"Vita3K could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in Vita3K failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in Vita3K… {play.QUIT_HINT}")
        self.log.info(f"Starting {game.title} in Vita3K, without Steam.")

    # The browser (core's browse): the firmware file in Downloads, or a game to install

    def show_browser(self, looking_for: str) -> None:
        """The browser for *looking_for*, opened where the last one of its kind was left (owner, 29-10-2026), else
        in Downloads."""
        self.browsing = looking_for
        start = browse.places(self.user_home, self.roots)
        downloads = (self.user_home or Path.home()) / "Downloads"
        at = browse.remembered(self.settings, looking_for) or (downloads if downloads.is_dir() else None)
        if looking_for == FIRMWARE:
            self.browser = browse.Browser(start, userdata.FIRMWARE_SUFFIXES, at)
            self.browse_pane.heading.setText("Choose the firmware file")
        else:
            self.browser = browse.Browser(start, userdata.ARCHIVE_SUFFIXES + userdata.PACKAGE_SUFFIXES, at)
            self.browse_pane.heading.setText("Choose a game to install")
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        hint = ("Where is PSP2UPDAT.PUP? Open the folder you downloaded it into, then the A button on it."
                if self.browsing == FIRMWARE else
                "Where is the game? Open its folder, then the A button on a .vpk, .zip or .pkg file, or the X button "
                "on a dumped game's folder.")
        self.browse_pane.summary.setText(wrappable(path) if path is not None else hint)
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is not None:
            browse.remember(self.settings, self.browsing, picked.parent)
        if picked is not None and self.browsing == FIRMWARE:
            self.leave_browser()
            self.install_firmware(picked)
            return
        if picked is not None:
            if picked.suffix.lower() in userdata.PACKAGE_SUFFIXES:
                self.ask_zrif(picked)
            else:
                self.leave_browser()
                self.install_game(picked)
            return
        self.browse_pane.status.setText("")
        self.show_browse()

    def install_browsed(self) -> None:
        """X in the browser for a game: the open folder installed as a dumped game (back to the Vita3K pane)."""
        if self.browsing != GAME:
            return
        if self.browser is None or self.browser.path is None:
            self.browse_pane.status.setText(OPEN_A_FOLDER)
            return
        folder = self.browser.path
        if not userdata.is_dump(folder):
            self.browse_pane.status.setText(f"No PS Vita game in {folder.name or folder}: open the game's own folder "
                                            "(with sce_sys and eboot.bin), then the X button.")
            return
        browse.remember(self.settings, GAME, folder.parent)    # the folder the dumped games are in
        self.leave_browser()
        self.install_game(folder)

    def leave_browser(self) -> None:
        self.browser = None
        self.show_pane(self.pane)
        self.vita3k_card.setFocus()

    # The package's license key (the BC250 app's question for the zRIF, as a page)

    def ask_zrif(self, package: Path) -> None:
        self.package = package
        self.zrif_pane.set_field(f"The license of {package.name}", ZRIF_TEXT, placeholder="KO5i…", length=4096)
        self.show_pane(self.zrif_pane)
        self.zrif_pane.field.setFocus()

    def keep_zrif(self) -> None:
        """A on the license's page: the package installed with the key given, which must look like a zRIF."""
        zrif = "".join(self.zrif_pane.field.text().split())
        why = userdata.check_zrif(zrif)
        if why:
            self.zrif_pane.status.setText(why)
            return
        package = self.package
        self.zrif_pane.field.clear()                    # the key is not left in the window
        self.package = None
        self.leave_browser()
        if package is not None:
            self.install_package(package, zrif)

    # The SteamGridDB key (the BC250 app's Covers… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's cover." if old else
                                     "No key: Update Steam draws the pictures from the game's own.")
        self.show_pane(self.key_pane)
        self.key_pane.field.setFocus()

    def paste(self, pane: FieldPane) -> None:
        """The clipboard's text into the page's field (copied in a browser on the device): typing a key on a handheld
        is the hard way."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            pane.status.setText("The clipboard is empty: copy the text in a browser on this device first.")
            return
        pane.field.setText(text.split()[0])
        pane.status.setText("The text is in the field: the A button " + ("saves it." if pane is self.key_pane else
                                                                           "installs the package."))

    def save_key(self) -> None:
        key = self.key_pane.field.text().strip()
        old = covers.read_key(library.key_file())
        if key == old:
            self.back_to_games()
            return
        try:
            covers.write_key(key, library.key_file())
        except OSError as error:
            self.key_pane.status.setText(f"The key was not saved: {error.strerror or error}")
            self.log.error(f"Saving the SteamGridDB key failed: {error.strerror or error}")
            return
        self.log.info("The SteamGridDB key was changed." if key else "The SteamGridDB key was taken out.")
        self.back_to_games("The SteamGridDB key was changed." if key else
                           "The SteamGridDB key was taken out; the pictures kept stay in use.")

    def remove_key(self) -> None:
        """Remove key asks for a second press (no dialog on a handheld); the pictures kept stay in use."""
        if not covers.read_key(library.key_file()):
            self.key_pane.status.setText("There is no key to remove: the X button pastes one, the A button saves it.")
            return
        if not self.confirm_key:
            self.confirm_key = True
            self.confirm_timer.start()
            self.key_pane.status.setText("Press the Y button again to remove the key.")
            self.update_legend()
            return
        self._confirm_over()
        try:
            covers.write_key("", library.key_file())
        except OSError as error:
            self.key_pane.status.setText(f"The key was not taken out: {error.strerror or error}")
            return
        self.log.info("The SteamGridDB key was taken out.")
        self.back_to_games("The SteamGridDB key was taken out; the pictures kept stay in use.")

    def back_to_games(self, said: str = "") -> None:
        self.key_pane.field.clear()                     # the key is not left in the window
        self.show_pane(self.games_pane)
        if said:
            self.games_pane.status.setText(said)
        self.focus_list(self.games_pane)

    # The legend's buttons: what A (beside a card or a row), X, Y, LB and RB do on the pane that shows (a tap on the
    # legend's entry does the same)

    def a_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.key_pane:
            self.save_key()
        elif pane is self.zrif_pane:
            self.keep_zrif()
        elif pane is self.pane:
            self.main_action()
        elif pane is self.log_pane:
            self.view_log()

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_action()
        elif pane is self.browse_pane:
            self.install_browsed()
        elif pane in (self.key_pane, self.zrif_pane):
            self.paste(pane)
        elif pane is self.games_pane:
            self.play_game()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.other_action()
        elif pane is self.games_pane:
            self.update_steam()
        elif pane is self.key_pane:
            self.remove_key()

    def lb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.choose_firmware()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.choose_game()
        elif pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    # Log

    def refresh_log(self) -> None:
        rows: list[tuple[str, str]] = [("Vita3K's folder", wrappable(emulator.portable_folder(self.home)))]
        if emulator.installed(self.home):
            rows += [("Firmware", self.firmware_text()), ("Installed games", str(len(installed_games(self.fs))))]
        self.log_pane.fill(rows, [private(line) for line in self.log_lines()[-LOG_LINES:]])

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The whole log (its newest lines) in the Log pane: the d-pad scrolls it, B goes back (owner, 29-10-2026:
        Notepad, where it opened before, has no button to close it)."""
        self.show_pane(self.log_pane)
        self.log_pane.show_whole(private("\n".join(self.log_lines()[-LOG_MAX:])))   # older lines too
        self.update_legend()

    # The Settings pane

    def focus_settings(self) -> None:
        self.settings_pane.focus_first()

    def step_setting(self, setting: Setting) -> None:
        """A on a setting's row: its next value, written now, unless Vita3K runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(vita3k_settings.read_setting(self.home, setting))
        try:
            vita3k_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, X, Y, LB and RB on the Vita3K pane

    def main_action(self) -> None:
        """A on the Vita3K card or pane: Install while Vita3K is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        if self.running(self.home):
            self.message = "Vita3K is open: close it first, then update it."
            self.refresh()
            return
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._job = "install"
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing Vita3K build {emulator.VERSION} in {self.home}.")
        self.worker.run(lambda: self.install_job(self.home, progress=self._progress, say=self.worker.said.emit))

    def _progress(self, got: int) -> None:
        self.got = got                                  # read by refresh() on the window's thread

    def _said(self, text: str) -> None:
        self.stage = text
        self.refresh()

    def _done(self, result: object) -> None:
        job, self._job = self._job, ""
        if job == "steam":
            self._steam_done(result)
            return
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if job == "install":
            if isinstance(result, Exception):
                self.message = private(f"Vita3K could not be installed: {result}")
                self.log.error(f"Installing Vita3K failed: {result}")
            else:
                self.message = f"Vita3K build {result} is installed."
                self.log.info(f"Vita3K build {result} installed.")
                self.prepare()                          # before its first start
        else:                                           # the firmware or a game: (ok, what to say)
            ok, text = result if isinstance(result, tuple) else (False, f"Vita3K could not do it: {result}")
            self.message = private(text)
            (self.log.info if ok else self.log.error)(text)
        self.read_vita3k()
        self.refresh_games()
        self.refresh()

    def _steam_done(self, result: object) -> None:
        """What Update Steam did, and the games in Steam as it read them back right after the write (PCSX2
        Manager's check): a game written but not read back is logged by name, so the log tells whether the file or
        the reading is at fault."""
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        ok, text, found = result if isinstance(result, tuple) else (False, f"Steam was not changed: {result}", None)
        add, _remove = getattr(self, "_steam_plan", ([], []))
        if ok and found is not None:
            missing = [g.title for g in add if g.name not in found]
            if missing:
                text += (f"\nRead back from Steam's file, {len(add) - len(missing)} of the {len(add)} game(s) are "
                         f"there: not {', '.join(missing)}. The log has the details.")
                self.log.error(f"Update Steam wrote {len(add)} game(s), but reading Steam's file back finds "
                               f"{len(add) - len(missing)}; not found: {', '.join(missing)}. Steam's file names "
                               f"{len(found)} game(s) of this app in all.")
            else:
                self.log.info(f"Steam's file names {len(found)} game(s) of this app, read back after the write.")
        self.games_pane.status.setText(text)
        (self.log.info if ok else self.log.error)(text.replace("\n", " "))
        self._unmarked = set()
        self.refresh_games(found)

    def remove_action(self) -> None:
        """X Remove Vita3K asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "Vita3K is not installed: there is nothing to remove."
            self.refresh()
            return
        if self.running(self.home):
            self.message = "Vita3K is open: close it first, then remove it."
            self.refresh()
            return
        if not self.confirm_remove:
            self.confirm_remove, self.message = True, ""
            self.confirm_timer.start()
            self.refresh()
            return
        self._confirm_over()
        try:
            emulator.remove(self.home)
        except OSError as error:
            self.message = f"Vita3K could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing Vita3K failed: {error}")
        else:
            self.message = ("Vita3K is removed. Its folder, with the firmware, your games, your saves and its "
                            "settings, stays.")
            self.log.info("Vita3K removed.")
        self.refresh()

    def _ready_for_vita3k(self) -> bool:
        """Whether Vita3K can be given a job now (the firmware or a game); else the status line says why."""
        if self.busy:
            self.message = BUSY
        elif not emulator.installed(self.home):
            self.message = NEEDS_VITA3K
        elif self.running(self.home):
            self.message = "Vita3K is open: close it first; it installs while it is closed."
        else:
            return True
        self.refresh()
        return False

    def choose_firmware(self) -> None:
        """LB Firmware: the browser in Downloads, showing the .PUP files; A on one gives it to Vita3K."""
        if self._ready_for_vita3k():
            self.message = ""
            self.show_browser(FIRMWARE)

    def choose_game(self) -> None:
        """RB Install a game: the browser showing the .vpk, .zip and .pkg files; A on one installs it, X the open
        folder."""
        if self._ready_for_vita3k():
            self.message = ""
            self.show_browser(GAME)

    def _run_job(self, job: str, stage: str, work: Callable[[], tuple[bool, str]]) -> None:
        self.prepare()
        self.busy, self.message, self._job, self.stage = True, "", job, stage
        self.refresh()
        self.worker.run(work)

    def install_firmware(self, pup: Path) -> None:
        """Through Vita3K itself, without its window (--firmware), as the window's job; the parts it wrote are named.
        Vita3K also quits as after an install on a file it could not use, so what it wrote is what tells."""
        if not self._ready_for_vita3k():
            return
        home, fs, run = self.home, self.fs, self.run_quiet
        start = time.time() - 1                         # a second's room for the file system's clock

        def job() -> tuple[bool, str]:
            try:
                run(home, "--firmware", str(pup))
            except (OSError, subprocess.TimeoutExpired) as error:
                return False, f"Vita3K could not install {pup.name}: {error}"
            named = userdata.firmware_parts(userdata.firmware_written(fs, start))
            if named:
                return True, f"{pup.name}: {named} installed."
            return False, (f"Vita3K did not install {pup.name}: nothing of the firmware was written. Is it one of "
                           "the PS Vita's PSP2UPDAT.PUP files?")
        self.log.info(f"Vita3K installs the firmware file {pup}.")
        self._run_job("firmware", f"Vita3K installs {pup.name}, without its window… it takes a minute or two.", job)

    def install_package(self, pkg: Path, zrif: str) -> None:
        """A .pkg with its zRIF through Vita3K (--pkg, --zrif), which installs it without a window and quits."""
        if not self._ready_for_vita3k():
            return
        home, fs, run = self.home, self.fs, self.run_quiet
        start = time.time() - 1

        def job() -> tuple[bool, str]:
            try:
                run(home, "--pkg", str(pkg), "--zrif", zrif)
            except (OSError, subprocess.TimeoutExpired) as error:
                return False, f"Vita3K could not install {pkg.name}: {error}"
            ok, text = content_message(userdata.content_written(fs, start), fs, pkg.name)
            return ok, text if ok else (f"Vita3K did not install {pkg.name}: is the license key the package's "
                                        "own?")
        self.log.info(f"Vita3K installs the package {pkg}.")          # the key is not logged
        self._run_job("package", f"Vita3K installs {pkg.name}, without its window… a large game takes minutes.", job)

    def install_game(self, content: Path) -> None:
        """A .vpk, .zip or dumped folder through Vita3K, which the app closes once the game is installed
        (emulator.install_content); what came into Vita3K's storage is named."""
        if not self._ready_for_vita3k():
            return
        home, fs, install = self.home, self.fs, self.install_content
        start = time.time() - 1

        def job() -> tuple[bool, str]:
            try:
                install(home, content)
            except (OSError, emulator.EmulatorError) as error:
                return False, f"Vita3K could not install {content.name}: {error}"
            return content_message(userdata.content_written(fs, start), fs, content.name)
        self.log.info(f"Vita3K installs {content}.")
        self._run_job("content", f"Vita3K installs {content.name}… a large game takes minutes; Vita3K's window may "
                                 "show for a moment at the end.", job)

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.confirm_key:
            self.confirm_key = False
            if self.key_pane.status.text().startswith("Press the Y button again"):
                self.key_pane.status.setText("")
        changed = self.confirm_remove or self.close_asked
        if self.close_asked and self.message.startswith("Press View again"):
            self.message = ""
        self.confirm_remove = self.close_asked = False
        if changed:
            self.refresh()
        self.update_legend()

    # B

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): the whole log to its summary, the browser a level up (from
        the places to where it came from), the key page to Your games (nothing saved), the license's page to the
        browser (nothing installed), a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.browse_pane:
            if self.browser is not None and self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.zrif_pane:                    # back to the folder the package is in
            self.zrif_pane.field.clear()
            self.package = None
            self.show_pane(self.browse_pane)
            self.show_browse()
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the job (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = {"steam": "Press View again to exit: Steam's shortcuts may be left half changed.",
                            "firmware": "Press View again to exit: Vita3K goes on installing the firmware by itself.",
                            "package": "Press View again to exit: Vita3K goes on installing the package by itself.",
                            "content": "Press View again to exit: Vita3K goes on installing the game, and then "
                                       "starts it in its window."}.get(
                self._job, "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
