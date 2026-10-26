# SPDX-License-Identifier: GPL-3.0-or-later
"""The quiz scores and trophies, in ~/.local/share/bazzite-datstation/scores.json (the Android app kept them in its
user database). Every round of a saved game adds a score; a perfect round adds a Perfect trophy. The quick quiz
adds nothing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from bc250_core.platform import data_home

from . import APP_ID
from .quiz import Result

PERFECT = "Perfect"
TOP = 10


@dataclass(frozen=True)
class Score:
    score: int
    category: str
    round: int
    when: str                           # ISO 8601, local time, to the second


@dataclass(frozen=True)
class Trophy:
    kind: str
    category: str
    when: str


def default_path() -> Path:
    return data_home() / APP_ID / "scores.json"


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class ScoreStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.scores: list[Score] = []
        self.trophies: list[Trophy] = []
        self.load()

    def load(self) -> None:
        self.scores, self.trophies = [], []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        scores = data.get("scores")
        for item in scores if isinstance(scores, list) else []:
            try:
                self.scores.append(Score(int(item["score"]), str(item["category"]), int(item.get("round", 1)),
                                         str(item.get("when", ""))))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        trophies = data.get("trophies")
        for item in trophies if isinstance(trophies, list) else []:
            if isinstance(item, dict):
                self.trophies.append(Trophy(str(item.get("kind", PERFECT)), str(item.get("category", "")),
                                            str(item.get("when", ""))))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"scores": [asdict(s) for s in self.scores], "trophies": [asdict(t) for t in self.trophies]}
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def add(self, result: Result, when: str | None = None) -> list[Trophy]:
        """Record a round; returns the trophies it earned (none, or one Perfect)."""
        if not result.saves:
            return []
        when = when or _now()
        self.scores.append(Score(result.score, result.category, result.round, when))
        earned = []
        if result.perfect:
            earned.append(Trophy(PERFECT, result.category, when))
            self.trophies.extend(earned)
        self.save()
        return earned

    def top(self, count: int = TOP) -> list[Score]:
        return sorted(self.scores, key=lambda s: (-s.score, s.when))[:count]

    def best(self) -> int:
        return max((s.score for s in self.scores), default=0)

    def clear(self) -> None:
        self.scores, self.trophies = [], []
        self.save()
