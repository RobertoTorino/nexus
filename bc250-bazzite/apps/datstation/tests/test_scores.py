# SPDX-License-Identifier: GPL-3.0-or-later
"""The score store: what a round adds, the top list, the file, a damaged file, and clearing."""

from __future__ import annotations

import json

from datstation.quiz import QUICK, Result
from datstation.scores import PERFECT, ScoreStore, default_path


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


def test_the_default_path_is_under_the_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert default_path() == tmp_path / "share" / "bazzite-datstation" / "scores.json"
    store = ScoreStore()
    store.add(_result(10))
    assert (tmp_path / "share" / "bazzite-datstation" / "scores.json").is_file()
