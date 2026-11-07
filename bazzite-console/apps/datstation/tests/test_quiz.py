# SPDX-License-Identifier: GPL-3.0-or-later
"""The quiz engine: the shipped questions, a round's clock and score, skips, the end of a round, the next round
and the quick quiz, against the rules of the Android app."""

from __future__ import annotations

import random

import pytest

from datstation import quiz
from datstation.quiz import (ALL, CATEGORIES, DATA_CATEGORIES, PENALTY, QUICK, QUICK_QUESTIONS,
                                     ROUND_GROWTH, ROUND_QUESTIONS, START_TIME, TRUE_FALSE, Quiz, State,
                                     load_questions, matches, review)


def test_the_shipped_questions_are_complete_and_answerable():
    questions = load_questions()
    assert len(questions) == 1436
    assert all(q.correct in q.options for q in questions)
    assert all(q.type in ("MC", "TF") and q.text and q.points > 0 for q in questions)
    assert len({q.id for q in questions}) == len(questions)
    categories = {q.category for q in questions}
    assert set(DATA_CATEGORIES.values()) == categories             # every category of the menu has questions
    game = Quiz(questions)
    assert all(game.count(c) > 0 for c in CATEGORIES)
    assert game.count("APPS") == 100 and game.count(TRUE_FALSE) == 230
    assert sum(1 for q in questions if q.explanation) == 56       # the "False: ..." answers, split


def test_matching_categories(questions):
    assert all(matches(q, ALL) and matches(q, QUICK) for q in questions)
    assert [q.id for q in questions if matches(q, TRUE_FALSE)] == ["tf1", "tf2"]
    assert [q.id for q in questions if matches(q, "PS1")] == ["q0", "q4", "q8", "tf2"]
    assert [q.id for q in questions if matches(q, "APPS")] == ["q3", "q7"]


def test_a_round_scores_and_keeps_time(questions):
    game = Quiz(questions, random.Random(1))
    assert game.state is State.SELECTING
    game.start(ALL)
    assert game.state is State.PLAYING and game.time_left == START_TIME and game.in_round == ROUND_QUESTIONS
    assert game.current is not None and game.current.id in game.asked
    first = game.current
    assert set(first.options) == set(next(q for q in questions if q.id == first.id).options)
    assert game.tick() is False and game.time_left == START_TIME - 1
    assert game.submit(first.correct) is True
    assert game.score == 10 and game.correct == 1 and game.time_left == START_TIME - 1 + 5
    assert game.submit(first.correct) is None                      # already answered
    assert game.tick() is False and game.time_left == START_TIME + 4   # the clock stops while the answer shows
    assert game.delay_ms == quiz.CORRECT_DELAY_MS
    game.advance()
    assert game.answered == 1 and game.feedback is None and game.current is not first
    wrong = next(o for o in game.current.options if o != game.current.correct)
    assert game.submit(wrong) is False
    assert game.wrong == 1 and game.perfect is False and game.time_left == START_TIME + 4 - PENALTY
    assert game.delay_ms == quiz.WRONG_DELAY_MS
    assert game.letter(game.current.correct) in "ABCD" and game.letter("nothing") == ""
    game.advance()
    assert game.answered == 2
    assert len(game.asked) == 3                                    # no question twice in a game


def test_skip_pause_and_running_out_of_time(questions):
    game = Quiz(questions, random.Random(2))
    game.start("PS1")                                              # four questions: q0, q4, q8, tf2
    assert game.skip() is True
    assert game.wrong == 1 and game.answered == 1 and game.time_left == START_TIME - PENALTY and not game.perfect
    assert game.toggle_pause() is True
    assert game.tick() is False and game.time_left == START_TIME - PENALTY   # paused: no time passes
    assert game.submit(game.current.correct) is None and game.skip() is False
    assert game.toggle_pause() is False
    ended = [game.tick() for _ in range(START_TIME)]
    assert ended.count(True) == 1 and ended[-1] is False           # the tick that reached zero ended the round
    assert game.state is State.RESULTS and game.time_left == 0
    result = game.result
    assert result is not None and not result.completed and not result.perfect and result.answered == 1
    assert game.retry_needed
    assert game.tick() is False and game.submit("Right") is None  # nothing moves after the end


def test_a_category_runs_out_of_questions(questions):
    finished = []
    game = Quiz(questions, random.Random(3), on_finished=finished.append)
    game.start("APPS")                                             # two questions, a round wants ten
    for _ in range(2):
        game.submit(game.current.correct)
        game.advance()
    assert game.state is State.RESULTS and finished and finished[0].answered == 2
    assert not finished[0].completed and not finished[0].perfect and finished[0].score == 20


def test_a_perfect_round_then_the_next_and_the_results(questions):
    finished = []
    game = Quiz(questions, random.Random(4), on_finished=finished.append)
    game.start(ALL)
    for _ in range(ROUND_QUESTIONS):
        assert game.submit(game.current.correct) is True
        game.advance()
    assert game.state is State.RESULTS
    result = finished[-1]
    assert result.completed and result.perfect and result.score == 100 and result.saves
    assert game.percentage == 100 and not game.retry_needed
    assert review(game.percentage) == ("You are a PlayStation Genius!", "gold")
    time_before, score_before = game.time_left, game.score
    game.next_round()
    assert game.state is State.PLAYING and game.round == 2 and game.in_round == ROUND_QUESTIONS + ROUND_GROWTH
    assert game.answered == 0 and game.perfect and game.score == score_before and game.time_left == time_before
    assert len(game.asked) == ROUND_QUESTIONS + 1                  # the pool continues; only two are left
    game.restart()
    assert game.round == 1 and game.score == 0 and game.time_left == START_TIME and len(game.asked) == 1


def test_the_quick_quiz_is_short_and_not_saved(questions):
    finished = []
    game = Quiz(questions, random.Random(5), on_finished=finished.append)
    game.start(QUICK)
    assert game.in_round == QUICK_QUESTIONS
    for _ in range(QUICK_QUESTIONS):
        game.submit(game.current.correct)
        game.advance()
    assert finished[-1].perfect and not finished[-1].saves and game.retry_needed
    game.to_selection()
    assert game.state is State.SELECTING and game.current is None


@pytest.mark.parametrize("percentage, text, star", [
    (0, "You can do better try again.", ""), (24, "You can do better try again.", ""),
    (25, "You improved, but still below average.", ""), (50, "You made great progress, keep going!", "bronze"),
    (74, "You made great progress, keep going!", "bronze"), (75, "Great! You are a PlayStation fact-checker!", "silver"),
    (95, "You are a PlayStation Genius!", "gold"), (100, "You are a PlayStation Genius!", "gold")])
def test_the_review_by_percentage(percentage, text, star):
    assert review(percentage) == (text, star)
