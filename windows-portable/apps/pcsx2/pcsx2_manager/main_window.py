# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as Windows Portable Test lays it out: the cards on the left (PCSX2, Your
games, Settings, Memory cards, Log: the BC250 suite's PCSX2 Manager's parts, owner 29-10-2026), what the focused one
shows on the right, the controller's buttons at the bottom.

An action with a controller button is in the legend at the bottom, not on a pill too (owner, 29-10-2026: "we have
update steam 2 times ... use that bottom row for actions"); a tap on the legend's entry does the same. The pills that
stay are the actions without a button: Remove BIOS and Remove PCSX2 (a second press each), A Install, A Save, A Open
the log.

The Your games pane (panes.py, library.py): the games in the chosen folders; A plays one, X marks it for Steam, Y
Update Steam makes Steam's shortcuts match the marks; LB Folders lists the folders, the usual places and a drive to
add, and Choose a folder (Windows' own folder window), LB Games goes back; RB Steam artwork keeps the SteamGridDB key.
The Memory cards pane: the cards and the saves on each, X New card and Y Copy card. The Log pane: PCSX2's last run and
the newest lines of the app's log.

The PCSX2 pane: what is installed, where, the BIOS; X Choose BIOS, Y Reinstall or Update, and the pills Remove BIOS,
Remove PCSX2 (a second press each) and A Install until PCSX2 is installed (PCSX2's own window is never opened). A pill
is never grayed out: one that cannot act now says why on the status line. Nothing downloads before A. The download and
the unpacking run off the window's thread; the pane counts the megabytes. B while they run asks first, as the portal
does.

The Settings pane: PCSX2's settings that matter on the handheld, in tabs (LB and RB: Picture, Game, Controller, On
screen), a row each with its value; A steps to the next value and writes it into PCSX2.ini at once (pcsx2_settings),
never while PCSX2 runs (it writes its own settings back when it closes). What the app owns in PCSX2.ini is set after
an install, when the window opens and before PCSX2 opens (pcsx2_settings.prepare), so PCSX2 opens ready to play: the
BC250 suite's PCSX2 Manager's rules."""

from __future__ import annotations

import datetime
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import open_path
from bc250_core.portable import (AMBER, BODY, DIM, Card, InfoPill, Legend, Pane, Pill, PortableHeader,
                                 PortableWindow, Row, Tabs, pill_row, px, status_clock, text_label)

from . import (APP_ID, APP_NAME, LOGO_PATH, __version__, catalogue, emulator, library, memcards, pcsx2_settings,
               shortcuts, userdata)
from .games import Game, scan
from .panes import CARDS_INFO, GAMES_INFO, KeyPane, ListPane, LogPane
from .pcsx2_settings import OWN, TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and B while PCSX2 is being installed, ask for a second press within this
CARDS_WIDTH = 460               # the cards' column; the panes take the rest, the PCSX2 pane's one row of pills
ABOUT = ("PCSX2, the PlayStation 2 emulator, installed for your own user in portable mode: its settings, the BIOS, "
         "the memory cards and the save states stay in its folder.")
CLOSE, BACK = ("B", "Close"), ("B", "Back")
CARD_HEIGHT = 100               # five cards and their gaps fit the column at 720 px high
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
BACK_KEY = "\u2039"            # the first row of a card's saves: back to the cards
FOLDERS, GAMES_VIEW = "folders", "games"
RUNNING = "PCSX2 is open: close it first, it would write its own settings over the change."
# Without a BIOS PCSX2 stops at its own Startup Error window (seen on the Ally, 29-10-2026): no game starts then
NO_BIOS = "Choose BIOS first (the PCSX2 card): PCSX2 cannot start a game without your console's BIOS."
NOT_INSTALLED = "Install PCSX2 first: the settings are in its folder."
BUSY = "Wait a moment: the app is still busy with the step before."
BIOS_NEEDS_PCSX2 = "Install PCSX2 first: the BIOS goes in its folder."
NO_BIOS_TO_REMOVE = "There is no BIOS to remove: Choose BIOS takes your own console's dump."
NO_CARD_TO_COPY = "Copy card copies the card the focus was on last: move to a card in the list first."
ALL_SETTINGS = pcsx2_settings.SETTINGS
BIOS_INFO = (
    "PCSX2 needs the PS2's BIOS to start any game, and it is not ours to give: it comes from your own PlayStation 2. "
    "Dump it with biosdrain, a homebrew tool run on the console (PCSX2's BIOS page, "
    f"{userdata.BIOS_HELP_URL}, says how), and copy the dump to the device. A dump is a .bin or .rom file of 4 MB, "
    "often with files beside it under the same name (.nvm, .mec, .erom).\n\n"
    "X Choose BIOS opens Windows' own file window, in your Downloads: pick the .bin, and the app copies it, with the "
    "files beside it, into PCSX2's bios folder and makes PCSX2 use it. Remove BIOS takes the one PCSX2 uses out of "
    "that folder again, with its files, on a second press; the dump you chose it from stays where it is. Neither "
    "works while PCSX2 runs: it writes its settings back when it closes.")
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("A changes the setting the focus is on, LB and RB change the tab; PCSX2 reads the settings the "
                  "next time it opens.\n\n" + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}


def wrappable(path: Path) -> str:
    """A path that a label can wrap after each backslash: a long one would make the pane wider than the screen."""
    return str(path).replace("\\", "\\\u200b")


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


NOT_THE_GAMES = "Update Steam works on the games: Games shows them again."
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: X on a game marks it for Steam or takes the mark away, then Y "
                     "Update Steam.")


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
            self.info.setFocus()                        # off the old page first: a row hidden with the focus would
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
                 play: Callable[[Path, Path], None] = emulator.start, steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 choose_folder: Callable[[], str] | None = None, user_home: Path | None = None,
                 drives: Callable[[], list[Path]] = library.removable_drives,
                 any_running: Callable[[], bool] = memcards.pcsx2_running, settings: QSettings | None = None,
                 choose_file: Callable[[], str] | None = None):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *choose_folder*: a folder
        picked by the user ("" when none), Windows' own folder window by default; *settings*: the app's (its .ini,
        create_app's), where the game folders are kept; *choose_file*: a BIOS dump picked by the user ("" when
        none), Windows' own file window by default."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.running = install, running
        self.choose_file = choose_file or self._bios_window
        self.confirm_bios = False                       # Remove BIOS pressed once
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.stage = ""                                 # "Checking the download…", "Unpacking…"
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.play_game, self.steam_closed, self.any_running = play, steam_closed, any_running
        self._job = ""                                  # "steam" while Update Steam runs in the worker
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.choose_folder = choose_folder or self._folder_window
        self.user_home, self.drives = user_home, drives
        self.settings = settings if settings is not None else QSettings()
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.marked: set[str] = set()
        self.games_view = GAMES_VIEW
        self.forget_asked = ""                          # a folder pressed once: A again takes it off the list
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
        self.games_card = Card("Your games", "Play them, and put them in Steam.")
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
        self.pane.column.addSpacing(px(8))
        # The pills: the actions without a controller button (the others are in the legend), one row
        self.remove_bios_pill = Pill("Remove BIOS")
        self.remove_pill = Pill("Remove PCSX2")
        self.main = Pill("Install", "A", main=True)
        self.pane.column.addLayout(pill_row(self.remove_bios_pill, self.remove_pill, self.main))
        self.main.hide()                                # refresh() shows what the state asks for
        self.settings_pane = SettingsPane()
        self.games_pane = ListPane("Your games", "Your games", GAMES_INFO)
        self.key_pane = KeyPane()
        self.cards_pane = ListPane("Memory cards", "The memory cards", CARDS_INFO)
        self.log_pane = LogPane()
        for pane in (self.pane, self.games_pane, self.settings_pane, self.cards_pane, self.log_pane, self.key_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.pcsx2_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.cards_pane: self.cards_card,
                      self.log_pane: self.log_card, self.key_pane: self.games_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([CLOSE])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._installed)
        self.worker.said.connect(self._said)
        self.pcsx2_card.focused.connect(lambda: self.show_pane(self.pane))
        self.pcsx2_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.cards_card.focused.connect(lambda: self.show_pane(self.cards_pane))
        self.cards_card.activated.connect(lambda: self.focus_list(self.cards_pane))
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.open_log)
        self.games_pane.list.picked.connect(self.game_picked)
        self.key_pane.save.activated.connect(self.save_key)
        self.confirm_key = False                        # Remove key pressed once
        self.cards_pane.list.picked.connect(self.card_picked)
        self.cards_pane.list.current.connect(self._card_focused)
        self.log_pane.open.activated.connect(self.open_log)
        self.main.activated.connect(self.main_action)
        self.remove_bios_pill.activated.connect(self.remove_bios)
        self.remove_pill.activated.connect(self.remove_action)
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
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
        self.refresh()
        self.refresh_games()
        self.refresh_cards()
        self.pcsx2_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([power.text(self.battery()), *status_clock()])

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
        """The status line (amber), the main pill's text (A) and Y's in the legend (Reinstall, Update); "" hides
        either. Installed, there is no main pill (owner, 29-10-2026: Your games is the card on the left)."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading PCSX2 {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if emulator.replaced(self.home):
            return (f"PCSX2 replaced itself with another build. Reinstall puts {emulator.VERSION} back.",
                    "", "Reinstall")
        if version != emulator.VERSION:
            return f"This app installs PCSX2 {emulator.VERSION}: Update puts it in.", "", "Update"
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
            return "No BIOS yet: PCSX2 needs your own console's BIOS to start a game. Choose BIOS takes the dump."
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
        status, main, _other = self.state()
        self.status.setText(self.message or status)
        self.main.set_text(main)
        self.main.setVisible(bool(main))
        self.remove_pill.set_text("Press again" if self.confirm_remove else "Remove PCSX2")
        self.remove_pill.setVisible(not self.busy and bool(emulator.installed(self.home)))
        installed = bool(emulator.installed(self.home))
        self.remove_bios_pill.set_text("Press again" if self.confirm_bios else "Remove BIOS")
        self.pcsx2_card.set_text("No BIOS yet: X Choose BIOS on the PCSX2 pane." if installed and self.bios_used() is None
                                 else "Install, update or remove it, and its BIOS.")
        self.refresh_settings()
        self.update_legend()
        focus = self.focusWidget()
        if focus is not None and not focus.isVisible() and focus in (self.main, self.remove_pill):
            visible = [pill for pill in (self.main, self.remove_pill) if pill.isVisible()]
            (visible[0] if visible else self.pcsx2_card).setFocus()

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
        self.panes.setCurrentWidget(pane)
        if pane is self.log_pane:
            self.refresh_log()
        self.update_legend()

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows: its actions on the controller's buttons (a tap on an entry does the
        same), B last. A press that cannot act now says why on the pane's status line."""
        if self.close_asked:
            return [("B", "Press again to close")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            other = self.state()[2]
            items = [("X", "Choose BIOS"), *([("Y", other)] if other else [])]
        elif pane is self.games_pane:
            items = ([("X", "Steam mark"), ("Y", "Update Steam"), ("LB", "Folders")]
                     if self.games_view == GAMES_VIEW else [("LB", "Games")]) + [("RB", "Steam artwork")]
        elif pane is self.cards_pane:
            items = [("X", "New card"), ("Y", "Copy card")]
        elif pane is self.key_pane:
            items = [("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key")]
        return [*items, BACK if pane is self.key_pane else CLOSE]

    def update_legend(self) -> None:
        self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games in the chosen folders, which are in Steam (*in_steam* when given: what Update Steam read back,
        else Steam's file now), and the list as the view shows it."""
        chosen = library.folders(self.settings)
        self.games = scan(chosen, catalogue.titles(catalogue.folder(self.home)))
        if in_steam is not None:
            self.in_steam = in_steam
        else:
            try:
                self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir is not None else {}
            except OSError as error:
                self.in_steam = {}
                self.log.error(f"Steam's shortcuts could not be read: {error}")
        found = {str(g.file) for g in self.games}
        self.marked = {f for f in self.marked if f in found} | {f for f in self.in_steam if f in found
                                                                  and f not in self._unmarked}
        self.show_games()

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        chosen = library.folders(self.settings)
        in_steam = sum(1 for g in self.games if str(g.file) in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(chosen)} folder(s)"
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        if self.games_view == FOLDERS:
            rows = [(f"folder:{f}", ("Press A again to take it off the list" if self.forget_asked == str(f)
                                     else f"{f}  ·  {len(scan([f]))} game(s)")) for f in chosen]
            rows += [(f"add:{p}", f"+ Add {p}") for p in library.suggested(chosen, self.user_home, self.drives)]
            rows.append(("choose", "+ Choose a folder…"))
        else:
            rows = [(str(g.file), self.game_text(g)) for g in self.games]
            if not rows:
                pane.status.setText(pane.status.text() or "No games yet: LB Folders adds the folders your games are in.")
        pane.list.set_items(rows)
        self.update_legend()                            # Update Steam is the games' (owner's screen, 29-10-2026)

    def game_text(self, game: Game) -> str:
        mark = "\u2713 Steam" if str(game.file) in self.marked else ""
        changed = (str(game.file) in self.marked) != (str(game.file) in self.in_steam)
        return "  ·  ".join(p for p in (game.title, game.serial, mark + (" (Update Steam)" if changed else "")) if p)

    def game_picked(self, key: str) -> None:
        if key == "choose":
            folder = self.choose_folder()
            if folder:
                self.add_folder(Path(folder))
        elif key.startswith("add:"):
            self.add_folder(Path(key[4:]))
        elif key.startswith("folder:"):
            self.forget_folder(Path(key[7:]))
        else:
            self.play(next((g for g in self.games if str(g.file) == key), None))

    def toggle_folders(self) -> None:
        self.games_view = GAMES_VIEW if self.games_view == FOLDERS else FOLDERS
        self.forget_asked = ""
        self.games_pane.status.setText("")
        self.show_games()
        self.show_pane(self.games_pane)
        self.focus_list(self.games_pane)

    def add_folder(self, folder: Path) -> None:
        chosen = library.folders(self.settings)
        if str(folder) not in {str(f) for f in chosen}:
            library.set_folders(self.settings, chosen + [folder])
        self.refresh_games()
        found = sum(1 for g in self.games if g.folder == folder or folder in g.file.parents)
        self.games_pane.status.setText(f"{folder.name or folder} is a game folder now: {found} game(s) in it.")
        self.log.info(f"Game folder added: {folder} ({found} game(s)).")

    def forget_folder(self, folder: Path) -> None:
        """A on a folder asks for a second press (no dialog on a handheld); the second takes it off the list."""
        if self.forget_asked != str(folder):
            self.forget_asked = str(folder)
            self.confirm_timer.start()
            self.show_games()
            self.games_pane.list.pills[f"folder:{folder}"].setFocus()
            return
        self.forget_asked = ""
        library.set_folders(self.settings, [f for f in library.folders(self.settings) if f != folder])
        self.refresh_games()
        self.games_pane.status.setText(f"{folder.name or folder} is no longer a game folder; its games stay where "
                                       "they are.")
        self.log.info(f"Game folder taken off the list: {folder}.")
        self.focus_list(self.games_pane)

    def _folder_window(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Add a game folder", str(self.user_home or Path.home()))

    def play(self, game: Game | None) -> None:
        if game is None or self.busy:
            return
        if not emulator.installed(self.home):
            self.games_pane.status.setText("Install PCSX2 first (the PCSX2 card).")
            return
        if self.bios_used() is None:                    # PCSX2 would stop at its own error window
            self.games_pane.status.setText(NO_BIOS)
            return
        if self.running(self.home):
            self.games_pane.status.setText("PCSX2 is open: close it first, then play the game.")
            return
        self.prepare()
        try:
            self.play_game(self.home, game.file)
        except OSError as error:
            self.games_pane.status.setText(f"{game.title} could not be started: {error}")
            self.log.error(f"{game.title} could not be started: {error}")
            return
        self.games_pane.status.setText(f"{game.title} starts in PCSX2.")
        self.log.info(f"Played {game.title} ({game.serial or game.file.name}).")

    # The SteamGridDB key (the BC250 app's Steam artwork… and core's covers.edit_key, as a page)

    def show_key(self) -> None:
        old = covers.read_key(library.key_file())
        self.key_pane.field.setText(old)
        self.key_pane.status.setText("A key is kept: Update Steam fetches each game's pictures." if old else
                                     "No key: Update Steam draws the pictures from the app's icon.")
        self.show_pane(self.key_pane)
        self.key_pane.save.setFocus()

    def paste_key(self) -> None:
        """The key from the clipboard (copied in a browser on the device): typing 32 characters on a handheld is
        the hard way."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.key_pane.status.setText("The clipboard is empty: copy the key on SteamGridDB's API page first.")
            return
        self.key_pane.field.setText(text.split()[0])
        self.key_pane.status.setText("The key is in the field: Save keeps it.")
        self.key_pane.save.setFocus()

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
            self.key_pane.status.setText("There is no key to remove: Paste puts one in, Save keeps it.")
            return
        if not self.confirm_key:
            self.confirm_key = True
            self.confirm_timer.start()
            self.key_pane.status.setText("Press Y again to remove the key.")
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

    # The legend's buttons: what X, Y, LB and RB do on the pane that shows (a tap on the legend's entry does the same)

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.choose_bios()
        elif pane is self.games_pane:
            self.mark_game()
        elif pane is self.cards_pane:
            self.new_card()
        elif pane is self.key_pane:
            self.paste_key()

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
        if pane is self.games_pane:
            self.toggle_folders()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(-1)

    def rb_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.games_pane:
            self.show_key()
        elif pane is self.settings_pane:
            self.settings_pane.tabs.step(1)

    def mark_game(self) -> None:
        """X on a game: mark it for Steam, or take the mark away."""
        if self.games_view != GAMES_VIEW:
            return
        pills = self.games_pane.list.pills
        focus = self.focusWidget()
        key = next((k for k, pill in pills.items() if pill is focus), "")
        if not key:
            self.games_pane.status.setText("Move to a game in the list first: X marks the one with the focus.")
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
        if self.games_view != GAMES_VIEW:
            self.games_pane.status.setText(NOT_THE_GAMES)
            return
        if self.steam_dir is None:
            self.games_pane.status.setText(NO_STEAM)
            return
        if not library.pending(self.games, self.marked, self.in_steam):
            self.games_pane.status.setText(NOTHING_TO_CHANGE)
            return
        add, remove = library.plan(self.games, self.marked, self.in_steam)
        if add and not emulator.installed(self.home):
            self.games_pane.status.setText("Install PCSX2 first: the games in Steam start it.")
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
                return
        rows = []
        for card in found:
            slot = slots.get(card.name)
            parts = [card.name, f"slot {slot}" if slot else "",
                     f"{len(card.saves)} save(s), {memcards.kib(card.free)} free" if card.readable else card.error]
            rows.append((card.name, "  ·  ".join(p for p in parts if p)))
        pane.summary.setText(f"{len(found)} card(s) in {wrappable(folder)}" if found else
                             f"No memory cards yet in {wrappable(folder)}: PCSX2 makes its two at its first start, "
                             "New card makes one.")
        pane.list.set_items(rows)

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
            self.cards_pane.status.setText(f"No card was made: {error}")
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
        lines: list[str] = []
        if self.log_path is not None:
            try:
                lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_LINES:]
            except OSError:
                lines = []
        self.log_pane.fill(rows, lines)

    def open_log(self) -> None:
        if self.log_path is not None and self.log_path.is_file():
            open_path(self.log_path)

    # The Settings pane

    def focus_settings(self) -> None:
        self.settings_pane.focus_first()

    def step_setting(self, setting: Setting) -> None:
        """A on a setting's pill: its next value, written now, unless PCSX2 runs."""
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

    # A, Y and Remove

    def main_action(self) -> None:
        if self.busy:
            return
        _, main, _ = self.state()
        if main == "Install":
            self.install()
        else:                                           # installed: A on the card goes to the pane's pills
            self.remove_bios_pill.setFocus()

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
        self.busy, self.stage = False, ""
        self.progress_timer.stop()
        if self.close_asked:
            self._confirm_over()
        if isinstance(result, Exception):
            self.message = f"PCSX2 could not be installed: {result}"
            self.log.error(f"Installing PCSX2 failed: {result}")
        else:
            self.message = f"PCSX2 {result} is installed."
            self.log.info(f"PCSX2 {result} installed.")
            self.prepare()                              # before its first start: no setup wizard, no updater
        self.refresh()
        self.main.setFocus()

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

    # The BIOS (the BC250 app's BIOS Install and BIOS Uninstall)

    def _bios_window(self) -> str:
        downloads = (self.user_home or Path.home()) / "Downloads"
        path, _ = QFileDialog.getOpenFileName(self, "Choose your BIOS dump", str(downloads),
                                              "PS2 BIOS dumps (*.bin *.BIN *.rom *.ROM)")
        return path

    def choose_bios(self) -> None:
        """Copies the dump picked in Windows' file window, with the files beside it, into PCSX2's bios folder and makes
        it the one PCSX2 uses."""
        if self.busy or not emulator.installed(self.home):
            self.message = BUSY if self.busy else BIOS_NEEDS_PCSX2
            self.refresh()
            return
        if self.running(self.home):
            self.message = RUNNING
            self.refresh()
            return
        picked = self.choose_file()
        if not picked:
            return
        try:
            placed = userdata.copy_bios(Path(picked), userdata.bios_dir(self.home))
            pcsx2_settings.choose_bios(self.home, placed.name)
        except OSError as error:
            self.message = f"The BIOS was not taken: {error.strerror or error}"
            self.log.error(f"Choosing the BIOS failed: {error}")
            self.refresh()
            return
        self.message = f"PCSX2 uses {placed.name} now."
        self.log.info(f"BIOS chosen: {placed.name}.")
        self.refresh()

    def remove_bios(self) -> None:
        """Remove BIOS asks for a second press (no dialog on a handheld); the second takes the dump PCSX2 uses out of
        its bios folder, with the files beside it. PCSX2 then uses another one, when there is."""
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
        if not self.confirm_bios:
            self.confirm_bios = True
            self.confirm_timer.start()
            self.refresh()
            return
        self._confirm_over()
        try:
            removed = userdata.remove_bios(used)
            others = self.bios_dumps()
            if others:
                pcsx2_settings.choose_bios(self.home, others[0].name)
        except OSError as error:
            self.message = f"{used.name} was not removed: {error.strerror or error}"
            self.log.error(f"Removing the BIOS failed: {error}")
            self.refresh()
            return
        self.message = (f"{', '.join(removed)} removed from PCSX2's bios folder. "
                        + (f"PCSX2 uses {others[0].name} now." if others else "PCSX2 has no BIOS now."))
        self.log.info(f"BIOS removed: {', '.join(removed)}.")
        self.refresh()

    def remove_action(self) -> None:
        """Remove asks for a second press (no dialog on a handheld): the pill says so for a few seconds."""
        if self.busy or not emulator.installed(self.home):
            if self.busy:
                self.message = BUSY
                self.refresh()
            return
        if not self.confirm_remove:
            self.confirm_remove = True
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
        self.main.setFocus()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.forget_asked:
            self.forget_asked = ""
            self.show_games()
        if self.confirm_bios:
            self.confirm_bios = False
            self.refresh()
        if self.confirm_key:
            self.confirm_key = False
            if self.key_pane.status.text().startswith("Press Y again"):
                self.key_pane.status.setText("")
        changed = self.confirm_remove or self.close_asked
        if self.close_asked and self.message.startswith("Press B again"):
            self.message = ""
        self.confirm_remove = self.close_asked = False
        if changed:
            self.refresh()
        self.update_legend()

    # B

    def on_back(self) -> None:
        if self.panes.currentWidget() is self.key_pane:  # B on the key page: back to Your games, nothing saved
            self.back_to_games()
            return
        if self.busy and not self.close_asked:          # closing drops the download (owner, 28-10-2026: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = ("Press B again to close: Steam's shortcuts may be left half changed."
                            if self._job == "steam" else "Press B again to close: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
