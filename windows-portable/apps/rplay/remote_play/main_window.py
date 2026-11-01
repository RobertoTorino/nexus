# SPDX-License-Identifier: AGPL-3.0-or-later
"""The window: the cards on the left (Consoles, Register, My consoles, History, Settings), what the focused one shows
on the right, the controller's buttons at the bottom. It is the BC250 suite's Console Link made for the handheld:
find the consoles on the network (or at one address), register the handheld with one, then play it: A on a console of
My consoles wakes it when it rests and streams it full screen (stream_window.py), until View, LB and RB are held
(the suite's way out of a game) or the screen is touched and held. X opens the console's page: waking, the test
session and stream, its stream settings, its login passcode, its Steam entry, rest mode and removing it.

Console Link's fields are a row each here, a row's page with the touch keyboard: the address, the PSN account ID, the
PIN and a console's login passcode. The account ID can come from the PlayStation sign-in in the browser: the app
watches the clipboard and takes the address of the sign-in's last page as soon as it is copied, as Console Link's
dialog does. The personal details (account ID, online ID, addresses) are masked on the screen until Settings shows
them, and always in the log (privacy.py). Nothing runs before it is asked for (owner, 28-10-2026); every step on the
network runs off the window's thread (jobs.py)."""

from __future__ import annotations

import datetime
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from PyQt6.QtCore import QEvent, QObject, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, platform, power, steam
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private, suite_data
from bc250_core.portable import KEYBOARD, Card, Legend, Pane, PortableHeader, PortableWindow, px, status_clock

from . import APP_ID, APP_NAME, LOGO_PATH, SUITE, __version__, jobs, privacy, psn, steam_shortcuts, stream_stats
from .consoles import ConsoleStore, RegisteredConsole, parse_account_id, parse_login_pin, parse_pin
from .discovery import Console
from .history import HistoryStore, duration, newest_first
from .jobs import Outcome
from .panes import FieldPane, ListPane
from .stream_options import AUTO, FRAME_RATES, RESOLUTIONS, SCREENS, StreamOptions
from .stream_window import PlayWindow
from .target import rp_version, software_version

STATUS_MS = 30_000              # the header's time and battery
CONFIRM_MS = 5000               # Remove, Rest mode, Take out of Steam and Clear ask for a second press
CARDS_WIDTH = 400
CARD_HEIGHT = 84                # five cards and their gaps fit the column at 720 px high
LOG_MAX = 2000                  # the lines of the log the view shows, the newest
APART = "  ·  "
OPENS = "  ›"
STATES = {"ready": "On", "standby": "Rest mode", "unknown": "Not known"}
SHOWN_KEY = "privacy/shown"     # the personal details shown on the screen: "on" or "off" (the default)
ACCOUNT_KEY = "account_id"      # the PSN account ID, as typed or from the sign-in (Console Link's setting)
ADDRESS_KEY = "address"         # the console's address searched last
NOT_FOUND = "Search first: the X button searches the network, the address row one console."

# A console's stream settings, each stepped by A on its row of the console's page (Console Link's dialog's choices)
BITRATE_STEPS = (AUTO, 5000, 10000, 15000, 20000, 30000, 40000, 50000)      # kbit/s
AUDIO_DELAY_STEPS = (0, 50, 100, 150, 200, 300, 500)                         # ms
OPTION_ROWS = ("resolution", "fps", "bitrate", "screen", "audio_delay", "low_latency")

CONSOLES_INFO = (
    "The PS4 and PS5 consoles on this network. The X button searches the network: every console with Remote Play "
    "on (Settings > System > Remote Play > Enable Remote Play) that is on, or in rest mode, answers. A console the "
    "search does not find (in another part of the network) is searched at its address: the A button on the address "
    "row changes it, the Y button searches it.\n\n"
    "The A button on a console chooses it on the Register card, or goes to it on My consoles when this handheld is "
    "registered with it. Windows may ask once whether Remote Play may use the network: allow it for private networks.")
REGISTER_INFO = (
    "Registering lets this handheld wake the console and start Remote Play with it, as the PSN account it is "
    "registered for. It needs the console, your PSN account ID and the PIN the console shows.\n\n"
    "The account ID is not shown anywhere on PlayStation: the sign-in row opens the PlayStation sign-in in the "
    "browser. Sign in with the account you use on the console; the sign-in ends on a page that only says "
    "\"redirect\". Copy that page's address from the address bar, and the app takes it from there by itself: it sends "
    "the code in it to PSN once, keeps only the account ID, and fills it in. The code works for a few minutes.\n\n"
    "The PIN: on a PS5 under Settings > System > Remote Play > Link Device, on a PS4 under Settings > Remote Play "
    "Connection Settings > Add Device. The X button registers while the console shows it.")
MINE_INFO = (
    "The consoles this handheld is registered with. The A button plays one: it wakes the console when it rests "
    "(about 20 seconds), then streams it full screen, the handheld's controls as the console's controller. To end the "
    "stream, hold View, LB and RB together, or touch and hold the screen. The X button opens the console's page: "
    "waking, a test, the stream's settings, the login passcode, its Steam entry, rest mode and removing it.\n\n"
    "Waking from rest mode needs the console's rest-mode settings: PS5, Settings > System > Power Saving > Features "
    "Available in Rest Mode, Stay Connected to the Internet and Enable Turning On PS5 from Network; PS4, Settings > "
    "Power Saving Settings > Set Features Available in Rest Mode, the same two.")
CONSOLE_INFO = (
    "The A button acts on the row the focus is on. Wake turns the console on from rest mode. Test session starts a "
    "session and closes it again, which proves the registration; Test stream also runs the stream for five seconds "
    "without showing it, which proves the network and the decoding.\n\n"
    "The stream's settings step to their next value: the resolution and the bitrate (Automatic: 1080p at 15 Mbit/s "
    "from a PS5 or a PS4 Pro, 720p at 10 Mbit/s from a PS4, which streams 720p at most), the frame rate, how the "
    "picture fills the screen, how much later the sound plays (to meet a late picture) and low latency (a shorter "
    "sound buffer). They count from the next stream.\n\n"
    "In Steam adds the console to Steam's library, to play it from there: Steam closes for it and starts again. Y "
    "takes it out again, on a second press. Rest mode and Remove ask for a second press.")
HISTORY_INFO = (
    "The games played through the app and how long, counted while a console streams to this handheld (from Steam "
    "too): the console is asked what it runs every 30 seconds. Play on the console itself is not seen. Kept only on "
    "this handheld; the X button forgets it all, on a second press.")
SETTINGS_INFO = (
    "The A button changes a setting. Personal details: the account ID, the online ID and the consoles' addresses, "
    "masked on the screen (only their end shows) until shown here; the log always masks them. The last row shows the "
    "app's log: the d-pad scrolls it, the B button goes back.")

# The field pages: (title, what it is for, hidden, placeholder, longest)
FIELDS = {
    "address": ("Console's address", "The console's IP address, for a console the network search does not find. The "
                "console shows it under Settings > Network, View Connection Status.", False, "192.168.1.20", 253),
    "account": ("PSN account ID", "Your PSN account ID: the number, or the 12-character code that ends with =. The "
                "sign-in row on the Register card fills it in for you.", False, "", 24),
    "pin": ("PIN", "The 8 digits the console shows: a PS5 under Settings > System > Remote Play > Link Device, a PS4 "
            "under Settings > Remote Play Connection Settings > Add Device. Used once, never saved.", False,
            "1234 5678", 9),
    "passcode": ("Login passcode", "The 4-digit login passcode of the PSN account on {console}, when the account has "
                 "one; empty when it has none. Kept with the console's keys.", True, "", 4),
}


def _next(values: tuple, value):
    return values[(values.index(value) + 1) % len(values)] if value in values else values[0]


def step_option(options: StreamOptions, key: str) -> StreamOptions:
    """The stream setting *key* stepped to its next value."""
    if key == "resolution":
        return replace(options, resolution=_next((AUTO, *RESOLUTIONS), options.resolution))
    if key == "fps":
        return replace(options, fps=_next(FRAME_RATES, options.fps))
    if key == "bitrate":
        return replace(options, bitrate=_next(BITRATE_STEPS, options.bitrate))
    if key == "screen":
        return replace(options, screen=_next(tuple(SCREENS), options.screen))
    if key == "audio_delay":
        return replace(options, audio_delay=_next(AUDIO_DELAY_STEPS, options.audio_delay))
    return replace(options, low_latency=not options.low_latency)


def option_text(options: StreamOptions, key: str, console: RegisteredConsole, server_type: str = "") -> str:
    height = options.height(console.ps5, server_type)
    if key == "resolution":
        return f"Resolution: {'Automatic (' + str(height) + 'p)' if options.resolution == AUTO else str(height) + 'p'}"
    if key == "fps":
        return f"Frame rate: {options.fps} fps"
    if key == "bitrate":
        mbit = f"{options.kbps(height) / 1000:g} Mbit/s"
        return f"Bitrate: {'Automatic (' + mbit + ')' if options.bitrate == AUTO else mbit}"
    if key == "screen":
        return f"Picture: {SCREENS[options.screen].split(':')[0]}"
    if key == "audio_delay":
        return f"Sound later by: {options.audio_delay} ms"
    return f"Low latency: {'On' if options.low_latency else 'Off'}"


def _when(text: str) -> str:
    try:
        return f"{datetime.datetime.fromisoformat(text):%d/%m/%Y %H:%M}"
    except ValueError:
        return text


class _Worker(QObject):
    """Runs a step off the window's thread; its Outcome arrives on the window's. It stays busy until the window has
    it, so a step started meanwhile waits for the one before to be shown."""

    done = pyqtSignal(object)
    _outcome = pyqtSignal(object)                       # from the step's thread to the window's

    def __init__(self):
        super().__init__()
        self.busy = False
        self._outcome.connect(self._deliver)

    def start(self, work: Callable[[], Outcome]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def _run(self, work: Callable[[], Outcome]) -> None:
        try:
            outcome = work()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            outcome = Outcome(False, f"It failed: {error}.")
        self._outcome.emit(outcome)

    def _deliver(self, outcome: Outcome) -> None:
        self.busy = False
        self.done.emit(outcome)


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery, folder: Path | None = None,
                 settings: QSettings | None = None, ops: ModuleType = jobs,
                 open_url: Callable[[str], bool] = platform.open_path, steam_dir: Path | None | bool = False,
                 play_window: Callable[..., PlayWindow] = PlayWindow, stats_dir: Path | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.settings = settings or QSettings()
        self.ops, self.open_url, self.play_window = ops, open_url, play_window
        self.steam_dir = steam.find_steam() if steam_dir is False else steam_dir
        self.stats_dir = stats_dir
        folder = folder or suite_data(SUITE) / APP_ID                   # the keys: in the user's local folder
        self.store = ConsoleStore(folder)
        self.history = HistoryStore(folder)
        self.registered: list[RegisteredConsole] = self.store.load()
        self.found: list[Console] = []
        self.searched = False
        self.chosen = ""                                # the found console to register: its key
        self.pin = ""                                   # used once, never saved
        self.passcode_for = ""                          # the registered console whose passcode the field page sets
        self.page_console = ""                          # the registered console the console's page shows
        self.in_steam: set[str] = self.steam_keys()
        self.masker = privacy.Masker()
        self.masker.remember(account=self.account(), address=self.address())
        for console in self.registered:
            self.masker.remember(address=console.address)
        self.signing_in = False                         # watching the clipboard for the sign-in's last page
        self.clipboard_before = ""
        self.job = ""                                   # what the worker does: find, account, register, play, ...
        self.job_console = ""                           # the registered console it does it for
        self.job_pane: ListPane | None = None           # the pane whose status line shows it
        self.one_address = False                        # the search was at one address: the others found stay
        self.asked = ""                                 # the action pressed once, waiting for its second press
        self.session_info: dict[str, str] = {}         # a registered console's model, as its last session said
        self.stream_window: PlayWindow | None = None
        self.stream_stop: threading.Event | None = None

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
        cards.setSpacing(px(10))
        self.consoles_card = Card("Consoles", "")
        self.register_card = Card("Register", "")
        self.mine_card = Card("My consoles", "")
        self.history_card = Card("History", "")
        self.settings_card = Card("Settings", "Personal details, and the log.")
        for card in (self.consoles_card, self.register_card, self.mine_card, self.history_card, self.settings_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.consoles_pane = ListPane("Consoles", CONSOLES_INFO)
        self.register_pane = ListPane("Register", REGISTER_INFO)
        self.mine_pane = ListPane("My consoles", MINE_INFO)
        self.console_pane = ListPane("Console", CONSOLE_INFO)
        self.history_pane = ListPane("History", HISTORY_INFO)
        self.settings_pane = ListPane("Settings", SETTINGS_INFO)
        self.field_pane = FieldPane()
        for pane in (self.consoles_pane, self.register_pane, self.mine_pane, self.console_pane, self.history_pane,
                     self.settings_pane, self.field_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)
        self.cards = {self.consoles_pane: self.consoles_card, self.register_pane: self.register_card,
                      self.mine_pane: self.mine_card, self.history_pane: self.history_card,
                      self.settings_pane: self.settings_card}
        self.field_back = self.consoles_pane            # the pane a field's page goes back to

        self.worker = _Worker()
        self.worker.done.connect(self._done)
        for pane, card in self.cards.items():
            card.focused.connect(lambda pane=pane: self.show_pane(pane))
            card.activated.connect(lambda pane=pane: self.focus_list(pane))
        self.consoles_pane.list.picked.connect(self.consoles_row)
        self.register_pane.list.picked.connect(self.register_row)
        self.mine_pane.list.picked.connect(lambda key: self.play())
        self.mine_pane.list.current.connect(lambda key: self.show_console_details())
        self.console_pane.list.picked.connect(self.console_row)
        self.history_pane.list.picked.connect(lambda key: None)
        self.settings_pane.list.picked.connect(self.settings_row)
        for pane in (*self.cards, self.console_pane):
            pane.list.current.connect(lambda key: self.update_legend())
        self.field_pane.field.returnPressed.connect(self.keep_field)
        QGuiApplication.clipboard().dataChanged.connect(self.check_clipboard)
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("y", self.y_action)
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)
        self.show_all()
        self.show_pane(self.consoles_pane)

    def start(self) -> None:
        """After the window is shown: the controller and the status line; nothing searches before X asks for it."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.consoles_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    @property
    def busy(self) -> bool:
        """A step runs: PortableWindow waits with a move to another screen until it is done."""
        return self.worker.busy

    # Personal details

    @property
    def revealed(self) -> bool:
        return self.settings.value(SHOWN_KEY, "off") == "on"

    def shown(self, text: str) -> str:
        """*text* as the screen shows it: masked unless the personal details are shown."""
        return text if self.revealed else self.masker.mask(text)

    def note(self, text: str, error: bool = False) -> None:
        """A line in the log, always masked."""
        (self.log.error if error else self.log.info)(self.masker.mask(text))

    def account(self) -> str:
        return str(self.settings.value(ACCOUNT_KEY, "") or "")

    def address(self) -> str:
        return str(self.settings.value(ADDRESS_KEY, "") or "")

    def show_all(self) -> None:
        self.show_consoles()
        self.show_register()
        self.show_mine()
        self.show_console_page()
        self.show_history()
        self.show_settings()

    # Panes and the legend

    def show_pane(self, pane: Pane) -> None:
        current = self.panes.currentWidget()
        if current is not pane and getattr(current, "viewing", False):
            current.show_body()
        if current is self.field_pane and pane is not self.field_pane:
            self.field_pane.field.clear()               # a PIN or passcode is not left in the window
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty (its status says why)."""
        if not pane.list.focus(""):
            if pane is self.mine_pane:
                pane.status.setText("No console registered yet: the Register card registers one.")
            elif pane is self.history_pane:
                pane.status.setText("Nothing played yet: A on a console of My consoles plays it.")
            self.cards[pane].setFocus()

    def enter(self, pane: ListPane, row: str) -> None:
        """Another card's pane, the focus on its *row*: through its card, so that card is the one selected and B goes
        back to it."""
        self.cards[pane].setFocus()
        pane.list.focus(row)

    def legend_items(self) -> list[tuple[str, str]]:
        """The legend for the pane that shows and the row the focus is on: its actions on the controller's buttons,
        A too (a tap on an entry does the same), then core's Menu Info, B Back and View Exit. A press that cannot
        act now says why on the status line."""
        pane = self.panes.currentWidget()
        items: list[tuple[str, str]] = []
        if pane is self.field_pane:
            items = [("A", "Keep"), ("X", "Paste"), KEYBOARD]
        elif getattr(pane, "viewing", False):
            items = []
        elif pane is self.consoles_pane:
            row = pane.list.focused()
            found = self.found_console(row)
            if found is not None:
                items = [("A", "My consoles" if self.registered_for(found) is not None else "Register")]
            elif row == "address":
                items = [("A", "Change")]
            items += [("X", "Search the network"), ("Y", "Search the address")]
        elif pane is self.register_pane:
            row = pane.list.focused()
            a = {"console": "Next console", "signin": "Sign in", "account": "Change", "pin": "Change"}.get(row)
            items = [*([("A", a)] if a else []), ("X", "Register")]
        elif pane is self.mine_pane:
            if self.registered_console(pane.list.focused()) is not None:
                items = [("A", "Play"), ("X", "Its page")]
        elif pane is self.console_pane:
            items = self.console_items(pane.list.focused())
        elif pane is self.history_pane:
            items = [("X", "Press again" if self.asked == "clear" else "Clear")]
        elif pane is self.settings_pane:
            row = pane.list.focused()
            items = [("A", "View the log" if row == "log" else "Change" if row else "Open")]
        on_a_page = pane in (self.field_pane, self.console_pane) or getattr(pane, "viewing", False)
        return [*items, *self.common_items(True if on_a_page else None)]

    def console_items(self, row: str) -> list[tuple[str, str]]:
        """The console page's legend for *row*: A acts on it; Y takes the entry out of Steam on its row."""
        console = self.page()
        if console is None or not row:
            return []
        again = self.asked == f"{row}:{console.key}"
        a = {"wake": "Wake", "test": "Test session", "teststream": "Test stream", "passcode": "Change",
             "steam": "Update in Steam" if console.key in self.in_steam else "Add to Steam",
             "rest": "Press again" if again else "Rest mode",
             "remove": "Press again" if again else "Remove"}.get(row, "Change")
        items = [("A", a)]
        if row == "steam" and console.key in self.in_steam:
            items.append(("Y", "Press again" if self.asked == f"unsteam:{console.key}" else "Take out of Steam"))
        return items

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    # The buttons

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A) or in a text field: the pane's own A."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.keep_field()
        elif isinstance(pane, ListPane) and not pane.viewing:
            row = pane.list.focused()
            if row:
                pane.list.picked.emit(row)
            elif pane is not self.console_pane:
                self.focus_list(pane)

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.paste()
        elif getattr(pane, "viewing", False):
            return
        elif pane is self.consoles_pane:
            self.search()
        elif pane is self.register_pane:
            self.register()
        elif pane is self.mine_pane:
            self.open_page()
        elif pane is self.history_pane:
            self.clear_history()

    def y_action(self) -> None:
        pane = self.panes.currentWidget()
        if getattr(pane, "viewing", False) or pane is self.field_pane:
            return
        if pane is self.consoles_pane:
            self.search_address()
        elif pane is self.console_pane and pane.list.focused() == "steam":
            self.steam_entry(remove=True)

    def on_back(self) -> None:
        """B goes back (the suite's rule, owner 29-10-2026): a field's page to its row (nothing kept), the log to its
        pane, the console's page to its row on My consoles, a pane to its card; on a card it does nothing (View
        exits)."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.back_from_field()
        elif pane is self.console_pane:
            self.show_pane(self.mine_pane)
            self.mine_pane.list.focus(f"mine:{self.page_console}")
        elif getattr(pane, "viewing", False):
            pane.show_body()
            if not pane.list.focused():
                self.focus_list(pane)
            self.update_legend()
        else:
            self.go_back()

    def ask(self, what: str, pane: ListPane, text: str) -> bool:
        """A second press of *what* within five seconds: True on it; on the first, *text* on the pane's status line."""
        if self.asked == what:
            self._confirm_over(keep_status=True)
            return True
        self.asked = what
        self.confirm_timer.start()
        pane.status.setText(text)
        self.update_legend()
        return False

    def _confirm_over(self, keep_status: bool = False) -> None:
        self.confirm_timer.stop()
        if self.asked and not keep_status:
            for pane in (self.console_pane, self.history_pane):
                if pane.status.text().startswith("Press "):
                    pane.status.setText("")
        self.asked = ""
        self.update_legend()

    # The worker

    def run(self, job: str, pane: ListPane, work: Callable[[], Outcome], text: str, console: str = "") -> bool:
        """*work* off the window's thread, *text* on the pane's status line meanwhile; while another step runs, the
        status says so."""
        if self.worker.busy:
            pane.status.setText("Still busy with the step before: a moment.")
            return False
        self.job, self.job_console = job, console
        self.job_pane = pane
        pane.status.setText(self.shown(text))
        self.note(text)
        self.worker.start(work)
        return True

    def _done(self, outcome: Outcome) -> None:
        job, self.job = self.job, ""
        for line in outcome.log:
            self.note(f"  {line}")
        self.note(outcome.message, error=not outcome.ok)
        if outcome.ok:
            if job == "find":
                self.found_consoles(outcome.value)
            elif job == "account":
                self.account_found(outcome.value)
            elif job == "register":
                self.registered_with(outcome.value)
            elif job == "steam":
                self.in_steam = self.steam_keys()
                self.show_console_page()
        if job in ("test", "teststream", "rest", "play") and getattr(outcome.value, "server_type", ""):
            self.session_info[self.job_console] = outcome.value.server_type
            self.show_console_details()
        if job == "play":
            self.stream_over()
        if self.job_pane is not None:
            self.job_pane.status.setText(self.shown(outcome.message))
        self.update_legend()

    # The Consoles card

    def show_consoles(self) -> None:
        rows = [(f"found:{self.console_key(c)}", self.shown(self.found_text(c))) for c in self.found]
        address = self.address()
        rows.append(("address", f"Search an address: {self.shown(address) if address else 'Not filled in'}"))
        self.consoles_pane.list.set_items(rows)
        if not self.searched:
            text = "Not searched yet: X searches the network."
        elif self.found:
            text = f"{len(self.found)} found: " + ", ".join(c.host_name or c.model for c in self.found)
        else:
            text = "None found: are they on, on this network?"
        self.consoles_card.set_text(self.shown(text) if self.searched else text)
        self.consoles_pane.summary.setText("The consoles on this network that answered the search.")
        self.update_legend()

    @staticmethod
    def console_key(console: Console) -> str:
        return console.host_id or console.address

    def found_text(self, console: Console) -> str:
        registered = "registered" if self.registered_for(console) is not None else "not registered"
        return APART.join((console.host_name or console.model, console.model, console.address,
                           STATES[console.state], registered))

    def found_console(self, row: str) -> Console | None:
        key = row.removeprefix("found:") if row.startswith("found:") else None
        return next((c for c in self.found if self.console_key(c) == key), None)

    def registered_for(self, console: Console) -> RegisteredConsole | None:
        for registered in self.registered:
            if (console.host_id and registered.host_id == console.host_id) or registered.address == console.address:
                return registered
        return None

    def found_for(self, console: RegisteredConsole) -> Console | None:
        """The search's answer from a registered console (by host id, else address)."""
        for found in self.found:
            if (console.host_id and found.host_id == console.host_id) or found.address == console.address:
                return found
        return None

    def consoles_row(self, key: str) -> None:
        """A on a row of the Consoles card: a console chosen for registering, or shown on My consoles; the address
        row's page."""
        if key == "address":
            self.open_field("address", self.consoles_pane, self.address())
            return
        console = self.found_console(key)
        if console is None:
            return
        registered = self.registered_for(console)
        if registered is not None:
            self.enter(self.mine_pane, f"mine:{registered.key}")
            return
        self.chosen = self.console_key(console)
        self.show_register()
        self.enter(self.register_pane, "account" if not self.account() else "pin")
        nxt = "the PIN next" if self.account() else "your account ID next, then the PIN"
        self.register_pane.status.setText(self.shown(f"{console.host_name or console.model} is chosen: {nxt}, then "
                                                     "the X button registers."))

    def search(self) -> None:
        self.one_address = False
        self.run("find", self.consoles_pane, lambda: self.ops.find(), "Searching the network …")

    def search_address(self) -> None:
        address = self.address()
        if not address:
            self.consoles_pane.status.setText("Fill in the address first: the A button on its row.")
            self.consoles_pane.list.focus("address")
            return
        self.one_address = True
        self.run("find", self.consoles_pane, lambda: self.ops.find(address), f"Asking {address} …")

    def found_consoles(self, consoles: list[Console]) -> None:
        self.searched = True
        # A search of one address keeps the others found before; the network's replaces them.
        found = {self.console_key(c): c for c in self.found} if self.one_address else {}
        for console in consoles:
            self.masker.remember(address=console.address)
            found[self.console_key(console)] = console
            registered = self.registered_for(console)
            if registered is not None and registered.address != console.address:     # the router gave another
                self.registered = self.store.put(replace(registered, address=console.address))
        self.found = list(found.values())
        self.choose()
        self.show_all()

    def choose(self) -> None:
        """The console to register: the one chosen while it is still found and not registered with, else the first
        found that is not."""
        unregistered = [self.console_key(c) for c in self.found if self.registered_for(c) is None]
        if self.chosen not in unregistered:
            self.chosen = unregistered[0] if unregistered else ""

    # The Register card

    def show_register(self) -> None:
        chosen = next((c for c in self.found if self.console_key(c) == self.chosen), None)
        account = self.account()
        rows = [("console", "Console: " + (self.shown(f"{chosen.host_name or chosen.model}{APART}{chosen.address}")
                                           if chosen is not None else "None chosen: A on one on the Consoles card")),
                ("signin", f"Account ID from the PlayStation sign-in{OPENS}"),
                ("account", f"Account ID: {self.shown(account) if account else 'Not filled in'}"),
                ("pin", f"PIN: {'Typed' if self.pin else 'Not filled in'}")]
        self.register_pane.list.set_items(rows)
        ready = chosen is not None and account and self.pin
        self.register_card.set_text("Ready: X registers." if ready else "This handheld with a console.")
        self.register_pane.summary.setText("The console, your PSN account ID and the console's PIN; then the X "
                                           "button.")
        self.update_legend()

    def register_row(self, key: str) -> None:
        pane = self.register_pane
        if key == "console":
            choices = [self.console_key(c) for c in self.found if self.registered_for(c) is None]
            if not choices:
                pane.status.setText("No console to register: " + (NOT_FOUND if not self.found else
                                                                     "this handheld is registered with every one "
                                                                     "found."))
                return
            at = choices.index(self.chosen) if self.chosen in choices else -1
            self.chosen = choices[(at + 1) % len(choices)]
            self.show_register()
            pane.status.setText("")
        elif key == "signin":
            self.sign_in()
        elif key == "account":
            self.open_field("account", pane, self.account())
        elif key == "pin":
            self.open_field("pin", pane, self.pin)

    def sign_in(self) -> None:
        """The PlayStation sign-in in the browser; the clipboard watched for the address of its last page."""
        pane = self.register_pane
        if not self.open_url(psn.login_url()):
            pane.status.setText("The browser did not open: Windows has no default browser.")
            return
        self.signing_in = True
        self.clipboard_before = QGuiApplication.clipboard().text()
        pane.status.setText("Sign in in the browser. On the page that says \"redirect\", copy its address: the app "
                            "takes it from there.")
        self.note("The PlayStation sign-in opened in the browser.")

    def check_clipboard(self) -> None:
        """The address of the sign-in's last page, copied: its code sent to PSN for the account ID. Anything else on
        the clipboard, and what was there when the sign-in opened, is left alone."""
        if not self.signing_in:
            return
        text = QGuiApplication.clipboard().text().strip()
        if text == self.clipboard_before or not text.startswith(psn.REDIRECT_URI) or "code=" not in text:
            return
        self.signing_in = False
        self.run("account", self.register_pane, lambda: self.ops.psn_account(text), "Asking PSN for the account ID …")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.check_clipboard()                      # back from the browser

    def account_found(self, account: psn.Account) -> None:
        self.masker.remember(account=account.code, online_id=account.online_id)
        self.masker.remember(account=str(account.number))
        self.settings.setValue(ACCOUNT_KEY, account.code)
        self.show_register()
        self.register_pane.list.focus("pin")

    def register(self) -> None:
        pane = self.register_pane
        console = next((c for c in self.found if self.console_key(c) == self.chosen), None)
        if console is None:
            pane.status.setText("Choose the console first: " + (NOT_FOUND if not self.found else
                                                                 "the A button on the Console row."))
            return
        try:
            account_id = parse_account_id(self.account())
        except ValueError:
            pane.status.setText("Fill in your PSN account ID first: the sign-in row, or the Account ID row.")
            return
        try:
            pin = parse_pin(self.pin)
        except ValueError as error:
            pane.status.setText(str(error))
            return
        self.run("register", pane, lambda: self.ops.register(console, account_id, pin),
                 f"Registering with {console.host_name or console.address} …")

    def registered_with(self, console: RegisteredConsole) -> None:
        self.pin = ""
        self.masker.remember(address=console.address)
        self.registered = self.store.put(console)
        self.choose()
        self.show_all()

    # The field pages

    def open_field(self, key: str, back: ListPane, value: str) -> None:
        title, text, hidden, placeholder, length = FIELDS[key]
        if key == "passcode":
            console = self.registered_console(f"mine:{self.passcode_for}")
            text = text.format(console=self.shown(console.nickname or console.address) if console else "the console")
        self.field_back = back
        self.field_pane.set_field(key, title, text, value, hidden or (key in ("address", "account") and
                                                                      not self.revealed), placeholder, length)
        self.show_pane(self.field_pane)
        self.field_pane.field.setFocus()

    def back_from_field(self, said: str = "") -> None:
        key = self.field_pane.key
        back = self.field_back
        self.show_pane(back)
        back.status.setText(said)
        back.list.focus(key)

    def keep_field(self) -> None:
        """A on a field's page: the value checked and kept, back to its row."""
        key, value = self.field_pane.key, self.field_pane.field.text().strip()
        try:
            if key == "account" and value:
                parse_account_id(value)
            elif key == "pin":
                parse_pin(value)
            elif key == "passcode":
                value = parse_login_pin(value)
        except ValueError as error:
            self.field_pane.status.setText(str(error))
            return
        said = f"{FIELDS[key][0]} kept."
        if key == "address":
            self.settings.setValue(ADDRESS_KEY, value)
            self.masker.remember(address=value)
            self.show_consoles()
        elif key == "account":
            self.settings.setValue(ACCOUNT_KEY, value)
            self.masker.remember(account=value)
            self.show_register()
        elif key == "pin":
            self.pin = value
            self.show_register()
        elif key == "passcode":
            console = self.registered_console(f"mine:{self.passcode_for}")
            if console is not None:
                self.registered = self.store.put(replace(console, login_pin=value))
                said = "Login passcode " + ("kept." if value else "removed.")
                self.note(f"Login passcode {'saved' if value else 'removed'} for {console.nickname or 'a console'}.")
                self.show_mine()
                self.show_console_page()
        self.back_from_field(said)

    def paste(self) -> None:
        """The clipboard's text into the page's field (copied in a browser on the device)."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.field_pane.status.setText("The clipboard is empty: copy the text on this device first.")
            return
        self.field_pane.field.setText(text)
        self.field_pane.status.setText("The text is in the field: the A button keeps it.")

    # The My consoles card

    def show_mine(self) -> None:
        rows = [(f"mine:{c.key}", self.shown(self.mine_text(c))) for c in self.registered]
        self.mine_pane.list.set_items(rows)
        count = len(self.registered)
        self.mine_card.set_text(f"{count} registered: A plays one." if count else "None registered yet.")
        self.show_console_details()

    def mine_text(self, console: RegisteredConsole) -> str:
        found = self.found_for(console)
        state = STATES[found.state] if found is not None else "Not searched"
        parts = [console.nickname or console.address, console.target.console, state]
        if console.key in self.in_steam:
            parts.append("in Steam")
        return APART.join(parts)

    def registered_console(self, row: str) -> RegisteredConsole | None:
        key = row.removeprefix("mine:") if row.startswith("mine:") else None
        return next((c for c in self.registered if c.key == key), None)

    def details(self, console: RegisteredConsole) -> str:
        """The console's model (exact once a session said it, PS4 Pro), system software, what runs and its Remote
        Play version."""
        found = self.found_for(console)
        parts = [self.session_info.get(console.key) or console.target.console]
        version = software_version(found.system_version, console.ps5) if found is not None else ""
        if version:
            parts.append(f"system software {version}")
        if found is not None and found.state == "ready":
            parts.append(f"running {found.running_app}" if found.running_app else "on the home screen")
        parts.append(f"Remote Play {rp_version(console.target) or 'unknown'}")
        return self.shown(f"{console.nickname or console.address}: " + APART.join(parts))

    def show_console_details(self) -> None:
        """The line under My consoles' heading: the focused console's details."""
        console = self.registered_console(self.mine_pane.list.focused())
        if console is None:
            self.mine_pane.summary.setText("The consoles this handheld is registered with." if self.registered else
                                           "None yet: the Register card registers this handheld with one.")
        else:
            self.mine_pane.summary.setText(self.details(console))
        self.update_legend()

    def focused_console(self) -> RegisteredConsole | None:
        console = self.registered_console(self.mine_pane.list.focused())
        if console is None:
            self.mine_pane.status.setText("Put the focus on a console first." if self.registered else
                                          "No console registered yet: the Register card registers one.")
        return console

    def play(self) -> None:
        """A: the console woken when it rests, then streamed full screen until the stream window closes."""
        console = self.focused_console()
        if console is None:
            return
        if self.worker.busy:
            self.mine_pane.status.setText("Still busy with the step before: a moment.")
            return
        name = self.shown(console.nickname or console.address)
        stop = threading.Event()
        window = self.play_window(f"{name} · {APP_NAME}", stop.set, console.options)
        self.stream_window, self.stream_stop = window, stop
        window.showFullScreen()
        window.bring_forward()
        window.say(f"Looking for {name}…")
        stats_dir = self.stats_dir or stream_stats.folder()

        def work() -> Outcome:
            on = self.ops.wake_and_wait(console, lambda text: window.say(self.shown(text)))
            if not on.ok:
                return on
            window.say(self.shown(f"{on.message} Starting the stream…"))
            return self.ops.watch_stream(on.value, window.deliver, window.wanted, stop, window.play,
                                         figures=window.figures, stats_dir=stats_dir, played=self.history,
                                         on_quit=window.end)

        self.run("play", self.mine_pane, work, f"Playing {name} …", console.key)

    def stream_over(self) -> None:
        """The stream ended (its window closed, the console ended it, or it failed): back to the window."""
        window, self.stream_window, self.stream_stop = self.stream_window, None, None
        if window is not None and window.isVisible():
            window.close()
        self.show_history()
        self.raise_()
        self.activateWindow()

    def open_page(self) -> None:
        """X: the console's page."""
        console = self.focused_console()
        if console is None:
            return
        self.page_console = console.key
        self.show_console_page()
        self.show_pane(self.console_pane)
        self.console_pane.list.focus("wake")

    # The console's page

    def page(self) -> RegisteredConsole | None:
        return self.registered_console(f"mine:{self.page_console}")

    def steam_keys(self) -> set[str]:
        try:
            return steam_shortcuts.in_steam(self.steam_dir) if self.steam_dir is not None else set()
        except OSError:
            return set()

    def show_console_page(self) -> None:
        console = self.page()
        if console is None:
            self.console_pane.list.set_items([])
            return
        server = self.session_info.get(console.key, "")
        steam_text = ("In Steam: Added" if console.key in self.in_steam else "In Steam: Not added"
                      ) if self.steam_dir is not None else "In Steam: Steam is not installed"
        rows = [("wake", "Wake from rest mode"), ("test", "Test session"),
                ("teststream", "Test stream: five seconds, not shown"),
                *((key, option_text(console.options, key, console, server)) for key in OPTION_ROWS),
                ("passcode", f"Login passcode: {'Set' if console.login_pin else 'None'}"),
                ("steam", steam_text), ("rest", "Rest mode"), ("remove", "Remove this console")]
        self.console_pane.list.set_items(rows)
        self.console_pane.heading.setText(self.shown(console.nickname or console.address))
        self.console_pane.summary.setText(self.details(console))
        self.update_legend()

    def console_row(self, key: str) -> None:
        """A on a row of the console's page."""
        console = self.page()
        if console is None:
            return
        pane, name = self.console_pane, console.nickname or console.address
        if key == "wake":
            self.run("wake", pane, lambda: self.ops.wake(console), f"Waking {name} …", console.key)
        elif key == "test":
            self.run("test", pane, lambda: self.ops.test_session(console), f"Starting a session with {name} …",
                     console.key)
        elif key == "teststream":
            self.run("teststream", pane, lambda: self.ops.test_stream(console),
                     f"Starting a test stream with {name} …", console.key)
        elif key in OPTION_ROWS:
            options = step_option(console.options, key)
            self.registered = self.store.put(replace(console, options=options))
            self.show_console_page()
            pane.status.setText(f"{option_text(options, key, console, self.session_info.get(console.key, ''))}"
                                ", from the next stream.")
            self.note(f"Stream settings for {name}: {options.describe(console.ps5)}.")
        elif key == "passcode":
            self.passcode_for = console.key
            self.open_field("passcode", pane, console.login_pin)
        elif key == "steam":
            self.steam_entry(remove=False)
        elif key == "rest":
            if self.ask(f"rest:{console.key}", pane, self.shown(f"Press A again to put {name} in rest mode: a game on "
                                                                "it stops.")):
                self.run("rest", pane, lambda: self.ops.rest_mode(console), f"Putting {name} in rest mode …",
                         console.key)
        elif key == "remove":
            steam_too = " Its Steam entry goes too: Steam closes for it." if console.key in self.in_steam else ""
            if self.ask(f"remove:{console.key}", pane, self.shown(f"Press A again to remove {name}: to use it again, "
                                                                  f"register again.{steam_too}")):
                self.remove(console)

    def steam_entry(self, remove: bool) -> None:
        console = self.page()
        if console is None:
            return
        pane = self.console_pane
        if self.steam_dir is None:
            pane.status.setText("Steam is not installed, or was never signed in on this handheld.")
            return
        if remove and not self.ask(f"unsteam:{console.key}", pane, "Press Y again to take the console out of Steam: "
                                                                   "Steam closes for it and starts again."):
            return
        steam_dir = self.steam_dir
        self.run("steam", pane, lambda: self.ops.steam_entry(console, steam_dir, LOGO_PATH, remove),
                 "Changing Steam's library …", console.key)

    def remove(self, console: RegisteredConsole) -> None:
        name = console.nickname or console.address
        self.registered = self.store.remove(console.key)
        self.note(f"Removed {name}.")
        if console.key in self.in_steam and self.steam_dir is not None:
            steam_dir = self.steam_dir
            self.run("steam", self.mine_pane, lambda: self.ops.steam_entry(console, steam_dir, LOGO_PATH, True),
                     f"{name} is removed; taking it out of Steam …", console.key)
        else:
            self.mine_pane.status.setText(self.shown(f"{name} is removed."))
        self.page_console = ""
        self.show_all()
        self.show_pane(self.mine_pane)
        self.focus_list(self.mine_pane)

    # The History card

    def show_history(self) -> None:
        games = newest_first(self.history.load())
        rows = [(f"game:{n}", APART.join((game.title, game.console_name, duration(game.seconds),
                                          f"last {_when(game.last_played)}")))
                for n, game in enumerate(games)]
        self.history_pane.list.set_items(rows)
        total = sum(game.seconds for game in games)
        text = (f"{len(games)} game{'s' if len(games) != 1 else ''}, {duration(total)} in all." if games else
                "Nothing played yet.")
        self.history_pane.summary.setText(text)
        self.history_card.set_text(text)
        self.update_legend()

    def clear_history(self) -> None:
        pane = self.history_pane
        if not self.history.load():
            pane.status.setText("Nothing to clear.")
            return
        if not self.ask("clear", pane, "Press X again to forget every game and its time."):
            return
        self.history.clear()
        self.note("The history was cleared.")
        self.show_history()
        pane.status.setText("The history is cleared.")
        self.history_card.setFocus()

    # The Settings card

    def show_settings(self) -> None:
        self.settings_pane.list.set_items([
            ("details", f"Personal details: {'Shown' if self.revealed else 'Hidden'}"),
            ("log", f"The app's log{OPENS}")])
        self.settings_pane.summary.setText("What the screen shows. The A button changes a setting.")
        self.update_legend()

    def settings_row(self, key: str) -> None:
        if key == "log":
            self.view_log()
            return
        self.settings.setValue(SHOWN_KEY, "off" if self.revealed else "on")
        self.show_all()
        self.settings_pane.status.setText("Personal details are shown." if self.revealed else
                                          "Personal details are hidden: only their end shows.")

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The log's newest lines in the Settings pane: the d-pad scrolls it, B goes back (not in Notepad, which no
        button closes)."""
        text = self.masker.mask(private("\n".join(self.log_lines()[-LOG_MAX:])))
        self.settings_pane.show_text("The log", text or "Nothing logged yet.", end=True)
        self.settings_pane.status.setText("The d-pad scrolls it, the B button goes back.")
        self.update_legend()

    # View

    def exit_app(self) -> None:
        self.close()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.confirm_timer.stop()
        self.signing_in = False
        if self.stream_stop is not None:
            self.stream_stop.set()
        if self.stream_window is not None:
            self.stream_window.close()
        super().closeEvent(event)
