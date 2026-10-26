# SPDX-License-Identifier: GPL-3.0-or-later
"""The unlock gate: the 8C/16T unlock is accepted only when the control, the post-control, every new core and the
combined item passed every round, as bc250-cores-bisect.sh's own summary decides."""

from __future__ import annotations

import pytest

from cores_unlock.gate import check, verdict
from conftest import all_passed


def test_verdicts():
    assert verdict([]) == "none"
    assert verdict(["PASS", "PASS"]) == "good"
    assert verdict(["MCE", "VERIFY"]) == "bad"
    assert verdict(["PASS", "MCE"]) == "random"


def test_no_results(state, tmp_path):
    result = check(state(phase=None))
    assert not result.accepted and "Run that script first" in result.reasons[0]


def test_a_finished_clean_bisect_is_accepted(state):
    result = check(state(runs=all_passed()))
    assert result.accepted
    assert result.base_cores == [0, 1, 2, 4, 5, 6] and result.new_cores == [3, 7]
    assert result.core_verdicts == {3: "good", 7: "good"}
    assert "passed every one of 2 round(s)" in result.reasons[0]


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"phase": "control", "runs": [(1, "control", "PASS")]}, "hasn't started yet"),
    ({"runs": all_passed(), "pending": True}, "still marked as in progress"),
    ({"rounds": 0, "runs": all_passed()}, "No valid round count"),
    ({"runs": [(1, "control", "MCE"), *all_passed()[1:]]}, "The control (stock 6C/12T"),
    ({"runs": [r for r in all_passed() if r[1] != "control"]}, "No control result"),
    ({"runs": [*all_passed()[:1], (1, "post-control", "VERIFY"), *all_passed()[2:]]}, "POST-CONTROL failed"),
    ({"runs": all_passed()[:5]}, "isn't finished: 4 of 8"),
])
def test_rejections(state, kwargs, reason):
    result = check(state(**kwargs))
    assert not result.accepted
    assert any(reason in line for line in result.reasons), result.reasons


def test_a_failing_core_rejects_the_whole_unlock(state):
    runs = [run if run[1] != "core7" or run[0] != 2 else (2, "core7", "MCE") for run in all_passed()]
    result = check(state(runs=runs))
    assert not result.accepted
    assert result.core_verdicts == {3: "good", 7: "random"}
    assert "core7: PASS MCE (RANDOM)" in result.reasons
    assert "power or heat" in result.reasons[-1]


def test_aborted_attempts_do_not_count(state):
    result = check(state(runs=[*all_passed(), (2, "core3", "ABORTED")]))
    assert result.accepted


def test_notes_do_not_block(state):
    runs = [run for run in all_passed() if not (run[1] == "control" and run[0] == 2)]
    runs = [(*run, 300) if run[1] == "core3" else run for run in runs]
    result = check(state(runs=runs))
    assert result.accepted
    assert any("control ran 1 round(s)" in line for line in result.reasons)
    assert any("different load than the current 600s (core3)" in line for line in result.reasons)
