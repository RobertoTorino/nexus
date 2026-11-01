# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as Windows Portable Test lays it out: the cards on the left (PCSX2, Your
games, Settings, Memory cards, Log: the BC250 suite's PCSX2 Manager's parts, owner 29-10-2026), what the focused one
shows on the right, the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: "we have update steam 2 times ... use that bottom row for actions", then one way
everywhere). Core's rule ends the legend: B goes back (a pane to its card, a card's saves to the cards, the key page
to the games), View exits the app and Menu shows the information of the pane that shows. Nothing is browsed to
(owner, 30-10-2026): the games and the BIOS are put in the app's own folders (library.fixed: Games\\PS2 and
Games\\PS2\\BIOS in your user folder), and the app takes care of them.

The Your games pane (panes.py, library.py): the games in the app's own Games\\PS2 folders (owner, 30-10-2026: the
games are dropped there; library.fixed, an SD card's too), played from Steam (owner, 29-10-2026: X Play starts one in
Steam; on a device without Steam X starts PCSX2 with it itself, owner 30-10-2026: a fallback, as its shortcut would
start it); A marks one for Steam, Y Update Steam makes Steam's shortcuts match the marks; LB Steam artwork keeps the
SteamGridDB key; RB Remove game shows what would go, the disc image and the shortcut in Steam, on the keep page.
Nothing is deleted before the user decides what to keep (owner, 01-11-2026; core's keep): every row starts as Delete,
A turns one to Keep and back, X deletes the rows still marked Delete, B goes back and deletes nothing. Steam's library
is the portal's RT Steam (owner, 30-10-2026: Open Steam moved there). The Memory cards pane: the cards and the saves
on each, X New card and Y Copy card. The Log pane: PCSX2's last run, where Games\\PS2 is and the newest lines of the
app's log; A (or a tap on the pane) shows the whole log in the pane, B goes back.

The PCSX2 pane: what is installed, where, the BIOS; A Install until PCSX2 is installed, Y Reinstall or Update, LB
Remove BIOS (the keep page: PCSX2's copy and the one in Games\\PS2\\BIOS) and RB Remove PCSX2 (a second press).
The BIOS dump put in Games\\PS2\\BIOS is copied into PCSX2's bios folder when the app opens and when the PCSX2 card
gets the focus (userdata.sync_bios, only what is new or changed). A press that cannot act now says why on the status
line. Nothing downloads before A. The download, the unpacking and the keep page's deleting run off the window's
thread; the pane counts the megabytes. View (exit) while they run asks first, as the portal does.

The Settings pane: PCSX2's settings that matter on the handheld, in tabs (LB and RB: Picture, Game, Controller, On
screen), a row each with its value; A steps to the next value and writes it into PCSX2.ini at once (pcsx2_settings),
never while PCSX2 runs (it writes its own settings back when it closes). What the app owns in PCSX2.ini is set after
an install and when the window opens (pcsx2_settings.prepare), so PCSX2 opens ready to play: the BC250 suite's PCSX2
Manager's rules."""

from __future__ import annotations

import datetime
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, keep, platform, play, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, KEYBOARD, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)

from . import (APP_ID, APP_NAME, LOGO_PATH, __version__, catalogue, emulator, library, memcards, pcsx2_settings,
               shortcuts, userdata)
from .games import Game, scan
from .panes import CARDS_INFO, GAMES_INFO, KEEP_INFO, KeyPane, ListPane, LogPane
from .pcsx2_settings import OWN, TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and View (exit) while PCSX2 is being installed, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
ABOUT = ("PCSX2, the PlayStation 2 emulator, installed for your own user in portable mode: its settings, the BIOS, "
         "the memory cards and the save states stay in its folder.")
CARD_HEIGHT = 100               # five cards and their gaps fit the column at 720 px high
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
BACK_KEY = "‹"            # the first row of a card's saves: back to the cards
RUNNING = "PCSX2 is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install PCSX2 first: the settings are in its folder."
BUSY = "Wait a moment: the app is still busy with the step before."
BIOS_NEEDS_PCSX2 = "Install PCSX2 first: the BIOS goes in its folder."
NO_BIOS_TO_REMOVE = ("There is no BIOS to remove: put your own console's dump in the BIOS folder of Games\\PS2, and "
                     "the app gives it to PCSX2.")
NOTHING_MARKED = "Nothing is marked Delete: B goes back, and nothing is deleted."
NO_CARD_TO_COPY = "Copy card copies the card the focus was on last: move to a card in the list first."
ALL_SETTINGS = pcsx2_settings.SETTINGS
BIOS_INFO = (
    "PCSX2 needs the PS2's BIOS to start any game, and it is not ours to give: it comes from your own PlayStation 2. "
    "Dump it with biosdrain, a homebrew tool run on the console (PCSX2's BIOS page, "
    f"{userdata.BIOS_HELP_URL}, says how), and copy the dump to the device. A dump is a .bin or .rom file of 4 MB, "
    "often with files beside it under the same name (.nvm, .mec, .erom).\n\n"
    "Put the dump, with the files beside it, in the BIOS folder of your Games\\PS2 folder (Games\\PS2\\BIOS in your "
    "user folder). The app copies it into PCSX2's bios folder by itself when it opens and each time the PCSX2 card "
    "gets the focus, and makes PCSX2 use it when it has no other. The LB button (Remove BIOS) shows the one PCSX2 "
    "uses, in PCSX2's bios folder and in Games\\PS2\\BIOS, with its files, and you decide what to keep before "
    "anything is deleted; a copy kept in Games\\PS2\\BIOS goes into PCSX2 again. Neither works while PCSX2 runs: "
    "it writes its settings back when it closes.")
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; PCSX2 "
                  "reads the settings the next time it opens.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


class _Worker(QObject):
    """Runs the install off the window's thread; done (the version, or the exception) and what it is doing (said)
    arrive on the window's."""

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


PICK_A_GAME = "Put the focus on a game first: the X button starts it."
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")
# Without a BIOS PCSX2 stops at its own Startup Error window (seen on the Ally, 29-10-2026): a game in Steam would not
# start
NO_BIOS = ("Put your console's BIOS in the BIOS folder of Games\\PS2 first (the PCSX2 card names it): PCSX2 cannot "
           "start a game without it.")


class SettingsPane(Pane):
    """The settings in tabs (owner, 29-10-2026: "we can use tabs in the settings page to add more"): LB and RB step
    through Picture, Game, Controller and On screen, a tap picks one; a tab is a page of rows, "Renderer: Automatic",
    and A on one steps to the next value (the window writes it). Seven rows fit a page at 720 px high. The
    information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("PCSX2's settings", TAB_INFO[TABS[0][0]])
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
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 any_running: Callable[[], bool] = memcards.pcsx2_running, settings: QSettings | None = None,
                 open_url: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *user_home*: the user's folder
        (where Games\\PS2 is); *drives*: the removable drives, whose Games\\PS2 is looked in too; *settings*: the
        app's (its .ini, create_app's); *open_url*: hands a steam:// address to Steam (Play); *start*: starts a
        program on its own (PCSX2 with a game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running = install, running
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…"
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed, self.any_running = steam_closed, any_running
        self._job = ""                                  # "steam", "remove" or "bios" while one runs in the worker
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.user_home, self.drives = user_home, drives
        self.settings = settings if settings is not None else QSettings()
        self.open_url, self.start_program = open_url, start
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.keeping: list[keep.Item] = []              # the keep page's rows, while it shows (core's keep)
        self.keep_game: Game | None = None              # the game Remove game shows them for; None: the BIOS
        self.keep_note = ""                             # what the keep page says stays anyway
        self.card_view = ""                             # "" the cards, else the card whose saves show
        self.last_card = ""                             # the card the focus was on last: Copy card copies it

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
        self.pcsx2_card = Card("PCSX2", "Install, update or remove it, and its BIOS.")
        self.games_card = Card("Your games", "Mark them for Steam, or remove them.")
        self.settings_card = Card("Settings", "The picture, the controllers and how PCSX2 opens.")
        self.cards_card = Card("Memory cards", "The cards and the saves on them.")
        self.log_card = Card("Log", "PCSX2's last run, and this app's log.")
        for card in (self.pcsx2_card, self.games_card, self.settings_card, self.cards_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        heading = QHBoxLayout()
        heading.addWidget(text_label("PCSX2", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.bios_info = InfoPill("The BIOS", BIOS_INFO)
        heading.addWidget(self.bios_info, 0, Qt.AlignmentFlag.AlignTop)
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
        self.cards_pane = ListPane("Memory cards", "The memory cards", CARDS_INFO)
        self.log_pane = LogPane()
        self.keep_pane = ListPane("Remove", "What to keep", KEEP_INFO)
        for pane in (self.pane, self.games_pane, self.settings_pane, self.cards_pane, self.log_pane, self.key_pane,
                     self.keep_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.pcsx2_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.cards_pane: self.cards_card,
                      self.log_pane: self.log_card, self.key_pane: self.games_card,
                      self.keep_pane: self.games_card}         # the keep page's: the card it came from
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._installed)
        self.worker.said.connect(self._said)
        self.pcsx2_card.focused.connect(self.show_pcsx2)
        self.pcsx2_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.cards_card.focused.connect(lambda: self.show_pane(self.cards_pane))
        self.cards_card.activated.connect(lambda: self.focus_list(self.cards_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.mark_game)
        self.confirm_key = False                        # Remove key pressed once
        self.cards_pane.list.picked.connect(self.card_picked)
        self.cards_pane.list.current.connect(self._card_focused)
        self.keep_pane.list.picked.connect(self.toggle_keep)
        self.keep_pane.list.current.connect(lambda _key: self.update_legend())
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
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, PCSX2's settings brought to what the app owns,
        and the focus on the PCSX2 card."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.sync_bios()
        self.refresh()
        self.refresh_games()
        self.refresh_cards()
        self.pcsx2_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def show_pcsx2(self) -> None:
        self.sync_bios()
        self.show_pane(self.pane)

    def sync_bios(self) -> None:
        """The BIOS dump put in Games\\PS2\\BIOS (owner, 30-10-2026: drop it there, the app takes care of it) copied
        into PCSX2's bios folder while PCSX2 is installed and closed (it writes PCSX2.ini back when it closes), the new
        or changed files only; PCSX2 is made to use it when the one PCSX2.ini names is not there. What was copied goes
        to the status line and the log."""
        if self.busy or not emulator.installed(self.home) or self.running(self.home):
            return
        source = library.bios_home(self.user_home)
        try:
            copied = userdata.sync_bios(source, userdata.bios_dir(self.home))
            dumps = self.bios_dumps()
            if copied and dumps and pcsx2_settings.chosen_bios(self.home) not in {d.name for d in dumps}:
                taken = next((d for d in dumps if d.name in copied), dumps[0])
                pcsx2_settings.choose_bios(self.home, taken.name)
        except OSError as error:
            self.message = f"The BIOS was not copied: {error.strerror or error}"
            self.log.error(f"Copying the BIOS from {source} failed: {error}")
            self.refresh()
            return
        if not copied:
            return
        used = self.bios_used()
        self.message = (f"{len(copied)} BIOS file(s) taken from the BIOS folder"
                        + (f": PCSX2 uses {used.name}." if used is not None else "."))
        self.log.info(self.message)
        self.refresh()

    def prepare(self) -> bool:
        """pcsx2_settings.prepare() while PCSX2 is installed and not running; whether PCSX2.ini is ready."""
        if not emulator.installed(self.home) or self.running(self.home):
            return False
        try:
            done = pcsx2_settings.prepare(self.home)
        except OSError as error:
            self.log.error(f"PCSX2's settings could not be written: {error}")
            return False
        if done:
            self.log.info(f"PCSX2's settings: {', '.join(done)}.")
        return True

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Reinstall, Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy and self._job == "remove":
            return "A game is being removed (Your games).", "", ""
        if self.busy and self._job == "bios":
            return "The BIOS is being removed.", "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading PCSX2 {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if emulator.replaced(self.home):
            return (f"PCSX2 replaced itself with another build. The Y button (Reinstall) puts {emulator.VERSION} "
                    "back.", "", "Reinstall")
        if version != emulator.VERSION:
            return f"This app installs PCSX2 {emulator.VERSION}: the Y button updates it.", "", "Update"
        if self.bios_used() is None:
            return (f"PCSX2 needs your own console's BIOS: put the dump in "
                    f"{private(library.bios_home(self.user_home))}, and the app copies it into PCSX2.", "", "")
        return "", "", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        installed = version + (", replaced by another build" if version and emulator.replaced(self.home) else "")
        return [("Installed", installed or "not installed"), ("This app installs", emulator.VERSION),
                ("BIOS", self.bios_state()), ("Folder", wrappable(self.home))]

    def bios_dumps(self) -> list[Path]:
        return userdata.bios_files(userdata.bios_dir(self.home))

    def bios_used(self) -> Path | None:
        """The dump PCSX2 uses: the one PCSX2.ini names when it is there, else the first in the bios folder."""
        dumps = self.bios_dumps()
        chosen = pcsx2_settings.chosen_bios(self.home)
        return next((d for d in dumps if d.name == chosen), dumps[0] if dumps else None)

    def bios_state(self) -> str:
        """The BIOS row: "PCSX2 uses <name>", or why there is none (as the BC250 app's BIOS line)."""
        if not emulator.installed(self.home):
            return "install PCSX2 first"
        used = self.bios_used()
        if used is None:
            return (f"No BIOS yet: PCSX2 needs your own console's BIOS to start a game. Put the dump in "
                    f"{private(library.bios_home(self.user_home))}, and the app gives it to PCSX2.")
        others = [d.name for d in self.bios_dumps() if d != used]
        return f"PCSX2 uses {used.name}" + (f"; also there: {', '.join(others)}" if others else "")

    def setting_value(self, setting: Setting) -> str:
        if setting.key in OWN:
            return "true" if OWN[setting.key][0](self.home) else "false"
        return pcsx2_settings.read_setting(self.home, setting)

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
            status = "Press the RB button again to remove PCSX2: its BIOS, memory cards and settings stay."
        self.status.setText(self.message or status)
        installed = bool(emulator.installed(self.home))
        self.pcsx2_card.set_text("No BIOS yet: put it in the BIOS folder of Games\\PS2."
                                 if installed and self.bios_used() is None
                                 else "Install, update or remove it, and its BIOS.")
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
        the same), then core's Menu Info, B Back (in a pane, and on a card's saves, the key page and the whole log)
        and View Exit. A press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []), *([("Y", other)] if other else []),
                     *([("LB", "Remove BIOS"),
                        ("RB", "Press again" if self.confirm_remove else "Remove PCSX2")] if installed else [])]
        elif pane is self.games_pane:
            focused = self.focused_game()
            items = [("A", "Steam mark"), *([("X", "Play")] if focused else []), ("Y", "Update Steam"),
                     ("LB", "Steam artwork"),
                     *([("RB", "Remove game")] if focused else [])]
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.cards_pane:
            items = [*([] if self.card_view else [("A", "Saves")]), ("X", "New card"), ("Y", "Copy card")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key"),
                     KEYBOARD]
        elif pane is self.keep_pane:
            focused = self.focused_item()
            items = [*([("A", "Keep" if focused.delete else "Delete")] if focused else []), ("X", "Delete marked")]
        on_a_page = (pane in (self.key_pane, self.keep_pane) or self.log_pane.viewing
                     or (pane is self.cards_pane and bool(self.card_view)))
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def game_folders(self) -> list[Path]:
        """The app's own Games\\PS2 folders (made when missing): the user's, then each SD card's."""
        return library.fixed(self.user_home, self.drives)

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games in the app's own folders, which are in Steam (*in_steam* when given: what Update Steam read back,
        else Steam's file now), and the list."""
        self.games = scan(self.game_folders(), catalogue.titles(catalogue.folder(self.home)))
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
        found = {str(g.file) for g in self.games}
        self.marked = {f for f in self.marked if f in found} | {f for f in self.in_steam if f in found
                                                                  and f not in self._unmarked}
        self.show_games()

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        folders = self.game_folders()
        in_steam = sum(1 for g in self.games if str(g.file) in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(folders)} folder(s)"
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        rows = [(str(g.file), self.game_text(g)) for g in self.games]
        if not rows:
            pane.status.setText(pane.status.text() or
                                f"No games yet: put your disc images (ISO, CHD, CSO) in {private(folders[0])}, or in "
                                "Games\\PS2 on an SD card.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        mark = "✓ Steam" if str(game.file) in self.marked else ""
        changed = ((str(game.file) in self.marked) != (str(game.file) in self.in_steam)
                   or str(game.file) in self.marked and str(game.file) in self.outdated)
        return "  ·  ".join(p for p in (game.title, game.serial, mark + (" (Update Steam)" if changed else "")) if p)

    def focused_game(self) -> Game | None:
        """The game whose row has the focus."""
        key = next((key for key, pill in self.games_pane.list.pills.items() if pill.hasFocus()), None)
        return next((game for game in self.games if str(game.file) == key), None)

    def play(self) -> None:
        """X on a game: started through Steam, as its shortcut there (owner, 29-10-2026: a game started from the
        app; Steam keeps its controller layout and its overlay). Steam starts first when it is not open. On a device
        without Steam PCSX2 starts it itself. Without a BIOS it says so and starts nothing (owner, 30-10-2026: "we check
        for a BIOS since we are the manager"; PCSX2 would stop at its Startup Error window)."""
        game = self.focused_game()
        if game is None:
            self.games_pane.status.setText(PICK_A_GAME)
            return
        if emulator.installed(self.home) and self.bios_used() is None:
            self.games_pane.status.setText(NO_BIOS)
            return
        if self.steam_dir is None:
            self.play_without_steam(game)
            return
        try:
            number = (shortcuts.numbers(self.steam_dir) if self.steam_dir is not None else {}).get(str(game.file))
        except OSError as error:
            number = None
            self.log.error(f"Steam's shortcuts could not be read: {error}")
        if number is None:
            self.games_pane.status.setText(f"{game.title} is not in Steam yet: A marks it, then Y Update Steam puts "
                                           "it there.")
            return
        try:
            self.open_url(steam.play_url(number))
        except OSError as error:
            self.games_pane.status.setText(f"Steam could not be asked to start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in Steam failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in Steam… {play.QUIT_HINT}")
        self.log.info(f"Play: {game.title}, started in Steam.")

    def play_without_steam(self, game: Game) -> None:
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): PCSX2 started with it full screen,
        as its Steam shortcut would start it, outside the app's bundle (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install PCSX2 first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"PCSX2 could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in PCSX2 failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in PCSX2… {play.QUIT_HINT}")
        self.log.info(f"Play: {game.title}, started in PCSX2, without Steam.")

    def remove_game(self) -> None:
        """RB on a game (owner, 30-10-2026: a game that no longer plays goes): the keep page shows what would go, its
        disc image and its shortcut in Steam, and the user decides what to keep (owner, 01-11-2026: before deleting
        anything, let the user decide what to keep; core's keep). Its saves stay on the memory cards, and its folder
        stays."""
        game = self.focused_game()
        if game is None:
            return
        if self.busy:
            self.games_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.games_pane.status.setText("PCSX2 is open: quit the game first, then remove it.")
            return
        items = [keep.Item("file", f"{game.file.name} (the disc image)", (game.file,))]
        if str(game.file) in self.in_steam:
            items.append(keep.Item("steam", "The shortcut in Steam"))
        self.keep_game = game
        self.show_keep(f"Remove {game.title}", items, "Its saves stay on the memory cards.", self.games_card)

    # The keep page (core's keep): what Remove game and Remove BIOS would delete, the user decides what stays

    def show_keep(self, heading: str, items: list[keep.Item], note: str, card: Card) -> None:
        """The keep page for *items*, every row marked Delete at first, measured; *note* says what stays anyway; B
        goes back to *card*'s pane."""
        keep.measure(items)
        self.keeping, self.keep_note = items, note
        self.cards[self.keep_pane] = card
        self.keep_pane.heading.setText(heading)
        self.keep_pane.status.setText("")
        self.show_pane(self.keep_pane)
        self.show_keep_rows()
        self.focus_list(self.keep_pane)
        self.update_legend()

    def show_keep_rows(self) -> None:
        self.keep_pane.summary.setText(
            f"The X button deletes what is marked Delete ({keep.human(keep.total(self.keeping))}); the A button on a row "
            f"keeps it. The B button goes back and deletes nothing. {self.keep_note}")
        self.keep_pane.list.set_items(keep.rows(self.keeping))

    def focused_item(self) -> keep.Item | None:
        key = next((key for key, pill in self.keep_pane.list.pills.items() if pill.hasFocus()), None)
        return next((item for item in self.keeping if item.key == key), None)

    def toggle_keep(self, key: str) -> None:
        """A on a row: Delete becomes Keep and back; the focus stays on the row."""
        if keep.toggle(self.keeping, key) is None:
            return
        self.keep_pane.status.setText("")
        self.show_keep_rows()
        self.keep_pane.list.pills[key].setFocus()
        self.update_legend()

    def delete_marked(self) -> None:
        """X on the keep page: the rows still marked Delete deleted off the window's thread, the others kept."""
        if self.busy:
            self.keep_pane.status.setText(BUSY)
            return
        if not keep.chosen(self.keeping):
            self.keep_pane.status.setText(NOTHING_MARKED)
            return
        if self.running(self.home):
            self.keep_pane.status.setText("PCSX2 is open: quit it first, then delete.")
            return
        if self.keep_game is not None:
            self.delete_game(self.keep_game, self.keeping)
        else:
            self.delete_bios(self.keeping)

    def leave_keep(self, said: str) -> None:
        """Back to the pane the keep page came from, *said* on its status line."""
        self.keeping, self.keep_game = [], None
        self.keep_pane.list.set_items([])
        if self.cards[self.keep_pane] is self.games_card:
            self.show_pane(self.games_pane)
            self.games_pane.status.setText(said)
            self.focus_list(self.games_pane)
        else:
            self.message = said
            self.show_pane(self.pane)
            self.refresh()
            self.pcsx2_card.setFocus()

    def delete_game(self, game: Game, items: list[keep.Item]) -> None:
        """Remove game's deleting: the shortcut taken out of Steam when it is marked, then the disc image when it is,
        as the window's job."""
        chosen = keep.chosen(items)
        kept = [item.label for item in items if not item.delete]
        steam_dir = self.steam_dir if any(item.key == "steam" for item in chosen) else None
        paths = [path for item in chosen for path in item.paths]
        closed, program, existing = self.steam_closed, emulator.program(self.home), self.in_steam
        if steam_dir is not None:
            self.marked.discard(str(game.file))         # out of Steam: no mark left to ask for Update Steam

        def job() -> tuple[bool, str, dict[str, str] | None]:
            found = None
            if steam_dir is not None:
                ok, said, found = library.update_steam(steam_dir, [], [game], program, LOGO_PATH, existing, closed)
                if not ok:
                    return False, f"Nothing of {game.title} was deleted: {said}", None
            failed = keep.delete(paths)
            deleted = [item.label for item in chosen]
            text = (f"{game.title}: deleted {', '.join(deleted)}" + (f"; kept {', '.join(kept)}" if kept else "")
                    + ". Its saves stay on the memory cards.")
            if failed:
                return False, f"{text} Not deleted: {', '.join(failed)}.", found
            return True, text, found
        self.busy, self.message = True, ""
        self._job = "remove"
        self.leave_keep(f"Removing {game.title}…")
        self.log.info(f"Removing {game.title}: {', '.join(str(p) for p in paths) or 'nothing on the disk'}"
                      + (", and its Steam shortcut." if steam_dir is not None else ".")
                      + (f" Kept: {', '.join(kept)}." if kept else ""))
        self.worker.run(job)

    # The SteamGridDB key (the BC250 app's Steam artwork… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's pictures." if old else
                                     "No key: Update Steam draws the pictures from the app's icon.")
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
        if pane is self.games_pane:
            self.play()
        elif pane is self.cards_pane:
            self.new_card()
        elif pane is self.key_pane:
            self.paste_key()
        elif pane is self.keep_pane:
            self.delete_marked()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.other_action()
        elif pane is self.games_pane:
            self.update_steam()
        elif pane is self.cards_pane:
            self.copy_card()
        elif pane is self.key_pane:
            self.remove_key()

    def lb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_bios()
        elif pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_action()
        elif pane is self.games_pane:
            self.remove_game()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {str(g.file) for g in self.games}:
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
            self.games_pane.status.setText("Install PCSX2 first (the PCSX2 card): the games in Steam start it.")
            return
        if add and self.bios_used() is None:
            self.games_pane.status.setText(NO_BIOS)
            return
        folder, closed, program, existing = self.steam_dir, self.steam_closed, emulator.program(self.home), self.in_steam
        key = covers.read_key(library.key_file())
        self.busy, self.message = True, ""
        self.games_pane.status.setText("Looking up pictures and changing Steam's shortcuts…" if key else
                                       "Changing Steam's shortcuts…")
        self.log.info(f"Update Steam: {len(add)} in, {len(remove)} out.")
        self._job = "steam"
        self._steam_plan = (add, remove)
        self.worker.run(lambda: library.update_steam(folder, add, remove, program, LOGO_PATH, existing, closed, key))

    # Memory cards

    def card_folder(self) -> Path:
        return memcards.card_folder(self.home)

    def refresh_cards(self) -> None:
        pane = self.cards_pane
        folder = self.card_folder()
        found = memcards.find_cards(folder)
        slots = memcards.slot_cards(self.home)
        if self.card_view:
            card = next((c for c in found if c.name == self.card_view), None)
            if card is None:
                self.card_view = ""
            else:
                rows = [(BACK_KEY, f"{BACK_KEY} The cards")]
                rows += [(f"save:{s.name}", "  ·  ".join(x for x in (s.label, memcards.kib(s.size),
                                                                       memcards.when(s.modified) if s.modified else "")
                                                         if x)) for s in card.saves]
                pane.summary.setText(f"{card.name}: {len(card.saves)} save(s), {memcards.kib(card.free)} free of "
                                     f"{memcards.kib(card.total)}" if card.readable else f"{card.name}: {card.error}")
                pane.list.set_items(rows)
                self.update_legend()
                return
        rows = []
        for card in found:
            slot = slots.get(card.name)
            parts = [card.name, f"slot {slot}" if slot else "",
                     f"{len(card.saves)} save(s), {memcards.kib(card.free)} free" if card.readable else card.error]
            rows.append((card.name, "  ·  ".join(p for p in parts if p)))
        pane.summary.setText(f"{len(found)} card(s) in {wrappable(folder)}" if found else
                             f"No memory cards yet in {wrappable(folder)}: PCSX2 makes its two at its first start, "
                             "the X button (New card) makes one.")
        pane.list.set_items(rows)
        self.update_legend()

    def _card_focused(self, key: str) -> None:
        if not self.card_view and key != BACK_KEY and not key.startswith("save:"):
            self.last_card = key

    def card_picked(self, key: str) -> None:
        if key == BACK_KEY:
            self.card_view = ""
        elif not key.startswith("save:"):
            self.card_view = key
        else:
            return
        self.refresh_cards()
        self.focus_list(self.cards_pane)

    def new_card(self) -> None:
        folder = self.card_folder()
        n = 1
        while (folder / f"Mcd{n:03d}.ps2").exists():
            n += 1
        try:
            folder.mkdir(parents=True, exist_ok=True)
            made = memcards.new_card(folder, f"Mcd{n:03d}.ps2", 8)
        except (memcards.CardError, OSError) as error:
            self.cards_pane.status.setText(private(f"No card was made: {error}"))
            self.log.error(f"New card failed: {error}")
            return
        self.cards_pane.status.setText(f"{made.name} is made: 8 MB, empty.")
        self.log.info(f"Memory card made: {made.name}.")
        self.card_view = ""
        self.refresh_cards()

    def copy_card(self) -> None:
        """A copy of the card the focus was on last, beside it under a new name, saves and all."""
        source = self.card_folder() / self.last_card
        if not self.last_card or not source.is_file():
            self.cards_pane.status.setText(NO_CARD_TO_COPY)
            return
        if self.any_running():
            self.cards_pane.status.setText("PCSX2 is running: close it first, it may be writing the card.")
            return
        n = 2
        target = source.with_name(f"{source.stem} copy{source.suffix}")
        while target.exists():
            target = source.with_name(f"{source.stem} copy {n}{source.suffix}")
            n += 1
        try:
            shutil.copy2(source, target)
        except OSError as error:
            self.cards_pane.status.setText(f"The card was not copied: {error.strerror or error}")
            return
        self.cards_pane.status.setText(f"{source.name} is copied to {target.name}.")
        self.log.info(f"Memory card copied: {source.name} to {target.name}.")
        self.refresh_cards()

    # Log

    def refresh_log(self) -> None:
        rows: list[tuple[str, str]] = []
        session = userdata.last_session(self.home)
        if session is not None:
            titles = catalogue.titles(catalogue.folder(self.home))
            game = (titles.get(session.serial) or session.serial) if session.serial else "no game"
            when = datetime.datetime.fromtimestamp(session.ended).strftime("%d-%m-%Y %H:%M")
            rows += [("PCSX2's last run", f"{when}, {game}"),
                     ("Played", userdata.played(session.seconds) + ("" if session.counted else " (until the log ended)")),
                     ("Controllers", ", ".join(session.controllers) or "none opened")]
        total = sum(seconds for seconds, _ in userdata.play_times(self.home).values())
        if total:
            rows.append(("Play time in all", userdata.played(total)))
        if not rows:
            rows.append(("PCSX2's last run", "none yet"))
        rows.append(("Games", wrappable(self.game_folders()[0])))       # BIOS is in it
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
        """A on a setting's row: its next value, written now, unless PCSX2 runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(self.setting_value(setting))
        try:
            if setting.key in OWN:
                OWN[setting.key][1](self.home, value == "true")
            else:
                pcsx2_settings.write_setting(self.home, setting, value)
        except OSError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error.strerror or error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, Y, and Remove on the PCSX2 pane

    def main_action(self) -> None:
        """A on the PCSX2 card or pane: Install while PCSX2 is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing PCSX2 {emulator.VERSION} in {self.home}.")
        self.worker.run(lambda: self.install_job(self.home, progress=self._progress, say=self.worker.said.emit))

    def _progress(self, got: int) -> None:
        self.got = got                                  # read by refresh() on the window's thread

    def _said(self, text: str) -> None:
        self.stage = text
        self.refresh()

    def _installed(self, result: object) -> None:
        if self._job == "steam":
            self._job = ""
            self._steam_done(result)
            return
        if self._job == "remove":
            self._job = ""
            self._removed(result)
            return
        if self._job == "bios":
            self._job = ""
            self._bios_removed(result)
            return
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if isinstance(result, Exception):
            self.message = private(f"PCSX2 could not be installed: {result}")
            self.log.error(f"Installing PCSX2 failed: {result}")
        else:
            self.message = f"PCSX2 {result} is installed."
            self.log.info(f"PCSX2 {result} installed.")
            self.prepare()                              # before its first start: no setup wizard, no updater
        self.refresh()

    def _steam_done(self, result: object) -> None:
        """What Update Steam did, and the games in Steam as it read them back right after the write (29-10-2026:
        "it still says 0 games in Steam"): a game written but not read back is logged by name, so the log tells
        whether the file or the reading is at fault."""
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        ok, text, found = result if isinstance(result, tuple) else (False, f"Steam was not changed: {result}", None)
        add, _remove = getattr(self, "_steam_plan", ([], []))
        if ok and found is not None:
            missing = [g.title for g in add if str(g.file) not in found]
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

    def _removed(self, result: object) -> None:
        """What Remove game did; the games as they are now, Steam's as read back when its shortcut went."""
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        ok, text, found = result if isinstance(result, tuple) else (False, f"The game was not removed: {result}", None)
        self.games_pane.status.setText(private(text))
        (self.log.info if ok else self.log.error)(text)
        self.refresh()
        self.refresh_games(found)
        self.focus_list(self.games_pane)

    # The BIOS (the BC250 app's BIOS Uninstall; the dump itself comes from Games\PS2\BIOS: sync_bios)

    def remove_bios(self) -> None:
        """LB Remove BIOS: the keep page shows the dump PCSX2 uses, with the files beside it, in PCSX2's bios folder
        and in Games\\PS2\\BIOS, and the user decides what to keep (owner, 01-11-2026: before deleting anything, let
        the user decide what to keep). A copy kept in Games\\PS2\\BIOS goes into PCSX2 again with the next sync."""
        used = self.bios_used()
        if self.busy or used is None:
            self.message = (BUSY if self.busy else NO_BIOS_TO_REMOVE if emulator.installed(self.home)
                            else BIOS_NEEDS_PCSX2)
            self.refresh()
            return
        if self.running(self.home):
            self.message = RUNNING
            self.refresh()
            return
        self._confirm_over()
        items = [keep.Item("pcsx2", f"{used.name} in PCSX2's bios folder", tuple(userdata.bios_set(used)))]
        source = userdata.bios_set(library.bios_home(self.user_home) / used.name)
        if source:
            items.append(keep.Item("source", f"{used.name} in Games\\PS2\\BIOS", tuple(source)))
        self.keep_game = None
        self.show_keep("Remove the BIOS", items,
                       "A copy kept in Games\\PS2\\BIOS goes into PCSX2 again when the PCSX2 card gets the focus.",
                       self.pcsx2_card)

    def delete_bios(self, items: list[keep.Item]) -> None:
        """Remove BIOS's deleting, as the window's job; PCSX2 is then made to use another dump, when there is."""
        chosen = keep.chosen(items)
        kept = [item.label for item in items if not item.delete]
        paths = [path for item in chosen for path in item.paths]

        def job() -> tuple[list[str], list[str], list[str]]:
            return [p.name for p in paths], kept, keep.delete(paths)
        self.busy, self.message = True, ""
        self._job = "bios"
        self.leave_keep("")
        self.log.info(f"Removing the BIOS: {', '.join(str(p) for p in paths)}."
                      + (f" Kept: {', '.join(kept)}." if kept else ""))
        self.worker.run(job)

    def _bios_removed(self, result: object) -> None:
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        if not isinstance(result, tuple):
            self.message = f"The BIOS was not removed: {result}"
            self.log.error(self.message)
            self.refresh()
            return
        names, kept, failed = result
        dumps = self.bios_dumps()
        try:
            if dumps and pcsx2_settings.chosen_bios(self.home) not in {d.name for d in dumps}:
                pcsx2_settings.choose_bios(self.home, dumps[0].name)
        except OSError as error:
            self.log.error(f"PCSX2.ini could not name another BIOS: {error}")
        used = self.bios_used()
        deleted = [n for n in names if not any(f.startswith(f"{n} (") for f in failed)]
        self.message = (f"Deleted {', '.join(deleted) or 'nothing'}"
                        + (f"; kept {', '.join(kept)}" if kept else "") + ". "
                        + (f"Not deleted: {', '.join(failed)}. " if failed else "")
                        + (f"PCSX2 uses {used.name} now." if used is not None else "PCSX2 has no BIOS now."))
        (self.log.error if failed else self.log.info)(self.message)
        self.refresh()

    def remove_action(self) -> None:
        """RB Remove PCSX2 asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "PCSX2 is not installed: there is nothing to remove."
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
            self.message = f"PCSX2 could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing PCSX2 failed: {error}")
        else:
            self.message = "PCSX2 is removed. Its BIOS, memory cards and settings stay in its folder."
            self.log.info("PCSX2 removed.")
        self.refresh()

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
        (nothing saved), a card's saves to the cards, a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.keep_pane:
            self.leave_keep("Nothing was deleted.")
        elif pane is self.cards_pane and self.card_view:
            self.card_picked(BACK_KEY)
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the download (owner, 28-10-2026: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = {"steam": "Press View again to exit: Steam's shortcuts may be left half changed.",
                            "remove": "Press View again to exit: the game is left half deleted.",
                            "bios": "Press View again to exit: the BIOS is left half deleted."
                            }.get(self._job, "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
