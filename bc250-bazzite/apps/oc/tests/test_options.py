# SPDX-License-Identifier: GPL-3.0-or-later
"""The sweep options as a bc250-gpu-oc-bisect.sh command line, and the hard rails the script also enforces."""

from __future__ import annotations

import shlex

import pytest

from oc_bisect.options import HARD_MAX_FREQ, HARD_MAX_VOLT, HARD_MIN_VOLT, SweepOptions


def test_defaults_pass_only_time_and_rounds():
    assert SweepOptions().to_args() == ["-t", "180", "-r", "3"]
    assert SweepOptions().validate() == []


def test_one_ladder_and_changed_values():
    assert SweepOptions(sweep_uv=False, max_freq=2000, freq_step=25, oc_volt=1000).to_args() == [
        "-t", "180", "-r", "3", "--oc", "--max-freq", "2000", "--freq-step", "25", "--oc-volt", "1000"]
    assert SweepOptions(sweep_oc=False, min_volt=800, volt_step=10, per_boot=True).to_args() == [
        "-t", "180", "-r", "3", "--uv", "--min-volt", "800", "--volt-step", "10", "--per-boot"]


def test_values_of_the_other_ladder_are_left_out():
    assert SweepOptions(sweep_uv=False, min_volt=800).to_args() == ["-t", "180", "-r", "3", "--oc"]


def test_command_is_quoted_for_bash():
    command = SweepOptions().to_command("/opt/bc250-gpu-oc-bisect/bc250-gpu-oc-bisect.sh")
    assert shlex.split(command)[:2] == ["bash", "/opt/bc250-gpu-oc-bisect/bc250-gpu-oc-bisect.sh"]


@pytest.mark.parametrize(("opts", "message"), [
    (SweepOptions(time_secs=59), "at least 60 seconds"),
    (SweepOptions(rounds=1), "between 2 and 9"),
    (SweepOptions(sweep_oc=False, sweep_uv=False), "Pick at least one sweep"),
    (SweepOptions(max_freq=HARD_MAX_FREQ + 1), "hard ceiling"),
    (SweepOptions(min_volt=HARD_MIN_VOLT - 1), "hard floor"),
    (SweepOptions(oc_volt=HARD_MAX_VOLT + 1), "hard ceiling"),
    (SweepOptions(freq_step=10), "25 MHz or more"),
    (SweepOptions(volt_step=1), "5 mV or more"),
])
def test_validation(opts, message):
    assert any(message in error for error in opts.validate())


def test_the_hard_rails():
    assert (HARD_MAX_FREQ, HARD_MAX_VOLT, HARD_MIN_VOLT) == (2500, 1100, 700)
