# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as Windows Portable Test lays it out: the cards on the left (PCSX2, Your
games, Settings, Memory cards, Log: the BC250 suite's PCSX2 Manager's parts, owner 29-10-2026), what the focused one
shows on the right, the controller's buttons at the bottom.

The Your games pane (panes.py, library.py): the games in the chosen folders; A plays one, X marks it for Steam, Y
Update Steam makes Steam's shortcuts match the marks; Folders lists the folders, the usual places and a drive to add,
and Choose a folder (Windows' own folder window). The Memory cards pane: the cards and the saves on each, New card and
Copy card. The Log pane: PCSX2's last run and the newest lines of the app's log.

The PCSX2 pane: what is installed, where, and the pills: A Install or Open PCSX2, Y Reinstall or Update, Remove with
a second press. Nothing downloads before A. The download and the unpacking run off the window's thread; the pane
counts the megabytes. B while they run asks first, as the portal does.

The Settings pane: PCSX2's settings that matter on the handheld, a pill each with its value; A steps to the next
value and writes it into PCSX2.ini at once (pcsx2_settings), never while PCSX2 runs (it writes its own settings back
when it closes). What the app owns in PCSX2.ini is set after an install, when the window opens and before PCSX2
opens (pcsx2_settings.prepare), so PCSX2 opens ready to play: the BC250 suite's PCSX2 Manager's rules."""

from __future__ import annotations

import datetime
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import open_path
from bc250_core.portable import (AMBER, BODY, DIM, Card, InfoPill, Legend, Pane, Pill, PortableHeader,
                                 PortableWindow, px, status_clock, text_label)

from . import (APP_ID, APP_NAME, LOGO_PATH, __version__, catalogue, emulator, library, memcards, pcsx2_settings,
               shortcuts, userdata)
from .games import Game, scan
from .panes import CARDS_INFO, GAMES_INFO, ListPane, LogPane
from .pcsx2_settings import SWITCH, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download
CONFIRM_MS = 5000               # Remove, and B while PCSX2 is being installed, ask for a second press within this
CARDS_WIDTH = 520               # the cards' column; the panes take the rest
SETTING_HEIGHT = 40             # a setting's pill: nine of them fit the pane at 720 px high
ABOUT = ("PCSX2, the PlayStation 2 emulator, installed for your own user in portable mode: its settings, the BIOS, "
         "the memory cards and the save states stay in its folder.")
LEGEND = (("B", "Close"),)
GAMES_LEGEND = (("X", "Steam mark"), ("Y", "Update Steam"), ("B", "Close"))
CARD_HEIGHT = 100               # five cards and their gaps fit the column at 720 px high
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
BACK_KEY = "\u2039"            # the first row of a card's saves: back to the cards
FOLDERS, GAMES_VIEW = "folders", "games"
RUNNING = "PCSX2 is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install PCSX2 first: the settings are in its folder."
# The switches with a function of their own in pcsx2_settings, after SETTINGS
PLAYER2 = Setting("player2", "Player 2", "Pad2", ("Type",), SWITCH,
                  tip="a second controller is player 2, with the same buttons as player 1.")
QUIT = Setting("quit", "Quit with Select + Start", "Hotkeys", ("ShutdownVM",), SWITCH,
               tip="View and Menu together end the game; off, PCSX2's pause menu does.")
BIG_PICTURE = Setting("bigpicture", "Big Picture", "UI", ("StartBigPictureMode",), SWITCH,
                      tip="PCSX2 opens full screen, made for a controller; off, its desktop window.")
OWN = {PLAYER2.key: (pcsx2_settings.player2, pcsx2_settings.set_player2),
       QUIT.key: (pcsx2_settings.quit_chord, pcsx2_settings.set_quit_chord),
       BIG_PICTURE.key: (pcsx2_settings.big_picture, pcsx2_settings.set_big_picture)}
ALL_SETTINGS = (*pcsx2_settings.SETTINGS, PLAYER2, QUIT, BIG_PICTURE)
SETTINGS_INFO = ("A changes the setting the focus is on; PCSX2 reads it the next time it opens.\n\n"
                 + "\n".join(f"{setting.label}: {setting.tip}" for setting in ALL_SETTINGS))


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


class SettingsPane(Pane):
    """A pill per setting, "Renderer: Automatic"; A on one steps to the next value (the window writes it)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("PCSX2's settings", SETTINGS_INFO)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.column.addSpacing(px(8))
        self.pills: dict[str, Pill] = {}
        for setting in ALL_SETTINGS:
            pill = Pill(setting.label)
            pill.setFixedHeight(px(SETTING_HEIGHT))
            self.pills[setting.key] = pill
            self.column.addWidget(pill)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, home: Path | None = None,
                 install: Callable[..., str] = emulator.install, start: Callable[[Path], None] = emulator.start,
                 running: Callable[[Path], bool] = emulator.running,
                 play: Callable[[Path, Path], None] = emulator.start, steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 choose_folder: Callable[[], str] | None = None, user_home: Path | None = None,
                 drives: Callable[[], list[Path]] = library.removable_drives,
                 any_running: Callable[[], bool] = memcards.pcsx2_running, settings: QSettings | None = None):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *choose_folder*: a folder
        picked by the user ("" when none), Windows' own folder window by default; *settings*: the app's (its .ini,
        create_app's), where the game folders are kept."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.install_job, self.start_program, self.running = install, start, running
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
        self.pcsx2_card = Card("PCSX2", "Install, open, update or remove the emulator.")
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
        self.pane.column.addWidget(text_label("PCSX2", 24, QFont.Weight.ExtraBold))
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
        pills = QHBoxLayout()
        pills.setSpacing(px(12))
        self.remove_pill = Pill("Remove")
        self.other = Pill("Reinstall", "Y")
        self.main = Pill("Install", "A", main=True)
        pills.addWidget(self.remove_pill)
        pills.addStretch()
        pills.addWidget(self.other)
        pills.addWidget(self.main)
        self.pane.column.addLayout(pills)
        self.settings_pane = SettingsPane()
        self.games_pane = ListPane("Your games", "Your games", GAMES_INFO)
        self.folders_pill = self.games_pane.add_pill(Pill("Folders"))
        self.steam_pill = self.games_pane.add_pill(Pill("Update Steam", "Y"), stretch_before=True)
        self.cards_pane = ListPane("Memory cards", "The memory cards", CARDS_INFO)
        self.new_card_pill = self.cards_pane.add_pill(Pill("New card"))
        self.copy_card_pill = self.cards_pane.add_pill(Pill("Copy card"), stretch_before=True)
        self.log_pane = LogPane()
        for pane in (self.pane, self.games_pane, self.settings_pane, self.cards_pane, self.log_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend(LEGEND)
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
        self.folders_pill.activated.connect(self.toggle_folders)
        self.steam_pill.activated.connect(self.update_steam)
        self.cards_pane.list.picked.connect(self.card_picked)
        self.cards_pane.list.current.connect(self._card_focused)
        self.new_card_pill.activated.connect(self.new_card)
        self.copy_card_pill.activated.connect(self.copy_card)
        self.log_pane.open.activated.connect(self.open_log)
        self.main.activated.connect(self.main_action)
        self.other.activated.connect(self.other_action)
        self.remove_pill.activated.connect(self.remove_action)
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        self.bind("y", self.y_action)
        self.bind("x", self.x_action)
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
        """The status line (amber), the main pill's text (A) and the other's (Y); "" hides a pill."""
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
                    "Open PCSX2", "Reinstall")
        if version != emulator.VERSION:
            return f"This app installs PCSX2 {emulator.VERSION}.", "Open PCSX2", f"Update to {emulator.VERSION}"
        return "", "Open PCSX2", ""

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        installed = version + (", replaced by another build" if version and emulator.replaced(self.home) else "")
        return [("Installed", installed or "not installed"), ("This app installs", emulator.VERSION),
                ("Folder", wrappable(self.home))]

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
        status, main, other = self.state()
        self.status.setText(self.message or status)
        self.main.set_text(main)
        self.main.setVisible(bool(main))
        self.other.set_text(other)
        self.other.setVisible(bool(other))
        self.remove_pill.set_text("Press again to remove" if self.confirm_remove else "Remove")
        self.remove_pill.setVisible(not self.busy and bool(emulator.installed(self.home)))
        self.refresh_settings()
        focus = self.focusWidget()
        if focus is not None and not focus.isVisible() and focus in (self.main, self.other, self.remove_pill):
            visible = [pill for pill in (self.main, self.other, self.remove_pill) if pill.isVisible()]
            (visible[0] if visible else self.pcsx2_card).setFocus()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        for setting in ALL_SETTINGS:
            pill = self.settings_pane.pills[setting.key]
            pill.set_text(f"{setting.label}: {setting.shown(self.setting_value(setting))}" if ready
                          else setting.label)
            pill.setEnabled(ready)
        if not ready and not self.settings_pane.status.text():
            self.settings_pane.status.setText(NOT_INSTALLED)
        elif ready and self.settings_pane.status.text() == NOT_INSTALLED:
            self.settings_pane.status.setText("")

    def show_pane(self, pane: Pane) -> None:
        self.panes.setCurrentWidget(pane)
        if pane is self.log_pane:
            self.refresh_log()
        games = pane is self.games_pane and self.games_view == GAMES_VIEW     # X and Y act on the games alone
        self.legend.set_items(GAMES_LEGEND if games and not self.busy and not self.close_asked
                              else [("B", "Press again to close")] if self.close_asked else LEGEND)

    def focus_list(self, pane: ListPane) -> None:
        first = pane.list.first()
        (first or next((p for p in (pane.pills.itemAt(i).widget() for i in range(pane.pills.count()))
                        if isinstance(p, Pill) and p.isVisible()), None) or self.focusWidget()).setFocus()

    # Your games

    def refresh_games(self) -> None:
        """The games in the chosen folders, which are in Steam, and the list as the view shows it."""
        chosen = library.folders(self.settings)
        self.games = scan(chosen, catalogue.titles(catalogue.folder(self.home)))
        try:
            self.in_steam = shortcuts.in_steam(self.steam_dir) if self.steam_dir is not None else {}
        except OSError:
            self.in_steam = {}
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
            self.folders_pill.set_text("Games")
            self.steam_pill.hide()                      # Update Steam is the games' (owner's screen, 29-10-2026)
        else:
            rows = [(str(g.file), self.game_text(g)) for g in self.games]
            self.folders_pill.set_text("Folders")
            self.steam_pill.show()
            if not rows:
                pane.status.setText(pane.status.text() or "No games yet: Folders adds the folders your games are in.")
        pane.list.set_items(rows)
        self.steam_pill.setEnabled(self.steam_dir is not None and not self.busy
                                   and library.pending(self.games, self.marked, self.in_steam))

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

    def x_action(self) -> None:
        """X on a game: mark it for Steam, or take the mark away."""
        if self.panes.currentWidget() is not self.games_pane or self.games_view != GAMES_VIEW:
            return
        pills = self.games_pane.list.pills
        focus = self.focusWidget()
        key = next((k for k, pill in pills.items() if pill is focus), "")
        if not key:
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

    def y_action(self) -> None:
        if self.panes.currentWidget() is self.games_pane:
            self.update_steam()
        else:
            self.other_action()

    def update_steam(self) -> None:
        """Y Update Steam: the marked games in Steam, the others out, off the window's thread."""
        if self.busy or self.steam_dir is None or not library.pending(self.games, self.marked, self.in_steam):
            return
        add, remove = library.plan(self.games, self.marked, self.in_steam)
        if add and not emulator.installed(self.home):
            self.games_pane.status.setText("Install PCSX2 first: the games in Steam start it.")
            return
        folder, closed, program, existing = self.steam_dir, self.steam_closed, emulator.program(self.home), self.in_steam
        key = covers.read_key(library.key_file())
        self.busy, self.message = True, ""
        self.games_pane.status.setText("Looking up pictures and changing Steam's shortcuts…" if key else
                                       "Changing Steam's shortcuts…")
        self.steam_pill.setEnabled(False)
        self.log.info(f"Update Steam: {len(add)} in, {len(remove)} out.")
        self._job = "steam"
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
        self.copy_card_pill.setEnabled(bool(self.last_card) and any(c.name == self.last_card for c in found))

    def _card_focused(self, key: str) -> None:
        if not self.card_view and key != BACK_KEY and not key.startswith("save:"):
            self.last_card = key
            self.copy_card_pill.setEnabled(True)

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
        first = self.settings_pane.pills[ALL_SETTINGS[0].key]
        if first.isEnabled():
            first.setFocus()

    def step_setting(self, setting: Setting) -> None:
        """A on a setting's pill: its next value, written now, unless PCSX2 runs."""
        if self.busy or not emulator.installed(self.home):
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
        elif main == "Open PCSX2":
            self.open_pcsx2()

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
        self.busy = False
        if self.close_asked:
            self._confirm_over()
        ok, text = result if isinstance(result, tuple) else (False, f"Steam was not changed: {result}")
        self.games_pane.status.setText(text)
        (self.log.info if ok else self.log.error)(text.replace("\n", " "))
        self._unmarked = set()
        self.refresh_games()

    def open_pcsx2(self) -> None:
        if self.running(self.home):
            self.message = "PCSX2 is open already."
            self.refresh()
            return
        self.prepare()
        try:
            self.start_program(self.home)
        except OSError as error:
            self.message = f"PCSX2 could not be started: {error}"
            self.log.error(f"PCSX2 could not be started: {error}")
            self.refresh()
            return
        self.message = ""
        self.log.info("Opened PCSX2.")
        self.refresh()

    def remove_action(self) -> None:
        """Remove asks for a second press (no dialog on a handheld): the pill says so for a few seconds."""
        if self.busy or not emulator.installed(self.home):
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
        changed = self.confirm_remove or self.close_asked
        if self.close_asked:
            self.legend.set_items(LEGEND)
            if self.message.startswith("Press B again"):
                self.message = ""
        self.confirm_remove = self.close_asked = False
        if changed:
            self.refresh()

    # B

    def on_back(self) -> None:
        if self.busy and not self.close_asked:          # closing drops the download (owner, 28-10-2026: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = ("Press B again to close: Steam's shortcuts may be left half changed."
                            if self._job == "steam" else "Press B again to close: the download stops.")
            self.legend.set_items([("B", "Press again to close")])
            self.refresh()
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
