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
