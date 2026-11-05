# SPDX-License-Identifier: GPL-3.0-or-later
"""The weather beside the header's symbols (owner, 05-11-2026): Open-Meteo's answers read, without the network."""

from __future__ import annotations

import urllib.error

import pytest

from bc250_portal import weather

AMSTERDAM = weather.Place("Amsterdam", "North Holland", "Netherlands", 52.37, 4.89)


def test_a_search_lists_the_places_and_skips_a_broken_one():
    asked = []

    def fetch(url, params):
        asked.append((url, params))
        return {"results": [{"name": "Amsterdam", "admin1": "North Holland", "country": "Netherlands",
                             "latitude": 52.37, "longitude": 4.89},
                            {"name": "broken"},
                            {"name": "Amsterdam", "country": "United States", "latitude": 42.9, "longitude": -74.2}]}
    places = weather.search(" Amsterdam ", fetch)
    assert [p.label for p in places] == ["Amsterdam, North Holland, Netherlands", "Amsterdam, United States"]
    assert asked[0][0] == weather.GEOCODE_URL and asked[0][1]["name"] == "Amsterdam"
    assert weather.search("Nowhere", lambda url, params: {}) == []


def test_the_current_weather_and_its_symbol():
    def fetch(url, params):
        assert url == weather.FORECAST_URL and (params["latitude"], params["longitude"]) == (52.37, 4.89)
        return {"current": {"temperature_2m": 11.4, "weather_code": 61, "wind_speed_10m": 18.0,
                            "relative_humidity_2m": 87, "is_day": 0}}
    now = weather.current(AMSTERDAM, fetch)
    assert (now.temperature, now.description, now.symbol, now.is_day) == (11.4, "Light rain", "rain", False)
    assert [weather.Weather(10, code).symbol for code in (0, 2, 3, 45, 73, 81, 95, 42)] == [
        "clear", "partly", "cloudy", "fog", "snow", "rain", "thunder", "cloudy"]
    with pytest.raises(weather.WeatherError):
        weather.current(AMSTERDAM, lambda url, params: {"current": {}})


def test_a_place_is_kept_as_json():
    assert weather.Place.from_json(AMSTERDAM.to_json()) == AMSTERDAM
    assert weather.Place.from_json("") is None and weather.Place.from_json("{broken") is None


def test_open_meteo_down_or_unreachable_says_so(monkeypatch):
    def busy(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(weather.urllib.request, "urlopen", busy)
    with pytest.raises(weather.WeatherError, match="unavailable for now"):
        weather.http_fetch("test/1")(weather.FORECAST_URL, {})

    def offline(request, timeout):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(weather.urllib.request, "urlopen", offline)
    with pytest.raises(weather.WeatherError, match="cannot be reached"):
        weather.http_fetch("test/1")(weather.FORECAST_URL, {})
