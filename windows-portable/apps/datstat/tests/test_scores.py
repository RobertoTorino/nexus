# SPDX-License-Identifier: GPL-3.0-or-later
"""The score store: what a round adds, the top list, the file, a damaged file, clearing, and where it is kept (the
suite's folder in %LOCALAPPDATA%); the scores page's lines."""

from __future__ import annotations

import json

from dat_station.panes import score_text, scores_summary, trophy_text, when
from dat_station.quiz import QUICK, Result
from dat_station.scores import PERFECT, Score, ScoreStore, Trophy, default_path


def _result(score: int, category: str = "PS1", perfect: bool = False, round_number: int = 1) -> Result:
    return Result(category, score, round_number, 10, 10, 10 if perfect else 7, 0 if perfect else 3, 12, perfect)


def test_rounds_add_scores_and_perfect_rounds_trophies(tmp_path):
    store = ScoreStore(tmp_path / "scores.json")
    assert store.best() == 0 and store.top() == [] and store.trophies == []
    assert store.add(_result(70), "2026-10-15T10:00:00") == []
    earned = store.add(_result(100, "PS2", perfect=True, round_number=2), "2026-10-15T10:05:00")
    assert [t.kind for t in earned] == [PERFECT] and earned[0].category == "PS2"
    assert store.add(_result(60, QUICK, perfect=True)) == []       # the quick quiz saves nothing
    assert store.best() == 100 and [s.score for s in store.top()] == [100, 70]
    assert store.top(1)[0].round == 2
    data = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    assert [s["score"] for s in data["scores"]] == [70, 100] and data["trophies"][0]["when"] == "2026-10-15T10:05:00"
    again = ScoreStore(tmp_path / "scores.json")
    assert again.best() == 100 and len(again.trophies) == 1 and len(again.scores) == 2
    again.clear()
    assert again.scores == [] and ScoreStore(tmp_path / "scores.json").trophies == []


def test_a_damaged_or_missing_file_is_an_empty_store(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text("{not json", encoding="utf-8")
    assert ScoreStore(path).scores == []
    path.write_text(json.dumps({"scores": [{"score": "x"}, {"score": 5, "category": "ALL"}], "trophies": 3}),
                    encoding="utf-8")
    store = ScoreStore(path)
    assert [s.score for s in store.scores] == [5] and store.trophies == []
    assert ScoreStore(tmp_path / "missing" / "scores.json").best() == 0


def test_the_scores_are_in_the_suites_folder(tmp_path):
    expected = tmp_path / "Local" / "windows-portable-suite" / "windows-portable-datstat" / "scores.json"
    assert default_path() == expected                               # LOCALAPPDATA from conftest
    store = ScoreStore()
    store.add(_result(10))
    assert expected.is_file()


def test_the_pages_lines():
    assert when("2026-10-15T10:05:00") == "2026-10-15 10:05:00" and when("") == ""
    assert score_text(1, Score(100, "PS2", 2, "2026-10-15T10:05:00")) == \
        "1.  100  ·  PS2  ·  round 2  ·  2026-10-15 10:05:00"
    assert trophy_text(Trophy(PERFECT, "PS2", "2026-10-15T10:05:00")) == "Perfect  ·  PS2  ·  2026-10-15 10:05:00"


def test_the_summary(tmp_path):
    store = ScoreStore(tmp_path / "scores.json")
    store.add(_result(100, perfect=True), "2026-10-15T10:05:00")
    store.add(_result(70), "2026-10-15T10:06:00")
    assert scores_summary(store) == ("Best score: 100. 2 rounds played, 1 trophies earned. The quick quiz is not "
                                     "counted.")
