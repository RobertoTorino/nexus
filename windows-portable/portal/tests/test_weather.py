# SPDX-License-Identifier: GPL-3.0-or-later
"""The weather at the top (weather.py): Open-Meteo's place search and current weather read from their answers, the
symbol per WMO code, the header's text, and the suite's place kept (owner, 06-11-2026)."""

from __future__ import annotations

import pytest

from portable_portal import weather
from portable_portal.weather import Place, Weather

SEARCH = {"results": [
    {"name": "Amsterdam", "latitude": 52.37403, "longitude": 4.88969, "country": "Netherlands",
     "admin1": "North Holland"},
    {"name": "Amsterdam", "latitude": 42.93869, "longitude": -74.18819, "country": "United States",
     "admin1": "New York"},
    {"name": "Broken"},                                             # no coordinates: left out
]}
FORECAST = {"current": {"time": "2026-11-06T01:15", "temperature_2m": 8.6, "weather_code": 3, "is_day": 0}}


def test_a_search_lists_the_places_with_where_they_are():
    asked = []

    def fetch(url):
        asked.append(url)
        return SEARCH
    places = weather.search(" Amst ", fetch)
    assert places == [Place("Amsterdam", "North Holland, Netherlands", 52.37403, 4.88969),
                      Place("Amsterdam", "New York, United States", 42.93869, -74.18819)]
    assert places[0].label == "Amsterdam, North Holland, Netherlands"
    assert asked[0].startswith("https://geocoding-api.open-meteo.com/v1/search?") and "name=Amst&" in asked[0]
    assert weather.search("A", fetch) == [] and len(asked) == 1     # one letter: not asked
    assert weather.search("Nowhere", lambda url: {}) == []          # Open-Meteo leaves results out when none


def test_a_bad_answer_is_the_callers():
    with pytest.raises(ValueError):
        weather.search("Amsterdam", lambda url: [])
    with pytest.raises(ValueError):
        weather.current(Place("Amsterdam", "", 52.4, 4.9), lambda url: {"current": {"temperature_2m": "x"}})


def test_the_current_weather_and_its_text():
    asked = []

    def fetch(url):
        asked.append(url)
        return FORECAST
    place = Place("Amsterdam", "North Holland, Netherlands", 52.37403, 4.88969)
    now = weather.current(place, fetch)
    assert now == Weather(8.6, 3, False) and now.symbol == "☁"
    assert asked[0].startswith("https://api.open-meteo.com/v1/forecast?latitude=52.37403&longitude=4.88969&")
    assert weather.text(place, now) == "Amsterdam ☁ 9°"
    assert weather.text(place, None) == "Amsterdam" and weather.text(None, now) == ""


def test_a_symbol_per_weather_code():
    assert [weather.symbol(code) for code in (0, 2, 3, 45, 61, 81, 71, 95)] == \
        ["☀", "⛅", "☁", "🌫", "🌧", "🌧", "❄", "⛈"]
    assert weather.symbol(0, day=False) == "☾" and weather.symbol(1, day=False) == "☁"


def test_the_suites_place_is_kept_and_taken_out(qapp):
    place = Place("Utrecht", "Utrecht, Netherlands", 52.09083, 5.12222)
    assert weather.place("weather-test") is None                   # nothing chosen yet: Off
    weather.set_place("weather-test", place)
    assert weather.place("weather-test") == place
    weather.set_place("weather-test", None)
    assert weather.place("weather-test") is None


def test_a_place_is_listed_once_and_at_most_five():
    """Owner, 06-11-2026: "Dubai" listed "Dubai, Uttar Pradesh, India" three times, and eight places did not fit the
    page. The same name and area once, the first (the best match); at most MATCHES, of ASKED asked."""
    asked = []
    same = [{"name": "Dubai", "latitude": 25.0 + n, "longitude": 55.0, "country": "India", "admin1": "Uttar Pradesh"}
            for n in range(3)]
    others = [{"name": f"Dubai {n}", "latitude": 1.0, "longitude": 2.0, "country": "X"} for n in range(6)]

    def fetch(url):
        asked.append(url)
        return {"results": [*same, *others]}
    places = weather.search("Dubai", fetch)
    assert len(places) == weather.MATCHES == 5 and "count=10&" in asked[0]
    assert [p.label for p in places].count("Dubai, Uttar Pradesh, India") == 1 and places[0].latitude == 25.0
