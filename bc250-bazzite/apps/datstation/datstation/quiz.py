# SPDX-License-Identifier: GPL-3.0-or-later
"""The quiz itself, without Qt: the questions (data/questions.json) and one game of rounds, as the Android app plays
it (PlayStationQuiz.kt's QuizViewModel).

A round asks a number of questions against one clock: 42 seconds at the start, 5 more for a right answer, 5 less
for a wrong one or a skip. The clock stops while an answer is shown and while the game is paused. A round is
complete when all its questions were answered; it ends early when the clock runs out. After a complete round with
no wrong answer the next round has 5 questions more, with the score and the clock carried over; otherwise the game
is played again from the start. Questions are not asked twice in one game until the pool of the category is used
up. The quick quiz is 6 questions and is not saved.

The page drives it: tick() once a second, submit() or skip() on a click, advance() when the answer was shown long
enough (CORRECT_DELAY_MS or WRONG_DELAY_MS), next_round(), restart() or to_selection() from the results."""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import DATA_DIR

QUESTIONS_FILE = DATA_DIR / "questions.json"

QUICK = "QUICK"
ALL = "ALL"
TRUE_FALSE = "TRUE/FALSE"
CATEGORIES = (ALL, TRUE_FALSE, "PS1", "PS2", "PS3", "PS4", "PS5", "PSVITA", "PSP", "CONTROLLER", "GENERAL",
              "DIALOGUE", "APPS")
# The category names in the data file. The Android app looked "APPS" up as "Apps", which the data does not have.
DATA_CATEGORIES = {"PS1": "PlayStation1", "PS2": "PlayStation2", "PS3": "PlayStation3", "PS4": "PlayStation4",
                   "PS5": "PlayStation5", "PSVITA": "PlayStationVita", "PSP": "PlayStationPortable",
                   "CONTROLLER": "Controller", "GENERAL": "General", "DIALOGUE": "Dialogue", "APPS": "App"}

START_TIME = 42
QUICK_QUESTIONS = 6
ROUND_QUESTIONS = 10
ROUND_GROWTH = 5
BONUS = 5                               # seconds for a right answer
PENALTY = 5                             # seconds for a wrong answer or a skip
CORRECT_DELAY_MS = 2000                 # how long a right answer is shown before the next question
WRONG_DELAY_MS = 4000
LETTERS = "ABCDEFGH"

# The review of a complete round, by the share of right answers, and the star that goes with it.
REVIEWS = ((25, "You can do better try again.", ""),
           (50, "You improved, but still below average.", ""),
           (75, "You made great progress, keep going!", "bronze"),
           (95, "Great! You are a PlayStation fact-checker!", "silver"),
           (101, "You are a PlayStation Genius!", "gold"))


class State(Enum):
    SELECTING = "selecting"
    PLAYING = "playing"
    RESULTS = "results"


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    type: str                           # "MC" (several options) or "TF" (True / False)
    category: str
    options: tuple[str, ...]
    correct: str
    points: int = 10
    explanation: str = ""               # why the answer is what it is, when the data has it


@dataclass(frozen=True)
class Result:
    """How a round ended, for the scores: saved unless it was the quick quiz."""
    category: str
    score: int
    round: int
    in_round: int
    answered: int
    correct: int
    wrong: int
    time_left: int
    perfect: bool                       # complete, and every answer right

    @property
    def completed(self) -> bool:
        return self.answered >= self.in_round

    @property
    def saves(self) -> bool:
        return self.category != QUICK


def load_questions(path: Path = QUESTIONS_FILE) -> list[Question]:
    with open(path, encoding="utf-8") as handle:
        items = json.load(handle)
    questions = []
    for item in items:
        options = tuple(str(option) for option in item["options"])
        questions.append(Question(id=str(item["id"]), text=str(item["text"]), type=str(item.get("type", "MC")),
                                  category=str(item["category"]), options=options,
                                  correct=str(item["correct_answer"]), points=int(item.get("points", 10)),
                                  explanation=str(item.get("explanation", ""))))
    return questions


def matches(question: Question, category: str) -> bool:
    if category in (ALL, QUICK):
        return True
    if category == TRUE_FALSE:
        return question.type == "TF"
    return question.category == DATA_CATEGORIES.get(category, category)


def review(percentage: int) -> tuple[str, str]:
    """The review text and star ("", "bronze", "silver", "gold") of a complete round."""
    for limit, text, star in REVIEWS:
        if percentage < limit:
            return text, star
    return REVIEWS[-1][1], REVIEWS[-1][2]


class Quiz:
    def __init__(self, questions: Iterable[Question], rng: random.Random | None = None,
                 on_finished: Callable[[Result], None] | None = None):
        self.questions = list(questions)
        self.rng = rng or random.Random()
        self.on_finished = on_finished
        self.state = State.SELECTING
        self.category = ALL
        self.score = 0
        self.round = 1
        self.in_round = ROUND_QUESTIONS
        self.answered = 0
        self.correct = 0
        self.wrong = 0
        self.time_left = START_TIME
        self.perfect = True
        self.paused = False
        self.feedback: tuple[str, bool] | None = None       # the option chosen and whether it was right
        self.current: Question | None = None
        self.asked: set[str] = set()
        self.result: Result | None = None

    # -- a game -------------------------------------------------------------------------------------------------

    def start(self, category: str) -> None:
        """A new game in *category*: the first round, the clock at the start, no question asked yet."""
        self.category = category
        self.score = 0
        self.round = 1
        self.in_round = QUICK_QUESTIONS if category == QUICK else ROUND_QUESTIONS
        self.answered = self.correct = self.wrong = 0
        self.time_left = START_TIME
        self.perfect = True
        self.paused = False
        self.feedback = None
        self.result = None
        self.asked.clear()
        self.state = State.PLAYING
        self._next_question()

    def restart(self) -> None:
        self.start(self.category)

    def next_round(self) -> None:
        """After a perfect round: more questions, the score and the clock kept."""
        self.round += 1
        self.in_round += ROUND_GROWTH
        self.answered = self.correct = self.wrong = 0
        self.perfect = True
        self.feedback = None
        self.result = None
        self.state = State.PLAYING
        self._next_question()

    def to_selection(self) -> None:
        self.state = State.SELECTING
        self.paused = False
        self.feedback = None
        self.current = None

    # -- a question ---------------------------------------------------------------------------------------------

    def tick(self) -> bool:
        """One second passed. The clock only runs while a question waits for its answer; at zero the round is
        over. Returns whether this tick ended the round."""
        if self.state is not State.PLAYING or self.paused or self.feedback is not None or self.time_left <= 0:
            return False
        self.time_left -= 1
        if self.time_left == 0:
            self.perfect = False
            self._finish()
            return True
        return False

    def submit(self, option: str) -> bool | None:
        """The answer to the current question; None when there is nothing to answer now. The question stays shown
        with the feedback until advance()."""
        if self.state is not State.PLAYING or self.current is None or self.feedback is not None or self.paused:
            return None
        right = option == self.current.correct
        self.feedback = (option, right)
        if right:
            self.score += self.current.points
            self.time_left += BONUS
            self.correct += 1
        else:
            self.time_left = max(0, self.time_left - PENALTY)
            self.perfect = False
            self.wrong += 1
        return right

    def advance(self) -> None:
        """The feedback was shown: on to the next question (or the results)."""
        if self.state is not State.PLAYING or self.feedback is None:
            return
        self.feedback = None
        self.answered += 1
        self._next_question()

    def skip(self) -> bool:
        """Counts as a wrong answer, straight on to the next question."""
        if self.state is not State.PLAYING or self.current is None or self.feedback is not None or self.paused:
            return False
        self.wrong += 1
        self.perfect = False
        self.time_left = max(0, self.time_left - PENALTY)
        self.answered += 1
        self._next_question()
        return True

    def toggle_pause(self) -> bool:
        if self.state is State.PLAYING:
            self.paused = not self.paused
        return self.paused

    @property
    def delay_ms(self) -> int:
        """How long the current feedback is shown."""
        return CORRECT_DELAY_MS if self.feedback and self.feedback[1] else WRONG_DELAY_MS

    def letter(self, option: str) -> str:
        """A, B, C ... of an option of the current question."""
        if self.current is None or option not in self.current.options:
            return ""
        return LETTERS[self.current.options.index(option)]

    # -- the results --------------------------------------------------------------------------------------------

    @property
    def percentage(self) -> int:
        return int(self.correct / self.in_round * 100) if self.in_round else 0

    @property
    def retry_needed(self) -> bool:
        """Whether the results offer Retry (a new game) rather than Next round."""
        return self.wrong > 0 or self.time_left == 0 or self.category == QUICK

    def pool(self, category: str | None = None) -> list[Question]:
        """The questions of a category not asked yet in this game."""
        category = self.category if category is None else category
        return [q for q in self.questions if matches(q, category) and q.id not in self.asked]

    def count(self, category: str) -> int:
        return sum(1 for q in self.questions if matches(q, category))

    # -- internals ----------------------------------------------------------------------------------------------

    def _next_question(self) -> None:
        if self.answered >= self.in_round:
            self._finish()
            return
        pool = self.pool()
        if not pool:
            self._finish()              # the category has no question left: the round ends as it stands
            return
        question = self.rng.choice(pool)
        self.asked.add(question.id)
        options = list(question.options)
        self.rng.shuffle(options)
        self.current = Question(question.id, question.text, question.type, question.category, tuple(options),
                                question.correct, question.points, question.explanation)

    def _finish(self) -> None:
        self.state = State.RESULTS
        self.paused = False
        self.feedback = None
        self.result = Result(self.category, self.score, self.round, self.in_round, self.answered, self.correct,
                             self.wrong, self.time_left, self.perfect and self.answered >= self.in_round)
        if self.on_finished is not None:
            self.on_finished(self.result)
