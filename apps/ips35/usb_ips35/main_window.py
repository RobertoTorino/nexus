# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the screen's state in the header, a preview of what it shows (saved as a picture or a report of every
value), and its settings in tabs (the screen: brightness and orientation; the values and the network interface; the
look: theme, colors, header text, a picture behind the tiles; the clock: hours, time zone and date; the weather's
place; start and quit). Every second it reads the sensors, draws the picture and hands it to the link, which sends what
changed to the screen. A theme or color being tried shows in the preview only, until it is chosen. The weather is
fetched off the GUI thread, only while its tile is shown and a place is chosen."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (QBoxLayout, QCheckBox, QColorDialog, QComboBox, QFileDialog, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider, QTabWidget,
                             QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.sensors import Sensors
from bc250_core.settings import SettingsStore, restore_geometry, save_geometry
from bc250_core.theme import ACCENT
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import AppHeader, MetricBox, StatusText, accent_button, hint_label, same_width

from . import APP_NAME, INFO, LOGO_PATH, __version__, access, autostart, network, render, runner, screen, weather
from .link import Link, State

INTERVAL_MS = 1000
PREVIEW_MAX = 480                               # the preview is the screen's own size, 1:1, up to this on its long side
TITLE_CHARS = 24
ALL_INTERFACES = "All interfaces"
PICTURES = "Pictures (*.png *.jpg *.jpeg *.webp *.bmp)"
# The look's settings a trial may override in the preview; the colors are "" for the theme's own or #rrggbb.
LOOK = ("theme", *(f"colour_{key}" for key in render.COLOURS))
COLOUR_NAMES = {"text": "Text", "tiles": "Tiles", "accent": "Accent", "background": "Background"}
HOURS = {24: "24-hour", 12: "12-hour (AM/PM)"}
ZONES = {"": "Not shown", "name": "Name", "offset": "Offset from UTC"}
DATES = {"": "Not shown", "weekday": "Weekday, day and month", "dmy": "DD-MM-YYYY", "mdy": "MM/DD/YYYY",
         "ymd": "YYYY-MM-DD"}


class ScreenSettings(SettingsStore):
    DEFAULTS = {"brightness": 50, "orientation": "Portrait", "tiles": ",".join(render.DEFAULT_TILES),
                "off_on_quit": True, "theme": render.DEFAULT_THEME, "title": render.TITLE, "picture": "",
                "interface": "", "weather_place": "",       # interface "": all; weather_place: weather.Place as JSON
                "hours": 24, "zone": "", "date": "",
                **{f"colour_{key}": "" for key in render.COLOURS}}


class TrialComboBox(QComboBox):
    """A combo box that says when its list closes, so what was tried while it was open can be put back."""
    popup_closed = pyqtSignal()

    def hidePopup(self) -> None:  # noqa: N802 (Qt override)
        super().hidePopup()
        self.popup_closed.emit()


def _job(function: Callable, *args) -> Callable[[], object]:
    """A job for UpdateChecker: its result, or the WeatherError it raised (a thread must not raise)."""
    def run():
        try:
            return function(*args)
        except weather.WeatherError as exc:
            return exc
    return run


class MainWindow(QWidget):
    def __init__(self, sensors: Sensors | None = None, link: Link | None = None,
                 run_root: Callable[[list[str]], runner.Result] = runner.run_root, config_home=None,
                 fetch: weather.Fetch | None = None, net_root: Path = network.NET):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.sensors = sensors or Sensors()
        self.settings = ScreenSettings(INFO, self)
        self.sensors.interface = self.settings.get("interface") or None
        self.run_root = run_root
        self.config_home = config_home
        self.net_root = net_root
        self.fetch = fetch or partial(weather.fetch_json, user_agent=INFO.user_agent)
        self.model = screen.TURING_35           # until the screen says what it is
        self.state = State("searching")
        self.reading = None
        self.picture: QImage | None = None
        self.place = weather.Place.from_json(self.settings.get("weather_place"))
        self.weather: weather.Weather | None = None
        self.places: list[weather.Place] = []
        self.trial: dict[str, str] = {}         # LOOK settings being tried: in the preview only, not on the screen
        self.image: QImage | None = None        # the screen's picture as last drawn, upright

        layout = QVBoxLayout(self)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        self.badge = StatusText("Looking for the screen")
        header.add_state(self.badge)
        self.power_button = QPushButton("Screen off")
        self.power_button.setCheckable(True)
        self.power_button.setToolTip("Switches the screen's backlight off and on; the app keeps running.")
        self.power_button.toggled.connect(self.set_power)
        header.add_action(self.power_button)
        self.model_box = MetricBox("Screen")
        self.port_box = MetricBox("Port")
        self.size_box = MetricBox("Resolution")
        boxes = [self.model_box, self.port_box, self.size_box]
        for box in boxes:
            header.add_second(box)
        same_width(boxes)
        header.add_second(QWidget(), 1)
        layout.addLayout(header)

        self.access_box = QGroupBox("Access to the screen")
        access_layout = QVBoxLayout(self.access_box)
        self.access_text = hint_label(
            "The screen is plugged in, but your user may not use its port yet. Allow access adds a udev rule for "
            "this screen only (it asks for your password); it takes effect at once, without unplugging it.")
        self.access_button = accent_button("Allow access…")
        self.access_button.clicked.connect(self.allow_access)
        access_layout.addWidget(self.access_text)
        access_layout.addWidget(self.access_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.access_box)

        self.body = body = QBoxLayout(QBoxLayout.Direction.LeftToRight)     # the tabs under a landscape preview
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setToolTip("What the screen shows, at its own size.")
        self.save_picture_button = QPushButton("Save picture…")
        self.save_picture_button.setToolTip("Saves what the screen shows, at its own size, as a PNG.")
        self.save_picture_button.clicked.connect(self.save_picture)
        self.save_report_button = QPushButton("Save report…")
        self.save_report_button.setToolTip("Saves every value at this moment, with the date and time, as a text file.")
        self.save_report_button.clicked.connect(self.save_report)
        saves = QHBoxLayout()
        saves.addWidget(self.save_picture_button)
        saves.addWidget(self.save_report_button)
        saves.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(self.preview)
        left.addLayout(saves)
        left.addStretch(1)
        body.addLayout(left)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(False)      # every tab in sight; the window is as wide as they need
        self.tabs.addTab(self._screen_tab(), "Screen")
        self.tabs.addTab(self._values_tab(), "Values")
        self.tabs.addTab(self._look_tab(), "Look")
        self.tabs.addTab(self._clock_tab(), "Clock")
        self.tabs.addTab(self._weather_tab(), "Weather")
        self.tabs.addTab(self._start_tab(), "Start")
        body.addWidget(self.tabs, 1)
        layout.addLayout(body, 1)
        self._load_picture()

        self.weather_job = UpdateChecker(self)
        self.weather_job.finished.connect(self._weather_done)
        self.search_job = UpdateChecker(self)
        self.search_job.finished.connect(self._search_done)
        self.weather_timer = QTimer(self, interval=weather.INTERVAL_S * 1000)
        self.weather_timer.timeout.connect(self.update_weather)
        self.weather_timer.start()

        self.link = link or Link()
        self.link.state_changed.connect(self.show_state)
        self.link.sent.connect(self.show_sent)
        self.link.set_brightness(self.settings.get("brightness"))
        self.show_state(self.state)
        self.link.start()

        self.timer = QTimer(self, interval=INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        restore_geometry(self, self.settings.qsettings)
        self.refresh()
        self.update_weather()

    # ------------------------------------------------------------------- tabs
    def _screen_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(0, 100)
        self.brightness.setValue(self.settings.get("brightness"))
        self.brightness_label = QLabel(f"{self.brightness.value()} %")
        self.brightness.valueChanged.connect(self.set_brightness)
        grid.addWidget(QLabel("Brightness"), 0, 0)
        grid.addWidget(self.brightness, 0, 1, 1, 2)
        grid.addWidget(self.brightness_label, 0, 3)
        self.orientation = QComboBox()
        self.orientation.addItems(render.ORIENTATIONS)
        self.orientation.setCurrentText(self.settings.get("orientation"))
        self.orientation.currentTextChanged.connect(self.set_orientation)
        self.orientation.setToolTip("How the screen stands. Turn it upside down when the USB cable is at the "
                                    "bottom or on the other side.")
        grid.addWidget(QLabel("Orientation"), 1, 0)
        grid.addWidget(self.orientation, 1, 1, 1, 3)
        grid.setRowStretch(2, 1)
        return tab

    def _values_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        shown = self.shown_tiles()
        self.tile_boxes: dict[str, QCheckBox] = {}
        for n, (key, caption) in enumerate(render.TILES):
            box = QCheckBox(caption)
            box.setToolTip(render.TILE_HINTS[key])
            box.setChecked(key in shown)
            box.toggled.connect(self.save_tiles)
            grid.addWidget(box, n // 3, n % 3)
            self.tile_boxes[key] = box
        rows = -(-len(render.TILES) // 3)
        grid.addWidget(hint_label("GPU load needs the GPU governor's fix-metrics; without it the GPU tile shows the "
                                  "clock. The weather needs a place, on the Weather tab."), rows, 0, 1, 3)
        self.interface = QComboBox()
        self.interface.addItem(ALL_INTERFACES, "")
        for name in self.sensors.interfaces():
            self.interface.addItem(network.label(name, self.net_root), name)
        chosen = self.settings.get("interface")
        if chosen and self.interface.findData(chosen) < 0:
            self.interface.addItem(chosen, chosen)          # not there now (unplugged, renamed): keep the choice
        self.interface.setCurrentIndex(max(0, self.interface.findData(chosen)))
        self.interface.currentIndexChanged.connect(lambda: self.set_interface(self.interface.currentData()))
        self.interface.setToolTip("The interface the Network tile measures: Ethernet, Wi-Fi, or all of them "
                                  "added up.")
        grid.addWidget(QLabel("Network tile"), rows + 1, 0)
        grid.addWidget(self.interface, rows + 1, 1, 1, 2)
        grid.setRowStretch(rows + 2, 1)
        return tab

    def _look_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        self.theme = TrialComboBox()
        self.theme.addItems(render.THEMES)
        self.theme.setCurrentText(self.settings.get("theme"))
        self.theme.currentTextChanged.connect(self.set_theme)
        self.theme.highlighted.connect(lambda n: self.try_look("theme", self.theme.itemText(n)))
        self.theme.popup_closed.connect(self.end_trial)
        self.theme.setToolTip("Dark takes the suite's accent color; the others have their own. Moving through the "
                              "list shows each theme in the preview; the screen changes when you choose one.")
        grid.addWidget(QLabel("Theme"), 0, 0)
        grid.addWidget(self.theme, 0, 1, 1, 2)
        self.colour_buttons: dict[str, QPushButton] = {}
        colours = QHBoxLayout()
        for key, name in COLOUR_NAMES.items():
            button = QPushButton(name)
            button.setToolTip(f"Your own colour for the {name.lower()}, instead of the theme's. The preview shows "
                              "each color you try; the screen changes when you choose OK.")
            button.clicked.connect(partial(self.choose_colour, key))
            colours.addWidget(button)
            self.colour_buttons[key] = button
        self.colours_clear = QPushButton("Theme's")
        self.colours_clear.setToolTip("Back to the theme's own colors.")
        self.colours_clear.clicked.connect(self.clear_colours)
        colours.addWidget(self.colours_clear)
        colours.addStretch(1)
        grid.addWidget(QLabel("Colors"), 1, 0)
        grid.addLayout(colours, 1, 1, 1, 2)
        self._show_colours()
        self.title = QLineEdit(self.settings.get("title"))
        self.title.setMaxLength(TITLE_CHARS)
        self.title.setPlaceholderText("Nothing: only the time")
        self.title.setToolTip("Your own text in the header, for example the board's name or its CPU.")
        self.title.textChanged.connect(self.set_title)
        grid.addWidget(QLabel("Header text"), 2, 0)
        grid.addWidget(self.title, 2, 1, 1, 2)
        self.picture_label = QLabel()
        self.picture_label.setWordWrap(True)
        choose = QPushButton("Choose…")
        choose.clicked.connect(self.choose_picture)
        self.picture_clear = QPushButton("None")
        self.picture_clear.clicked.connect(lambda: self.set_picture(""))
        grid.addWidget(QLabel("Background"), 3, 0)
        grid.addWidget(self.picture_label, 3, 1, 1, 2)
        buttons = QHBoxLayout()
        buttons.addWidget(choose)
        buttons.addWidget(self.picture_clear)
        buttons.addStretch(1)
        grid.addLayout(buttons, 4, 1, 1, 2)
        grid.addWidget(hint_label("A picture of your own behind the tiles, cut to the screen's shape. The app keeps "
                                  "where it is, not a copy: leave it there."), 5, 0, 1, 3)
        grid.setRowStretch(6, 1)
        return tab

    def _clock_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        self.hours = self._choice(HOURS, self.settings.get("hours"), "hours")
        self.zone = self._choice(ZONES, self.settings.get("zone"), "zone")
        self.date = self._choice(DATES, self.settings.get("date"), "date")
        for row, (caption, box) in enumerate((("Time", self.hours), ("Time zone", self.zone), ("Date", self.date))):
            grid.addWidget(QLabel(caption), row, 0)
            grid.addWidget(box, row, 1, 1, 2)
        self.zone_hint = hint_label("")
        grid.addWidget(self.zone_hint, 3, 0, 1, 3)
        grid.setRowStretch(4, 1)
        self._show_zone()
        return tab

    def _choice(self, choices: dict, current, key: str) -> QComboBox:
        """A combo box of *choices* (setting: text) that keeps the chosen setting under *key*."""
        box = QComboBox()
        for value, text in choices.items():
            box.addItem(text, value)
        box.setCurrentIndex(max(0, box.findData(current)))
        box.currentIndexChanged.connect(lambda: self.set_clock(key, box.currentData()))
        return box

    def _weather_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        self.place_label = QLabel()
        self.place_label.setWordWrap(True)
        grid.addWidget(QLabel("Place"), 0, 0)
        grid.addWidget(self.place_label, 0, 1, 1, 2)
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("City or town")
        self.search_text.returnPressed.connect(self.search_places)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_places)
        grid.addWidget(self.search_text, 1, 1)
        grid.addWidget(self.search_button, 1, 2)
        self.results = QComboBox()
        self.results.setEnabled(False)
        self.use_button = QPushButton("Use this place")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self.use_place)
        grid.addWidget(self.results, 2, 1)
        grid.addWidget(self.use_button, 2, 2)
        self.forget_button = QPushButton("No weather")
        self.forget_button.clicked.connect(lambda: self.set_place(None))
        grid.addWidget(self.forget_button, 3, 2)
        self.weather_status = QLabel()
        self.weather_status.setWordWrap(True)
        grid.addWidget(self.weather_status, 4, 0, 1, 3)
        grid.addWidget(hint_label(
            "The weather comes from <a href='https://open-meteo.com/'>Open-Meteo</a>, free and without an account. "
            "Search sends the name you type; then the place's coordinates go to it every 30 minutes, only while the "
            "Weather tile is on the screen. Nothing else about you is sent."), 5, 0, 1, 3)
        grid.setRowStretch(6, 1)
        self._show_place()
        return tab

    def _start_tab(self) -> QWidget:
        tab = QWidget()
        column = QVBoxLayout(tab)
        self.autostart = QCheckBox("Start with the desktop, minimized")
        self.autostart.setChecked(autostart.enabled(self.config_home))
        self.autostart.toggled.connect(lambda on: autostart.set_enabled(on, self.config_home))
        self.off_on_quit = QCheckBox("Switch the screen off when the app quits")
        self.off_on_quit.setChecked(self.settings.get("off_on_quit"))
        self.off_on_quit.toggled.connect(lambda on: self.settings.set("off_on_quit", on))
        column.addWidget(self.autostart)
        column.addWidget(self.off_on_quit)
        column.addWidget(hint_label("The screen shows the values while the app runs; minimized is enough. "
                                    "Otherwise it keeps the last picture."))
        column.addStretch(1)
        return tab

    # ----------------------------------------------------------------- values
    def shown_tiles(self) -> list[str]:
        return [k for k in self.settings.get("tiles").split(",") if k]

    def save_tiles(self) -> None:
        self.settings.set("tiles", ",".join(k for k, _ in render.TILES if self.tile_boxes[k].isChecked()))
        self.refresh(read=False)
        self.update_weather()                   # the weather tile may just have been switched on

    def set_interface(self, name: str) -> None:
        self.settings.set("interface", name)
        self.sensors.interface = name or None

    def picture_size(self) -> tuple[int, int]:
        """The upright picture: the screen's own size, turned for a landscape orientation."""
        w, h = self.model.width, self.model.height
        return (h, w) if render.ORIENTATIONS[self.settings.get("orientation")] % 180 else (w, h)

    def preview_size(self) -> tuple[int, int]:
        """The picture 1:1; a screen larger than PREVIEW_MAX (the 5" and 7") scaled down to fit."""
        w, h = self.picture_size()
        scale = min(1.0, PREVIEW_MAX / max(w, h))
        return round(w * scale), round(h * scale)

    def theme_of(self, trial: dict[str, str] | None = None) -> render.Theme:
        """The chosen theme with the chosen colors, or with what *trial* tries instead."""
        look = {key: self.settings.get(key) for key in LOOK} | (trial or {})
        theme = render.THEMES.get(look["theme"], render.THEMES[render.DEFAULT_THEME])
        return render.with_colours(theme, {key: look[f"colour_{key}"] for key in render.COLOURS})

    def clock_style(self) -> render.Clock:
        return render.Clock(self.settings.get("hours"), self.settings.get("zone"), self.settings.get("date"))

    def draw(self, theme: render.Theme, when: float | None = None) -> QImage:
        width, height = self.picture_size()
        return render.draw(self.reading, self.shown_tiles(), width, height, QColor(ACCENT),
                           title=self.settings.get("title"), clock=when, theme=theme, picture=self.picture,
                           weather=self.weather, place=self.place.name if self.place else "",
                           style=self.clock_style())

    def refresh(self, read: bool = True) -> None:
        if read or self.reading is None:
            self.reading = self.sensors.read()
            self._show_zone()                   # summer or winter time may just have begun
        self.image = image = self.draw(self.theme_of())
        size = self.preview_size()
        pixmap = QPixmap.fromImage(self.draw(self.theme_of(self.trial)) if self.trial else image)
        if (pixmap.width(), pixmap.height()) != size:
            pixmap = pixmap.scaled(*size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if (self.preview.width(), self.preview.height()) != size:
            self.preview.setFixedSize(*size)
            self.body.setDirection(QBoxLayout.Direction.TopToBottom if size[0] > size[1]
                                   else QBoxLayout.Direction.LeftToRight)
            self.adjustSize()                   # the window follows the picture's shape
        self.preview.setPixmap(pixmap)
        upright = render.for_screen(image, render.ORIENTATIONS[self.settings.get("orientation")])
        self.link.show(render.rgb565(upright), self.model.width, self.model.height)

    # ------------------------------------------------------------------- look
    def set_theme(self, name: str) -> None:
        self.settings.set("theme", name)
        self.end_trial()

    def try_look(self, key: str, value: str) -> None:
        """Shows *value* for the LOOK setting *key* in the preview; the screen keeps what is chosen."""
        self.trial = {key: value}
        self.refresh(read=False)

    def end_trial(self) -> None:
        self.trial = {}
        self.refresh(read=False)

    def choose_colour(self, key: str) -> None:
        setting = f"colour_{key}"
        dialog = QColorDialog(getattr(self.theme_of(), render.COLOURS[key]) or QColor(ACCENT), self)
        dialog.setWindowTitle(window_title(f"{COLOUR_NAMES[key]} colour"))
        dialog.currentColorChanged.connect(lambda colour: self.try_look(setting, colour.name()))
        if dialog.exec():
            self.set_colour(key, dialog.selectedColor().name())
        else:
            self.end_trial()

    def set_colour(self, key: str, value: str) -> None:
        """*value* "#rrggbb", or "" for the theme's own."""
        self.settings.set(f"colour_{key}", value)
        self._show_colours()
        self.end_trial()

    def clear_colours(self) -> None:
        for key in render.COLOURS:
            self.settings.set(f"colour_{key}", "")
        self._show_colours()
        self.end_trial()

    def _show_colours(self) -> None:
        """A swatch on each button whose color is the user's own."""
        own = False
        for key, button in self.colour_buttons.items():
            value = self.settings.get(f"colour_{key}")
            if value and QColor(value).isValid():
                swatch = QPixmap(14, 14)
                swatch.fill(QColor(value))
                button.setIcon(QIcon(swatch))
                own = True
            else:
                button.setIcon(QIcon())
        self.colours_clear.setEnabled(own)

    def set_title(self, text: str) -> None:
        self.settings.set("title", text)
        self.refresh(read=False)

    def choose_picture(self) -> None:
        start = self.settings.get("picture") or str(Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(self, window_title("Background"), start, PICTURES)
        if path:
            self.set_picture(path)

    def set_picture(self, path: str) -> None:
        if path and QImage(path).isNull():
            QMessageBox.warning(self, window_title("Background"), f"{path} is not a picture the app can read.")
            return
        self.settings.set("picture", path)
        self._load_picture()
        self.refresh(read=False)

    def _load_picture(self) -> None:
        path = self.settings.get("picture")
        image = QImage(path) if path else None
        self.picture = image if image is not None and not image.isNull() else None
        if not path:
            self.picture_label.setText("None: the theme's color")
        elif self.picture is None:
            self.picture_label.setText(f"{path} cannot be read (moved or removed?): the theme's colour for now")
        else:
            self.picture_label.setText(path)
        self.picture_clear.setEnabled(bool(path))

    # ------------------------------------------------------------------ clock
    def set_clock(self, key: str, value) -> None:
        self.settings.set(key, value)
        self._show_zone()
        self.refresh(read=False)

    def _show_zone(self, when: float | None = None) -> None:
        """The zone the system is in now, so the choices say what they show."""
        local = time.localtime(when)
        for n, value in enumerate(ZONES):
            if value:
                self.zone.setItemText(n, f"{ZONES[value]}: {render.zone_text(local, value)}")
        self.zone_hint.setText(
            f"The time is the system's, in its time zone ({local.tm_zone}, {render.offset(local)} now). Summer and "
            "winter time follow by themselves: the name and offset change with them.")

    # ------------------------------------------------------------------- save
    def save_picture(self) -> None:
        start = Path.home() / "Pictures" / time.strftime("bc250-usb-ips35-%Y%m%d-%H%M%S.png")
        path, _ = QFileDialog.getSaveFileName(self, window_title("Save picture"), str(start), "PNG image (*.png)")
        if path and self.image is not None and not self.image.save(path, "PNG"):
            QMessageBox.warning(self, window_title("Save picture"), f"{path} could not be written.")

    def report_text(self, when: float | None = None) -> str:
        name = self.settings.get("interface")
        return render.report(self.reading, when, self.weather, self.place.name if self.place else "",
                             network.label(name, self.net_root) if name else ALL_INTERFACES.lower(),
                             self.settings.get("title"))

    def save_report(self) -> None:
        text = self.report_text()
        start = Path.home() / time.strftime("bc250-usb-ips35-%Y%m%d-%H%M%S.txt")
        path, _ = QFileDialog.getSaveFileName(self, window_title("Save report"), str(start), "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, window_title("Save report"), f"{path} could not be written: {exc.strerror}.")

    # ---------------------------------------------------------------- weather
    def _show_place(self) -> None:
        self.place_label.setText(self.place.label if self.place else "None chosen: no weather, nothing is sent")
        self.forget_button.setEnabled(self.place is not None)

    def search_places(self) -> None:
        name = self.search_text.text().strip()
        if not name or not self.search_job.start(_job(weather.search, name, self.fetch)):
            return
        self.search_button.setEnabled(False)
        self.weather_status.setText(f"Looking for {name}…")

    def _search_done(self, result) -> None:
        self.search_button.setEnabled(True)
        if isinstance(result, weather.WeatherError):
            self.weather_status.setText(str(result))
            return
        self.places = result
        self.results.clear()
        self.results.addItems([p.label for p in self.places])
        self.results.setEnabled(bool(self.places))
        self.use_button.setEnabled(bool(self.places))
        self.weather_status.setText(f"{len(self.places)} found: choose one and Use this place." if self.places
                                    else "Nothing found by that name.")

    def use_place(self) -> None:
        if 0 <= self.results.currentIndex() < len(self.places):
            self.set_place(self.places[self.results.currentIndex()])
            if not self.tile_boxes["weather"].isChecked():
                self.tile_boxes["weather"].setChecked(True)     # chose a place: show it

    def set_place(self, place: weather.Place | None) -> None:
        self.place, self.weather = place, None
        self.settings.set("weather_place", place.to_json() if place else "")
        self._show_place()
        self.weather_status.setText("")
        self.refresh(read=False)
        self.update_weather()

    def update_weather(self) -> None:
        """Only with a place and the weather tile on the screen: otherwise nothing goes over the network."""
        if self.place is None or "weather" not in self.shown_tiles():
            return
        self.weather_job.start(_job(weather.current, self.place, self.fetch))

    def _weather_done(self, result) -> None:
        if isinstance(result, weather.WeatherError):
            self.weather_status.setText(f"{result} The screen keeps the last weather it had.")
            return
        self.weather = result
        wind = f", wind {result.wind_kmh:.0f} km/h" if result.wind_kmh is not None else ""
        humidity = f", humidity {result.humidity} %" if result.humidity is not None else ""
        self.weather_status.setText(f"Now: {result.temperature:.0f} °C, {result.description.lower()}{wind}{humidity}.")
        self.refresh(read=False)

    # --------------------------------------------------------------- settings
    def set_brightness(self, value: int) -> None:
        self.brightness_label.setText(f"{value} %")
        self.settings.set("brightness", value)
        self.link.set_brightness(value)

    def set_orientation(self, name: str) -> None:
        self.settings.set("orientation", name)
        self._show_size()
        self.refresh(read=False)

    def _show_size(self) -> None:
        """As the screen is seen: 480×320 lying down."""
        width, height = self.picture_size()
        self.size_box.set_value(f"{width}×{height}" if self.state.kind == "connected" else "—")

    def set_power(self, off: bool) -> None:
        self.power_button.setText("Screen on" if off else "Screen off")
        self.link.set_power(not off)

    # ------------------------------------------------------------------ state
    def show_state(self, state: State) -> None:
        self.state = state
        texts = {"searching": ("No screen found", "neutral",
                               "No USB IPS screen (USB ID 1a86:5722) is plugged in. Plug it in; the app finds it "
                               "by itself."),
                 "no-access": ("No access", "warn", "Allow access gives your user the screen's port."),
                 "resetting": ("Starting the screen", "info", "The screen restarts once when the app connects, "
                                                             "so it starts from a clean state."),
                 "connected": ("Connected", "ok", ""),
                 "error": ("Error", "bad", state.message)}
        text, kind, tooltip = texts[state.kind]
        self.badge.set_status(text, kind, tooltip)
        self.access_box.setVisible(state.kind == "no-access")
        if state.model is not None and state.model != self.model:
            self.model = state.model
            self.refresh(read=False)
        connected = state.kind == "connected"
        if connected and not tooltip:
            self.badge.setToolTip("Connected. Nothing sent yet.")
        self.model_box.set_value(self.model.short if connected else "—", self.model.name if connected else "")
        self.port_box.set_value(state.found.port.name if state.found else "—")
        self._show_size()
        self.power_button.setEnabled(connected)

    def show_sent(self, size: int) -> None:
        """How much the last update sent, in the state's tooltip: a few KB a second, a whole picture at start."""
        if self.state.kind == "connected":
            self.badge.setToolTip(f"Connected. The last update sent {size / 1000:.1f} KB.")

    def allow_access(self) -> None:
        result = self.run_root(access.command(["install"]))
        problem = access.answer(result.code, result.out)
        if problem:
            QMessageBox.warning(self, window_title("Access to the screen"), problem)

    # ------------------------------------------------------------------- quit
    def shut_down(self) -> None:
        self.timer.stop()
        self.weather_timer.stop()
        self.weather_job.stop(1000)
        self.search_job.stop(1000)
        self.link.stop(screen_off=self.settings.get("off_on_quit"))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        save_geometry(self, self.settings.qsettings)
        super().closeEvent(event)
