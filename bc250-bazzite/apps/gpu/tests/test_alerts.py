# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from gpu_governor.alerts import COOLDOWN_S, AlertMonitor, AlertSettings


def titles(messages):
    return sorted(title for title, _ in messages)


def test_temperature_edge_hysteresis_cooldown(snapshot):
    m = AlertMonitor(AlertSettings(temp_c=80, throttle_enabled=False))
    assert m.check(snapshot(temp=60), 0) == []
    assert titles(m.check(snapshot(temp=81), 1)) == ["GPU temperature"]
    assert m.check(snapshot(temp=85), 2) == []                      # still hot: no repeat
    assert m.check(snapshot(temp=77), 3) == []                      # not 5 °C below yet
    assert m.check(snapshot(temp=74), 4) == []                      # re-armed
    assert m.check(snapshot(temp=81), 5) == []                      # ...but in cooldown
    assert titles(m.check(snapshot(temp=81), COOLDOWN_S + 10)) == ["GPU temperature"]


def test_throttle_uses_bus_then_saved_threshold(snapshot):
    m = AlertMonitor(AlertSettings(temp_enabled=False))
    assert titles(m.check(snapshot(temp=86, throttling=85), 0)) == ["Governor throttling"]
    m = AlertMonitor(AlertSettings(temp_enabled=False))
    assert titles(m.check(snapshot(temp=86, bus=False, throttling=85), 0)) == ["Governor throttling"]
    m = AlertMonitor(AlertSettings(temp_enabled=False))
    assert m.check(snapshot(temp=84, throttling=85), 0) == []


def test_service_alert_only_after_seen_running(snapshot):
    m = AlertMonitor()
    assert m.check(snapshot(temp=50, active=False), 0) == []
    m.check(snapshot(temp=50), 1)
    m.check(snapshot(temp=50), 2)
    out = m.check(snapshot(temp=50, active=False, sub_state="failed"), 3)
    assert titles(out) == ["Governor failed"]
    assert m.check(snapshot(temp=50, active=False, sub_state="failed"), 4) == []


def test_disabled_alerts_are_silent(snapshot):
    m = AlertMonitor(AlertSettings(temp_enabled=False, throttle_enabled=False, service_enabled=False))
    m.check(snapshot(temp=50), 0)
    m.check(snapshot(temp=50), 1)
    assert m.check(snapshot(temp=99, active=False), 2) == []


def test_no_temperature_sensor(snapshot):
    m = AlertMonitor()
    assert m.check(snapshot(temp=None), 0) == []
