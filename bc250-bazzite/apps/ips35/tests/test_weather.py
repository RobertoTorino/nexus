# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-Meteo's answers (recorded 22-10-2026, trimmed) turned into places and weather, and its failures."""

from __future__ import annotations

import urllib.error

import pytest

from usb_ips35 import weather

BERLIN = {"results": [
    {"id": 2950159, "name": "Berlin", "latitude": 52.52437, "longitude": 13.41053, "country": "Germany",
     "admin1": "State of Berlin"},
    {"id": 5083330, "name": "Berlin", "latitude": 44.46867, "longitude": -71.18508, "country": "United States",
     "admin1": "New Hampshire"},
    {"id": 1, "name": "Broken"},                                      # no coordinates: left out
]}
NOW = {"current": {"time": "2026-10-22T22:15", "temperature_2m": 11.8, "weather_code": 2, "wind_speed_10m": 10.7,
                   "relative_humidity_2m": 64, "is_day": 0}}


def test_search():
    asked = []
    places = weather.search(" Berlin ", lambda url, params: asked.append((url, params)) or BERLIN)
    assert [p.label for p in places] == ["Berlin, State of Berlin, Germany", "Berlin, New Hampshire, United States"]
    assert asked == [(weather.GEOCODE_URL, {"name": "Berlin", "count": 10, "language": "en", "format": "json"})]
    assert weather.search("zzzz", lambda url, params: {"generationtime_ms": 0.1}) == []


def test_current():
    place = weather.search("Berlin", lambda url, params: BERLIN)[0]
    asked = []
    now = weather.current(place, lambda url, params: asked.append(params) or NOW)
    assert now == weather.Weather(11.8, 2, 10.7, 64, is_day=False) and now.description == "Partly cloudy"
    assert "is_day" in asked[0]["current"].split(",")
    assert (asked[0]["latitude"], asked[0]["longitude"]) == (52.52437, 13.41053)
    with pytest.raises(weather.WeatherError):
        weather.current(place, lambda url, params: {"current": {}})


@pytest.mark.parametrize("code, icon", [(0, "clear"), (1, "clear"), (2, "partly"), (3, "cloudy"), (48, "fog"),
                                        (53, "rain"), (66, "rain"), (81, "rain"), (75, "snow"), (86, "snow"),
                                        (95, "thunder"), (99, "thunder"), (4, None)])
def test_icons(code, icon):
    assert weather.Weather(10.0, code).icon == icon


def test_place_round_trip():
    place = weather.Place("Berlin", "State of Berlin", "Germany", 52.52, 13.41)
    assert weather.Place.from_json(place.to_json()) == place
    assert weather.Place.from_json("") is None and weather.Place.from_json("{broken") is None


@pytest.mark.parametrize("error, text", [
    (urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None), "429 Too Many Requests"),
    (urllib.error.URLError("no route"), "cannot be reached"),
])
def test_fetch_failures_say_what_happened(monkeypatch, error, text):
    def refuse(*args, **kwargs):
        raise error
    monkeypatch.setattr(weather.urllib.request, "urlopen", refuse)
    with pytest.raises(weather.WeatherError, match=text):
        weather.fetch_json(weather.FORECAST_URL, {})
