# SPDX-License-Identifier: GPL-3.0-or-later
"""The weather beside the header's symbols (owner, 05-11-2026), from Open-Meteo (open-meteo.com: free, no account or
key), as USB IPS3.5's screen has it. Nothing goes over the network until the user has chosen a place on the
Settings page: the name they search for goes to the geocoding search, then the place's coordinates to the forecast,
every INTERVAL_S while the portal shows. No Qt, so it is tested on its own; the window runs it off the GUI thread."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 10
INTERVAL_S = 30 * 60                    # Open-Meteo updates its current values every 15 minutes
BUSY = {429, 502, 503, 504}             # Open-Meteo is overloaded or down for a while: no fault of the request
RESULTS = 10

# WMO weather codes, as Open-Meteo reports them.
CODES = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
         51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
         61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
         71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
         82: "Heavy showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm, hail",
         99: "Thunderstorm, hail"}
# The symbol for each code (glyphs.weather draws them); rain and snow by their ranges.
SYMBOLS = {0: "clear", 1: "clear", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog", 95: "thunder", 96: "thunder",
           99: "thunder"}

Fetch = Callable[[str, dict], dict]


class WeatherError(Exception):
    """What went wrong, in a sentence for the window."""


@dataclass(frozen=True)
class Place:
    name: str
    region: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return ", ".join(p for p in (self.name, self.region, self.country) if p)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> Place | None:
        try:
            return cls(**json.loads(text)) if text else None
        except (ValueError, TypeError):
            return None


@dataclass(frozen=True)
class Weather:
    temperature: float                  # °C
    code: int
    wind_kmh: float | None = None
    humidity: int | None = None         # %
    is_day: bool = True                 # the sun is up: a sun, otherwise a moon, in the symbol

    @property
    def description(self) -> str:
        return CODES.get(self.code, "")

    @property
    def symbol(self) -> str:
        """clear, partly, cloudy, fog, rain, snow or thunder; cloudy for a code Open-Meteo does not document."""
        if self.code in SYMBOLS:
            return SYMBOLS[self.code]
        if 51 <= self.code <= 67 or 80 <= self.code <= 82:
            return "rain"
        if 71 <= self.code <= 77 or 85 <= self.code <= 86:
            return "snow"
        return "cloudy"


def _reason(error: urllib.error.HTTPError) -> str:
    """Open-Meteo's own reason in its JSON answer ({"reason": ..., "error": true}), or the HTTP status's."""
    try:
        reason = json.loads(error.read().decode("utf-8")).get("reason")
    except (AttributeError, OSError, ValueError):
        reason = None
    return str(reason or error.reason or "").strip().rstrip(".")


def http_fetch(user_agent: str) -> Fetch:
    """Open-Meteo's JSON answer to *url* with *params*; WeatherError, in a sentence, when there is none."""
    def fetch(url: str, params: dict) -> dict:
        request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                         headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            reason = _reason(exc)
            if exc.code in BUSY:
                raise WeatherError(f"Open-Meteo is unavailable for now ({exc.code}: {reason}).") from exc
            raise WeatherError(f"Open-Meteo answered {exc.code}: {reason}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise WeatherError("Open-Meteo cannot be reached: check the network.") from exc
        except ValueError as exc:
            raise WeatherError("Open-Meteo's answer could not be read.") from exc
    return fetch


def search(name: str, fetch: Fetch) -> list[Place]:
    """Places by that name, the most likely first."""
    data = fetch(GEOCODE_URL, {"name": name.strip(), "count": RESULTS, "language": "en", "format": "json"})
    places = []
    for item in data.get("results") or []:
        try:
            places.append(Place(str(item["name"]), str(item.get("admin1") or ""), str(item.get("country") or ""),
                                float(item["latitude"]), float(item["longitude"])))
        except (KeyError, TypeError, ValueError):
            continue
    return places


def current(place: Place, fetch: Fetch) -> Weather:
    data = fetch(FORECAST_URL, {"latitude": place.latitude, "longitude": place.longitude, "timezone": "auto",
                                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,is_day"})
    now = data.get("current") or {}
    try:
        return Weather(float(now["temperature_2m"]), int(now["weather_code"]),
                       float(now["wind_speed_10m"]) if now.get("wind_speed_10m") is not None else None,
                       int(now["relative_humidity_2m"]) if now.get("relative_humidity_2m") is not None else None,
                       now.get("is_day") != 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("Open-Meteo's answer has no current weather.") from exc
