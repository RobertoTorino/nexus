# SPDX-License-Identifier: GPL-3.0-or-later
"""The window with a fake link and fixed readings: the states, the settings it hands the link, the frame it sends
(size, orientation and position), a look tried in the preview only, the clock, saving and Allow access."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from bc250_core.sensors import Reading
from usb_ips35 import main_window, render, runner, screen, weather
from usb_ips35.link import State
from conftest import interfaces, wait_until

FOUND = screen.Found(Path("/dev/ttyACM0"), "UsbMonitor", "USB35INCHIPSV2")
FIVE_INCH = screen.MODELS[bytes([2] * 6)]


class FakeLink(QObject):
    state_changed = pyqtSignal(object)
    sent = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.frames: list[tuple[bytes, int, int]] = []
        self.brightness: list[int] = []
        self.power: list[bool] = []
        self.started = False
        self.stopped: bool | None = None

    def start(self):
        self.started = True

    def show(self, frame, width, height):
        self.frames.append((frame, width, height))

    def set_brightness(self, percent):
        self.brightness.append(percent)

    def set_power(self, on):
        self.power.append(on)

    def stop(self, screen_off=True):
        self.stopped = screen_off


class FakeSensors:
    interface: str | None = None

    def read(self) -> Reading:
        return Reading(cpu_load=10.0, gpu_mhz=1500, cpu_temp=55.0, gpu_temp=60.0)

    def interfaces(self) -> list[str]:
        return ["enp4s0", "wlan0"]


BERLIN = weather.Place("Berlin", "State of Berlin", "Germany", 52.52, 13.41)


class FakeOpenMeteo:
    """Open-Meteo's answers, as recorded 22-10-2026 (trimmed), and the requests it got."""

    def __init__(self, fail: bool = False):
        self.requests: list[tuple[str, dict]] = []
        self.fail = fail

    def __call__(self, url: str, params: dict) -> dict:
        self.requests.append((url, params))
        if self.fail:
            raise weather.WeatherError("Open-Meteo cannot be reached: check the network.")
        if url == weather.GEOCODE_URL:
            return {"results": [{"name": "Berlin", "admin1": "State of Berlin", "country": "Germany",
                                 "latitude": 52.52, "longitude": 13.41}]}
        return {"current": {"temperature_2m": 11.8, "weather_code": 2, "wind_speed_10m": 10.7,
                            "relative_humidity_2m": 64}}


@pytest.fixture
def make(qapp, tmp_path):
    made = []

    def make(run_root=None, fetch=None):
        link = FakeLink()
        window = main_window.MainWindow(sensors=FakeSensors(), link=link, config_home=tmp_path / "config",
                                        run_root=run_root or (lambda argv: runner.Result(0, '{"error": ""}')),
                                        fetch=fetch or FakeOpenMeteo(), net_root=interfaces(tmp_path / "sys"))
        window.timer.stop()
        made.append(window)
        return window, link

    yield make
    for window in made:
        window.close()


def test_starts_the_link_and_sends_a_frame(make):
    window, link = make()
    assert link.started and link.brightness == [50]
    frame, width, height = link.frames[-1]
    assert (width, height) == (320, 480) and len(frame) == 320 * 480 * 2
    assert window.badge.text() == "No screen found" and window.access_box.isHidden()


def test_states(make):
    window, link = make()
    link.state_changed.emit(State("no-access", FOUND))
    assert window.badge.text() == "No access" and not window.access_box.isHidden()
    assert not window.power_button.isEnabled()
    link.state_changed.emit(State("resetting", FOUND))
    assert window.badge.text() == "Starting the screen" and window.access_box.isHidden()
    link.state_changed.emit(State("connected", FOUND, screen.TURING_35))
    assert window.badge.text() == "Connected" and window.power_button.isEnabled()
    assert window.model_box.value.text() == 'Turing 3.5"' and window.model_box.toolTip() == screen.TURING_35.name
    assert window.port_box.value.text() == "ttyACM0" and window.size_box.value.text() == "320×480"
    link.state_changed.emit(State("error", message="The screen stopped answering"))
    assert window.badge.text() == "Error" and window.model_box.value.text() == "—"


def test_the_frame_is_the_picture_as_drawn(make):
    window, link = make()
    upright = render.rgb565(render.for_screen(
        render.draw(window.reading, window.shown_tiles(), 320, 480, render.QColor(main_window.ACCENT)), 0))
    assert window.settings.get("title") == render.TITLE and window.settings.get("theme") == render.DEFAULT_THEME
    assert link.frames[-1][0] == upright


def test_a_larger_screen_gets_frames_of_its_size(make):
    window, link = make()
    link.state_changed.emit(State("connected", FOUND, FIVE_INCH))
    frame, width, height = link.frames[-1]
    assert (width, height) == (480, 800) and len(frame) == 480 * 800 * 2


def test_landscape_is_turned_for_the_screen(make):
    window, link = make()
    link.state_changed.emit(State("connected", FOUND, screen.TURING_35))
    assert (window.preview.width(), window.preview.height()) == (320, 480)          # 1:1
    window.orientation.setCurrentText("Landscape")
    assert window.picture_size() == (480, 320) and window.size_box.value.text() == "480×320"
    frame, width, height = link.frames[-1]
    assert (width, height) == (320, 480) and len(frame) == 320 * 480 * 2
    assert (window.preview.width(), window.preview.height()) == (480, 320)
    assert (window.preview.pixmap().width(), window.preview.pixmap().height()) == (480, 320)
    assert window.body.direction() == main_window.QBoxLayout.Direction.TopToBottom    # the tabs under it
    window.orientation.setCurrentText("Portrait")
    assert window.body.direction() == main_window.QBoxLayout.Direction.LeftToRight


def test_last_update_in_the_states_tooltip(make):
    window, link = make()
    link.state_changed.emit(State("connected", FOUND, screen.TURING_35))
    link.sent.emit(3200)
    assert window.badge.toolTip() == "Connected. The last update sent 3.2 KB."


def test_a_large_screen_is_previewed_smaller(make):
    window, link = make()
    link.state_changed.emit(State("connected", FOUND, screen.MODELS[bytes([3] * 6)]))      # the 7", 600×1024
    assert (window.preview.width(), window.preview.height()) == (281, 480)
    assert window.size_box.value.text() == "600×1024"


def test_settings_go_to_the_link_and_are_kept(make):
    window, link = make()
    window.brightness.setValue(80)
    window.power_button.setChecked(True)
    window.tile_boxes["disk"].setChecked(True)
    window.tile_boxes["cpu"].setChecked(False)
    assert link.brightness[-1] == 80 and link.power == [False] and window.power_button.text() == "Screen on"
    window2, link2 = make()
    assert window2.brightness.value() == 80 and link2.brightness == [80]
    assert window2.shown_tiles() == ["gpu", "vram", "ram", "fan", "net", "disk"]


def test_autostart_and_quit(make, tmp_path):
    window, link = make()
    window.autostart.setChecked(True)
    assert (tmp_path / "config/autostart/bc250-usb-ips35.desktop").is_file()
    window.off_on_quit.setChecked(False)
    window.shut_down()
    assert link.stopped is False


def test_allow_access_runs_the_helper_as_root(make, monkeypatch):
    calls, warnings = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window, link = make(run_root=lambda argv: calls.append(argv) or runner.Result(126, ""))
    link.state_changed.emit(State("no-access", FOUND))
    window.access_button.click()
    assert calls[0][0] == "pkexec" and calls[0][-2:][1] == "install"
    assert warnings and "canceled" in warnings[0]


def test_look(make, tmp_path):
    window, link = make()
    before = link.frames[-1][0]
    window.theme.setCurrentText("Light")
    assert link.frames[-1][0] != before and window.settings.get("theme") == "Light"
    window.title.setText("My board")
    assert window.settings.get("title") == "My board"
    picture = tmp_path / "back.png"
    image = render.QImage(64, 64, render.QImage.Format.Format_RGB32)
    image.fill(render.QColor("darkgreen"))
    image.save(str(picture))
    window.set_picture(str(picture))
    assert window.picture is not None and window.picture_clear.isEnabled()
    window2, _ = make()
    assert window2.theme.currentText() == "Light" and window2.title.text() == "My board"
    assert window2.picture is not None
    picture.unlink()                                                  # moved away: the theme's color, said so
    window3, _ = make()
    assert window3.picture is None and "cannot be read" in window3.picture_label.text()
    window3.set_picture("")
    assert window3.settings.get("picture") == "" and not window3.picture_clear.isEnabled()


def test_a_file_that_is_no_picture_is_refused(make, tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window, _ = make()
    (tmp_path / "notes.png").write_text("not a picture")
    window.set_picture(str(tmp_path / "notes.png"))
    assert warnings and window.settings.get("picture") == ""


def test_network_interface(make):
    window, _ = make()
    assert [window.interface.itemText(i) for i in range(window.interface.count())] == \
        [main_window.ALL_INTERFACES, "enp4s0 (Ethernet)", "wlan0 (Wi-Fi)"]
    window.interface.setCurrentText("wlan0 (Wi-Fi)")
    assert window.sensors.interface == "wlan0" and window.settings.get("interface") == "wlan0"
    window2, _ = make()
    assert window2.interface.currentText() == "wlan0 (Wi-Fi)" and window2.sensors.interface == "wlan0"
    window2.interface.setCurrentText(main_window.ALL_INTERFACES)
    assert window2.sensors.interface is None and window2.settings.get("interface") == ""


def test_no_weather_and_nothing_sent_without_a_place(make, qapp):
    fetch = FakeOpenMeteo()
    window, _ = make(fetch=fetch)
    window.tile_boxes["weather"].setChecked(True)
    qapp.processEvents()
    assert fetch.requests == [] and "None chosen" in window.place_label.text()


def test_weather_search_choose_and_show(make, qapp):
    fetch = FakeOpenMeteo()
    window, link = make(fetch=fetch)
    window.search_text.setText("Berlin")
    window.search_places()
    assert wait_until(qapp, lambda: window.use_button.isEnabled())
    assert fetch.requests[0] == (weather.GEOCODE_URL, {"name": "Berlin", "count": weather.RESULTS, "language": "en",
                                                       "format": "json"})
    window.use_place()
    assert window.tile_boxes["weather"].isChecked() and window.place == BERLIN
    assert wait_until(qapp, lambda: window.weather is not None)
    url, params = fetch.requests[-1]
    assert url == weather.FORECAST_URL and (params["latitude"], params["longitude"]) == (52.52, 13.41)
    assert window.weather_status.text() == "Now: 12 °C, partly cloudy, wind 11 km/h, humidity 64 %."
    window2, _ = make(fetch=fetch)
    assert window2.place == BERLIN
    window2.set_place(None)
    requests = len(fetch.requests)
    window2.update_weather()
    assert len(fetch.requests) == requests and window2.settings.get("weather_place") == ""


def test_weather_tile_off_sends_nothing(make, qapp):
    fetch = FakeOpenMeteo()
    window, _ = make(fetch=fetch)
    window.set_place(BERLIN)                                          # the tile is not on the screen
    qapp.processEvents()
    assert fetch.requests == []


def test_weather_failure_keeps_the_last(make, qapp):
    fetch = FakeOpenMeteo(fail=True)
    window, _ = make(fetch=fetch)
    window.tile_boxes["weather"].setChecked(True)
    window.set_place(BERLIN)
    assert wait_until(qapp, lambda: "cannot be reached" in window.weather_status.text())
    assert window.weather is None


def test_a_chosen_interface_that_is_gone_is_kept(make):
    window, _ = make()
    window.interface.setCurrentText("wlan0 (Wi-Fi)")
    window.settings.set("interface", "usb0")
    window2, _ = make()
    assert window2.interface.currentText() == "usb0" and window2.sensors.interface == "usb0"


def test_a_theme_is_tried_in_the_preview_only(make):
    window, link = make()
    frames, screen_frame = len(link.frames), link.frames[-1][0]
    chosen = window.preview.pixmap().toImage()
    window.theme.highlighted.emit(window.theme.findText("Ember"))
    assert window.preview.pixmap().toImage() != chosen
    assert all(frame == screen_frame for frame, _, _ in link.frames[frames:])        # the screen keeps Dark
    assert window.settings.get("theme") == render.DEFAULT_THEME
    window.theme.popup_closed.emit()                                     # closed without choosing
    assert window.preview.pixmap().toImage() == chosen and window.trial == {}
    window.theme.setCurrentText("Ember")
    assert window.settings.get("theme") == "Ember" and link.frames[-1][0] != screen_frame


def test_own_colours(make):
    window, link = make()
    before = link.frames[-1][0]
    assert not window.colours_clear.isEnabled() and window.colour_buttons["text"].icon().isNull()
    window.try_look("colour_tiles", "#00ff00")
    assert link.frames[-1][0] == before and window.settings.get("colour_tiles") == ""
    window.set_colour("tiles", "#00ff00")
    assert window.settings.get("colour_tiles") == "#00ff00" and link.frames[-1][0] != before
    assert window.theme_of().surface == QColor("#00ff00") and window.trial == {}
    assert window.colours_clear.isEnabled() and not window.colour_buttons["tiles"].icon().isNull()
    window2, _ = make()
    assert window2.theme_of().surface == QColor("#00ff00")
    window2.clear_colours()
    assert window2.settings.get("colour_tiles") == "" and not window2.colours_clear.isEnabled()


def test_clock(make):
    window, link = make()
    assert window.clock_style() == render.Clock()
    window.hours.setCurrentIndex(window.hours.findData(12))
    window.zone.setCurrentIndex(window.zone.findData("name"))
    window.date.setCurrentIndex(window.date.findData("dmy"))
    assert window.clock_style() == render.Clock(12, "name", "dmy")
    assert window.zone.currentText().startswith("Name: ") and "time zone" in window.zone_hint.text()
    window2, _ = make()
    assert window2.clock_style() == render.Clock(12, "name", "dmy") and window2.hours.currentText() == "12-hour (AM/PM)"


def test_save_picture_and_report(make, tmp_path, monkeypatch):
    window, _ = make()
    window.interface.setCurrentText("enp4s0 (Ethernet)")
    picture, report = tmp_path / "screen.png", tmp_path / "values.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(picture), ""))
    window.save_picture()
    saved = render.QImage(str(picture))
    assert (saved.width(), saved.height()) == (320, 480)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(report), ""))
    window.save_report()
    text = report.read_text(encoding="utf-8")
    assert text.startswith(render.TITLE + "\n") and "CPU                    10 %" in text
    assert "Network (enp4s0 (Ethernet))" in text
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))       # canceled
    window.save_report()
