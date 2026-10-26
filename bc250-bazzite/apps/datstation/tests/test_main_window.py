# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the tiles open their pages and Back or Escape returns, the user guides open the browser, the Steam
state, the quiz page through a round, the scores page and the news page with a test feed."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from bc250_core import steam

from datstation import news
from datstation.front_page import COLUMNS, FEATURES, KEYS, ROWS
from datstation.main_window import GUIDES_URL, MainWindow
from datstation.news import NewsItem
from datstation.quiz import ALL, QUICK, State
from datstation.quiz_page import Music, QuizPage
from datstation.scores import ScoreStore
from conftest import FIXTURES


@pytest.fixture
def opened():
    return []


@pytest.fixture
def window(qapp, tmp_path, opened, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"unexpected warning: {a[1:3]}"))
    monkeypatch.setattr(steam, "steam_running", lambda: False)
    monkeypatch.setattr(steam, "game_mode", lambda: False)
    steam_dir = tmp_path / "Steam" / "userdata" / "1000" / "config"
    steam_dir.mkdir(parents=True)
    launcher = tmp_path / "bin" / "bazzite-datstation"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n")
    win = MainWindow(ScoreStore(tmp_path / "scores.json"), steam_dir=tmp_path / "Steam",
                     opener=lambda url: opened.append(url) or True, launcher=launcher)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_the_tiles_open_their_pages_and_back_returns(window, opened):
    assert window.stack.currentWidget() is window.front
    assert [tile.feature.key for tile in window.front.tiles] == list(KEYS)
    for key in ("history", "versions", "regions", "scores", "quiz"):
        window.front.tile(key).click()
        assert window.stack.currentWidget() is window.pages[key]
        assert window.pages[key].page_title in window.pages[key].title.text()
        window.pages[key].back_button.click()
        assert window.stack.currentWidget() is window.front
        assert window.focusWidget() is window.front.tile(key)
    window.open("regions")
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.stack.currentWidget() is window.front
    window.front.tile("guides").click()
    assert opened == [GUIDES_URL] and window.stack.currentWidget() is window.front


def test_arrow_keys_move_between_tiles(window):
    window.front.focus_tile("quiz")
    QTest.keyClick(window.front, Qt.Key.Key_Right)
    assert window.focusWidget() is window.front.tile("history")
    QTest.keyClick(window.front, Qt.Key.Key_Down)
    assert window.focusWidget() is window.front.tile("news")
    QTest.keyClick(window.front, Qt.Key.Key_Left)
    assert window.focusWidget() is window.front.tile("guides")
    QTest.keyClick(window.front, Qt.Key.Key_Up)
    assert window.focusWidget() is window.front.tile("quiz")
    QTest.keyClick(window.front, Qt.Key.Key_Up)                    # the edge: the focus stays
    assert window.focusWidget() is window.front.tile("quiz")
    window.front.focus_tile("news")
    QTest.keyClick(window.front, Qt.Key.Key_Down)                  # a Coming Soon slot below: the focus stays
    assert window.focusWidget() is window.front.tile("news")


def test_four_by_four_with_coming_soon_in_the_empty_slots(window):
    front = window.front
    assert len(front.tiles) + len(front.coming_soon) == COLUMNS * ROWS == 16
    assert all(not slot.isEnabled() and slot.text() == "Coming Soon" and slot.focusPolicy() == Qt.FocusPolicy.NoFocus
               for slot in front.coming_soon)
    row = [front.tiles[n] for n in range(COLUMNS)]
    widths = [tile.width() for tile in row]
    assert len({tile.y() for tile in row}) == 1 and max(widths) - min(widths) <= 1          # the columns share the width
    right = row[-1].mapTo(front, row[-1].rect().topRight()).x()
    assert right > front.width() - 40                                   # the row fills the width: no gap on the right


def test_the_menu_looks_like_back_and_the_state_stands_on_the_titles_baseline(window):
    assert window.settings_button.property("quiet") is True
    assert window.pages["quiz"].back_button.property("quiet") is True
    title, state = window.header.title, window.steam_state.label
    title_baseline = title.mapTo(window, title.rect().bottomLeft()).y() - title.fontMetrics().descent()
    state_baseline = state.mapTo(window, state.rect().bottomLeft()).y() - state.fontMetrics().descent()
    assert abs(title_baseline - state_baseline) <= 1


def test_the_steam_state_and_adding_to_steam(window, qapp, monkeypatch):
    assert window.steam_state.text() == "Not in Steam" and not window.remove_steam_action.isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(steam, "with_steam_closed", lambda change: change() or False)
    window.add_to_steam()
    assert window.worker is not None
    window.worker.wait(10000)
    QTest.qWait(50)
    assert window.steam_state.text() == "In Steam" and window.remove_steam_action.isEnabled()
    assert "was added to Steam" in window.statusBar().currentMessage()
    window.remove_from_steam()
    window.worker.wait(10000)
    QTest.qWait(50)
    assert window.steam_state.text() == "Not in Steam"


def test_adding_is_refused_in_game_mode(window, monkeypatch):
    monkeypatch.setattr(steam, "game_mode", lambda: True)
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    window.add_to_steam()
    assert window.worker is None and told and "Desktop Mode" in told[0]


def test_the_quiz_page_plays_a_round(qapp, tmp_path, questions):
    store = ScoreStore(tmp_path / "scores.json")
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "t", "t")
    page = QuizPage(store, settings, questions, Music(tmp_path / "no-music.ogg"))
    page.quiz.rng = random.Random(7)
    page.show()
    page.activate()
    assert page.screens.currentIndex() == 0 and page.quick_button.isVisible()
    assert page.category_buttons["PS1"].toolTip() == "4 questions"
    page.category_buttons["PS1"].click()
    assert page.screens.currentIndex() == 1 and page.tick_timer.isActive()
    question = page.quiz.current
    shown = [b for b in page.option_buttons if b.isVisible()]
    assert len(shown) == len(question.options) and shown[0].text().startswith("A: ")
    # A wrong answer: the right one turns green, the chosen one red, the feedback names the right letter.
    wrong_index = next(i for i, o in enumerate(question.options) if o != question.correct)
    page._answer(wrong_index)
    assert page.quiz.wrong == 1 and page.feedback_timer.isActive()
    assert shown[wrong_index].property("result") == "wrong"
    assert "is incorrect" in page.feedback_label.text() or "Incorrect:" in page.feedback_label.text()
    page.feedback_timer.stop()
    page._advance()
    assert page.quiz.answered == 1 and page.feedback_label.text() == ""
    page.toggle_pause()
    assert page.play_stack.currentIndex() == 1 and page.quiz.paused
    page.toggle_pause()
    assert page.play_stack.currentIndex() == 0
    page.skip_button.click()
    assert page.quiz.answered == 2
    # The rest right: the category runs out after four questions, so the round ends early.
    while page.quiz.state is State.PLAYING:
        page._answer(page.quiz.current.options.index(page.quiz.current.correct))
        page.feedback_timer.stop()
        page._advance()
    assert page.screens.currentIndex() == 2 and not page.tick_timer.isActive()
    assert page.results_category.text() == "PS1" and page.again_button.text().endswith("Retry")
    assert page.trophy_label.text() == "Score saved." and len(store.scores) == 1
    assert not page.perfect_label.isVisible()
    page.again_button.click()
    assert page.screens.currentIndex() == 1 and page.quiz.round == 1
    page.show_categories()
    assert page.screens.currentIndex() == 0 and page.quiz.state is State.SELECTING


def test_a_perfect_quick_quiz_and_the_mute_setting(qapp, tmp_path, questions):
    store = ScoreStore(tmp_path / "scores.json")
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "t", "t2")
    page = QuizPage(store, settings, questions, Music(tmp_path / "no-music.ogg"))
    page.show()
    assert not page.muted and page.mute_button.text().endswith("Music on")
    page.mute_button.click()
    assert page.muted and page.mute_button.text().endswith("Music off")
    page.start(QUICK)
    while page.quiz.state is State.PLAYING:
        page._answer(page.quiz.current.options.index(page.quiz.current.correct))
        page.feedback_timer.stop()
        page._advance()
    assert page.perfect_label.isVisible() and page.trophy_label.text() == "Quick quiz: nothing saved."
    assert not page.review_label.isVisible() and store.scores == [] and store.trophies == []
    page.start(ALL)
    while page.quiz.state is State.PLAYING:
        page._answer(page.quiz.current.options.index(page.quiz.current.correct))
        page.feedback_timer.stop()
        page._advance()
    assert page.again_button.text().endswith("Next round") and page.trophy_label.text().startswith("Trophy earned")
    assert page.star_label.isVisible() and len(store.trophies) == 1
    page.again_button.click()
    assert page.quiz.round == 2 and page.round_value.text() == "2"


def test_the_scores_page_shows_the_store(window, tmp_path, monkeypatch):
    from datstation.quiz import Result
    window.store.add(Result("PS2", 120, 2, 15, 15, 15, 0, 30, True), "2026-10-15T09:00:00")
    window.open("scores")
    html = window.pages["scores"].view.toPlainText()
    assert "Best score: 120" in html and "Perfect" in html and "PS2" in html
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.pages["scores"].clear_button.click()
    assert window.store.best() == 0 and "No scores yet" in window.pages["scores"].view.toPlainText()


def test_the_news_page_with_a_test_feed(window, opened, monkeypatch):
    page = window.pages["news"]
    page.feed_url = (FIXTURES / "feed.xml").resolve().as_uri()
    window.open("news")
    assert page.worker is not None
    page.worker.wait(10000)
    QTest.qWait(50)
    assert len(page.items) == 10 and "Example Racing" in page.view.toPlainText()
    page.on_link(QUrl(page.items[0].link))
    assert opened == [page.items[0].link]
    page.on_link(QUrl("https://example.com/"))
    assert opened == [page.items[0].link] and "Blocked" in window.statusBar().currentMessage()
    page.upcoming_button.click()
    assert opened[-1] == news.UPCOMING_URL
    page.show_error("HTTP 503 while loading the PlayStation feed.")
    assert "Could not load announcements" in page.view.toPlainText() and page.items == []


def test_the_history_page_links(window, opened):
    page = window.pages["history"]
    window.open("history")
    assert "Lifetime totals" in page.view.toPlainText()
    page.on_link(QUrl("search:PlayStation 2 (2000)"))
    assert opened and opened[-1].startswith("https://www.google.com/search?q=PlayStation%202")
    assert "Searching the web for pictures of PlayStation 2 (2000)." in window.statusBar().currentMessage()


def test_the_versions_page_switches_systems(window):
    page = window.pages["versions"]
    window.open("versions")
    assert page.systems.currentRow() == 0 and "PlayStation 6" in page.view.toPlainText()
    page.systems.setCurrentRow(8)
    text = page.view.toPlainText()
    assert "PlayStation 1 System Software" in text and "DTL-H1000" in text and "46 versions" in text
    assert Path(page.folder).is_dir()


def test_the_quiz_tile_counts_the_shipped_questions():
    from datstation.quiz import load_questions
    assert FEATURES[0].key == "quiz"
    assert FEATURES[0].text.startswith(f"{len(load_questions()):,} questions in 11 categories")
