# SPDX-License-Identifier: GPL-3.0-or-later
"""The tiles' texts, the clock, the user's colors, the weather's icon, the report, the picture's size and turn, and
the screen's pixel format."""

from __future__ import annotations

import time

import pytest
from PyQt6.QtGui import QColor, QImage

from bc250_core.sensors import Fan, Reading
from usb_ips35 import render, weather

BOARD = Reading(cpu_load=12.4, cpu_mhz=3200, cpu_temp=72.1, gpu_load=None, gpu_mhz=2000, gpu_watts=95.3,
                gpu_temp=91.0, vram=(900_000_000, 6_000_000_000), ram=(5_000_000_000, 10_000_000_000),
                vrm_temp=58.0, nvme_temp=39.9, net=(1_500_000.0, 50_000.0), disk=(0.0, 2_000.0),
                fans=(Fan("Pump Fan", 1169),))


def test_tiles_in_the_screens_order():
    tiles = render.tiles(BOARD, ["net", "cpu", "gpu"])
    assert [t.caption for t in tiles] == ["CPU", "GPU", "Network"]
    cpu, gpu, net = tiles
    assert (cpu.value, cpu.detail, cpu.fraction, cpu.alert) == ("12 %", "3200 MHz · 72 °C", 0.124, None)
    # No GPU load without the governor's fix-metrics: the clock is the value, and 91 °C is hot.
    assert (gpu.value, gpu.detail, gpu.fraction, gpu.alert) == ("2000 MHz", "95 W · 91 °C", None, render.RED)
    assert (net.value, net.detail) == ("↓ 1.5 MB/s", "↑ 50.0 KB/s")


def test_every_tile_with_missing_values():
    tiles = render.tiles(Reading(), [k for k, _ in render.TILES])
    assert len(tiles) == len(render.TILES)
    assert all(t.value == render.DASH and t.fraction is None and t.alert is None for t in tiles)


def test_memory_and_fan():
    vram, ram, fan = render.tiles(BOARD, ["vram", "ram", "fan"])
    assert (vram.value, vram.fraction) == ("0.9 / 6.0 GB", 0.15)
    assert (ram.value, ram.fraction) == ("5.0 / 10.0 GB", 0.5)
    assert (fan.value, fan.detail) == ("1169 RPM", "Pump Fan")


def test_draw_and_turn(qapp):
    image = render.draw(BOARD, render.DEFAULT_TILES, 480, 320, QColor("#4a90d9"), clock=0)
    assert (image.width(), image.height()) == (480, 320)
    turned = render.for_screen(image, 90)
    assert (turned.width(), turned.height()) == (320, 480)
    assert render.for_screen(image, 0) is image
    assert len(render.rgb565(turned)) == 320 * 480 * 2


def test_rgb565_little_endian(qapp):
    image = QImage(3, 1, QImage.Format.Format_RGB32)
    for x, colour in enumerate(("red", "lime", "blue")):
        image.setPixelColor(x, 0, QColor(colour))
    assert render.rgb565(image) == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])


def test_rgb565_of_an_odd_width_has_no_padding(qapp):
    image = QImage(3, 2, QImage.Format.Format_RGB32)               # 6 bytes a row, padded to 8 by Qt
    image.fill(QColor("white"))
    assert render.rgb565(image) == b"\xff\xff" * 6


def test_temperature_tiles():
    cpu, gpu = render.tiles(BOARD, ["gpu_temp", "cpu_temp"])
    assert (cpu.caption, cpu.value, cpu.fraction, cpu.alert) == ("CPU temp", "72 °C", 0.721, None)
    assert (gpu.caption, gpu.value, gpu.alert) == ("GPU temp", "91 °C", render.RED)
    assert render.tiles(Reading(cpu_temp=85.0), ["cpu_temp"])[0].alert == render.ORANGE


def test_weather_tile():
    sunny = weather.Weather(21.6, 0)
    assert render.tiles(BOARD, ["weather"], sunny, "Berlin")[0] == render.Tile("Berlin", "22 °C", "Clear sky",
                                                                               icon="clear")
    night = render.tiles(BOARD, ["weather"], weather.Weather(9.0, 61, is_day=False), "Berlin")[0]
    assert (night.icon, night.night) == ("rain", True)
    assert render.tiles(BOARD, ["weather"])[0] == render.Tile("Weather", render.DASH, "choose a place")


@pytest.mark.parametrize("code", [0, 2, 3, 45, 61, 71, 95])
@pytest.mark.parametrize("is_day", [True, False])
def test_every_weather_icon_is_drawn(qapp, code, is_day):
    now = weather.Weather(12.0, code, is_day=is_day)
    plain = render.draw(BOARD, ["weather"], 320, 480, QColor("#4a90d9"), weather=weather.Weather(12.0, 1000), clock=0)
    image = render.draw(BOARD, ["weather"], 320, 480, QColor("#4a90d9"), weather=now, clock=0)
    assert now.icon and image != plain                                # 1000: no code, no icon


@pytest.fixture
def amsterdam(monkeypatch):
    """The owner's time zone, whatever the machine's own."""
    monkeypatch.setenv("TZ", "Europe/Amsterdam")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


SUMMER = 1792698180                                                 # 22-10-2026 21:43 CEST
WINTER = 1793001900                                                 # 26-10-2026 09:05 CET
MORNING = 1792643400                                                # 22-10-2026 06:30 CEST


def test_clock_follows_summer_and_winter_time(amsterdam):
    assert render.clock_text(SUMMER) == "21:43"
    assert render.clock_text(SUMMER, render.Clock(zone="name")) == "21:43 CEST"
    assert render.clock_text(SUMMER, render.Clock(zone="offset")) == "21:43 UTC+2"
    assert render.clock_text(WINTER, render.Clock(zone="name")) == "09:05 CET"
    assert render.clock_text(WINTER, render.Clock(zone="offset")) == "09:05 UTC+1"


def test_clock_in_12_hours_and_the_date(amsterdam):
    assert render.clock_text(SUMMER, render.Clock(12)) == "9:43 PM"
    assert render.clock_text(MORNING, render.Clock(12, "name")) == "6:30 AM CEST"
    assert render.date_text(SUMMER) == ""
    assert [render.date_text(SUMMER, render.Clock(date=d)) for d in ("weekday", "dmy", "mdy", "ymd")] == \
        ["Thu 22 Oct", "22-10-2026", "10/22/2026", "2026-10-22"]


def test_offsets_with_minutes(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    time.tzset()
    try:
        assert render.offset(time.localtime(SUMMER)) == "UTC+5:30"
    finally:
        monkeypatch.undo()
        time.tzset()


def test_the_date_goes_under_the_time(qapp, amsterdam):
    plain = render.draw(BOARD, [], 320, 480, QColor("#4a90d9"), clock=SUMMER)
    dated = render.draw(BOARD, [], 320, 480, QColor("#4a90d9"), clock=SUMMER, style=render.Clock(date="dmy"))
    assert plain != dated


def test_own_colours():
    dark = render.THEMES["Dark"]
    own = render.with_colours(dark, {"text": "#ff0000", "tiles": "#00ff00", "accent": "", "background": "nonsense"})
    assert (own.text, own.surface) == (QColor("#ff0000"), QColor("#00ff00"))
    assert (own.accent, own.background, own.muted) == (dark.accent, dark.background, dark.muted)
    assert render.with_colours(dark, {}) == dark


def test_report_has_every_value(amsterdam):
    text = render.report(BOARD, SUMMER, weather.Weather(11.8, 2), "Berlin", "enp4s0 (Ethernet)", "My board")
    lines = text.splitlines()
    assert lines[:3] == ["My board", "22-10-2026 21:43:00 CEST (UTC+2)", ""]
    assert len(lines) == 3 + len(render.TILES)
    assert "CPU                    12 % · 3200 MHz · 72 °C" in lines
    assert "Network (enp4s0 (Ethernet)) ↓ 1.5 MB/s · ↑ 50.0 KB/s" in lines
    assert "VRM temp               58 °C" in lines
    assert lines[-1] == "Berlin                 12 °C · Partly cloudy"


def test_every_theme_and_a_picture(qapp):
    picture = QImage(100, 50, QImage.Format.Format_RGB32)
    picture.fill(QColor(0, 200, 0))
    for name, theme in render.THEMES.items():
        image = render.draw(BOARD, ["cpu"], 320, 480, QColor("#4a90d9"), theme=theme, clock=0)
        assert image.pixelColor(1, 479) == theme.background, name
    image = render.draw(BOARD, ["cpu"], 320, 480, QColor("#4a90d9"), picture=picture, clock=0)
    assert image.pixelColor(1, 479) == QColor(0, 200, 0)              # the picture fills the background


def test_a_long_header_text_leaves_room_for_the_time(qapp):
    short = render.draw(BOARD, [], 320, 480, QColor("#4a90d9"), title="", clock=0)
    long = render.draw(BOARD, [], 320, 480, QColor("#4a90d9"), title="W" * 40, clock=0)
    right = range(270, 310)                                         # the time, at the right
    assert [short.pixelColor(x, 30) for x in right] == [long.pixelColor(x, 30) for x in right]
