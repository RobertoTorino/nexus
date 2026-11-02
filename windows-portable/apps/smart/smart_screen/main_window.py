# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the cards on the left (Screen, Values, Look, Clock, Weather, Start), what the focused one holds in the
middle, the picture the screen shows on the right, the controller's buttons at the bottom. It is the BC250 suite's
USB IPS3.5 made for the handheld: its tabs are the cards, each setting a row whose A steps to its next value (LB and
RB step back and on), the header's text and the weather's place a page with a field and the touch keyboard, the
background picture chosen in core's browser, and the saved picture and report go to the Pictures and Documents
folders instead of a file dialog.

Every second it reads the values (values.py), draws the picture (render.py) and hands it to the link (link.py), which
sends what changed to the screen. The screen is the app's work, so the link looks for it from the start, also when
the app starts minimized with Windows (owner's rule "nothing runs before it is asked for": what the app is opened for
is asked for). The weather is fetched off the window's thread, only while its tile is on the screen and a place is
chosen."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from bc250_core import applog, browse, power
from bc250_core.gamepad import Gamepad
from bc250_core.platform import private
from bc250_core.portable import (AMBER, DIM, KEYBOARD, VIEW, Card, Legend, PortableHeader, PortableWindow, px,
                                 status_clock)
from bc250_core.settings import SettingsStore

from . import APP_ID, APP_NAME, INFO, __version__, autostart, render, screen, weather
from .link import Link, State
from .panes import FieldPane, ListPane, Preview
from .values import Values

INTERVAL_MS = 1000              # the values read and the screen updated
STATUS_MS = 30_000              # the header's time and battery
CONFIRM_MS = 5000               # View, while the screen is connected, asks for a second press within this
CARDS_WIDTH = 330
CARD_HEIGHT = 84                # six cards and their gaps fit the column at 720 px high
PREVIEW_WIDEST = 480            # the picture beside the panes: the body's height, at most this wide (landscape 1:1)
TITLE_CHARS = 24
LOG_MAX = 2000                  # the lines of the log the view shows, the newest
BRIGHTNESS_STEP = 10
PICTURES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
BROWSED = "picture_folder"      # the browser's folder kept for next time (browse.remember)
ALL_ADAPTERS = "All adapters"
# The look's colors: the theme's own first, then these (no color dialog: one cannot be used with the controller)
PALETTE = (("", "The theme's"), ("#ffffff", "White"), ("#c8cad4", "Light gray"), ("#5a5e6e", "Gray"),
           ("#1e2028", "Dark gray"), ("#000000", "Black"), ("#f5a524", "Amber"), ("#f07828", "Orange"),
           ("#e64646", "Red"), ("#e8508c", "Pink"), ("#8b4fd8", "Purple"), ("#3c78dc", "Blue"),
           ("#32c8dc", "Cyan"), ("#46c878", "Green"), ("#c8dc3c", "Lime"))
COLOR_NAMES = {"text": "Text", "tiles": "Tiles", "accent": "Accent", "background": "Background"}
HOURS = {24: "24-hour", 12: "12-hour (AM/PM)"}
ZONES = {"": "Not shown", "offset": "Offset from UTC"}
DATES = {"": "Not shown", "weekday": "Weekday, day and month", "dmy": "DD-MM-YYYY", "mdy": "MM/DD/YYYY",
         "ymd": "YYYY-MM-DD"}
NO_TITLE = "None: only the time"

SCREEN_INFO = (
    "A Turzx USB IPS screen: the Turing Smart Screen 3.5 inch, or a UsbMonitor 3.5, 5 or 7 inch of the same family. "
    "It needs no driver and no administrator: Windows makes it a COM port by itself, and the app finds it there, also "
    "when it is plugged in later or into a dock. The first time, the app restarts the screen once, so it starts from "
    "a clean state. Then it sends the picture every second, only the parts that changed. One program at a time can "
    "use the screen: close the maker's own app (UsbMonitor) first.\n\n"
    "Brightness: the A button and RB make it brighter, LB darker. Orientation: how the screen stands; turn it upside "
    "down when its USB cable is at the bottom. Backlight switches the screen dark and back on; the app keeps running. "
    "Save the picture puts what the screen shows in your Pictures folder, Save a report every value with the date "
    "and the time in your Documents folder, each in a Smart Screen folder.")
VALUES_INFO = (
    "What the screen shows, a tile each, in this order. The A button puts a value on the screen or takes it off.\n\n"
    + "\n".join(f"{caption}: {render.TILE_HINTS[key]}" for key, caption in render.TILES) + "\n\n"
    "The temperatures, the power and the GPU's load come from AMD's driver; without it the GPU's load is Windows' own "
    "and the CPU's temperature and the power show —. Windows does not report a fan. The Network adapter row picks "
    "the adapter the Network tile measures, or all of them added up.")
LOOK_INFO = (
    "How the screen looks. The A button and RB step to the next choice, LB to the one before; the screen and the "
    "picture beside the panes change at once. Dark takes the suite's amber; the other themes have their own colors. "
    "The four colors are your own instead of the theme's: the X button on one puts the theme's back. The header's "
    "text is yours, for example the handheld's name: the A button opens a page with a field, R3 the touch keyboard. "
    "Background is a picture of your own behind the tiles, cut to the screen's shape: the A button picks it with the "
    "controller, the X button takes it away. The app keeps where it is, not a copy: leave it there.")
CLOCK_INFO = (
    "The time in the screen's header, in Windows' time zone: summer and winter time follow by themselves. The A "
    "button and RB step to the next choice, LB to the one before. The time zone is shown as its offset from UTC "
    "(UTC+1 in winter, UTC+2 in summer in Amsterdam).")
WEATHER_INFO = (
    "The weather comes from Open-Meteo (open-meteo.com), free and without an account. The A button on the Place row "
    "opens a page to type a city or a town (R3 for the touch keyboard); the places found are listed under it, and the "
    "A button on one uses it and puts the Weather tile on the screen. Search sends the name you type; then the "
    "place's coordinates go to Open-Meteo every 30 minutes, only while the Weather tile is on the screen. Nothing "
    "else about you is sent. No weather forgets the place.")
START_INFO = (
    "Start with Windows puts a shortcut in your Startup folder (nothing in the registry): the app starts minimized "
    "when you sign in, and the screen shows the values from then on. Only the app installed from the portal starts "
    "so. The screen shows the values while the app runs; minimized is enough. Run in the background minimizes the "
    "app now: the controller then belongs to your games, and the app comes back from the taskbar or the portal.\n\n"
    "When the app closes, the screen goes dark, or keeps the last picture it had. The last row shows the app's log: "
    "the d-pad scrolls it, the B button goes back.")
BROWSE_INFO = (
    "Find the picture: PNG, JPEG, WebP or BMP. The A button opens the folder the focus is on, or takes the picture; "
    "the B button goes a level up, and from the places back to the Look card. The places are your usual folders and "
    "every drive.")
FIELDS = {
    "title": ("Header text", "Your own text in the screen's header, up to 24 characters, for example the handheld's "
              "name. Empty: only the time.", NO_TITLE, TITLE_CHARS),
    "search": ("Weather place", "A city or a town: Open-Meteo gets the name to look it up, nothing else.",
               "City or town", 100),
}


class ScreenSettings(SettingsStore):
    DEFAULTS = {"brightness": 50, "orientation": "Portrait", "tiles": ",".join(render.DEFAULT_TILES),
                "off_on_quit": True, "theme": render.DEFAULT_THEME, "title": "", "picture": "",
                "interface": "", "weather_place": "",       # interface "": all; weather_place: weather.Place as JSON
                "hours": 24, "zone": "", "date": "",
                **{f"color_{key}": "" for key in render.COLORS}}


class _Worker(QObject):
    """Runs a slow step off the window's thread; done or failed arrive on the window's (sFTP Tools' worker)."""

    done = pyqtSignal(object)
    failed = pyqtSignal(object)
    _outcome = pyqtSignal(bool, object)                 # from the step's thread to the window's

    def __init__(self):
        super().__init__()
        self.busy = False
        self._outcome.connect(self._deliver)

    def start(self, work: Callable[[], object]) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def _run(self, work: Callable[[], object]) -> None:
        try:
            result = work()
        except Exception as error:  # noqa: BLE001  (shown in the pane, not raised)
            self._outcome.emit(False, error)
            return
        self._outcome.emit(True, result)

    def _deliver(self, ok: bool, result: object) -> None:
        self.busy = False
        (self.done if ok else self.failed).emit(result)


def step(choices: list, current, delta: int, wrap: bool = True):
    """The choice *delta* away from *current* (the first when it is not one of them); at an end it wraps around, or
    stays without *wrap*."""
    at = choices.index(current) if current in choices else 0
    if wrap:
        return choices[(at + delta) % len(choices)]
    return choices[max(0, min(len(choices) - 1, at + delta))]


def color_name(value: str) -> str:
    return dict(PALETTE).get(value.lower(), value) if value else PALETTE[0][1]


def new_path(folder: Path, suffix: str, now: float | None = None) -> Path:
    """A file in *folder* named after the app and the time ("Smart Screen 2026-11-02 21-04-09.png"), not one there
    already (USB HD Cam's record.new_path)."""
    stem = f"{APP_NAME} {time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(now))}"
    path, n = folder / f"{stem}{suffix}", 1
    while path.exists():
        n += 1
        path = folder / f"{stem} ({n}){suffix}"
    return path


def _standard(location: QStandardPaths.StandardLocation) -> Path:
    return Path(QStandardPaths.writableLocation(location)) / APP_NAME


class MainWindow(PortableWindow):
    def __init__(self, log_path: Path | None = None, gamepad: Gamepad | None = None,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery,
                 values: Values | None = None, link: Link | None = None, fetch: weather.Fetch | None = None,
                 family: str | None = None, startup: Path | None = None, program: Path | None = None,
                 roots: Callable[[], list[Path]] = browse.drives, user_home: Path | None = None,
                 pictures: Path | None = None, documents: Path | None = None):
        super().__init__(gamepad)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.log = applog.logger(APP_ID)
        self.log_path = log_path
        self.battery = battery
        self.settings = ScreenSettings(INFO, self)
        self.values = values or Values()
        self.values.interface = self.settings.get("interface") or None
        self.fetch = fetch or partial(weather.fetch_json, user_agent=INFO.user_agent)
        self.family = family
        self.startup, self.program = startup, program
        self.roots, self.user_home = roots, user_home
        self.pictures = pictures or _standard(QStandardPaths.StandardLocation.PicturesLocation)
        self.documents = documents or _standard(QStandardPaths.StandardLocation.DocumentsLocation)
        self.model = screen.TURING_35           # until the screen says what it is
        self.state = State("searching")
        self.sent = 0                           # bytes of the last update
        self.reading = None
        self.picture: QImage | None = None
        self.place = weather.Place.from_json(self.settings.get("weather_place"))
        self.weather: weather.Weather | None = None
        self.weather_text = ""                  # the weather's last news, for the Weather pane
        self.places: list[weather.Place] = []
        self.image: QImage | None = None        # the screen's picture as last drawn, upright
        self.screen_off = False                 # the backlight switched off (not kept: on at every start)
        self.browser: browse.Browser | None = None
        self.close_asked = False
        self.shut = False

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
        self.screen_card = Card("Screen", "")
        self.values_card = Card("Values", "")
        self.look_card = Card("Look", "")
        self.clock_card = Card("Clock", "")
        self.weather_card = Card("Weather", "")
        self.start_card = Card("Start", "")
        for card in (self.screen_card, self.values_card, self.look_card, self.clock_card, self.weather_card,
                     self.start_card):
            card.setFixedHeight(px(CARD_HEIGHT))
            cards.addWidget(card)
        cards.addStretch()
        body.addWidget(column)
        body.addSpacing(px(16))
        self.panes = QStackedWidget()
        self.screen_pane = ListPane("Screen", SCREEN_INFO)
        self.values_pane = ListPane("Values", VALUES_INFO)
        self.look_pane = ListPane("Look", LOOK_INFO)
        self.clock_pane = ListPane("Clock", CLOCK_INFO)
        self.weather_pane = ListPane("Weather", WEATHER_INFO)
        self.start_pane = ListPane("Start", START_INFO)
        self.browse_pane = ListPane("Pick a picture", BROWSE_INFO)
        self.field_pane = FieldPane()
        for pane in (self.screen_pane, self.values_pane, self.look_pane, self.clock_pane, self.weather_pane,
                     self.start_pane, self.browse_pane, self.field_pane):
            self.panes.addWidget(pane)
        body.addWidget(self.panes, 1)
        body.addSpacing(px(16))
        self.preview = Preview(PREVIEW_WIDEST)
        body.addWidget(self.preview)
        page.addLayout(body, 1)
        page.addSpacing(px(8))
        self.legend = Legend()
        page.addWidget(self.legend)
        self.cards = {self.screen_pane: self.screen_card, self.values_pane: self.values_card,
                      self.look_pane: self.look_card, self.clock_pane: self.clock_card,
                      self.weather_pane: self.weather_card, self.start_pane: self.start_card,
                      self.browse_pane: self.look_card}
        self.rows = {self.screen_pane: self.screen_row, self.values_pane: self.values_row,
                     self.look_pane: self.look_row, self.clock_pane: self.clock_row,
                     self.weather_pane: self.weather_row, self.start_pane: self.start_row}
        for pane, card in self.cards.items():
            if pane is not self.browse_pane:
                card.focused.connect(lambda pane=pane: self.show_pane(pane))
                card.activated.connect(lambda pane=pane: self.focus_list(pane))
                pane.list.picked.connect(self.rows[pane])
        self.browse_pane.list.picked.connect(self.browse_picked)
        self.field_pane.field.returnPressed.connect(self.keep_field)

        self.weather_worker = _Worker()
        self.weather_worker.done.connect(self._weather_done)
        self.weather_worker.failed.connect(self._weather_failed)
        self.search_worker = _Worker()
        self.search_worker.done.connect(self._search_done)
        self.search_worker.failed.connect(self._search_failed)
        self.bind("accept", self.a_action)
        self.bind("x", self.x_action)
        self.bind("previous", lambda: self.step_row(-1))
        self.bind("next", lambda: self.step_row(1))
        self.back.connect(self.on_back)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STATUS_MS)
        self.status_timer.timeout.connect(self.update_status)
        self.timer = QTimer(self)
        self.timer.setInterval(INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.weather_timer = QTimer(self)
        self.weather_timer.setInterval(weather.INTERVAL_S * 1000)
        self.weather_timer.timeout.connect(self.update_weather)
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setSingleShot(True)
        self.confirm_timer.setInterval(CONFIRM_MS)
        self.confirm_timer.timeout.connect(self._confirm_over)

        self.link = link or Link()
        self.link.state_changed.connect(self.show_state)
        self.link.sent.connect(self.show_sent)
        self.link.set_brightness(self.settings.get("brightness"))
        self._load_picture()
        for show in (self.show_screen, self.show_values, self.show_look, self.show_clock, self.show_weather,
                     self.show_start):
            show()
        self.show_pane(self.screen_pane)
        self.refresh()

    def start(self) -> None:
        """After the window is shown: the controller, the status line, the link to the screen, the values every
        second and the weather."""
        self.start_gamepad()
        self.update_status()
        self.status_timer.start()
        self.link.start()
        self.timer.start()
        self.weather_timer.start()
        self.update_weather()
        self.screen_card.setFocus()

    def update_status(self) -> None:
        self.header.set_status([*status_clock(), power.text(self.battery())])   # the battery last (owner, 30-10-2026)

    def show_pane(self, pane) -> None:
        current = self.panes.currentWidget()
        if current is not pane and getattr(current, "viewing", False):
            current.show_body()
        self.panes.setCurrentWidget(pane)
        self.update_legend()

    def focus_list(self, pane: ListPane) -> None:
        """The list's first row, or the pane's card while the list is empty."""
        if not pane.list.focus(""):
            self.cards[pane].setFocus()

    # The legend and the buttons

    def legend_items(self) -> list[tuple[str, str]]:
        """The pane's actions on the controller's buttons for the row the focus is on, A too, then core's Menu Info,
        B Back and View Exit."""
        if self.close_asked:
            return [(VIEW, "Press again to exit")]
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            return [("A", "Keep"), ("X", "Paste"), KEYBOARD, *self.common_items(True)]
        if getattr(pane, "viewing", False):
            return self.common_items(True)
        if pane is self.browse_pane:
            return [("A", "Open"), *self.common_items(True)]
        row = pane.list.focused() if isinstance(pane, ListPane) else ""
        items = self.row_items(pane, row) if row else [("A", "Open")]
        return [*items, *self.common_items()]

    def row_items(self, pane, row: str) -> list[tuple[str, str]]:
        steps = [("A", "Next"), ("LB", "Before"), ("RB", "Next")]
        if pane is self.screen_pane:
            return {"brightness": [("A", "Brighter"), ("LB", "Darker"), ("RB", "Brighter")],
                    "orientation": steps,
                    "backlight": [("A", "Switch on" if self.screen_off else "Switch off")]}.get(row, [("A", "Save")])
        if pane is self.values_pane:
            if row == "interface":
                return steps
            return [("A", "Take off" if row.removeprefix("tile:") in self.shown_tiles() else "Put on")]
        if pane is self.look_pane:
            if row.startswith("color:"):
                return [*steps, ("X", "Theme's")]
            return {"theme": steps, "title": [("A", "Change")],
                    "picture": [("A", "Choose"), ("X", "None")]}.get(row, [])
        if pane is self.clock_pane:
            return steps
        if pane is self.weather_pane:
            return [("A", {"place": "Search", "forget": "No weather"}.get(row, "Use"))]
        if pane is self.start_pane:
            return {"autostart": [("A", "Switch off" if self.autostart_on() else "Switch on")],
                    "off_on_quit": [("A", "Change")], "background": [("A", "Minimize")],
                    "log": [("A", "View")]}.get(row, [])
        return []

    def update_legend(self) -> None:
        if hasattr(self, "legend"):
            self.legend.set_items(self.legend_items())

    def a_action(self) -> None:
        """A beside a card (a tap on the legend's A) or in a text field: the pane's own A."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.keep_field()
        elif isinstance(pane, ListPane) and not pane.viewing:
            row = pane.list.focused()
            if row:
                pane.list.picked.emit(row)
            else:
                self.focus_list(pane)

    def x_action(self) -> None:
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.paste()
        elif pane is self.look_pane:
            row = pane.list.focused()
            if row.startswith("color:"):
                self.set_color(row.removeprefix("color:"), "")
            elif row == "picture":
                self.set_picture("")

    def step_row(self, delta: int) -> None:
        """LB and RB: the row the focus is on a step back or on (brightness without wrapping around)."""
        pane = self.panes.currentWidget()
        if not isinstance(pane, ListPane) or pane.viewing:
            return
        row = pane.list.focused()
        if pane is self.screen_pane and row in ("brightness", "orientation"):
            self.screen_step(row, delta)
        elif pane is self.values_pane and row == "interface":
            self.interface_step(delta)
        elif pane is self.look_pane and (row == "theme" or row.startswith("color:")):
            self.look_step(row, delta)
        elif pane is self.clock_pane and row:
            self.clock_step(row, delta)

    def on_back(self) -> None:
        """B goes back (the suite's rule): a field's page to its row (nothing kept), the log to its pane, the picture
        browser a folder up and from its places to the Look card, a pane to its card."""
        pane = self.panes.currentWidget()
        if pane is self.field_pane:
            self.leave_field()
        elif getattr(pane, "viewing", False):
            pane.show_body()
            self.focus_list(pane)
            self.update_legend()
        elif pane is self.browse_pane and self.browser is not None:
            if self.browser.up():
                self.show_browse()
            else:
                self.leave_browser()
        else:
            self.go_back()

    # The picture

    def shown_tiles(self) -> list[str]:
        return [k for k in self.settings.get("tiles").split(",") if k]

    def title(self) -> str:
        """The header's text: the user's, or the handheld's family until one is kept (empty: only the time)."""
        if self.settings.qsettings.contains("title"):
            return self.settings.get("title")
        return render.default_title(self.family)

    def picture_size(self) -> tuple[int, int]:
        """The upright picture: the screen's own size, turned for a landscape orientation."""
        w, h = self.model.width, self.model.height
        return (h, w) if render.ORIENTATIONS[self.orientation()] % 180 else (w, h)

    def orientation(self) -> str:
        name = self.settings.get("orientation")
        return name if name in render.ORIENTATIONS else "Portrait"

    def theme(self) -> render.Theme:
        theme = render.THEMES.get(self.settings.get("theme"), render.THEMES[render.DEFAULT_THEME])
        return render.with_colors(theme, {key: self.settings.get(f"color_{key}") for key in render.COLORS})

    def clock_style(self) -> render.Clock:
        return render.Clock(self.settings.get("hours"), self.settings.get("zone"), self.settings.get("date"))

    def draw(self, when: float | None = None) -> QImage:
        width, height = self.picture_size()
        return render.draw(self.reading, self.shown_tiles(), width, height, QColor(AMBER), title=self.title(),
                           clock=when, theme=self.theme(), picture=self.picture, weather=self.weather,
                           place=self.place.name if self.place else "", style=self.clock_style())

    def refresh(self, read: bool = True) -> None:
        if read or self.reading is None:
            self.reading = self.values.read()
        self.image = image = self.draw()
        self.preview.show_image(image)
        upright = render.for_screen(image, render.ORIENTATIONS[self.orientation()])
        self.link.show(render.rgb565(upright), self.model.width, self.model.height)

    # The Screen card

    def show_screen(self) -> None:
        found, kind = self.state.found, self.state.kind
        port = f" on {found.port}" if found else ""
        width, height = self.picture_size()
        card = {"searching": "No screen found: plug it in",
                "in-use": "In use by another program",
                "resetting": "Starting the screen",
                "connected": f"{self.model.short}{port}",
                "error": "It stopped: the pane says why"}[kind]
        self.screen_card.set_text(card, AMBER if kind in ("in-use", "error") else DIM)
        summary = {"searching": "No Turzx USB screen (USB ID 1a86:5722) is plugged in. Plug it in, into the handheld "
                                "or a dock: the app finds it by itself.",
                   "in-use": f"The screen is plugged in{port}, but another program has its port: close the screen "
                             "maker's app (UsbMonitor). The app tries again by itself.",
                   "resetting": "The screen restarts once when the app connects, so it starts from a clean state.",
                   "connected": f"{self.model.name}{port}, {width} x {height}. "
                                + (f"The last update sent {self.sent / 1000:.1f} KB." if self.sent else
                                   "Nothing sent yet."),
                   "error": self.state.message or "The screen stopped answering: the app looks for it again."}[kind]
        self.screen_pane.summary.setText(summary)
        brightness = self.settings.get("brightness")
        self.screen_pane.list.set_items([
            ("brightness", f"Brightness: {brightness} %"), ("orientation", f"Orientation: {self.orientation()}"),
            ("backlight", "Backlight: Off, the screen is dark" if self.screen_off else "Backlight: On"),
            ("picture", "Save the picture"), ("report", "Save a report")])
        self.update_legend()

    def screen_row(self, key: str) -> None:
        if key in ("brightness", "orientation"):
            self.screen_step(key, 1)
        elif key == "backlight":
            self.set_power(self.screen_off)
        elif key == "picture":
            self.save_picture()
        elif key == "report":
            self.save_report()

    def screen_step(self, key: str, delta: int) -> None:
        pane = self.screen_pane
        if key == "brightness":
            now = self.settings.get("brightness")
            value = step(list(range(0, 101, BRIGHTNESS_STEP)), now - now % BRIGHTNESS_STEP, delta, wrap=False)
            self.set_brightness(value)
            pane.status.setText(f"Brightness {value} %." if value != now else
                                "The brightest already: LB makes it darker." if delta > 0 else
                                "The darkest already: the A button or RB makes it brighter.")
        else:
            name = step(list(render.ORIENTATIONS), self.orientation(), delta)
            self.settings.set("orientation", name)
            self.log.info(f"Orientation: {name}.")
            self.refresh(read=False)
            pane.status.setText(f"{name}.")
        self.show_screen()

    def set_brightness(self, value: int) -> None:
        self.settings.set("brightness", value)
        self.link.set_brightness(value)

    def set_power(self, on: bool) -> None:
        self.screen_off = not on
        self.link.set_power(on)
        self.screen_pane.status.setText("The backlight is on." if on else
                                        "The screen is dark; the app keeps running. The A button switches it on.")
        self.show_screen()

    def save_picture(self) -> None:
        """What the screen shows, at its own size, as a PNG in Pictures\\Smart Screen."""
        if self.image is None:
            return
        try:
            self.pictures.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.screen_pane.status.setText(f"{private(self.pictures)} could not be made: {error.strerror}.")
            return
        path = new_path(self.pictures, ".png")
        if not self.image.save(str(path), "PNG"):
            self.screen_pane.status.setText(f"{private(path)} could not be written.")
            return
        self.screen_pane.status.setText(f"Saved: {private(path)}")
        self.log.info(f"Picture saved: {private(path)}.")

    def report_text(self, when: float | None = None) -> str:
        name = self.settings.get("interface")
        return render.report(self.reading, when, self.weather, self.place.name if self.place else "",
                             name or ALL_ADAPTERS.lower(), self.title())

    def save_report(self) -> None:
        """Every value at this moment, with the date and time, as a text file in Documents\\Smart Screen."""
        path = new_path(self.documents, ".txt")
        try:
            self.documents.mkdir(parents=True, exist_ok=True)
            path.write_text(self.report_text(), encoding="utf-8")
        except OSError as error:
            self.screen_pane.status.setText(f"{private(path)} could not be written: {error.strerror}.")
            return
        self.screen_pane.status.setText(f"Saved: {private(path)}")
        self.log.info(f"Report saved: {private(path)}.")

    def show_state(self, state: State) -> None:
        """The link's news: the Screen card and pane, and the picture at the model's size once it is known."""
        before, self.state = self.state, state
        if state.kind != before.kind:
            port = f" on {state.found.port}" if state.found else ""
            self.log.info({"searching": "No screen found.", "in-use": f"The screen's port{port} is in use.",
                           "resetting": f"Restarting the screen{port}.",
                           "connected": f"Connected: {state.model.name if state.model else 'the screen'}{port}.",
                           "error": f"The screen stopped: {state.message}"}[state.kind])
        if state.kind != "connected":
            self.sent = 0
        if state.model is not None and state.model != self.model:
            self.model = state.model
            self.refresh(read=False)
        self.show_screen()

    def show_sent(self, size: int) -> None:
        """How much the last update sent: a few KB a second, a whole picture at start."""
        self.sent = size
        if self.panes.currentWidget() is self.screen_pane:
            self.show_screen()

    # The Values card

    def show_values(self) -> None:
        shown = self.shown_tiles()
        rows = [(f"tile:{key}", ("✓ " if key in shown else "") + caption) for key, caption in render.TILES]
        rows.append(("interface", f"Network adapter: {self.settings.get('interface') or ALL_ADAPTERS}"))
        self.values_pane.list.set_items(rows)
        captions = [caption for key, caption in render.TILES if key in shown]
        self.values_card.set_text(f"{len(captions)} on the screen" if captions else "None: only the header")
        self.values_pane.summary.setText(f"{len(captions)} on the screen. The A button puts a value on it or takes it "
                                         "off.")
        self.update_legend()

    def values_row(self, key: str) -> None:
        if key == "interface":
            self.interface_step(1)
            return
        tile = key.removeprefix("tile:")
        shown = self.shown_tiles()
        shown = [k for k in shown if k != tile] if tile in shown else [*shown, tile]
        self.settings.set("tiles", ",".join(k for k, _ in render.TILES if k in shown))
        self.values_pane.status.setText("")
        self.show_values()
        self.refresh(read=False)
        self.update_weather()                   # the weather tile may just have been put on

    def interface_step(self, delta: int) -> None:
        names = ["", *self.values.interfaces()]
        chosen = self.settings.get("interface")
        if chosen and chosen not in names:
            names.append(chosen)                # not there now (unplugged): keep the choice
        name = step(names, chosen, delta)
        self.settings.set("interface", name)
        self.values.interface = name or None
        self.values_pane.status.setText(f"The Network tile measures {name or 'every adapter, added up'}.")
        self.show_values()

    # The Look card

    def show_look(self) -> None:
        rows = [("theme", f"Theme: {self.settings.get('theme')}")]
        rows += [(f"color:{key}", f"{name} color: {color_name(self.settings.get(f'color_{key}'))}")
                 for key, name in COLOR_NAMES.items()]
        title = self.title()
        rows.append(("title", f"Header text: {title or NO_TITLE}"))
        path = self.settings.get("picture")
        if not path:
            picture = "None, the theme's color"
        elif self.picture is None:
            picture = f"{Path(path).name} cannot be read (moved or removed?): the theme's color for now"
        else:
            picture = Path(path).name
        rows.append(("picture", f"Background: {picture}"))
        self.look_pane.list.set_items(rows)
        self.look_pane.summary.setText("The screen changes at once, as the picture beside shows.")
        self.look_card.set_text(f"{self.settings.get('theme')}, {title or 'only the time'}")
        self.update_legend()

    def look_row(self, key: str) -> None:
        if key == "title":
            self.open_field("title", self.title())
        elif key == "picture":
            self.show_browser()
        else:
            self.look_step(key, 1)

    def look_step(self, key: str, delta: int) -> None:
        if key == "theme":
            name = step(list(render.THEMES), self.settings.get("theme"), delta)
            self.settings.set("theme", name)
            self.look_pane.status.setText(f"{name}.")
            self.refresh(read=False)
            self.show_look()
        else:
            color = key.removeprefix("color:")
            value = step([value for value, _name in PALETTE], self.settings.get(f"color_{color}").lower(), delta)
            self.set_color(color, value)

    def set_color(self, key: str, value: str) -> None:
        """*value* "#rrggbb", or "" for the theme's own."""
        self.settings.set(f"color_{key}", value)
        self.look_pane.status.setText(f"{COLOR_NAMES[key]}: {color_name(value)}.")
        self.refresh(read=False)
        self.show_look()

    def set_title(self, text: str) -> None:
        """Kept also when it is empty (only the time), so the handheld's family no longer stands in for it."""
        self.settings.qsettings.setValue("title", text)
        self.settings.sync()
        self.refresh(read=False)
        self.show_look()

    def _load_picture(self) -> None:
        path = self.settings.get("picture")
        image = QImage(path) if path else None
        self.picture = image if image is not None and not image.isNull() else None

    def set_picture(self, path: str) -> bool:
        """*path* behind the tiles ("": none); False when it is not a picture the app can read."""
        if path and QImage(path).isNull():
            self.browse_pane.status.setText(f"{Path(path).name} is not a picture the app can read.")
            return False
        self.settings.set("picture", path)
        self._load_picture()
        self.look_pane.status.setText(f"Background: {Path(path).name}." if path else "No background picture.")
        self.refresh(read=False)
        self.show_look()
        return True

    # The picture browser (core's browse)

    def show_browser(self) -> None:
        current = self.settings.get("picture")
        start = Path(current).parent if current else browse.remembered(self.settings.qsettings, BROWSED)
        self.browser = browse.Browser(browse.places(self.user_home, self.roots), PICTURES,
                                      path=start if start is not None and start.is_dir() else None)
        self.browse_pane.status.setText("")
        self.show_pane(self.browse_pane)
        self.show_browse()

    def show_browse(self) -> None:
        path = self.browser.path if self.browser is not None else None
        self.browse_pane.summary.setText(private(path) if path is not None else
                                         "Where is the picture? Open a place, then the folder it is in.")
        self.browse_pane.list.set_items(self.browser.rows() if self.browser is not None else [])
        self.focus_list(self.browse_pane)
        self.update_legend()

    def browse_picked(self, key: str) -> None:
        if self.browser is None:
            return
        picked = self.browser.open(key)
        if picked is None:
            self.show_browse()
            return
        if not self.set_picture(str(picked)):
            return
        browse.remember(self.settings.qsettings, BROWSED, picked.parent)
        self.log.info("Background picture chosen.")
        self.leave_browser("picture")

    def leave_browser(self, focus: str = "picture") -> None:
        self.browser = None
        self.show_pane(self.look_pane)
        self.look_pane.list.focus(focus)

    # The field pages: the header's text, the weather's place

    def open_field(self, key: str, value: str) -> None:
        title, text, placeholder, length = FIELDS[key]
        self.field_pane.set_field(key, title, text, value, placeholder=placeholder, length=length)
        self.show_pane(self.field_pane)
        self.field_pane.field.setFocus()

    def keep_field(self) -> None:
        """A on a field's page: the header's text kept, or the place looked for."""
        key, value = self.field_pane.key, self.field_pane.field.text().strip()
        if key == "title":
            self.set_title(value[:TITLE_CHARS])
            self.leave_field(f"Header text: {value or NO_TITLE}.")
        elif key == "search":
            if not value:
                self.field_pane.status.setText("Type a city or a town first.")
                return
            if not self.search_worker.start(lambda: weather.search(value, self.fetch)):
                self.field_pane.status.setText("Still looking for the place before: a moment.")
                return
            self.leave_field(f"Looking for {value} …")

    def leave_field(self, said: str = "") -> None:
        key = self.field_pane.key
        self.field_pane.field.clear()
        pane, row = (self.look_pane, "title") if key == "title" else (self.weather_pane, "place")
        self.show_pane(pane)
        pane.status.setText(said)
        pane.list.focus(row)

    def paste(self) -> None:
        """The clipboard's text into the page's field (copied in a browser on the device)."""
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.field_pane.status.setText("The clipboard is empty: copy the text on this device first.")
            return
        self.field_pane.field.setText(text)
        self.field_pane.status.setText("The text is in the field: the A button keeps it.")

    # The Clock card

    def show_clock(self) -> None:
        offset = render.offset(time.localtime())
        zone = self.settings.get("zone")
        self.clock_pane.list.set_items([
            ("hours", f"Time: {HOURS.get(self.settings.get('hours'), HOURS[24])}"),
            ("zone", f"Time zone: {ZONES.get(zone, ZONES[''])}" + (f" ({offset} now)" if zone else "")),
            ("date", f"Date: {DATES.get(self.settings.get('date'), DATES[''])}")])
        self.clock_pane.summary.setText(f"The time is Windows', in its time zone ({offset} now).")
        date = DATES.get(self.settings.get("date"), "")
        self.clock_card.set_text(f"{HOURS.get(self.settings.get('hours'), HOURS[24]).split(' ')[0]}"
                                 + (f", {date}" if self.settings.get("date") else ", no date"))
        self.update_legend()

    def clock_row(self, key: str) -> None:
        self.clock_step(key, 1)

    def clock_step(self, key: str, delta: int) -> None:
        choices = {"hours": HOURS, "zone": ZONES, "date": DATES}[key]
        value = step(list(choices), self.settings.get(key), delta)
        self.settings.set(key, value)
        self.clock_pane.status.setText(f"{choices[value]}.")
        self.refresh(read=False)
        self.show_clock()

    # The Weather card

    def show_weather(self) -> None:
        rows = [("place", f"Place: {self.place.label if self.place else 'None: no weather, nothing is sent'}")]
        rows += [(f"found:{n}", f"Use {place.label}") for n, place in enumerate(self.places)]
        if self.place is not None:
            rows.append(("forget", "No weather"))
        self.weather_pane.list.set_items(rows)
        on_screen = "weather" in self.shown_tiles()
        if self.place is None:
            self.weather_pane.summary.setText("No place chosen: the A button on the Place row looks for one.")
        else:
            self.weather_pane.summary.setText(self.weather_text or ("The weather comes in a moment." if on_screen else
                                              "The Weather tile is not on the screen: the Values card puts it on."))
        self.weather_card.set_text(self.place.name if self.place else "No place: no weather")
        self.update_legend()

    def weather_row(self, key: str) -> None:
        if key == "place":
            self.open_field("search", "")
        elif key == "forget":
            self.set_place(None)
        elif key.startswith("found:"):
            n = int(key.removeprefix("found:"))
            if 0 <= n < len(self.places):
                self.use_place(self.places[n])

    def _search_done(self, places) -> None:
        self.places = places
        self.weather_pane.status.setText(f"{len(places)} found: the A button on one uses it." if places else
                                         "Nothing found by that name.")
        self.show_weather()
        self.weather_pane.list.focus("found:0" if places else "place")

    def _search_failed(self, error) -> None:
        self.weather_pane.status.setText(str(error))

    def use_place(self, place: weather.Place) -> None:
        self.places = []
        self.set_place(place)
        if "weather" not in self.shown_tiles():
            self.settings.set("tiles", ",".join(k for k, _ in render.TILES if k in [*self.shown_tiles(), "weather"]))
            self.show_values()
            self.refresh(read=False)
            self.update_weather()               # chose a place: show it
        self.weather_pane.list.focus("place")

    def set_place(self, place: weather.Place | None) -> None:
        self.place, self.weather, self.weather_text = place, None, ""
        self.settings.set("weather_place", place.to_json() if place else "")
        self.weather_pane.status.setText(f"{place.label}." if place else "No weather: nothing is sent.")
        self.log.info("Weather place chosen." if place else "Weather place forgotten.")
        self.show_weather()
        self.refresh(read=False)
        self.update_weather()

    def update_weather(self) -> None:
        """Only with a place and the weather tile on the screen: otherwise nothing goes over the network."""
        if self.place is None or "weather" not in self.shown_tiles():
            return
        place = self.place
        self.weather_worker.start(lambda: weather.current(place, self.fetch))

    def _weather_done(self, result: weather.Weather) -> None:
        self.weather = result
        wind = f", wind {result.wind_kmh:.0f} km/h" if result.wind_kmh is not None else ""
        humidity = f", humidity {result.humidity} %" if result.humidity is not None else ""
        self.weather_text = f"Now: {result.temperature:.0f} °C, {result.description.lower()}{wind}{humidity}."
        self.show_weather()
        self.refresh(read=False)

    def _weather_failed(self, error) -> None:
        self.weather_text = f"{error} The screen keeps the last weather it had."
        self.show_weather()

    # The Start card

    def autostart_on(self) -> bool:
        return autostart.enabled(self.startup)

    def show_start(self) -> None:
        on = self.autostart_on()
        self.start_pane.list.set_items([
            ("autostart", f"Start with Windows, minimized: {'On' if on else 'Off'}"),
            ("off_on_quit", "When the app closes: " + ("the screen goes dark" if self.settings.get("off_on_quit")
                                                       else "the screen keeps the last picture")),
            ("background", "Run in the background now"), ("log", "The app's log")])
        self.start_pane.summary.setText("The screen shows the values while the app runs; minimized is enough.")
        self.start_card.set_text("Starts with Windows" if on else "Started by hand")
        self.update_legend()

    def start_row(self, key: str) -> None:
        pane = self.start_pane
        if key == "autostart":
            on = not self.autostart_on()
            try:
                autostart.set_enabled(on, self.startup, self.program)
            except (OSError, RuntimeError) as error:
                pane.status.setText(str(error))
                return
            pane.status.setText("It starts minimized when you sign in." if on else "It no longer starts with Windows.")
            self.log.info(f"Start with Windows: {'on' if on else 'off'}.")
        elif key == "off_on_quit":
            self.settings.set("off_on_quit", not self.settings.get("off_on_quit"))
            pane.status.setText("")
        elif key == "background":
            self.showMinimized()
            return
        elif key == "log":
            self.view_log()
            return
        self.show_start()

    def log_lines(self) -> list[str]:
        if self.log_path is None:
            return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def view_log(self) -> None:
        """The log's newest lines in the Start pane: the d-pad scrolls it, B goes back (not in Notepad)."""
        self.start_pane.show_text("The log", private("\n".join(self.log_lines()[-LOG_MAX:])) or "Nothing logged yet.",
                                  end=True)
        self.start_pane.status.setText("The d-pad scrolls it, the B button goes back.")
        self.update_legend()

    # View

    def exit_app(self) -> None:
        """View: while the screen is connected, a second press within five seconds exits (the screen goes dark or
        keeps its last picture)."""
        if self.state.kind == "connected" and not self.close_asked:
            self.close_asked = True
            self.confirm_timer.start()
            pane = self.panes.currentWidget()
            if hasattr(pane, "status"):
                pane.status.setText("Press View again to exit: " + (
                    "the screen goes dark." if self.settings.get("off_on_quit") else
                    "the screen keeps its last picture.") + " Run in the background (the Start card) keeps it going.")
            self.update_legend()
            return
        self.close()

    def _confirm_over(self) -> None:
        self.confirm_timer.stop()
        if self.close_asked:
            self.close_asked = False
            pane = self.panes.currentWidget()
            if hasattr(pane, "status") and pane.status.text().startswith("Press View again"):
                pane.status.setText("")
            self.update_legend()

    def shut_down(self) -> None:
        """The timers stopped and the link ended, the screen dark when so set; once, at close or when the app quits."""
        if self.shut:
            return
        self.shut = True
        for timer in (self.timer, self.status_timer, self.weather_timer, self.confirm_timer):
            timer.stop()
        self.link.stop(screen_off=self.settings.get("off_on_quit"))
        self.values.close()

    def closeEvent(self, event) -> None:
        self.shut_down()
        super().closeEvent(event)
