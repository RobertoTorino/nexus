# SPDX-License-Identifier: GPL-3.0-or-later
"""The clock at the top of the portal, as the Settings page sets it (owner, 06-11-2026): 24 or 12 hours (AM and PM),
with or without seconds, in Amsterdam time (CET, CEST in summer) or UTC. Core's status_clock() writes it; this keeps
the choices, the suite's settings (suite.ini, beside the wallpaper's), so they stay when the portal is updated."""

from __future__ import annotations

from dataclasses import dataclass

from bc250_core import portable

HOURS_KEY, SECONDS_KEY, ZONE_KEY = "look/clock_hours", "look/clock_seconds", "look/clock_zone"
ZONE_NAMES = {"cet": "CET", "utc": "UTC"}       # CET: Amsterdam time, CEST in summer


@dataclass(frozen=True)
class Clock:
    twelve_hour: bool = False
    seconds: bool = False
    zone: str = "cet"

    def parts(self) -> list[str]:
        """The header's date and time with these choices."""
        return portable.status_clock(seconds=self.seconds, twelve_hour=self.twelve_hour, zone=self.zone)


def read(suite: str) -> Clock:
    """The suite's clock; 24 hours, no seconds and Amsterdam time until the Settings page changes them."""
    settings = portable.look_settings(suite)
    zone = str(settings.value(ZONE_KEY, "cet") or "cet")
    return Clock(str(settings.value(HOURS_KEY, "24")) == "12", str(settings.value(SECONDS_KEY, "false")) == "true",
                 zone if zone in ZONE_NAMES else "cet")


def save(suite: str, clock: Clock) -> None:
    settings = portable.look_settings(suite)
    settings.setValue(HOURS_KEY, "12" if clock.twelve_hour else "24")
    settings.setValue(SECONDS_KEY, "true" if clock.seconds else "false")
    settings.setValue(ZONE_KEY, clock.zone)
    settings.sync()
