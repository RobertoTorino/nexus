# SPDX-License-Identifier: GPL-3.0-or-later
"""The tiles' texts, the clock, the user's colors, the weather's icon, the report, the picture's size and turn, and
the screen's pixel format (the BC250 app's tests, with the handheld's values)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QColor, QImage

from smart_screen import render, weather
from smart_screen.values import Reading

ALLY = Reading(cpu_load=12.4, cpu_mhz=3200, cpu_temp=72.1, gpu_load=45.0, gpu_temp=91.0, watts=18,
               ram=(5_000_000_000, 10_000_000_000), battery=(82, False), net=(1_500_000.0, 50_000.0),
               disk=(0.0, 2_000.0))
AMBER = QColor("#f5a524")


def test_tiles_in_the_screens_order():
    tiles = render.tiles(ALLY, ["net", "cpu", "gpu"])
    assert [t.caption for t in tiles] == ["CPU", "GPU", "Network"]
    cpu, gpu, net = tiles
    assert (cpu.value, cpu.detail, cpu.fraction, cpu.alert) == ("12 %", "3200 MHz · 72 °C", 0.124, None)
    assert (gpu.value, gpu.detail, gpu.fraction, gpu.alert) == ("45 %", "91 °C", 0.45, render.RED)
    assert (net.value, net.detail) == ("↓ 1.5 MB/s", "↑ 50.0 KB/s")


def test_every_tile_with_missing_values():
    tiles = render.tiles(Reading(), [k for k, _ in render.TILES])
    assert len(tiles) == len(render.TILES)
    assert all(t.value == render.DASH and t.fraction is None and t.alert is None for t in tiles)


def test_power_memory_and_battery():
    power, ram, battery = render.tiles(ALLY, ["power", "ram", "battery"])
    assert (power.value, power.detail) == ("18 W", "the chip")
    assert (ram.value, ram.fraction) == ("5.0 / 10.0 GB", 0.5)
    assert (battery.value, battery.detail, battery.fraction, battery.alert) == ("82 %", "on battery", 0.82, None)


@pytest.mark.parametrize("state, alert", [((20, False), render.ORANGE), ((10, False), render.RED),
                                          ((5, True), None), ((21, False), None)])
def test_a_battery_running_low_turns_orange_then_red(state, alert):
    assert render.tiles(Reading(battery=state), ["battery"])[0].alert == alert


def test_the_default_header_is_the_handhelds_family():
    assert render.default_title("ROG Xbox Ally X") == "ROG Xbox Ally X"
    assert render.default_title("Default string") == render.TITLE == render.default_title("")


def test_draw_and_turn(qapp):
    image = render.draw(ALLY, render.DEFAULT_TILES, 480, 320, AMBER, clock=0)
    assert (image.width(), image.height()) == (480, 320)
    turned = render.for_screen(image, 90)
    assert (turned.width(), turned.height()) == (320, 480)
    assert render.for_screen(image, 0) is image
    assert len(render.rgb565(turned)) == 320 * 480 * 2


def test_rgb565_little_endian(qapp):
    image = QImage(3, 1, QImage.Format.Format_RGB32)
    for x, color in enumerate(("red", "lime", "blue")):
        image.setPixelColor(x, 0, QColor(color))
    assert render.rgb565(image) == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])


def test_rgb565_of_an_odd_width_has_no_padding(qapp):
    image = QImage(3, 2, QImage.Format.Format_RGB32)               # 6 bytes a row, padded to 8 by Qt
    image.fill(QColor("white"))
    assert render.rgb565(image) == b"\xff\xff" * 6


def test_temperature_tiles():
    cpu, gpu = render.tiles(ALLY, ["gpu_temp", "cpu_temp"])
    assert (cpu.caption, cpu.value, cpu.fraction, cpu.alert) == ("CPU temp", "72 °C", 0.721, None)
    assert (gpu.caption, gpu.value, gpu.alert) == ("GPU temp", "91 °C", render.RED)
    assert render.tiles(Reading(cpu_temp=85.0), ["cpu_temp"])[0].alert == render.ORANGE


def test_weather_tile():
    sunny = weather.Weather(21.6, 0)
    assert render.tiles(ALLY, ["weather"], sunny, "Berlin")[0] == render.Tile("Berlin", "22 °C", "Clear sky",
                                                                              icon="clear")
    night = render.tiles(ALLY, ["weather"], weather.Weather(9.0, 61, is_day=False), "Berlin")[0]
    assert (night.icon, night.night) == ("rain", True)
    assert render.tiles(ALLY, ["weather"])[0] == render.Tile("Weather", render.DASH, "choose a place")


@pytest.mark.parametrize("code", [0, 2, 3, 45, 61, 71, 95])
@pytest.mark.parametrize("is_day", [True, False])
def test_every_weather_icon_is_drawn(qapp, code, is_day):
    now = weather.Weather(12.0, code, is_day=is_day)
    plain = render.draw(ALLY, ["weather"], 320, 480, AMBER, weather=weather.Weather(12.0, 1000), clock=0)
    image = render.draw(ALLY, ["weather"], 320, 480, AMBER, weather=now, clock=0)
    assert now.icon and image != plain                                # 1000: no code, no icon


def local(hour: int, minute: int, offset_s: int, day: int = 22) -> time.struct_time:
    """A moment in a zone *offset_s* east of UTC (Windows has no TZ to set: time.localtime is replaced)."""
    return time.struct_time((2026, 10, day, hour, minute, 0, 3, 295, 0, "Some Zone", offset_s))


@pytest.fixture
def at(monkeypatch):
    """render's clock at a given moment: at(struct_time)."""
    def set_moment(moment: time.struct_time):
        monkeypatch.setattr(render, "time", SimpleNamespace(localtime=lambda _when=None: moment,
                                                            strftime=time.strftime))
    return set_moment


def test_clock_with_its_offset_in_summer_and_winter(at):
    at(local(21, 43, 7200))
    assert render.clock_text(None) == "21:43"
    assert render.clock_text(None, render.Clock(zone="offset")) == "21:43 UTC+2"
    at(local(9, 5, 3600, day=26))
    assert render.clock_text(None, render.Clock(zone="offset")) == "09:05 UTC+1"


def test_clock_in_12_hours_and_the_date(at):
    at(local(21, 43, 7200))
    assert render.clock_text(None, render.Clock(12)) == "9:43 PM"
    assert render.date_text(None) == ""
    assert [render.date_text(None, render.Clock(date=d)) for d in ("weekday", "dmy", "mdy", "ymd")] == \
        ["Thu 22 Oct", "22-10-2026", "10/22/2026", "2026-10-22"]
    at(local(6, 30, 7200))
    assert render.clock_text(None, render.Clock(12, "offset")) == "6:30 AM UTC+2"


def test_offsets_with_minutes_and_west_of_utc():
    assert render.offset(local(12, 0, 19800)) == "UTC+5:30"
    assert render.offset(local(12, 0, -12600)) == "UTC-3:30"
    assert render.offset(local(12, 0, 0)) == "UTC+0"


def test_the_date_goes_under_the_time(qapp):
    plain = render.draw(ALLY, [], 320, 480, AMBER, clock=0)
    dated = render.draw(ALLY, [], 320, 480, AMBER, clock=0, style=render.Clock(date="dmy"))
    assert plain != dated


def test_own_colors():
    dark = render.THEMES["Dark"]
    own = render.with_colors(dark, {"text": "#ff0000", "tiles": "#00ff00", "accent": "", "background": "nonsense"})
    assert (own.text, own.surface) == (QColor("#ff0000"), QColor("#00ff00"))
    assert (own.accent, own.background, own.muted) == (dark.accent, dark.background, dark.muted)
    assert render.with_colors(dark, {}) == dark


def test_report_has_every_value(at):
    at(local(21, 43, 7200))
    text = render.report(ALLY, None, weather.Weather(11.8, 2), "Berlin", "Wi-Fi adapter", "My Ally")
    lines = text.splitlines()
    assert lines[:3] == ["My Ally", "22-10-2026 21:43:00 UTC+2", ""]
    assert len(lines) == 3 + len(render.TILES)
    assert "CPU                    12 % · 3200 MHz · 72 °C" in lines
    assert "Network (Wi-Fi adapter) ↓ 1.5 MB/s · ↑ 50.0 KB/s" in lines
    assert "Battery                82 % · on battery" in lines
    assert lines[-1] == "Berlin                 12 °C · Partly cloudy"


def test_every_theme_and_a_picture(qapp):
    picture = QImage(100, 50, QImage.Format.Format_RGB32)
    picture.fill(QColor(0, 200, 0))
    for name, theme in render.THEMES.items():
        image = render.draw(ALLY, ["cpu"], 320, 480, AMBER, theme=theme, clock=0)
        assert image.pixelColor(1, 479) == theme.background, name
    image = render.draw(ALLY, ["cpu"], 320, 480, AMBER, picture=picture, clock=0)
    assert image.pixelColor(1, 479) == QColor(0, 200, 0)              # the picture fills the background


def test_a_long_header_text_leaves_room_for_the_time(qapp):
    short = render.draw(ALLY, [], 320, 480, AMBER, title="", clock=0)
    long = render.draw(ALLY, [], 320, 480, AMBER, title="W" * 40, clock=0)
    right = range(270, 310)                                         # the time, at the right
    assert [short.pixelColor(x, 30) for x in right] == [long.pixelColor(x, 30) for x in right]
