# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as PPSSPP Manager and PCSX2 Manager lay it out: the cards on the left
(RPCS3, Your games, Settings, Log: the BC250 suite's RPCS3 Manager's parts), what the focused one shows on the right,
the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a pane to its card,
the key page to Your games), View exits the app and Menu shows the information of the pane that shows. Nothing is
browsed to (owner, 30-10-2026): the games, the packages and the firmware are put in the app's own folders
(library.fixed: Games\\PS3 and Games\\PS3\\Firmware in your user folder, Games\\PS3 on an SD card), and the app takes
care of them.

The RPCS3 pane: what is installed, the firmware and where; A Install until RPCS3 is installed, Y Update when an older
build is there and X Remove RPCS3 (a second press). The firmware put in Games\\PS3\\Firmware is given to RPCS3 when the
app opens, when the RPCS3 card gets the focus and after RPCS3 is installed (owner, 01-11-2026: taken in
automatically), once per file: RPCS3 installs it without any window (--headless --installfw, the result read from its
log); a file whose version is installed already, or that was given to RPCS3 before as it is, is left alone. A press
that cannot act now says why on the status line. Nothing downloads before A. The download, the unpacking and RPCS3's
installs run off the window's thread; the pane counts the megabytes. View (exit) while a job runs asks first, as the
portal does. RPCS3's own window is never shown: what the app owns in RPCS3's files (userdata: its welcome dialog,
exit question and update check off, player 1 on the handheld's controller) is set after an install and when the
window opens, while RPCS3 does not run.

The Your games pane (panes.py, library.py): the disc games in the app's own Games\\PS3 folders (an SD card's too),
the games installed in RPCS3 and the disc games it knows, played from Steam (owner, 29-10-2026); A marks one for
Steam, X plays one that is in Steam, through Steam (steam://rungameid), and on a device without Steam starts it in the
app's play mode itself (owner, 30-10-2026: a fallback, as its shortcut would start it; core's play: View, LB and RB
held quit any game), Y Update Steam makes Steam's shortcuts match the marks and brings a shortcut made before the play
mode to it; RB Remove game shows the keep page with what would go (library.removal: the game's folders, its Steam
shortcut); LB Steam artwork keeps the SteamGridDB key. A package or a license put in the game folders
(userdata.waiting) is a row of its own, PKG, PKG update or License; A installs it, X Install all every one, the
licenses first, the updates last, each in a run of RPCS3 without its window (--headless --installpkg); the keep page
then lists the packages RPCS3 installed without a problem, and one kept is not listed again (PACKAGES_KEPT); the
licenses stay. Nothing is deleted before the user decides what to keep (owner, 01-11-2026; core's keep): the keep
page marks each row Delete, A keeps one, X deletes the marked, B deletes nothing. Steam's library is the portal's RT Steam (owner, 30-10-2026). The Log
pane: RPCS3's folder, the app's Games\\PS3 folder and the newest lines of the app's log; A (or a tap on the pane) shows
the whole log in the pane.

The Settings pane: RPCS3's settings that matter on the handheld, in tabs (LB and RB: Screen, Speed, Sound,
Messages; the Screen setting, how the games fill it, among the Screen tab's), a row each with its value; A steps to
the next value and writes it into config.yml at once (rpcs3_settings), never while RPCS3 runs (it writes its own
settings back when it closes)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, keep, platform, play, power, renamed, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, KEYBOARD, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)

from . import APP_ID, APP_NAME, LOGO_PATH, __version__, emulator, library, rpcs3_settings, shortcuts, userdata
from .games import Game, installed as installed_games, scan
from .panes import GAMES_INFO, KEEP_INFO, RPCS3_INFO, KeyPane, ListPane, LogPane
from .rpcs3_settings import TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and View (exit) while a job runs, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
ABOUT = ("RPCS3, the PS3 emulator, installed for your own user: the firmware, your saves, its settings and the games "
         "installed from packages stay in its folder.")
CARD_HEIGHT = 100               # the cards and their gaps fit the column at 720 px high
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
RUNNING = "RPCS3 is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install RPCS3 first: the settings are in its folder."
# The RPCS3 card's two lines, the same in every emulator manager (owner, 07-11-2026)
CARD_NOT_INSTALLED = "Not installed.\nInstall with the A button."
CARD_INSTALLED = "Installed.\nRemove with the X button."
NEEDS_RPCS3 = "Install RPCS3 first (the RPCS3 card): it is RPCS3 that installs the firmware and the packages."
NO_FIRMWARE = ("The PS3's firmware is not installed yet: put PS3UPDAT.PUP in your Games\\PS3\\Firmware folder, and "
               "RPCS3 installs it when the RPCS3 card gets the focus. Without it no game starts from Steam.")
BUSY = "Wait a moment: the app is still busy with the step before."
NO_GAME = "Put the focus on a game first: the X button starts it."
NOTHING_TO_INSTALL = ("Nothing to install: put .pkg files and .rap licenses in your Games\\PS3 folder, then the X "
                      "button installs them.")
FIRMWARE_TAKEN = "firmware/taken"   # the settings' key: the firmware file last given to RPCS3 (library.file_key)
PACKAGES_KEPT = "packages/kept"    # the settings' key: the installed packages the user kept (library.kept_key)
STEAM_ITEM = "steam"                # the keep page's row for a game's Steam shortcut
NOTHING_MARKED = "Nothing is marked Delete: B goes back, and nothing is deleted."
ALL_SETTINGS = rpcs3_settings.SETTINGS
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; RPCS3 "
                  "reads the settings when a game starts. A game's own settings in RPCS3, where it has them, come "
                  "before these.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


def _packages_in(hdd0_game: Path) -> tuple[set[str], set[str]]:
    """(the installed games, the licenses) in RPCS3's folder: compared before and after an install."""
    return ({str(g.eboot) for g in installed_games(hdd0_game)},
            {p.name for p in userdata.licenses(hdd0_game.parent)})


def install_message(report: userdata.InstallReport, new_games: int, new_licenses: int, folder: str) -> tuple[bool, str]:
    """What to say after an install, from RPCS3's log (the titles) and what came into RPCS3's folders (the counts,
    when the log says nothing of them); the BC250 app's."""
    def named(items: list[tuple[str, str]]) -> str:
        return ", ".join(f"{title} ({serial})" if serial else title for title, serial in items)
    parts = []
    if report.installed:
        parts.append(f"{len(report.installed)} game(s) installed in RPCS3: {named(report.installed)}")
    elif new_games:
        parts.append(f"{new_games} game(s) installed in RPCS3")
    copied = len(report.copied) or new_licenses
    if copied:
        parts.append(f"{copied} license(s) copied into RPCS3")
    if report.failed:
        parts.append(f"{len(report.failed)} package(s) RPCS3 could not install: {named(report.failed)}")
    if report.invalid:
        parts.append(f"{report.invalid} file(s) that are no PS3 package")
    if report.not_copied:
        parts.append(f"{len(report.not_copied)} license(s) RPCS3 could not copy: " + ", ".join(report.not_copied))
    if not parts:
        return False, f"RPCS3 installed nothing from {folder}. Its log (log\\RPCS3.log in its folder) says why."
    text = "; ".join(parts) + "."
    if report.problems:
        return False, f"{text} RPCS3's log (log\\RPCS3.log in its folder) has the details."
    return True, text


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
    """The settings in tabs, as PPSSPP Manager's: LB and RB step through Screen, Speed, Sound and Messages, a tap
    picks one; a tab is a page of rows, "Renderer: Vulkan", and A on one steps to the next value (the window writes
    it). The information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("RPCS3's settings", TAB_INFO[TABS[0][0]])
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
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, running: Callable[[Path], bool] = emulator.running,
                 run_headless: Callable[..., int] = emulator.run_headless,
                 runtime_missing: Callable[[], list[str]] = emulator.runtime_missing,
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 settings: QSettings | None = None,
                 play: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *run_headless*: RPCS3 without a
        window for a firmware or package install (tests pass their own); *runtime_missing*: the Visual C++ runtime's
        files that are missing; *user_home*: the user's folder (where Games\\PS3 is); *drives*: the removable
        drives, whose Games\\PS3 is looked in too; *settings*: the app's (its .ini, create_app's), where the firmware
        file last given to RPCS3 is kept; *play*: hands a steam:// address to Steam (a game); *start*: starts a program
        on its own (RPCS3 with a game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running, self.run_headless = install, running, run_headless
        self.runtime_missing = runtime_missing
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…", a job's line
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed = steam_closed
        self._job = ""                                  # "install", "steam", "firmware", "packages" or "delete"
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.user_home, self.drives = user_home, drives
        self.settings = settings if settings is not None else QSettings()
        self.play, self.start_program = play, start
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.moved: dict[str, str] = {}                 # a game found again: its file in Steam (renamed)
        self.keep_items: list[keep.Item] = []           # the keep page's rows (Remove game, the packages installed)
        self.keep_game: Game | None = None              # the game Remove game is about; None for the packages
        self.deleting: list[Path] = []                  # what the delete job is deleting
        self.packages: list[userdata.PackageInfo] = []  # the packages in the game folders, waiting for RPCS3
        self.licenses: list[Path] = []                  # the licenses there RPCS3 does not keep yet
        self.firmware = ""
        self.known: list[str] = []
        self.hdd0_game, self.dev_flash = userdata.drives(self.home)

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
        self.rpcs3_card = Card("RPCS3", CARD_NOT_INSTALLED)
        self.games_card = Card("Your games", "Mark them for Steam and press X to play.")
        self.settings_card = Card("Settings", "Screen, game and controller settings")
        self.log_card = Card("Log", "This app's log file.")
        for card in (self.rpcs3_card, self.games_card, self.settings_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        heading = QHBoxLayout()
        heading.addWidget(text_label("RPCS3", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.rpcs3_info = InfoPill("RPCS3", RPCS3_INFO)
        heading.addWidget(self.rpcs3_info, 0, Qt.AlignmentFlag.AlignTop)
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
        self.key_pane = KeyPane()
        self.log_pane = LogPane()
        self.keep_pane = ListPane("Remove", "Deciding what to keep", KEEP_INFO)
        for pane in (self.pane, self.games_pane, self.settings_pane, self.log_pane, self.key_pane, self.keep_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.rpcs3_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.log_pane: self.log_card,
                      self.key_pane: self.games_card, self.keep_pane: self.games_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.worker.said.connect(self._said)
        self.rpcs3_card.focused.connect(self.show_rpcs3)
        self.rpcs3_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.game_picked)
        self.keep_pane.list.picked.connect(self.toggle_keep)
        self.confirm_key = False                        # Remove key pressed once
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("accept", self.a_action)
        self.bind("y", self.y_action)
        self.bind("x", self.x_action)
        self.bind("previous", self.lb_action)
        self.bind("next", self.rb_action)
        self.bind("lt", self.lt_action)
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
        self.read_rpcs3()
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, RPCS3's files brought to what the app owns,
        and the focus on the RPCS3 card."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.read_rpcs3()
        self.refresh()
        self.refresh_games()
        self.rpcs3_card.setFocus()
        self.take_firmware()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def read_rpcs3(self) -> None:
        """RPCS3's drives, the firmware's version and the disc games it knows, from its files."""
        self.hdd0_game, self.dev_flash = userdata.drives(self.home)
        self.firmware = userdata.firmware_version(self.dev_flash)
        self.known = list(userdata.known_games(self.home).values())

    def show_rpcs3(self) -> None:
        self.show_pane(self.pane)
        self.take_firmware()

    def take_firmware(self) -> None:
        """The firmware put in Games\\PS3\\Firmware (owner, 01-11-2026: taken in automatically) given to RPCS3 while
        it is installed and closed and the app is not busy, once per file: a file whose version is installed already
        is left alone, and so is the file given to RPCS3 last, as it is (FIRMWARE_TAKEN, its name, size and time), so
        one RPCS3 refused is not given again on every focus; a changed or other file is."""
        if self.busy or not emulator.installed(self.home):
            return
        pup = library.firmware_file(self.user_home)
        key = library.file_key(pup) if pup is not None else ""
        if not key or key == self.settings.value(FIRMWARE_TAKEN, ""):
            return
        version = userdata.pup_version(pup)
        if version and version == self.firmware or self.running(self.home):
            return
        self.settings.setValue(FIRMWARE_TAKEN, key)
        self.install_firmware(pup)

    def prepare(self) -> bool:
        """RPCS3's files brought to what the app owns (userdata.prepare_gui and write_pads) while RPCS3 is installed
        and not running; whether its files may be written now."""
        if not emulator.installed(self.home) or self.running(self.home):
            return False
        try:
            done = userdata.prepare_gui(self.home)
            if userdata.write_pads(self.home):
                done.append(f"player 1 on {userdata.XINPUT_DEVICE}")
        except OSError as error:
            self.log.error(f"RPCS3's settings could not be written: {error}")
            return False
        if done:
            self.log.info(f"RPCS3 set up: {', '.join(done)}.")
        return True

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy and self._job == "delete":
            return "Files are being deleted (Your games).", "", ""
        if self.busy and self._job in ("firmware", "packages"):
            return self.stage, "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading RPCS3 {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if version != emulator.VERSION:
            return f"This app installs RPCS3 {emulator.VERSION}: the Y button updates it.", "", "Update"
        missing = self.runtime_missing()
        if missing:
            return (f"RPCS3 needs Microsoft's Visual C++ runtime ({', '.join(missing)} missing in System32): "
                    "install vc_redist.x64.exe from Microsoft, then open the app again.", "", "")
        if not self.firmware:
            return (f"No firmware yet: put PS3UPDAT.PUP in {private(library.firmware_home(self.user_home))}, and "
                    "RPCS3 installs it.", "", "")
        return "", "", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        rows = [("Installed", version or "not installed"), ("This app installs", emulator.VERSION),
                ("Firmware", self.firmware or "none yet")]
        total = sum(seconds for seconds, _ in userdata.play_times(self.home).values())
        if total:
            rows.append(("Play time", userdata.played(total)))
        return [*rows, ("Folder", wrappable(self.home))]

    def setting_value(self, setting: Setting) -> str:
        return rpcs3_settings.read_setting(self.home, setting)

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
            status = "Press the X button again to remove RPCS3: its folder, with the firmware and your saves, stays."
        self.status.setText(self.message or status)
        self.rpcs3_card.set_text(CARD_INSTALLED if emulator.installed(self.home) else CARD_NOT_INSTALLED)
        if self.busy and self._job == "packages":
            self.games_pane.status.setText(status)      # the packages are installed from Your games: the run there
        self.refresh_settings()
        self.update_legend()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(self.setting_value(setting))}" if ready
                          else setting.label)
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
        the same), then core's Menu Info, B Back (in a pane, and on the key page and the whole log) and View Exit. A
        press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []),
                     *([("X", "Press again" if self.confirm_remove else "Remove RPCS3")] if installed else []),
                     *([("Y", other)] if other else [])]
        elif pane is self.games_pane:
            focused = self.games_pane.list.focused()
            if focused.startswith("pkg:"):
                items = [("A", "Install"), ("X", "Install all"), ("Y", "Update Steam"),
                         ("LB", "Steam artwork"), ("LT", "Refresh")]
            else:
                items = [("A", "Steam mark"), *([("X", "Play")] if focused else []), ("Y", "Update Steam"),
                         ("LB", "Steam artwork"), *([("RB", "Remove game")] if focused else []), ("LT", "Refresh")]
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key"),
                     KEYBOARD]
        elif pane is self.keep_pane:
            item = next((i for i in self.keep_items if i.key == self.keep_pane.list.focused()), None)
            items = [*([("A", "Keep" if item.delete else "Delete")] if item is not None else []),
                     ("X", "Delete marked")]
        on_a_page = pane in (self.key_pane, self.keep_pane) or self.log_pane.viewing
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def game_folders(self) -> list[Path]:
        """The app's own Games\\PS3 folders (made when missing): the user's, then each SD card's."""
        return library.fixed(self.user_home, self.drives)

    def scan(self) -> list[Game]:
        """The games in the app's Games\\PS3 folders, installed in RPCS3 and known to it."""
        return scan(self.game_folders(), self.hdd0_game, self.known)

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games, the packages and licenses that wait, which games are in Steam (*in_steam* when given: what
        Update Steam read back, else Steam's file now), and the list."""
        self.games = self.scan()
        self.packages, self.licenses = userdata.waiting(self.game_folders(), self.hdd0_game.parent)
        kept = self.kept_packages()
        self.packages = [p for p in self.packages if library.kept_key(p.path) not in kept]   # the user kept them
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
        found = {str(g.eboot): renamed.identity(g.title_id, g.eboot) for g in self.games}
        known = renamed.load(self.settings)
        self.moved = renamed.follow(known, found, self.in_steam)     # renamed or moved: the mark goes along
        renamed.remember(self.settings, known, found, self.in_steam)
        self.marked = ({f for f in self.marked if f in found}
                       | {f for f in [*self.in_steam, *self.moved] if f in found and f not in self._unmarked})
        self.show_games()
        if self.moved:
            self.games_pane.status.setText(self.moved_text())

    def moved_text(self) -> str:
        """The status line for the games in Steam found again under a new name or in another folder."""
        return renamed.said(g.title for g in self.games if str(g.eboot) in self.moved)

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        own = self.game_folders()
        in_steam = sum(1 for g in self.games if str(g.eboot) in self.in_steam)
        waiting = len(self.packages) + len(self.licenses)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(own)} folder(s) and in RPCS3"
                             + (f", {waiting} to install" if waiting else "")
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        rows = [(str(g.eboot), self.game_text(g)) for g in self.games]
        rows += [(f"pkg:{p.path}", "  ·  ".join(t for t in (p.path.stem, p.serial, "PKG update" if p.patch else "PKG")
                                               if t)) for p in self.packages]
        rows += [(f"pkg:{p}", f"{p.name}  ·  License") for p in self.licenses]   # short, or the row is cut off
        if not rows:
            pane.status.setText(pane.status.text() or
                                f"No games yet: put your disc games, .pkg files and .rap licenses in "
                                f"{private(own[0])}, then the X button installs the packages.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        mark = "✓ Steam" if str(game.eboot) in self.marked else ""
        changed = ((str(game.eboot) in self.marked) != (str(game.eboot) in self.in_steam)
                   or str(game.eboot) in self.marked and str(game.eboot) in self.outdated)
        parts = (game.title, game.title_id, "" if game.startable else "no PS3_DISC.SFB",
                 mark + (" (Update Steam)" if changed else ""))
        return "  ·  ".join(p for p in parts if p)

    def game_picked(self, key: str) -> None:
        """A on a row: a game's Steam mark, or a package or license installed."""
        if key.startswith("pkg:"):
            path = Path(key[4:])
            self.install_waiting([p for p in self.packages if p.path == path], [p for p in self.licenses if p == path])
        else:
            self.mark_game(key)

    def play_game(self) -> None:
        """X on a game: started through Steam (owner, 29-10-2026), which starts RPCS3 with it full screen as its
        shortcut says; Steam starts first when it does not run. A game not in Steam yet says how it gets there; on a
        device without Steam RPCS3 starts it itself."""
        key = self.games_pane.list.focused()
        game = next((g for g in self.games if str(g.eboot) == key), None)
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
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): RPCS3 started with it full screen,
        as its Steam shortcut would start it, outside the app's bundle (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install RPCS3 first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"RPCS3 could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in RPCS3 failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in RPCS3… {play.QUIT_HINT}")
        self.log.info(f"Starting {game.title} in RPCS3, without Steam.")

    # The packages and licenses in the game folders, and Remove game

    def install_waiting(self, packages: list[userdata.PackageInfo], licenses: list[Path]) -> None:
        """A on a PKG or a License row, or X Install all (owner, 30-10-2026: drop the packages in the folder, the
        manager takes care of them): through RPCS3 itself, without its window (--headless --installpkg), once per
        file: the licenses (.rap, .edat) first, which RPCS3 copies into its exdata, then the packages in
        userdata.install_order (the games and DLC, then the updates: an update needs its game installed), each into
        RPCS3's dev_hdd0\\game. RPCS3's exit code says nothing of the outcome, so each run's result is read from
        RPCS3's log, and the games and licenses that came are counted. A package RPCS3 installed without a problem
        is not deleted by itself (owner, 01-11-2026: before deleting anything, let the user decide what to keep): the
        keep page lists them when the job ends (show_installed); the licenses stay."""
        status = self.games_pane.status
        if self.busy:
            status.setText(BUSY)
            return
        if not emulator.installed(self.home):
            status.setText(NEEDS_RPCS3)
            return
        if self.running(self.home):
            status.setText("RPCS3 is open: close it first; it installs while it is closed.")
            return
        if not packages and not licenses:
            status.setText(NOTHING_TO_INSTALL)
            return
        self.prepare()
        ordered = [*licenses, *(info.path for info in userdata.install_order([p.path for p in packages]))]
        what = " and ".join(part for part in (f"{len(packages)} package(s)" if packages else "",
                                              f"{len(licenses)} license(s)" if licenses else "") if part)
        name = ordered[0].name if len(ordered) == 1 else "the Games\\PS3 folders"
        hdd0, home, run = self.hdd0_game, self.home, self.run_headless
        log_path = userdata.rpcs3_log(home)
        before = _packages_in(hdd0)

        def job() -> tuple[bool, str, list[Path]]:
            report = userdata.InstallReport()
            installed: list[Path] = []
            for n, file in enumerate(ordered, 1):
                if len(ordered) > 1:
                    self.stage = (f"RPCS3 installs {n} of {len(ordered)}: {file.name}, without its window… a large "
                                  "package takes minutes.")
                try:
                    run(home, "--installpkg", str(file))
                except OSError as error:
                    return False, f"RPCS3 could not be started: {error}", installed
                one = userdata.read_install_report(log_path)
                report.extend(one)
                if file.suffix.lower() in userdata.PACKAGE_SUFFIXES and one.installed and not one.problems:
                    installed.append(file)
            games, copied = _packages_in(hdd0)
            ok, text = install_message(report, len(games - before[0]), len(copied - before[1]), name)
            return ok, text, installed
        self.busy, self.message = True, ""
        self._job = "packages"
        self.stage = (f"RPCS3 installs {what}, without its window… it starts once per file, and a large package "
                      "takes minutes.")
        self.progress_timer.start()                     # the line says which file it is on
        self.refresh()
        self.log.info(f"RPCS3 installs {what}: {', '.join(str(f) for f in ordered)}.")
        self.worker.run(job)

    def remove_game(self) -> None:
        """RB on a game (owner, 30-10-2026: a game that no longer plays goes): the keep page lists what would go
        (owner, 01-11-2026: before deleting anything, let the user decide what to keep): a disc game's folder in
        Games\\PS3 and its update in dev_hdd0\\game, or an installed game's folder there (library.removal), and its
        Steam shortcut. Its saves and the licenses are never listed: they stay in RPCS3's folder."""
        key = self.games_pane.list.focused()
        game = next((g for g in self.games if str(g.eboot) == key), None)
        if game is None:
            return
        if self.busy:
            self.games_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.games_pane.status.setText("RPCS3 is open: quit the game first, then remove it.")
            return
        folders, why = library.removal(game, self.game_folders(), self.games, self.hdd0_game)
        if not folders:
            self.games_pane.status.setText(private(why))
            return
        if game.disc:
            labels = [f"{folders[0].name}, the game", *(f"{f.name}, its update in RPCS3" for f in folders[1:])]
        else:
            labels = [f"{folders[0].name}, the game in RPCS3 with its update and add-ons"]
        items = [keep.Item(str(f), label, (f,)) for f, label in zip(folders, labels)]
        if key in self.in_steam and self.steam_dir is not None:
            items.append(keep.Item(STEAM_ITEM, "Steam shortcut"))
        self.show_keep(f"Remove {game.title}", items, game)

    def show_installed(self, packages: list[Path]) -> None:
        """The packages RPCS3 installed without a problem, on the keep page (owner, 01-11-2026): each marked Delete
        at first; B keeps them all. They are kept in the settings already (PACKAGES_KEPT), so one kept is no row of
        Your games and X Install all leaves it alone, until the file changes."""
        self.set_kept(self.kept_packages() | {library.kept_key(p) for p in packages})
        self.refresh_games()
        self.show_keep("Installed: delete the packages?",
                       [keep.Item(str(p), f"{p.name}, installed in RPCS3", (p,)) for p in packages], None)

    # The keep page (core's keep): what would go, a row each, every one marked Delete at first

    def show_keep(self, heading: str, items: list[keep.Item], game: Game | None) -> None:
        keep.measure(items)
        self.keep_items, self.keep_game = items, game
        self.keep_pane.heading.setText(heading)
        self.keep_pane.status.setText("")
        self.show_keep_rows()
        self.show_pane(self.keep_pane)
        self.focus_list(self.keep_pane)
        self.update_legend()

    def show_keep_rows(self) -> None:
        self.keep_pane.summary.setText(f"The X button deletes the rows marked Delete and frees "
                                       f"{keep.human(keep.total(self.keep_items))}; the A button keeps a row. The B "
                                       "button goes back and deletes nothing.")
        self.keep_pane.list.set_items(keep.rows(self.keep_items))

    def toggle_keep(self, key: str) -> None:
        """A on a row: Delete becomes Keep and back; the focus stays on the row."""
        if keep.toggle(self.keep_items, key) is None:
            return
        self.show_keep_rows()
        self.keep_pane.list.pills[key].setFocus()
        self.update_legend()

    def leave_keep(self, said: str = "") -> None:
        self.keep_items, self.keep_game = [], None
        self.show_pane(self.games_pane)
        self.games_pane.status.setText(said)
        self.focus_list(self.games_pane)

    def back_from_keep(self) -> None:
        """B on the keep page: nothing deleted."""
        packages = self.keep_game is None
        self.leave_keep("Nothing was deleted." + (" The packages stay, and are not listed again." if packages else ""))

    def delete_marked(self) -> None:
        """X on the keep page: the rows marked Delete go, off the window's thread: the Steam shortcut first (Steam
        closed for it), then the files and folders (keep.delete, read-only ones too); then back to Your games, where
        the status line says what was deleted and what was kept."""
        chosen = keep.chosen(self.keep_items)
        if not chosen:
            self.keep_pane.status.setText(NOTHING_MARKED)
            return
        if self.busy:
            self.keep_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.keep_pane.status.setText("RPCS3 is open: quit the game first, then delete.")
            return
        game = self.keep_game
        kept = [i.label for i in self.keep_items if not i.delete]
        deleted = [i.label for i in chosen]
        paths = [p for i in chosen for p in i.paths]
        steam_dir = self.steam_dir if game is not None and any(i.key == STEAM_ITEM for i in chosen) else None
        closed, program, existing = self.steam_closed, emulator.program(self.home), self.in_steam
        what = f"{game.title}: " if game is not None else ""
        saves = " Its saves stay in RPCS3's folder." if game is not None else ""

        def job() -> tuple[bool, str, dict[str, str] | None]:
            found = None
            if steam_dir is not None:
                ok, said, found = library.update_steam(steam_dir, [], [game], program, LOGO_PATH, existing, closed)
                if not ok:
                    return False, f"{what}nothing was deleted. {said}", None
            failed = keep.delete(paths)
            rest = f" Kept: {', '.join(kept)}." if kept else ""
            if failed:
                return False, f"{what}not everything was deleted: not {', '.join(failed)}.{rest}{saves}", found
            return True, f"{what}deleted {', '.join(deleted)}.{rest}{saves}", found
        self.deleting = paths
        self.leave_keep(f"Deleting {', '.join(deleted)}…")
        self.busy, self.message = True, ""
        self._job = "delete"
        self.log.info(f"Deleting {', '.join(str(p) for p in paths)}"
                      + (", and a Steam shortcut." if steam_dir is not None else "."))
        self.worker.run(job)

    def kept_packages(self) -> set[str]:
        """The installed packages the user kept (library.kept_key each), from the app's settings."""
        stored = self.settings.value(PACKAGES_KEPT, [])
        stored = [stored] if isinstance(stored, str) else list(stored or [])
        return {s for s in stored if s}

    def set_kept(self, kept: set[str]) -> None:
        self.settings.setValue(PACKAGES_KEPT, sorted(kept))

    # The SteamGridDB key (the BC250 app's Covers… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's cover." if old else
                                     "No key: Update Steam draws the pictures from the game's own.")
        self.show_pane(self.key_pane)
        self.key_pane.field.setFocus()

    def paste_key(self) -> None:
        """The key from the clipboard (copied in a browser on the device): typing 32 characters on a handheld is
        the hard way."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.key_pane.status.setText("The clipboard is empty: copy the key on SteamGridDB's API page first.")
            return
        self.key_pane.field.setText(text.split()[0])
        self.key_pane.status.setText("The key is in the field: the A button saves it.")

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
        elif pane is self.pane:
            self.main_action()
        elif pane is self.log_pane:
            self.view_log()

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_action()
        elif pane is self.key_pane:
            self.paste_key()
        elif pane is self.keep_pane:
            self.delete_marked()
        elif pane is self.games_pane:
            if self.games_pane.list.focused().startswith("pkg:"):
                self.install_waiting(self.packages, self.licenses)
            else:
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
        if pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.games_pane:
            self.remove_game()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def lt_action(self) -> None:
        if self.panes.currentWidget() is self.games_pane:
            self.rescan()

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {str(g.eboot) for g in self.games}:
            return
        if key in self.marked:
            self.marked.discard(key)
            if key in self.in_steam or key in self.moved:
                self._unmarked = self._unmarked | {key}
        else:
            self.marked.add(key)
            self._unmarked = self._unmarked - {key}
        self.show_games()
        self.games_pane.list.pills[key].setFocus()

    def rescan(self) -> None:
        """LT Refresh: the game folders read again, for a game put there, renamed or taken away while the app is open
        (owner, 01-11-2026: it showed only after the app started again); the focus stays on its game."""
        if self.busy:
            if self._job != "steam":                    # Steam's own job says so on the line already
                self.games_pane.status.setText(BUSY)
            return
        self.refresh_games()
        changed = library.pending(self.games, self.marked, self.in_steam, self.outdated)
        self.games_pane.status.setText(f"The game folders were read again: {len(self.games)} game(s)."
                                       + (f" {self.moved_text()}" if self.moved else
                                          " Steam does not match the marks yet: the Y button updates it."
                                          if changed and self.steam_dir is not None else ""))

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
            self.games_pane.status.setText("Install RPCS3 first (the RPCS3 card): the games in Steam start it.")
            return
        if add and not self.firmware:
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

    # Log

    def refresh_log(self) -> None:
        rows: list[tuple[str, str]] = [("RPCS3's folder", wrappable(self.home))]
        if emulator.installed(self.home):
            rows += [("Firmware", self.firmware or "none yet"),
                     ("Installed games", str(len(installed_games(self.hdd0_game)))),
                     ("Saves", str(userdata.saves(self.hdd0_game)))]
        rows.append(("Games", wrappable(self.game_folders()[0])))   # Firmware is in it
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
        """A on a setting's row: its next value, written now, unless RPCS3 runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(self.setting_value(setting))
        try:
            rpcs3_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, X, Y, LB and RB on the RPCS3 pane

    def main_action(self) -> None:
        """A on the RPCS3 card or pane: Install while RPCS3 is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._job = "install"
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing RPCS3 {emulator.VERSION} in {self.home}.")
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
        if job == "delete":
            ok, text, found = result if isinstance(result, tuple) else (False, f"Nothing was deleted: {result}", None)
            self.games_pane.status.setText(private(text))
            (self.log.info if ok else self.log.error)(text)
            gone = {library.kept_path(p) for p in self.deleting if not p.exists()}
            if gone:                                    # a package deleted: no longer kept
                self.set_kept({k for k in self.kept_packages() if k.split("|")[0] not in gone})
            self.deleting = []
            self.refresh()
            self.refresh_games(found)
            if self.panes.currentWidget() is self.games_pane:
                self.focus_list(self.games_pane)
            return
        if job == "install":
            if isinstance(result, Exception):
                self.message = private(f"RPCS3 could not be installed: {result}")
                self.log.error(f"Installing RPCS3 failed: {result}")
            else:
                self.message = f"RPCS3 {result} is installed."
                self.log.info(f"RPCS3 {result} installed.")
                self.prepare()                          # before its first start
        else:                                           # the firmware or the packages: (ok, what to say[, installed])
            ok, text, *rest = result if isinstance(result, tuple) else (False, f"RPCS3 could not be started: {result}")
            installed = rest[0] if job == "packages" and rest else []
            if job == "packages":
                self.games_pane.status.setText(private(text))
            else:
                self.message = text
            (self.log.info if ok else self.log.error)(text)
        self.read_rpcs3()
        self.refresh()
        self.refresh_games()
        if job == "install":
            self.take_firmware()                        # RPCS3 is there now: the firmware put in for it
        elif job == "packages" and installed:
            self.show_installed(installed)              # the user decides what to keep (owner, 01-11-2026)

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
            missing = [g.title for g in add if str(g.eboot) not in found]
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
        """X Remove RPCS3 asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "RPCS3 is not installed: there is nothing to remove."
            self.refresh()
            return
        if self.running(self.home):
            self.message = "RPCS3 is open: close it first, then remove it."
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
            self.message = f"RPCS3 could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing RPCS3 failed: {error}")
        else:
            self.message = ("RPCS3 is removed. Its folder, with the firmware, your saves, its settings and the "
                            "installed games, stays.")
            self.log.info("RPCS3 removed.")
        self.refresh()

    def _ready_for_rpcs3(self) -> bool:
        """Whether RPCS3 can be given a job now (a firmware or a package install); else the status line says why."""
        if self.busy:
            self.message = BUSY
        elif not emulator.installed(self.home):
            self.message = NEEDS_RPCS3
        elif self.running(self.home):
            self.message = "RPCS3 is open: close it first; it installs while it is closed."
        else:
            return True
        self.refresh()
        return False

    def install_firmware(self, pup: Path) -> None:
        """The firmware put in Games\\PS3\\Firmware (take_firmware) through RPCS3 itself, without its window
        (--headless --installfw), as the window's job; the result from RPCS3's log and the firmware's version file.
        The file stays where it is."""
        if not self._ready_for_rpcs3():
            return
        self.prepare()
        home, dev_flash, run = self.home, self.dev_flash, self.run_headless
        before = self.firmware

        def job() -> tuple[bool, str]:
            try:
                run(home, "--installfw", str(pup))
            except OSError as error:
                return False, f"RPCS3 could not be started: {error}"
            version, error = userdata.read_firmware_report(userdata.rpcs3_log(home))
            now = userdata.firmware_version(dev_flash)
            if version or (now and now != before):
                return True, f"PS3 firmware {version or now} is installed."
            return False, (f"RPCS3 did not install the firmware: {error}" if error else
                           f"RPCS3 did not install {pup.name}. Its log (log\\RPCS3.log in its folder) says why.")
        self.busy, self.message = True, ""
        self._job = "firmware"
        self.stage = f"RPCS3 installs {pup.name}, without its window… it takes a minute or two."
        self.refresh()
        self.log.info(f"RPCS3 installs the firmware {pup}.")
        self.worker.run(job)

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
        """B goes back (the suite's rule, owner 29-10-2026): the whole log to its summary, the key page to Your games
        (nothing saved), a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.keep_pane:
            self.back_from_keep()
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the job (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = {"steam": "Press View again to exit: Steam's shortcuts may be left half changed.",
                            "firmware": "Press View again to exit: RPCS3 goes on installing the firmware by itself.",
                            "packages": "Press View again to exit: RPCS3 goes on with the package it is on, "
                                        "the rest waits for the next time.",
                            "delete": "Press View again to exit: what is being deleted is left half deleted."}.get(
                self._job, "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
