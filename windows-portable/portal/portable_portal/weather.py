# SPDX-License-Identifier: GPL-3.0-or-later
"""The weather at the top of the portal (owner, 06-11-2026): a place chosen on the Settings page, its weather symbol
and temperature from Open-Meteo, before the date ("Amsterdam ☁ 9°"). Open-Meteo needs no key; its place search
(geocoding-api.open-meteo.com) finds the place by name, its forecast (api.open-meteo.com) gives the current
temperature and the WMO weather code. Weather data by Open-Meteo.com (CC BY 4.0).

The place is the suite's setting (suite.ini, beside the wallpaper's), so it stays when the portal is updated. The
functions take a fetch (url -> decoded JSON) so the tests need no network; the window runs them off its thread."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from bc250_core import portable

SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search?{query}"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast?{query}"
TIMEOUT = 10
MATCHES = 5                     # places a search lists, each shown once (owner, 06-11-2026: eight did not fit)
ASKED = 10                      # places asked of Open-Meteo, so that MATCHES are left after the same ones
EVERY_MS = 15 * 60 * 1000       # the weather looked up again
PLACE_KEY, LATITUDE_KEY, LONGITUDE_KEY, AREA_KEY = "look/place", "look/place_latitude", "look/place_longitude", \
    "look/place_area"

Fetch = Callable[[str], object]


@dataclass(frozen=True)
class Place:
    name: str                   # "Amsterdam"
    area: str                   # where it is, for the choice: "North Holland, Netherlands"
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.area}" if self.area else self.name


@dataclass(frozen=True)
class Weather:
    temperature: float          # °C
    code: int                   # the WMO weather code
    day: bool = True

    @property
    def symbol(self) -> str:
        return symbol(self.code, self.day)


def fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "windows-portable-suite"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def search(name: str, fetch: Fetch = fetch_json) -> list[Place]:
    """The places Open-Meteo knows by *name* (part of one will do), the best match first, at most MATCHES; [] for none.
    A place with the same name and area as one before it is left out (Open-Meteo lists villages that share them, and
    the list could not tell them apart). OSError and ValueError (no connection, a bad answer) are the caller's."""
    name = name.strip()
    if len(name) < 2:
        return []
    data = fetch(SEARCH_URL.format(query=urllib.parse.urlencode(
        {"name": name, "count": ASKED, "language": "en", "format": "json"})))
    if not isinstance(data, dict):
        raise ValueError("not a search answer")
    places = []
    for item in data.get("results") or []:
        try:
            area = ", ".join(str(part) for part in (item.get("admin1"), item.get("country")) if part)
            found = Place(str(item["name"]), area, float(item["latitude"]), float(item["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        if all(found.label != other.label for other in places):
            places.append(found)
    return places[:MATCHES]


def current(place: Place, fetch: Fetch = fetch_json) -> Weather:
    """The weather at *place* now. OSError and ValueError are the caller's."""
    data = fetch(FORECAST_URL.format(query=urllib.parse.urlencode(
        {"latitude": place.latitude, "longitude": place.longitude,
         "current": "temperature_2m,weather_code,is_day", "timezone": "auto"})))
    now = data.get("current") if isinstance(data, dict) else None
    if not isinstance(now, dict):
        raise ValueError("not a forecast answer")
    try:
        return Weather(float(now["temperature_2m"]), int(now["weather_code"]), bool(now.get("is_day", 1)))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"not a forecast answer ({error})") from error


def symbol(code: int, day: bool = True) -> str:
    """A WMO weather code (Open-Meteo's weather_code) as one symbol."""
    if code == 0:
        return "☀" if day else "☾"
    if code in (1, 2):
        return "⛅" if day else "☁"
    if code == 3:
        return "☁"
    if code in (45, 48):
        return "🌫"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄"
    if code in (95, 96, 99):
        return "⛈"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "🌧"
    return "☁"


def text(place: Place | None, weather: Weather | None) -> str:
    """What the header shows before the date: "Amsterdam ☁ 9°"; the place alone until its weather is in; "" without a
    place."""
    if place is None:
        return ""
    if weather is None:
        return place.name
    return f"{place.name} {weather.symbol} {round(weather.temperature)}°"


def place(suite: str) -> Place | None:
    """The suite's place, None when none was chosen (Location: Off)."""
    settings = portable.look_settings(suite)
    name = str(settings.value(PLACE_KEY, "") or "")
    try:
        latitude, longitude = float(settings.value(LATITUDE_KEY)), float(settings.value(LONGITUDE_KEY))
    except (TypeError, ValueError):
        return None
    return Place(name, str(settings.value(AREA_KEY, "") or ""), latitude, longitude) if name else None


def set_place(suite: str, chosen: Place | None) -> None:
    """*chosen* as the suite's place; None: Location Off, no weather."""
    settings = portable.look_settings(suite)
    if chosen is None:
        for key in (PLACE_KEY, LATITUDE_KEY, LONGITUDE_KEY, AREA_KEY):
            settings.remove(key)
    else:
        settings.setValue(PLACE_KEY, chosen.name)
        settings.setValue(AREA_KEY, chosen.area)
        settings.setValue(LATITUDE_KEY, chosen.latitude)
        settings.setValue(LONGITUDE_KEY, chosen.longitude)
    settings.sync()
