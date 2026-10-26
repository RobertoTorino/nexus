# SPDX-License-Identifier: GPL-3.0-or-later
"""The bisect GUI's choices as a bc250-cu-bisect.sh command line, and their validation."""

from __future__ import annotations

import shlex

import pytest

from cu_bisect.options import BASELINE_PRESETS, MASK_RE, BisectOptions


def test_defaults_are_the_scripts_own():
    assert BisectOptions().to_args() == ["-t", "180", "-r", "3"]
    assert BisectOptions().validate() == []


def test_every_switch_reaches_the_command_line():
    opts = BisectOptions(time_secs=300, rounds=5, baseline="0x1f,0x1f,0x1f,0x1f", control_only=True,
                         same_boot=True, unattended=True, no_watch=True)
    assert opts.to_args() == ["-t", "300", "-r", "5", "--baseline", "0x1f,0x1f,0x1f,0x1f", "--control-only",
                              "--same-boot", "--auto", "--no-watch"]


def test_command_is_quoted_for_bash():
    command = BisectOptions().to_command("/home/u/my apps/bc250-cu-bisect.sh")
    assert shlex.split(command) == ["bash", "/home/u/my apps/bc250-cu-bisect.sh", "-t", "180", "-r", "3"]


@pytest.mark.parametrize(("opts", "message"), [
    (BisectOptions(time_secs=59), "at least 60 seconds"),
    (BisectOptions(rounds=10), "between 1 and 9"),
    (BisectOptions(rounds=1), "at least 2"),
    (BisectOptions(baseline="0x07,0x07,0x07"), "4 masks"),
])
def test_validation(opts, message):
    assert any(message in error for error in opts.validate())


def test_one_round_is_allowed_for_a_control_only_retest():
    assert BisectOptions(rounds=1, control_only=True).validate() == []


def test_presets_are_valid_masks():
    masks = [value for value in BASELINE_PRESETS.values() if value]
    assert masks == ["0x07,0x07,0x07,0x07", "0x1f,0x1f,0x1f,0x1f"]
    assert all(MASK_RE.match(mask) for mask in masks)
    assert list(BASELINE_PRESETS.values())[0] is None          # auto-detect passes no --baseline
