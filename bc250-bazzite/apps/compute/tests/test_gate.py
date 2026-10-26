# SPDX-License-Identifier: GPL-3.0-or-later
"""The unlock gate: a mask is accepted only after bc250-cu-bisect.sh retested it as its own baseline and every
round passed, at one of the three even levels (24, 32 or 40 CUs)."""

from __future__ import annotations

import pytest

from cu_unlock.gate import check, cu_count, even_level

FULL = "0x1f,0x1f,0x1f,0x1f"
PASSED = [(1, "control", "PASS"), (2, "control", "PASS"), (3, "control", "PASS")]


def test_cu_counts_and_levels():
    assert cu_count("0x07,0x07,0x07,0x07") == 24
    assert cu_count("0x0f,0x0f,0x0f,0x0f") == 32
    assert cu_count(FULL) == 40
    assert even_level(FULL) == 5 and even_level("0x07,0x07,0x07,0x07") == 3
    assert even_level("0x1f,0x0f,0x1f,0x1f") is None          # uneven rows
    assert even_level("0x03,0x03,0x03,0x03") is None          # 2 per row is not a level


def test_no_results(state):
    state()
    result = check()
    assert not result.accepted and "Run that script first" in result.reasons[0]


def test_a_fully_retested_mask_is_accepted(state):
    state(FULL, rounds=3, runs=PASSED)
    result = check()
    assert result.accepted and result.masks == FULL and result.cu_total == 40
    assert "passed 3 retest round(s)" in result.reasons[0]


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"base": "none"}, "No usable baseline"),
    ({"base": FULL, "runs": PASSED, "pending": True}, "still marked as in progress"),
    ({"base": "0x1f,0x0f,0x1f,0x1f", "runs": PASSED}, "uneven across the 4 rows"),
    ({"base": "0x03,0x03,0x03,0x03", "runs": PASSED}, "Only 3 per row"),
    ({"base": FULL}, "No attempts recorded"),
    ({"base": FULL, "runs": [*PASSED, (1, "SE0.SH0.WGP4", "PASS")]}, "under individual test"),
    ({"base": FULL, "runs": PASSED[:2]}, "Only 2 of 3 retest round(s)"),
    ({"base": FULL, "runs": [*PASSED[:2], (3, "control", "DRIFT")]}, "round 3: DRIFT"),
    ({"base": FULL, "runs": [*PASSED[:2], (3, "control", "ABORTED")]}, "round 3: ABORTED"),
])
def test_rejections(state, kwargs, reason):
    state(**kwargs)
    result = check()
    assert not result.accepted
    assert any(reason in line for line in result.reasons), result.reasons


def test_uneven_mask_suggests_an_even_retest(state):
    state("0x1f,0x0f,0x1f,0x1f", runs=PASSED)
    assert "--baseline 0x0f,0x0f,0x0f,0x0f --control-only" in check().reasons[1]
