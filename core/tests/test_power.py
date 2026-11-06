# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable header's battery (power.py): GetSystemPowerStatus's answer, and none without a battery."""

from __future__ import annotations

import sys

from bc250_core import power


def test_the_status():
    assert power.from_status(0, 0, 82) == (82, False)
    assert power.from_status(1, 8, 64) == (64, True)
    assert power.from_status(1, power.NO_BATTERY, 255) is None                  # a desktop
    assert power.from_status(1, 0, power.UNKNOWN) is None


def test_the_text():
    assert power.text((82, False)) == "82%"
    assert power.text((64, True)) == "Plugged in"             # on the charger (owner, 30-10-2026)
    assert power.text((100, True)) == "Plugged in"
    assert power.text(None) == ""


def test_off_windows_there_is_none():
    if sys.platform != "win32":
        assert power.battery() is None
    else:
        state = power.battery()
        assert state is None or (0 <= state[0] <= 100 and isinstance(state[1], bool))


def test_the_status_clock():
    """The header's date and time after the battery (owner, 28-10-2026): "Monday 27/10/2026", "17:04"."""
    import datetime

    from bc250_core.portable import status_clock
    assert status_clock(datetime.datetime(2026, 10, 27, 17, 4)) == ["Tuesday 27/10/2026", "17:04"]
    assert status_clock(datetime.datetime(2026, 10, 26, 9, 5)) == ["Monday 26/10/2026", "09:05"]


def test_the_status_clock_with_the_portals_settings():
    """Seconds, 12 hours with AM and PM, and the zone: Amsterdam time (CET, CEST from the last Sunday of March to the
    last Sunday of October, at 01:00 UTC) or UTC, its name after the time (owner, 06-11-2026)."""
    import datetime

    from bc250_core.portable import status_clock, summer_time
    utc = datetime.datetime(2026, 11, 6, 0, 14, 32)                     # 01:14:32 in Amsterdam, winter
    assert status_clock(utc, zone="cet") == ["Friday 06/11/2026", "01:14 CET"]
    assert status_clock(utc, zone="utc", seconds=True) == ["Friday 06/11/2026", "00:14:32 UTC"]
    assert status_clock(utc, zone="cet", seconds=True, twelve_hour=True) == ["Friday 06/11/2026", "1:14:32 AM CET"]
    assert status_clock(datetime.datetime(2026, 7, 1, 11, 5), zone="cet", twelve_hour=True) ==         ["Wednesday 01/07/2026", "1:05 PM CEST"]                        # summer: UTC + 2
    assert status_clock(datetime.datetime(2026, 7, 1, 23, 30), zone="cet")[0] == "Thursday 02/07/2026"   # the next day
    assert status_clock(datetime.datetime(2026, 10, 27, 0, 4), twelve_hour=True)[1] == "12:04 AM"    # the device's own
    # The changes in 2026: the last Sundays, 29 March and 25 October, at 01:00 UTC
    assert not summer_time(datetime.datetime(2026, 3, 29, 0, 59)) and summer_time(datetime.datetime(2026, 3, 29, 1, 0))
    assert summer_time(datetime.datetime(2026, 10, 25, 0, 59)) and not summer_time(datetime.datetime(2026, 10, 25, 1, 0))
    aware = datetime.datetime(2026, 11, 6, 1, 14, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    assert status_clock(aware, zone="utc")[1] == "00:14 UTC"            # an aware time: taken to UTC first
