# SPDX-License-Identifier: GPL-3.0-or-later
"""The clock's choices (clock.py): 24 hours, no seconds and Amsterdam time until changed, then kept in the suite's
settings (owner, 06-11-2026). Core's test_power.py has the clock itself."""

from __future__ import annotations

from portable_portal import clock
from portable_portal.clock import Clock


def test_the_clock_is_kept_for_the_suite(qapp):
    assert clock.read("clock-test") == Clock(twelve_hour=False, seconds=False, zone="cet")
    clock.save("clock-test", Clock(twelve_hour=True, seconds=True, zone="utc"))
    assert clock.read("clock-test") == Clock(True, True, "utc")
    assert clock.read("clock-test").parts()[1].endswith(" UTC")


def test_an_unknown_zone_is_amsterdam_time(qapp):
    from bc250_core import portable
    portable.look_settings("clock-zone").setValue(clock.ZONE_KEY, "pst")
    assert clock.read("clock-zone").zone == "cet"
