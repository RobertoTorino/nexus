# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py) on a fake screen and fake values: it fits the handheld's screen, every card's rows
step their setting with A, LB and RB, the picture goes to the screen at its own size and turned, the weather is found
and fetched only when asked for, the picture and the report are saved without a dialog, and View asks for a second
press while the screen is connected; the version and the icons are where the checks expect them."""

from __future__ import annotations

import json
import re

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QImage

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import EXIT, INFO as INFO_ITEM, BACK
from smart_screen import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, render, screen, weather
from smart_screen.link import State
from smart_screen.main_window import MainWindow
from smart_screen.values import Reading

FOUND = screen.Found("COM3", r"USB\VID_1A86&PID_5722\SERIAL")


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


class FakeValues:
    def __init__(self):
        self.interface = None
        self.closed = False

    def read(self):
        return Reading(cpu_load=12, cpu_mhz=2500, cpu_temp=50, gpu_load=20, gpu_temp=51, watts=14, ram=(6e9, 16e9),
                       battery=(82, False), net=(1000.0, 10.0), disk=(0.0, 0.0))

    def interfaces(self):
        return ["Ethernet adapter", "Wi-Fi adapter"]

    def close(self):
        self.closed = True


class FakeLink(QObject):
    state_changed = pyqtSignal(object)
    sent = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.frames: list[tuple[bytes, int, int]] = []
        self.brightness: list[int] = []
        self.power: list[bool] = []
        self.stopped: list[bool] = []

    def start(self):
        pass

    def show(self, frame, width, height):
        self.frames.append((frame, width, height))

    def set_brightness(self, percent):
        self.brightness.append(percent)

    def set_power(self, on):
        self.power.append(on)

    def stop(self, screen_off=True):
        self.stopped.append(screen_off)


def make(qapp, tmp_path, fetch=None, **kwargs):
    portable.scale((1280, 720))
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), values=FakeValues(),
                        link=FakeLink(), fetch=fetch or (lambda url, params: {}), family="ROG Xbox Ally X",
                        startup=tmp_path / "Startup", roots=lambda: [], user_home=tmp_path / "home",
                        pictures=tmp_path / "Pictures", documents=tmp_path / "Documents", **kwargs)
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.start()
    return window


def into(window, card, row: str) -> None:
    """The focus on *row* of *card*'s pane, as the d-pad puts it there."""
    card.setFocus()
    pane = next(p for p, c in window.cards.items() if c is card)
    assert pane.list.focus(row) and pane.list.focused() == row


def act(window, monkeypatch, action: str) -> None:
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action(action)


def connect(window) -> None:
    window.link.state_changed.emit(State("connected", FOUND, screen.TURING_35))


def test_the_window_opens_with_the_suites_header(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("A", "Open"), INFO_ITEM, EXIT]
    assert window.screen_card.text.text() == "No screen found: plug it in"
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_the_picture_goes_to_the_screen_at_its_size_and_turned(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    connect(window)
    frame, width, height = window.link.frames[-1]
    assert (width, height) == (320, 480) and len(frame) == 320 * 480 * 2
    assert window.screen_card.text.text() == 'Turing 3.5" on COM3'
    into(window, window.screen_card, "orientation")
    act(window, monkeypatch, "accept")
    assert window.settings.get("orientation") == "Landscape"
    assert (window.image.width(), window.image.height()) == (480, 320)       # drawn lying down,
    assert window.link.frames[-1][1:] == (320, 480)                          # sent in the screen's own portrait
    act(window, monkeypatch, "previous")
    assert window.settings.get("orientation") == "Portrait"
    window.close()


def test_the_serial_number_is_never_shown_or_logged(qapp, tmp_path, caplog):
    window = make(qapp, tmp_path)
    connect(window)
    window.link.state_changed.emit(State("in-use", FOUND))
    texts = [window.screen_card.text.text(), window.screen_pane.summary.text(), caplog.text]
    assert all("SERIAL" not in text for text in texts)
    assert "UsbMonitor" in window.screen_pane.summary.text() and window.screen_card.text.text() == \
        "In use by another program"
    window.close()


def test_brightness_steps_and_stops_at_its_ends(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.screen_card, "brightness")
    assert window.legend.items[:3] == [("A", "Brighter"), ("LB", "Darker"), ("RB", "Brighter")]
    act(window, monkeypatch, "accept")
    act(window, monkeypatch, "next")
    assert window.settings.get("brightness") == 70 and window.link.brightness[-1] == 70
    for _ in range(5):
        act(window, monkeypatch, "next")
    assert window.settings.get("brightness") == 100
    assert window.screen_pane.status.text() == "The brightest already: LB makes it darker."
    act(window, monkeypatch, "previous")
    assert window.link.brightness[-1] == 90
    window.close()


def test_the_backlight_switches_off_and_on(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.screen_card, "backlight")
    act(window, monkeypatch, "accept")
    assert window.link.power == [False] and window.legend.items[0] == ("A", "Switch on")
    act(window, monkeypatch, "accept")
    assert window.link.power == [False, True]
    window.close()


def test_the_picture_and_the_report_are_saved_without_a_dialog(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.screen_card, "picture")
    act(window, monkeypatch, "accept")
    saved = list((tmp_path / "Pictures").glob(f"{APP_NAME} *.png"))
    assert len(saved) == 1 and QImage(str(saved[0])).size() == window.image.size()
    assert window.screen_pane.status.text().startswith("Saved: ")
    into(window, window.screen_card, "report")
    act(window, monkeypatch, "accept")
    report = next((tmp_path / "Documents").glob(f"{APP_NAME} *.txt")).read_text(encoding="utf-8")
    assert report.startswith("ROG Xbox Ally X\n") and "Battery                82 % · on battery" in report
    window.close()


def test_a_value_is_put_on_and_taken_off(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.values_card, "tile:disk")
    assert window.legend.items[0] == ("A", "Put on")
    act(window, monkeypatch, "accept")
    assert "disk" in window.shown_tiles() and window.values_card.text.text() == "7 on the screen"
    act(window, monkeypatch, "accept")
    assert "disk" not in window.shown_tiles()
    into(window, window.values_card, "interface")
    act(window, monkeypatch, "accept")
    assert window.settings.get("interface") == "Ethernet adapter" == window.values.interface
    act(window, monkeypatch, "previous")
    assert window.settings.get("interface") == "" and window.values.interface is None
    window.close()


def test_the_look_steps_and_the_theme_comes_back_with_x(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.look_card, "theme")
    act(window, monkeypatch, "accept")
    assert window.settings.get("theme") == "Light"
    into(window, window.look_card, "color:accent")
    act(window, monkeypatch, "next")
    assert window.settings.get("color_accent") == "#ffffff"
    assert window.theme().accent == QColor("#ffffff")
    act(window, monkeypatch, "x")
    assert window.settings.get("color_accent") == ""
    assert window.legend.items[:4] == [("A", "Next"), ("LB", "Before"), ("RB", "Next"), ("X", "Theme's")]
    window.close()


def test_the_header_text_on_its_own_page(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    assert window.title() == "ROG Xbox Ally X"                        # the family until one is kept
    into(window, window.look_card, "title")
    act(window, monkeypatch, "accept")
    assert window.panes.currentWidget() is window.field_pane
    assert window.field_pane.field.text() == "ROG Xbox Ally X"
    window.field_pane.field.setText("")
    act(window, monkeypatch, "accept")
    assert window.title() == "" and window.panes.currentWidget() is window.look_pane
    assert window.look_pane.list.focused() == "title"
    window.close()
    again = make(qapp, tmp_path)
    assert again.title() == ""                                       # kept empty: only the time
    again.close()


def test_a_background_picture_is_picked_with_the_controller(qapp, tmp_path, monkeypatch):
    folder = tmp_path / "home" / "Pictures"
    folder.mkdir(parents=True)
    picture = QImage(20, 10, QImage.Format.Format_RGB32)
    picture.fill(QColor(0, 200, 0))
    picture.save(str(folder / "green.png"))
    (folder / "notes.txt").write_text("not a picture")
    monkeypatch.setattr("bc250_core.browse.places", lambda home, roots: [folder])
    window = make(qapp, tmp_path)
    into(window, window.look_card, "picture")
    act(window, monkeypatch, "accept")
    assert window.panes.currentWidget() is window.browse_pane
    rows = list(window.browse_pane.list.pills)
    assert rows == [f"dir:{folder}"]
    window.browse_pane.list.picked.emit(f"dir:{folder}")
    assert [key for key in window.browse_pane.list.pills] == ["up", f"file:{folder / 'green.png'}"]
    window.browse_pane.list.picked.emit(f"file:{folder / 'green.png'}")
    assert window.settings.get("picture") == str(folder / "green.png") and window.picture is not None
    assert window.panes.currentWidget() is window.look_pane
    assert window.image.pixelColor(1, 479) == QColor(0, 200, 0)
    act(window, monkeypatch, "x")
    assert window.settings.get("picture") == "" and window.picture is None
    window.close()


def test_the_weather_is_found_used_and_fetched_only_when_shown(qapp, tmp_path, monkeypatch):
    asked = []

    def fetch(url, params):
        asked.append(url)
        if url == weather.GEOCODE_URL:
            return {"results": [{"name": "Berlin", "latitude": 52.5, "longitude": 13.4, "country": "Germany"}]}
        return {"current": {"temperature_2m": 11.8, "weather_code": 2, "is_day": 1}}

    window = make(qapp, tmp_path, fetch=fetch)
    assert asked == []                                              # no place: nothing sent
    into(window, window.weather_card, "place")
    act(window, monkeypatch, "accept")
    window.field_pane.field.setText("Berlin")
    act(window, monkeypatch, "accept")
    from conftest import wait_until
    assert wait_until(qapp, lambda: "found:0" in window.weather_pane.list.pills)
    window.weather_pane.list.picked.emit("found:0")
    assert window.place.name == "Berlin" and "weather" in window.shown_tiles()
    assert wait_until(qapp, lambda: window.weather is not None)
    assert asked == [weather.GEOCODE_URL, weather.FORECAST_URL]
    assert window.weather_pane.summary.text() == "Now: 12 °C, partly cloudy."
    assert json.loads(window.settings.get("weather_place"))["name"] == "Berlin"
    window.weather_pane.list.picked.emit("forget")
    assert window.place is None and window.weather_card.text.text() == "No place: no weather"
    window.close()


def test_start_with_windows_needs_the_installed_app(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.start_card, "autostart")
    act(window, monkeypatch, "accept")
    assert "install it from the portal" in window.start_pane.status.text()
    assert not (tmp_path / "Startup").exists()
    window.close()
    made = []
    program = tmp_path / "app" / f"{EXE_NAME}.exe"
    monkeypatch.setattr("bc250_core.platform.make_shortcut",
                        lambda link, *args, **kwargs: (made.append(link), link.parent.mkdir(parents=True),
                                                       link.write_text("lnk")))
    window = make(qapp, tmp_path, program=program)
    into(window, window.start_card, "autostart")
    act(window, monkeypatch, "accept")
    assert made == [tmp_path / "Startup" / f"{APP_NAME}.lnk"] and window.start_card.text.text() == "Starts with Windows"
    window.close()


def test_the_log_is_read_in_the_pane(qapp, tmp_path, monkeypatch):
    log = tmp_path / "smart.log"
    log.write_text("02-11-2026 01:57:59 INFO Connected.\n", encoding="utf-8")
    window = make(qapp, tmp_path, log_path=log)
    into(window, window.start_card, "log")
    act(window, monkeypatch, "accept")
    assert window.start_pane.viewing and "Connected." in window.start_pane.view.toPlainText()
    act(window, monkeypatch, "back")
    assert not window.start_pane.viewing
    window.close()


def test_b_goes_back_and_view_asks_while_connected(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    into(window, window.clock_card, "date")
    assert BACK in window.legend.items
    act(window, monkeypatch, "back")
    assert window.focusWidget() is window.clock_card
    connect(window)
    act(window, monkeypatch, "view")
    assert closed == [] and window.legend.items == [("⧉", "Press again to exit")]
    act(window, monkeypatch, "view")
    assert closed == [True]


def test_closing_ends_the_link_and_darkens_the_screen_when_so_set(qapp, tmp_path):
    window = make(qapp, tmp_path)
    link, reader = window.link, window.values
    window.close()
    assert link.stopped == [True] and reader.closed
    window.shut_down()                                              # once
    assert link.stopped == [True]
    window = make(qapp, tmp_path)
    window.settings.set("off_on_quit", False)
    window.close()
    assert window.link.stopped == [False]


def test_the_clock_steps(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    into(window, window.clock_card, "zone")
    act(window, monkeypatch, "accept")
    assert window.settings.get("zone") == "offset"
    assert re.fullmatch(r"Time zone: Offset from UTC \(UTC[+-]\d+(:\d\d)? now\)",
                        window.clock_pane.list.pills["zone"].label.text())
    into(window, window.clock_card, "hours")
    act(window, monkeypatch, "accept")
    assert window.settings.get("hours") == 12 and window.clock_card.text.text() == "12-hour, no date"
    window.close()


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
    assert render.DEFAULT_TILES and set(render.DEFAULT_TILES) <= {key for key, _ in render.TILES}


def test_the_preview_is_as_large_as_the_room_beside_the_panes(qapp, tmp_path, monkeypatch):
    """Standing, it is as high as the body and two thirds as wide; lying down, at most PREVIEW_WIDEST wide, so the
    panes keep their room (owner, 02-11-2026: the fixed square left a standing picture small)."""
    from smart_screen.main_window import PREVIEW_WIDEST
    window = make(qapp, tmp_path)
    qapp.processEvents()
    preview = window.preview
    assert preview.height() >= window.panes.height() - 2
    assert preview.width() == min(portable.px(PREVIEW_WIDEST), round(preview.height() * 2 / 3))
    standing = preview.width()
    into(window, window.screen_card, "orientation")
    act(window, monkeypatch, "accept")
    qapp.processEvents()
    assert preview.width() == min(portable.px(PREVIEW_WIDEST), round(preview.height() * 3 / 2)) >= standing
    assert window.panes.width() > preview.width() * 2 / 3
    assert window.minimumSizeHint().height() <= 720
    window.close()
