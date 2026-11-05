# SPDX-License-Identifier: GPL-3.0-or-later
"""ini_settings.py: every field of helixsr.ini has a row, A steps through its values (a value written by hand steps to
the next one), the rows follow the payload's HelixSR version."""

from __future__ import annotations

from dataclasses import fields

from upscale_boost import ini_settings
from upscale_boost.backend import SECOND_UPSCALER_DLL, HelixIni, validate_ini


def setting(key: str) -> ini_settings.Setting:
    return next(s for s in ini_settings.SETTINGS if s.key == key)


def test_every_field_has_one_row_with_valid_values():
    assert sorted(s.key for s in ini_settings.SETTINGS) == sorted(f.name for f in fields(HelixIni))
    for s in ini_settings.SETTINGS:
        for value in s.values:
            if s.key not in ("motion_threshold", "motion_limit"):
                assert validate_ini(HelixIni(**{s.key: value})) == [], (s.key, value)
        assert type(s.values[0]) is type(getattr(HelixIni(), s.key)), s.key


def test_a_step_goes_round_and_a_value_by_hand_steps_on():
    sharpness = setting("sharpness")
    assert sharpness.next_value(0.3) == 0.4 and sharpness.next_value(1.0) == 0.0
    assert sharpness.next_value(0.35) == 0.4
    assert setting("network").next_value("auto") == "nvidia" and setting("network").next_value("odd") == "auto"
    assert setting("upscaler_dll").next_value("") == SECOND_UPSCALER_DLL
    assert setting("log_enabled").next_value(True) is False


def test_how_a_value_shows():
    assert setting("sharpness").shown(0.3) == "0.3" and setting("sharpness").shown(0.0) == "0"
    assert setting("log_enabled").shown(True) == "on" and setting("forwarding_dll").shown("") == "default"


def test_the_rows_follow_the_version():
    keys = {s.key for s in ini_settings.shown_settings("2.0.0")}
    assert "sharpener" in keys and "sharpening_mode" not in keys and "network" not in keys
    keys = {s.key for s in ini_settings.shown_settings("1.4.3")}
    assert "sharpening_mode" in keys and "sharpener" not in keys
    assert len(ini_settings.shown_settings("")) == len(ini_settings.SETTINGS)
