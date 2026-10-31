# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the suite's portable window, as RPCS3 Manager and PCSX2 Manager lay it out: the cards on the left
(shadPS4, Your games, Settings, shadNet, Log: the BC250 suite's shadPS4 Manager's parts), what the focused one shows on
the right, the controller's buttons at the bottom.

Every action is a controller button in the legend at the bottom, A too, and a tap on the entry does the same; there
are no pills (owner, 29-10-2026: one way everywhere). Core's rule ends the legend: B goes back (a pane to its card,
a page to its pane), View exits the app and Menu shows the information of the pane that shows. Nothing is browsed to
(owner, 30-10-2026): the games, the packages and the system modules are put in the app's own folders (library.fixed:
Games\\PS4 and Games\\PS4\\Modules in your user folder), and the app takes care of them.

The shadPS4 pane: what is installed, the system modules, the play time and where; A Install until shadPS4 is
installed, Y Update when another version is there and X Remove shadPS4 (a second press); the system modules put in
Games\\PS4\\Modules are copied into shadPS4's module folder when the app opens and when the shadPS4 card gets the focus
(userdata.sync_modules, only what is new or changed). A press that cannot act now says why on the status line.
Nothing downloads before A. The download, the unpacking and shadNet's server run off the window's thread; the pane
counts the megabytes or the files. View (exit) while a job runs asks first, as the portal does. shadPS4's own window (Big Picture) is never shown: what the app owns in shadPS4's
files (userdata: the quit hotkeys, View + Menu) is set after an install and when the window opens.

The Your games pane (panes.py, library.py): the games in the app's own Games\\PS4 folders (owner, 30-10-2026: the
games and packages are dropped there; library.fixed, an SD card's too), played from Steam (owner, 29-10-2026); A
marks one for Steam, X plays one that is in Steam, through Steam (steam://rungameid), and on a device without Steam
starts it in the app's play mode itself (owner, 30-10-2026: a fallback, as its shortcut would start it; core's play:
View, LB and RB held quit any game), Y Update Steam makes Steam's shortcuts match the marks and brings a shortcut made
before the play mode to it, RB Remove game (a second press) takes a game out of Steam and deletes its folder with its
update. A package that waits there (extract.waiting: a game not unpacked, an update its game lacks) is a row of its
own, PKG; A unpacks it, X Unpack all every one, the games first and each update beside its game (extract.place), and a
package unpacked whole is deleted (extract.py, Extract PKG of the BC250 app). LB Steam artwork keeps the SteamGridDB key; Steam's library is the portal's RT Steam (owner,
30-10-2026: Open Steam moved there).
The Log pane: shadPS4's folder, the app's folders and the newest lines of the app's log; A (or a tap on the pane)
shows the whole log in the pane.

The Settings pane: the BC250 app's settings of shadPS4, in tabs (LB and RB: Picture, Sound, Controller, In a game), a
row each with its value; A steps to the next value and writes it into config.json at once (shadps4_settings). The
shadNet pane: the account shadPS4 signs in with when a game starts (the BC250 app's shadNet window), a row each; A on
a text row opens its page (FieldPane), with the touch keyboard; X creates the account on the server, Y tries the
sign-in. Neither writes while shadPS4 runs (it writes its own settings back when it ends)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, covers, platform, play, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, BODY, DIM, EXIT, KEYBOARD, VIEW, Card, InfoPill, Legend, Pane, PortableHeader,
                                 PortableWindow, Row, Tabs, px, status_clock, text_label)

from . import (APP_ID, APP_NAME, LOGO_PATH, __version__, emulator, extract, library, shadnet, shadps4_settings,
               shortcuts, userdata)
from .games import Game, scan
from .panes import GAMES_INFO, SHADPS4_INFO, FieldPane, KeyPane, ListPane, LogPane, ShadNetPane
from .shadps4_settings import TABS, Setting

STATUS_MS = 30_000              # the header's battery and time
PROGRESS_MS = 500               # the megabytes of a download, the files of an extraction
CONFIRM_MS = 5000               # Remove, a replaced update, and View (exit) while a job runs, ask for a second press
CARDS_WIDTH = 460               # the cards' column; the panes take the rest
CARD_HEIGHT = 100               # five cards and their gaps fit the column at 720 px high
ABOUT = ("shadPS4, the PS4 emulator, installed for your own user: its settings, your saves and the system modules "
         "stay in its folder.")
LOG_LINES = 12                  # the newest lines of the app's log in the Log pane
LOG_MAX = 2000                  # the lines of the log the whole view shows, the newest
RUNNING = "shadPS4 is open: close it first, it would write its own settings over the change."
NOT_INSTALLED = "Install shadPS4 first: the settings are in its folder."
BUSY = "Wait a moment: the app is still busy with the step before."
NO_GAME = "Put the focus on a game first: the X button starts it."
NOTHING_TO_UNPACK = "Nothing to unpack: put .pkg files in your Games\\PS4 folder, then the X button unpacks them."
ALL_SETTINGS = shadps4_settings.SETTINGS
# The Settings pane's information, per tab: what each setting of the tab does
TAB_INFO = {key: ("The A button changes the setting the focus is on, the LB and RB buttons change the tab; shadPS4 "
                  "reads the settings when a game starts. A game's own settings in shadPS4 come before these.\n\n"
                  + "\n".join(f"{setting.label}: {setting.tip}" for setting in group))
            for key, _name, group in TABS}
NO_STEAM = "Steam was never started on this device: start it once, then Update Steam puts the marked games in it."
NOTHING_TO_CHANGE = ("Nothing to change in Steam: the A button on a game marks it for Steam or takes the mark away, "
                     "then the Y button updates Steam.")
# shadNet's text rows: (title, what it is for, hidden, longest)
FIELDS = {
    "npid": ("shadNet name", "The name of your shadNet account: 3 to 16 letters, digits, - or _. Names are "
                             "case-sensitive. The A button keeps it, the X button pastes one you copied.", False, 16),
    "password": ("Password", "Your shadNet account's password. It goes over the network as it is: use one you use "
                             "nowhere else. The A button keeps it.", True, 128),
    "email": ("Email", "The email address of your shadNet account, needed to create one. The A button keeps it.",
              False, 254),
    "server": ("Server", f"The shadNet server shadPS4 signs in to: host:port. Empty is shadPS4's own server, "
                         f"{shadnet.DEFAULT_SERVER}. The A button keeps it.", False, 255),
    "key": ("Registration key", "Only when the server asks for one to create an account: ask whoever runs it. It is "
                                "used for creating the account and kept nowhere.", False, 255),
}


def wrappable(path: Path) -> str:
    """A path as the screen shows it: the user's folders by their variable (%LOCALAPPDATA%: never the user's name,
    owner 29-10-2026), wrapping after each backslash, as a long one would make the pane wider than the screen."""
    return private(path).replace("\\", "\\​")


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
    """The settings in tabs, as RPCS3 Manager's: LB and RB step through Picture, Sound, Controller and In a game, a
    tap picks one; a tab is a page of rows, "VSync: Mailbox (no tearing)", and A on one steps to the next value (the
    window writes it). The information icon tells what the tab's settings do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Settings", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("shadPS4's settings", TAB_INFO[TABS[0][0]])
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
                 runtime_missing: Callable[[], list[str]] = emulator.runtime_missing,
                 unpack: Callable[..., tuple[Path, int, int]] = extract.unpack,
                 connect: shadnet.Connect = shadnet._connect,
                 steam_dir: Path | None | bool = False,
                 steam_closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 user_home: Path | None = None, drives: Callable[[], list[Path]] = library.removable_drives,
                 settings: QSettings | None = None,
                 play: Callable[[str], None] = steam.open_url,
                 start: Callable[..., None] = platform.start_program):
        """*steam_dir*: Steam's folder (False: found on this system, None: no Steam); *runtime_missing*: the Visual
        C++ runtime's files that are missing; *unpack*: Extract PKG's job (extract.unpack); *connect*: opens the
        connection to a shadNet server (tests pass a fake server); *user_home*: the user's folder (where Games\\PS4
        is); *drives*: the removable drives, whose Games\\PS4 is looked in too; *settings*: the app's (its .ini,
        create_app's); *play*: hands a steam:// address to Steam (a game); *start*: starts a program on its own
        (shadPS4 with a game, without Steam)."""
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.home = home or emulator.emulator_home()
        self.shad_home = emulator.user_folder(self.home)
        self.install_job, self.running, self.unpack = install, running, unpack
        self.runtime_missing = runtime_missing
        self.connect = connect
        self.busy = False
        self.got = 0                                    # bytes of the download so far (the worker's thread writes it)
        self.files = (0, 0)                             # files of an extraction done, in all (the worker's thread)
        self.stage = ""                                 # "Checking the download…", "Unpacking…", a job's line
        self.message = ""                               # the last outcome
        self.confirm_remove = self.close_asked = False
        self.steam_closed = steam_closed
        self._job = ""                                  # "install", "steam", "extract" or "shadnet" while one runs
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.user_home, self.drives = user_home, drives
        self.settings = settings if settings is not None else QSettings()
        self.play, self.start_program = play, start
        self.games: list[Game] = []
        self.in_steam: dict[str, str] = {}
        self.outdated: set[str] = set()                 # games whose shortcut does not start the play mode yet
        self.marked: set[str] = set()
        self.remove_asked = ""                          # a game RB pressed once: RB again deletes it
        self.waiting: list[extract.Package] = []        # the game packages in the game folders not unpacked yet
        self.config: dict = {}
        self.modules = userdata.check_modules(self.shad_home / "sys_modules")
        self.users: list[userdata.User] = []
        self.user_index = 0                             # the shadNet pane's player
        self.registration = ""                          # shadNet's registration key: for creating an account only
        self.session = ("", "")                         # what shadPS4's log says of its last sign-in

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
        self.shadps4_card = Card("shadPS4", "Install it, the system modules and your packages.")
        self.games_card = Card("Your games", "Mark them for Steam, play them, their folders.")
        self.settings_card = Card("Settings", "The picture, the sound and the controller.")
        self.shadnet_card = Card("shadNet", "The online account shadPS4 signs in with.")
        self.log_card = Card("Log", "shadPS4's folder, and this app's log.")
        for card in (self.shadps4_card, self.games_card, self.settings_card, self.shadnet_card, self.log_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()

        self.pane = Pane()
        heading = QHBoxLayout()
        heading.addWidget(text_label("shadPS4", 24, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.shadps4_info = InfoPill("shadPS4", SHADPS4_INFO)
        heading.addWidget(self.shadps4_info, 0, Qt.AlignmentFlag.AlignTop)
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
        self.shadnet_pane = ShadNetPane()
        self.key_pane = KeyPane()
        self.field_pane = FieldPane()
        self.log_pane = LogPane()
        for pane in (self.pane, self.games_pane, self.settings_pane, self.shadnet_pane, self.log_pane, self.key_pane,
                     self.field_pane):
            self.panes.addWidget(pane)
        self.cards = {self.pane: self.shadps4_card, self.games_pane: self.games_card,
                      self.settings_pane: self.settings_card, self.shadnet_pane: self.shadnet_card,
                      self.log_pane: self.log_card, self.key_pane: self.games_card,
                      self.field_pane: self.shadnet_card}
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend([EXIT])
        page.addWidget(self.legend)

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        self.worker.said.connect(self._said)
        self.shadps4_card.focused.connect(self.show_shadps4)
        self.shadps4_card.activated.connect(self.main_action)
        self.settings_card.focused.connect(lambda: self.show_pane(self.settings_pane))
        self.settings_card.activated.connect(self.focus_settings)
        self.games_card.focused.connect(lambda: self.show_pane(self.games_pane))
        self.games_card.activated.connect(lambda: self.focus_list(self.games_pane))
        self.shadnet_card.focused.connect(self.show_shadnet_pane)
        self.shadnet_card.activated.connect(lambda: self.shadnet_pane.pills["on"].setFocus())
        self.log_card.focused.connect(lambda: self.show_pane(self.log_pane))
        self.log_card.activated.connect(self.view_log)
        self.log_pane.tapped.connect(self.view_log)
        self.games_pane.list.picked.connect(self.game_picked)
        self.confirm_key = False                        # Remove key pressed once
        for setting in ALL_SETTINGS:
            self.settings_pane.pills[setting.key].activated.connect(lambda s=setting: self.step_setting(s))
        for key, pill in self.shadnet_pane.pills.items():
            pill.activated.connect(lambda key=key: self.shadnet_row(key))
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
        self.read_shadps4()
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, shadPS4's files brought to what the app owns,
        and the focus on the shadPS4 card."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.prepare()
        self.read_shadps4()
        self.sync_modules()
        self.refresh()
        self.refresh_games()
        self.shadps4_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def read_shadps4(self) -> None:
        """shadPS4's settings, its users, the system modules and what its log says of shadNet, from its folder."""
        self.config = userdata.read_config(self.shad_home)
        self.modules = userdata.check_modules(userdata.modules_folder(self.shad_home, self.config))
        self.users = userdata.read_users(self.shad_home)
        self.user_index = min(self.user_index, max(len(self.users) - 1, 0))
        self.session = shadnet.session(self.shad_home / "log")

    def show_shadps4(self) -> None:
        self.sync_modules()
        self.show_pane(self.pane)

    def sync_modules(self) -> None:
        """The system modules put in Games\\PS4\\Modules (owner, 30-10-2026: drop them there, the app takes care of
        them) copied into shadPS4's module folder while shadPS4 is installed, the new or changed ones only; what was
        copied goes to the status line and the log."""
        if self.busy or not emulator.installed(self.home):
            return
        source = library.modules_home(self.user_home)
        try:
            copied = userdata.sync_modules(source, self.modules.folder)
        except OSError as error:
            self.message = f"The system modules were not copied: {error.strerror or error}"
            self.log.error(f"Copying the system modules from {source} failed: {error}")
            self.refresh()
            return
        if not copied:
            return
        self.read_shadps4()
        self.message = (f"{len(copied)} system module(s) taken from the Modules folder: {len(self.modules.needed)} of "
                        f"the {len(userdata.NEEDED)} shadPS4 cannot do without are there now.")
        self.log.info(self.message)
        self.refresh()

    def prepare(self) -> None:
        """shadPS4's files brought to what the app owns while it is installed: the quit hotkeys in
        input_config\\global.ini, which shadPS4 reads when a game starts (so it may run meanwhile); what was added
        goes to the log."""
        if not emulator.installed(self.home):
            return
        try:
            added = userdata.add_quit_bindings(self.shad_home)
        except OSError as error:
            self.log.error(f"shadPS4's quit hotkeys could not be written: {error}")
            return
        if added:
            self.log.info("shadPS4 set up: View + Menu (Back + Start) and Ctrl+Shift+End open its quit window.")

    # What the panes say

    def state(self) -> tuple[str, str, str]:
        """The status line (amber), A's entry (Install) and Y's (Update); "" leaves either out."""
        if self.busy and self._job == "steam":
            return "Steam's shortcuts are being changed (Your games).", "", ""
        if self.busy and self._job == "shadnet":
            return "Asking the shadNet server (shadNet).", "", ""
        if self.busy and self._job == "remove":
            return "A game is being removed (Your games).", "", ""
        if self.busy and self._job == "extract":
            done, total = self.files
            files = f" {done} of {total} files" if total else ""
            return f"{self.stage}{files}", "", ""
        if self.busy:
            if self.stage:
                return self.stage, "", ""
            got = f" {self.got / emulator.MB:.0f} of {emulator.SIZE / emulator.MB:.0f} MB" if self.got else ""
            return f"Downloading shadPS4 {emulator.VERSION}…{got}", "", ""
        version = emulator.installed(self.home)
        if not version:
            return "", "Install", ""
        if version != emulator.VERSION:
            return f"This app installs shadPS4 {emulator.VERSION}: the Y button updates it.", "", "Update"
        missing = self.runtime_missing()
        if missing:
            return (f"shadPS4 needs Microsoft's Visual C++ runtime ({', '.join(missing)} missing in System32): "
                    "install vc_redist.x64.exe from Microsoft, then open the app again.", "", "")
        if not self.modules.complete:
            return (f"Some games need system modules from your own PS4: put them in "
                    f"{private(library.modules_home(self.user_home))}, and the app copies them into shadPS4.", "", "")
        return "", "", ""

    def modules_text(self) -> str:
        m = self.modules
        if m.complete:
            return f"all {len(userdata.NEEDED)}"
        return f"{len(m.needed)} of {len(userdata.NEEDED)}"

    def rows(self) -> list[tuple[str, str]]:
        version = emulator.installed(self.home)
        rows = [("Installed", version or "not installed"), ("This app installs", emulator.VERSION),
                ("System modules", self.modules_text())]
        total = sum(seconds for seconds, _ in userdata.play_times(self.shad_home).values())
        if total:
            rows.append(("Play time", userdata.played(total)))
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
            status = ("Press the X button again to remove shadPS4: its folder, with your saves and the system modules, "
                      "stays.")
        self.status.setText(self.message or status)
        if self.busy and self._job == "extract":
            self.games_pane.status.setText(status)      # the packages are unpacked from Your games: their files there
        self.refresh_settings()
        self.refresh_shadnet()
        self.update_legend()

    def refresh_settings(self) -> None:
        ready = not self.busy and bool(emulator.installed(self.home))
        values = shadps4_settings.read_settings(self.shad_home) if ready else {}
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
        the same), then core's Menu Info, B Back (in a pane, and on the key page, a field's page and the whole log)
        and View Exit. A press that cannot act now says why on the status line."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.pane:
            _status, main, other = self.state()
            installed = not self.busy and bool(emulator.installed(self.home))
            items = [*([("A", main)] if main else []),
                     *([("X", "Press again" if self.confirm_remove else "Remove shadPS4")] if installed else []),
                     *([("Y", other)] if other else [])]
        elif pane is self.games_pane:
            focused = self.games_pane.list.focused()
            if focused.startswith("pkg:"):
                items = [("A", "Unpack"), ("X", "Unpack all"), ("Y", "Update Steam"), ("LB", "Steam artwork")]
            else:
                items = [("A", "Steam mark"), *([("X", "Play")] if focused else []), ("Y", "Update Steam"),
                         ("LB", "Steam artwork"),
                         *([("RB", "Press again" if self.remove_asked == focused else "Remove game")]
                           if focused else [])]
        elif pane is self.settings_pane:
            items = [("A", "Change"), ("LB", "Previous tab"), ("RB", "Next tab")]
        elif pane is self.shadnet_pane:
            items = [("A", "Change"), ("X", "Create account"), ("Y", "Try sign-in")]
        elif pane is self.log_pane:
            items = [] if self.log_pane.viewing else [("A", "View log")]
        elif pane is self.key_pane:
            items = [("A", "Save"), ("X", "Paste"), ("Y", "Press again" if self.confirm_key else "Remove key"),
                     KEYBOARD]
        elif pane is self.field_pane:
            items = [("A", "Keep"), ("X", "Paste"), KEYBOARD]
        on_a_page = pane in (self.key_pane, self.field_pane) or self.log_pane.viewing
        return [*items, *self.common_items(True if on_a_page else None)]

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        (pane.list.first() or self.cards[pane]).setFocus()

    # Your games

    def game_folders(self) -> list[Path]:
        """The app's own Games\\PS4 folders (made when missing): the user's, then each SD card's."""
        return library.fixed(self.user_home, self.drives)

    def scan(self) -> list[Game]:
        return scan(self.game_folders())

    def unpacked(self) -> dict[str, Path]:
        """Each game's folder by its title ID, a game without its update before one with it in it."""
        ordered = sorted((g for g in self.games if g.title_id), key=lambda g: not g.patched)
        return {g.title_id: g.folder for g in ordered}

    def refresh_games(self, in_steam: dict[str, str] | None = None) -> None:
        """The games, which are in Steam (*in_steam* when given: what Update Steam read back, else Steam's file now),
        and the list as the view shows it."""
        self.games = self.scan()
        self.waiting = extract.waiting(self.game_folders(), self.unpacked())
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
        found = {str(g.eboot) for g in self.games}
        self.marked = {f for f in self.marked if f in found} | {f for f in self.in_steam if f in found
                                                                  and f not in self._unmarked}
        self.show_games()

    _unmarked: set[str] = set()                         # games in Steam the user took the mark off, until Update

    def show_games(self) -> None:
        pane = self.games_pane
        own = library.fixed(self.user_home, self.drives)
        in_steam = sum(1 for g in self.games if str(g.eboot) in self.in_steam)
        pane.summary.setText(f"{len(self.games)} game(s) in {len(self.game_folders())} folder(s)"
                             + (f", {len(self.waiting)} to unpack" if self.waiting else "")
                             + (f", {in_steam} in Steam" if self.steam_dir is not None else
                                ". Steam was never started on this device: start it once to put games in it."))
        rows = [(str(g.eboot), self.game_text(g)) for g in self.games]
        unpacked = self.unpacked()
        rows += [(f"pkg:{p.path}", "  ·  ".join(t for t in (
            p.title or p.path.name, p.title_id,
            "PKG update" if p.category == "gp" and p.title_id in unpacked else "PKG") if t))
                 for p in self.waiting]                 # short, or the row is cut off (owner, 30-10-2026)
        if not rows:
            pane.status.setText(pane.status.text() or
                                f"No games yet: put your .pkg files or unpacked games in {private(own[0])}, then "
                                "the X button unpacks the packages.")
        pane.list.set_items(rows)
        self.update_legend()

    def game_text(self, game: Game) -> str:
        if self.remove_asked == str(game.eboot):
            return f"Press RB again to delete {game.title} from the disk"
        mark = "✓ Steam" if str(game.eboot) in self.marked else ""
        changed = ((str(game.eboot) in self.marked) != (str(game.eboot) in self.in_steam)
                   or str(game.eboot) in self.marked and str(game.eboot) in self.outdated)
        seconds = userdata.play_times(self.shad_home).get(game.title_id, (0, 0.0))[0] if game.title_id else 0
        parts = (game.title, game.title_id, userdata.played(seconds) if seconds else "",
                 mark + (" (Update Steam)" if changed else ""))
        return "  ·  ".join(p for p in parts if p)

    def game_picked(self, key: str) -> None:
        """A on a row: a game's Steam mark, or a package unpacked."""
        if key.startswith("pkg:"):
            self.unpack_packages([p for p in self.waiting if str(p.path) == key[4:]])
        else:
            self.mark_game(key)

    def play_game(self) -> None:
        """X on a game: started through Steam (owner, 29-10-2026), which starts shadPS4 with it full screen as its
        shortcut says; Steam starts first when it does not run. A game not in Steam yet says how it gets there; on a
        device without Steam shadPS4 starts it itself."""
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


    def unpack_packages(self, packages: list[extract.Package]) -> None:
        """A on a PKG, or X Unpack all (owner, 30-10-2026: drop the packages in the folder, the manager takes care of
        them): unpacked one after the other off the window's thread, the games first, each update beside its game (an
        older one there replaced), the files counted on the pane's line. A package unpacked without a missing file is
        deleted (owner, 30-10-2026: it takes as much room as its game)."""
        if self.busy:
            self.games_pane.status.setText(BUSY)
            return
        todo = sorted(packages, key=lambda p: extract.ORDER[p.category])
        if not todo:
            self.games_pane.status.setText(NOTHING_TO_UNPACK)
            return
        unpacked = self.unpacked()
        games = {p.title_id for p in todo if p.category == "gd"}
        waiting_games = {p.title_id for p in self.waiting if p.category == "gd"}
        alone = next((p for p in todo if p.category == "gp" and p.title_id not in unpacked
                      and p.title_id in waiting_games and p.title_id not in games), None)
        if alone is not None:                           # its game first, or the update takes the game's folder
            self.games_pane.status.setText(f"{alone.title or alone.title_id} is an update: unpack its game first, or "
                                           "the X button unpacks both.")
            return
        run, log = self.unpack, self.log

        def progress(done: int, total: int) -> None:
            self.files = (done, total)                  # read by refresh() on the window's thread

        def job() -> tuple[bool, str]:
            done: list[str] = []
            failed: list[str] = []
            for n, package in enumerate(todo, 1):
                what = package.title or package.title_id or package.path.name
                self.stage = f"Unpacking {n} of {len(todo)}: {what}…" if len(todo) > 1 else f"Unpacking {what}…"
                self.files = (0, 0)
                folder, game = extract.place(package, unpacked)
                log.info(f"Extract PKG: {package.path} ({package.title_id}, {package.kind}) into {folder}.")
                try:
                    final, written, missing = run(package, folder.parent, game is not None and
                                                  extract.has_entries(folder), progress, log.info, beside=game)
                except extract.ExtractError as error:
                    failed.append(f"{what} ({error})")
                    continue
                if missing:
                    failed.append(f"{what} ({missing} of {written + missing} file(s) missing, {extract.ERRORS} in "
                                  f"{final.name} names them; the package stays)")
                    continue
                if package.category == "gd":
                    unpacked[package.title_id] = final
                try:
                    package.path.unlink()
                except OSError as error:
                    failed.append(f"{what} (unpacked, but {package.path.name} was not deleted: "
                                  f"{error.strerror or error})")
                    continue
                done.append(what)
            if len(todo) == 1 and done:
                text = f"{done[0]} is unpacked, and its package is deleted."
            else:
                text = f"{len(done)} of {len(todo)} package(s) unpacked, each package deleted after."
            if failed:
                text += " Not done: " + "; ".join(failed) + "."
            return not failed, text
        self.busy, self.message, self.files = True, "", (0, 0)
        self._job = "extract"
        self.stage = f"Unpacking 1 of {len(todo)}…" if len(todo) > 1 else "Unpacking…"
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Extract PKG: {len(todo)} package(s).")
        self.worker.run(job)

    def remove_game(self) -> None:
        """RB on a game (owner, 30-10-2026: a game that no longer plays goes): with a second press (no dialog on a
        handheld), its shortcut taken out of Steam, then its folder deleted with its update, patch and mods beside it
        (library.removal), off the window's thread. Its saves and play time stay in shadPS4's folder; the package it
        came from is not touched."""
        key = self.games_pane.list.focused()
        game = next((g for g in self.games if str(g.eboot) == key), None)
        if game is None:
            return
        if self.busy:
            self.games_pane.status.setText(BUSY)
            return
        if self.running(self.home):
            self.games_pane.status.setText("shadPS4 is open: quit the game first, then remove it.")
            return
        folders, why = library.removal(game, self.game_folders(), self.games)
        if not folders:
            self.games_pane.status.setText(private(why))
            return
        if self.remove_asked != key:
            self.remove_asked = key
            self.confirm_timer.start()
            self.show_games()
            self.games_pane.list.pills[key].setFocus()
            self.games_pane.status.setText(
                f"Press the RB button again to delete {', '.join(f.name for f in folders)} from the disk"
                + (" and take the game out of Steam" if key in self.in_steam else "")
                + ". Its saves stay in shadPS4's folder.")
            self.update_legend()
            return
        self.remove_asked = ""
        steam_dir = self.steam_dir if key in self.in_steam else None
        closed, program, existing = self.steam_closed, emulator.program(self.home), self.in_steam

        def job() -> tuple[bool, str, dict[str, str] | None]:
            found = None
            if steam_dir is not None:
                ok, said, found = library.update_steam(steam_dir, [], [game], program, LOGO_PATH, existing, closed)
                if not ok:
                    return False, f"{game.title} was not removed: {said}", None
            failed = library.delete(folders)
            if failed:
                return False, f"{game.title} was not removed completely: not deleted {', '.join(failed)}.", found
            return True, (f"{game.title} is removed: {', '.join(f.name for f in folders)} deleted"
                          + (", its shortcut taken out of Steam" if steam_dir is not None else "")
                          + ". Its saves stay in shadPS4's folder."), found
        self.busy, self.message = True, ""
        self._job = "remove"
        self.games_pane.status.setText(f"Removing {game.title}…")
        self.log.info(f"Removing {game.title}: {', '.join(str(f) for f in folders)}"
                      + (", and its Steam shortcut." if steam_dir is not None else "."))
        self.worker.run(job)

    def play_without_steam(self, game: Game) -> None:
        """X on a game on a device without Steam (owner, 30-10-2026: a fallback): shadPS4 started with it full screen,
        as its Steam shortcut would start it, outside the app's bundle (platform.start_program)."""
        if not emulator.installed(self.home):
            self.games_pane.status.setText(f"Install shadPS4 first: it starts {game.title} on a device without Steam.")
            return
        command = shortcuts.command(game)
        try:
            self.start_program(command, cwd=emulator.program(self.home).parent)
        except OSError as error:
            self.games_pane.status.setText(f"shadPS4 could not start {game.title}: {error.strerror or error}")
            self.log.error(f"Starting {game.title} in shadPS4 failed: {error}")
            return
        self.games_pane.status.setText(f"Starting {game.title} in shadPS4… {play.QUIT_HINT}")
        self.log.info(f"Starting {game.title} in shadPS4, without Steam.")

    # The system modules

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
        pane.field.setText(text.split()[0] if pane is self.key_pane else text)
        pane.status.setText("The text is in the field: the A button keeps it.")

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

    # shadNet (the BC250 app's shadNet window as a pane of rows, a text row's page the FieldPane)

    def user(self) -> userdata.User | None:
        return self.users[self.user_index] if self.users else None

    def server(self) -> str:
        return userdata.shadnet_server(self.config)

    def show_shadnet_pane(self) -> None:
        self.read_shadps4()
        self.refresh_shadnet()
        self.show_pane(self.shadnet_pane)

    def refresh_shadnet(self) -> None:
        pane, user = self.shadnet_pane, self.user()
        signing_in = userdata.signing_in(self.config, self.users)
        state, detail = self.session
        if signing_in:
            text = (", ".join(u.npid for u in signing_in) + f" signs in to {self.server()} when a game starts.")
        else:
            text = "Off: shadPS4 plays offline. Sign in switches it on, once the account is filled in."
        if state == "online":
            text += f" The last game signed in as {detail}."
        elif state == "offline":
            text += f" The last game: {detail}."
        pane.summary.setText(text)
        on = bool(user and user.shadnet and userdata.shadnet_on(self.config))
        players = len(self.users)
        values = {"on": "On" if on else "Off",
                  "user": f"{user.name} (player {self.user_index + 1} of {players})" if user else "none",
                  "npid": (user.npid if user else "") or "not set",
                  "password": "••••••••" if user and user.password else "not set",
                  "email": (user.email if user else "") or "not set",
                  "server": self.server(),
                  "key": "given" if self.registration else "none (only when the server asks for one)"}
        for key, label in pane.ROWS:
            pane.pills[key].set_text(f"{label}: {values[key]}")

    def _shadnet_ready(self) -> bool:
        """Whether shadNet's account may be written now; else the status line says why."""
        if self.busy:
            self.shadnet_pane.status.setText(BUSY)
        elif not emulator.installed(self.home):
            self.shadnet_pane.status.setText("Install shadPS4 first: the account is kept in its folder.")
        elif self.running(self.home):
            self.shadnet_pane.status.setText(RUNNING)
        elif self.user() is None:
            self.shadnet_pane.status.setText("shadPS4's users could not be read (users.json in its folder).")
        else:
            return True
        return False

    def save_account(self, npid: str | None = None, password: str | None = None, email: str | None = None,
                     on: bool | None = None, server: str | None = None) -> bool:
        """The player's account with the values given changed, in shadPS4's files at once; whether it was."""
        user = self.user()
        if user is None or not self._shadnet_ready():
            return False
        npid = user.npid if npid is None else npid
        on = user.shadnet and userdata.shadnet_on(self.config) if on is None else on
        try:
            userdata.save_shadnet(self.shad_home, user.user_id, npid, user.password if password is None else password,
                                  user.email if email is None else email, on,
                                  self.server() if server is None else server)
        except userdata.UserDataError as error:
            self.shadnet_pane.status.setText(str(error))
            self.log.error(f"shadNet's settings were not saved: {error}")
            return False
        self.read_shadps4()
        self.refresh_shadnet()
        return True

    def shadnet_row(self, key: str) -> None:
        """A on one of shadNet's rows: Sign in on or off, the next player, or the row's own page."""
        user = self.user()
        if key == "user":
            if self.users:
                self.user_index = (self.user_index + 1) % len(self.users)
                self.shadnet_pane.status.setText("")
                self.refresh_shadnet()
            return
        if key == "on":
            if user is None:
                self._shadnet_ready()
                return
            turn_on = not (user.shadnet and userdata.shadnet_on(self.config))
            if turn_on and (why := shadnet.check_npid(user.npid)):
                self.shadnet_pane.status.setText(f"Fill in the shadNet name first. {why}")
                return
            if turn_on and not user.password:
                self.shadnet_pane.status.setText("Fill in the password first.")
                return
            if self.save_account(on=turn_on):
                said = (f"{user.npid} signs in to shadNet when a game starts." if turn_on else
                        f"{user.name} no longer signs in to shadNet.")
                self.shadnet_pane.status.setText(said)
                self.log.info(said)
            return
        title, text, hidden, length = FIELDS[key]
        value = {"npid": user.npid if user else "", "password": user.password if user else "",
                 "email": user.email if user else "", "server": self.server(), "key": self.registration}[key]
        self.field_pane.set_field(key, title, text, value, hidden, shadnet.DEFAULT_SERVER if key == "server" else "",
                                  length)
        self.show_pane(self.field_pane)
        self.field_pane.field.setFocus()

    def keep_field(self) -> None:
        """A on a field's page: the value kept (shadNet's in shadPS4's files; the registration key in the window
        only), back to the shadNet pane."""
        key, value = self.field_pane.key, self.field_pane.field.text().strip()
        if key == "key":
            self.registration = value
        elif key == "server":
            try:
                server = str(shadnet.parse_server(value or shadnet.DEFAULT_SERVER))
            except shadnet.ShadNetError as error:
                self.field_pane.status.setText(str(error))
                return
            if not self.save_account(server=server):
                self.field_pane.status.setText(self.shadnet_pane.status.text())
                return
        else:
            if key == "npid" and value and (why := shadnet.check_npid(value)):
                self.field_pane.status.setText(why)
                return
            if key == "password":
                value = self.field_pane.field.text()     # a password keeps its spaces
            if not self.save_account(**{key: value}):
                self.field_pane.status.setText(self.shadnet_pane.status.text())
                return
            if key == "npid" and not value:
                self.save_account(on=False)             # no name, no sign-in
        if key != "key":
            self.log.info(f"shadNet: {FIELDS[key][0]} changed.")
        self.back_to_shadnet(f"{FIELDS[key][0]} kept.")

    def back_to_shadnet(self, said: str = "") -> None:
        key = self.field_pane.key
        self.field_pane.field.clear()                   # a password is not left in the window
        self.show_pane(self.shadnet_pane)
        self.shadnet_pane.status.setText(said)
        self.shadnet_pane.pills.get(key, self.shadnet_pane.pills["on"]).setFocus()

    def shadnet_job(self, create: bool) -> None:
        """X Create account or Y Try sign-in, off the window's thread: the BC250 app's shadNet window's buttons."""
        pane, user = self.shadnet_pane, self.user()
        if self.busy:
            pane.status.setText(BUSY)
            return
        if user is None:
            self._shadnet_ready()
            return
        try:
            server = shadnet.parse_server(self.server())
            if why := shadnet.check_npid(user.npid):
                raise shadnet.ShadNetError(why)
            if not user.password:
                raise shadnet.ShadNetError("Fill in the password first.")
            if create and not user.email:
                raise shadnet.ShadNetError("Fill in the email address first: creating an account needs it.")
        except shadnet.ShadNetError as error:
            pane.status.setText(str(error))
            return
        npid, password, email, key, connect = user.npid, user.password, user.email, self.registration, self.connect

        def job() -> tuple[bool, str]:
            try:
                if create:
                    shadnet.create_account(server, npid, password, email, key, connect)
                else:
                    shadnet.try_sign_in(server, npid, password, connect)
            except shadnet.ShadNetError as error:
                return False, str(error)
            return True, (f"The account {npid} was created on {server}." if create else
                          f"{npid} signed in to {server}: the account works.")
        self.busy, self._job = True, "shadnet"
        pane.status.setText(f"Creating {npid} on {server}…" if create else f"Signing in to {server}…")
        self.log.info(f"shadNet: {'creating the account' if create else 'trying the sign-in of'} {npid} on {server}.")
        self.update_legend()
        self.worker.run(job)

    # The legend's buttons: what A (beside a card or a row), X, Y, LB and RB do on the pane that shows (a tap on the
    # legend's entry does the same)

    def a_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.key_pane:
            self.save_key()
        elif pane is self.field_pane:
            self.keep_field()
        elif pane is self.pane:
            self.main_action()
        elif pane is self.log_pane:
            self.view_log()

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.pane:
            self.remove_action()
        elif pane is self.key_pane:
            self.paste(self.key_pane)
        elif pane is self.field_pane:
            self.paste(self.field_pane)
        elif pane is self.shadnet_pane:
            self.shadnet_job(create=True)
        elif pane is self.games_pane:
            focused = self.games_pane.list.focused()
            if focused.startswith("pkg:"):
                self.unpack_packages(self.waiting)
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
        elif pane is self.shadnet_pane:
            self.shadnet_job(create=False)

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

    def mark_game(self, key: str) -> None:
        """A on a game: mark it for Steam, or take the mark away."""
        if key not in {str(g.eboot) for g in self.games}:
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
            self.games_pane.status.setText("Install shadPS4 first (the shadPS4 card): the games in Steam start it.")
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
        rows: list[tuple[str, str]] = [("shadPS4's folder", wrappable(self.shad_home))]
        if emulator.installed(self.home):
            rows += [("System modules", self.modules_text()),
                     ("Games", wrappable(library.fixed(self.user_home, self.drives)[0]))]   # Modules is in it
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
        """A on a setting's row: its next value, written now, unless shadPS4 runs."""
        if self.busy or not emulator.installed(self.home):
            self.settings_pane.status.setText(BUSY if self.busy else NOT_INSTALLED)
            return
        if self.running(self.home):
            self.settings_pane.status.setText(RUNNING)
            return
        value = setting.next_value(shadps4_settings.read_settings(self.shad_home)[setting.key])
        try:
            shadps4_settings.write_setting(self.shad_home, setting, value)
        except userdata.UserDataError as error:
            self.settings_pane.status.setText(f"The setting was not saved: {error}")
            self.log.error(f"Writing {setting.label} failed: {error}")
            return
        self.settings_pane.status.setText("")
        self.log.info(f"{setting.label}: {setting.shown(value)}.")
        self.refresh_settings()

    # A, X, Y, LB and RB on the shadPS4 pane

    def main_action(self) -> None:
        """A on the shadPS4 card or pane: Install while shadPS4 is not installed."""
        if not self.busy and self.state()[1] == "Install":
            self.install()

    def other_action(self) -> None:
        if not self.busy and self.state()[2]:
            self.install()

    def install(self) -> None:
        if self.running(self.home):
            self.message = "shadPS4 is open: close it first, then update it."
            self.refresh()
            return
        self.busy, self.got, self.stage, self.message = True, 0, "", ""
        self._job = "install"
        self._confirm_over()
        self.progress_timer.start()
        self.refresh()
        self.log.info(f"Installing shadPS4 {emulator.VERSION} in {self.home}.")
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
        if job == "shadnet":
            ok, text = result if isinstance(result, tuple) else (False, f"shadNet could not be asked: {result}")
            self.shadnet_pane.status.setText(text)
            (self.log.info if ok else self.log.error)(text)
            self.update_legend()
            return
        if job == "remove":
            ok, text, found = result if isinstance(result, tuple) else (False, f"The game was not removed: {result}",
                                                                        None)
            self.games_pane.status.setText(private(text))
            (self.log.info if ok else self.log.error)(text)
            self.refresh()
            self.refresh_games(found)
            self.focus_list(self.games_pane)
            return
        if job == "install":
            if isinstance(result, Exception):
                self.message = private(f"shadPS4 could not be installed: {result}")
                self.log.error(f"Installing shadPS4 failed: {result}")
            else:
                self.message = f"shadPS4 {result} is installed."
                self.log.info(f"shadPS4 {result} installed.")
                self.prepare()                          # before its first start
        elif job == "extract":
            ok, text = result if isinstance(result, tuple) else (False, f"The packages were not unpacked: {result}")
            self.games_pane.status.setText(private(text))
            (self.log.info if ok else self.log.error)(text)
            self.files = (0, 0)
        self.read_shadps4()
        self.refresh()
        self.refresh_games()

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
        """X Remove shadPS4 asks for a second press (no dialog on a handheld): the legend and the status line say so
        for a few seconds."""
        if self.busy:
            self.message = BUSY
            self.refresh()
            return
        if not emulator.installed(self.home):
            self.message = "shadPS4 is not installed: there is nothing to remove."
            self.refresh()
            return
        if self.running(self.home):
            self.message = "shadPS4 is open: close it first, then remove it."
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
            self.message = f"shadPS4 could not be removed: close it first. ({error.strerror or error})"
            self.log.error(f"Removing shadPS4 failed: {error}")
        else:
            self.message = "shadPS4 is removed. Its folder, with your saves, its settings and the system modules, stays."
            self.log.info("shadPS4 removed.")
        self.refresh()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.remove_asked:
            if self.games_pane.status.text().startswith("Press the RB button again"):
                self.games_pane.status.setText("")
            self.remove_asked = ""
            self.show_games()
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
        and a field's page to shadNet (nothing kept), a pane to its card; on a card it does nothing (View exits)."""
        pane = self.panes.currentWidget()
        if pane is self.log_pane and self.log_pane.viewing:
            self.log_pane.show_summary()
            self.log_card.setFocus()
            self.update_legend()
        elif pane is self.key_pane:
            self.back_to_games()
        elif pane is self.field_pane:
            self.back_to_shadnet()
        else:
            self.go_back()

    # View

    def exit_app(self) -> None:
        if self.busy and not self.close_asked:          # exiting drops the job (the portal's rule: ask first)
            self.close_asked = True
            self.confirm_timer.start()
            self.message = {"steam": "Press View again to exit: Steam's shortcuts may be left half changed.",
                            "extract": "Press View again to exit: the unpacking stops, and the game's folder is left "
                                       "half written.",
                            "shadnet": "Press View again to exit: the answer of the shadNet server is not waited for.",
                            "remove": "Press View again to exit: the game is left half deleted."
                            }.get(self._job, "Press View again to exit: the download stops.")
            self.refresh()                              # the legend says so too
            return
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.progress_timer.stop()
        self.confirm_timer.stop()
        super().closeEvent(event)
