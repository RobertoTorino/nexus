# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema-driven config.toml reading and rendering."""

from __future__ import annotations

import dataclasses

import pytest

from gpu_governor.backends.base import GovernorConfig
from gpu_governor.backends.cyan_skillfish import FEATURE_DOWN_EVENTS, FEATURE_SET_METHOD


def test_read_shipped_values(backend):
    config = backend.read_config()
    assert (config.freq_min, config.freq_max) == (1000, 2000)
    assert (config.load_upper, config.load_lower) == (0.95, 0.80)
    assert config.temp_throttling == 85 and config.temp_recovery == 0
    assert config.dbus_enabled is True and config.fix_metrics is True
    # sections absent from the file keep the governor's built-in defaults
    assert config.sample_us == 2000 and config.ramp_burst == 200.0 and config.set_method == "smu"


def test_round_trip_every_field(backend):
    wanted = GovernorConfig(fix_metrics=False, fix_freq=True, method="process", temp_read="sysfs", flush_every=3,
                            freq_min=1200, freq_max=1900, load_upper=0.9, load_lower=0.7, temp_throttling=80,
                            temp_recovery=70, dbus_enabled=False, set_method="kernel", sample_us=250,
                            adjust_us=100_000, burst_samples=60, down_events=5, ramp_normal=1.0, ramp_burst=50.0,
                            freq_adjust=15)
    wanted.validate()
    text = backend.render_config(backend.read_config_text(), wanted)
    backend.config_path.write_text(text, encoding="utf-8")
    assert backend.read_config() == wanted


def test_missing_sections_are_appended_after_safe_points(backend):
    config = dataclasses.replace(backend.read_config(), sample_us=500, freq_adjust=20)
    text = backend.render_config(backend.read_config_text(), config)
    # the new tables must not land inside the last [[safe-points]] entry
    tail = text[text.rindex("[[safe-points]]"):]
    assert "[timing.intervals]" in tail and "[frequency-thresholds]" in tail
    last_point = tail[:tail.index("[timing")]
    assert "sample =" not in last_point and "adjust =" not in last_point
    backend.config_path.write_text(text, encoding="utf-8")
    again = backend.read_config()
    assert again.sample_us == 500 and again.freq_adjust == 20
    assert [(p.frequency, p.voltage) for p in backend.safe_points()] == [(1000, 700), (1500, 800), (2000, 900)]


def test_unchanged_values_keep_their_text(backend):
    original = backend.read_config_text().replace("upper = 0.95", "upper = 0.950")
    text = backend.render_config(original, backend.read_config())
    assert "upper = 0.950" in text          # numerically equal, so the line is left alone


def test_float_rendering_is_compact(backend):
    config = dataclasses.replace(backend.read_config(), load_upper=0.9, ramp_normal=1.0)
    text = backend.render_config(backend.read_config_text(), config)
    assert "upper = 0.9\n" in text and "normal = 1.0\n" in text


def test_optional_zero_keys_are_omitted(backend):
    config = dataclasses.replace(backend.read_config(), temp_recovery=0, burst_samples=0, sample_us=300)
    text = backend.render_config(backend.read_config_text(), config)
    assert "throttling_recovery = " not in text
    assert "burst-samples = " not in text or "# burst-samples" in text
    config = dataclasses.replace(config, temp_recovery=70, burst_samples=8)
    text = backend.render_config(text, config)
    assert "throttling_recovery = 70" in text and "burst-samples = 8" in text


def test_out_of_range_burst_samples_reads_as_off(backend):
    backend.config_path.write_text(backend.read_config_text() + "\n[timing]\nburst-samples = 999\n")
    assert backend.read_config().burst_samples == 0


def test_tt_schema_subset(tt_backend):
    assert not tt_backend.supports(FEATURE_DOWN_EVENTS) and not tt_backend.supports(FEATURE_SET_METHOD)
    config = dataclasses.replace(tt_backend.read_config(), down_events=3, set_method="kernel", sample_us=400,
                                 dbus_enabled=True, freq_min=1100)
    text = tt_backend.render_config(tt_backend.read_config_text(), config)
    assert "down-events" not in text and "[gpu]\n" not in text
    assert "sample = 400" in text


@pytest.mark.parametrize("field, value, message", [
    ("freq_min", 2500, "min"), ("load_lower", 0.96, "lower"), ("temp_recovery", 90, "recovery"),
    ("adjust_us", 100, "adjust"), ("ramp_burst", 0.5, "burst"), ("burst_samples", 65, "burst"),
    ("method", "nope", "method"), ("set_method", "x", "set-method"),
])
def test_validate_rejects(field, value, message):
    config = dataclasses.replace(GovernorConfig(freq_min=1000, freq_max=2000), **{field: value})
    with pytest.raises(ValueError, match=message):
        config.validate()
