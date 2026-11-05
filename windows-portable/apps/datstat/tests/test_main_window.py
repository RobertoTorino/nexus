# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): it opens on the portable window with the header's battery, date and time and the
front page's tiles, fits the handheld's screen; each tile's page with its buttons: the quiz played through (answers,
skip, pause, the music, the results, a perfect round's trophy, B twice to leave a round), the history's pictures, the
versions and region codes read in their text, the news loaded off the window's thread (a blocked link, a failure),
the scores cleared on a second press, the user guides in the browser; the app in Steam and out again; B goes back
and View exits; the version and the icons are where the checks expect them. Fakes for the controller, the music, the
feed, the browser and Steam: never the real ones."""

from __future__ import annotations

import re
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import BACK, EXIT, VIEW
from bc250_core.portable import INFO as MENU_INFO
from conftest import FIXTURES, make_steam
from dat_station import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, news, steam_shortcut
from dat_station.main_window import GUIDES_URL, MainWindow
from dat_station.quiz import State
from dat_station.quiz_pane import MUTED_KEY
from dat_station.scores import ScoreStore


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


class FakeMusic:
    def __init__(self):
        self.playing = False

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False

    def stop(self):
        self.playing = False


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def make(qapp, monkeypatch=None, questions=None, steam_dir=None, load_news=None, store=None, **kwargs):
    opened = []
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), questions=questions,
                        music=FakeMusic(), steam_dir=steam_dir, store=store,
                        load_news=load_news or (lambda: news.parse_rss((FIXTURES / "feed.xml").read_bytes())),
                        open_url=lambda url: opened.append(url) or True, **kwargs)
    window.opened = opened
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    window.start()
    if monkeypatch is not None:
        monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    return window


def legend(window) -> dict[str, str]:
    return dict(window.legend.items)


def test_the_window_opens_with_the_suites_header(qapp):
    window = make(qapp)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("A", "Open"), MENU_INFO, EXIT]       # no Steam here: no Steam entry
    assert window.front_pane.status.text().startswith("Steam is not installed")
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp):
    window = make(qapp)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_the_tiles_and_their_pane(qapp, monkeypatch):
    window = make(qapp, monkeypatch)
    assert [tile.title.text() for tile in window.tiles.values()] == [
        "PlayStation Quiz", "PlayStation History", "System Versions", "Region Codes", "User Guides", "PS News",
        "Scores & Trophies"]
    assert window.tiles["quiz"].hasFocus() and window.front_pane.title.text() == "PlayStation Quiz"
    assert window.front_pane.text.text().startswith("1,436 questions in 11 categories")
    window.on_action("right")
    assert window.tiles["history"].hasFocus() and window.front_pane.title.text() == "PlayStation History"
    window.on_action("down")
    assert window.tiles["news"].hasFocus()
    window.on_action("left")
    assert window.tiles["guides"].hasFocus() and legend(window)["A"] == "Open in browser"
    window.on_action("accept")                                      # the guides open in the browser
    assert window.opened == [GUIDES_URL] and window.page == "front"
    assert window.front_pane.status.text() == f"Opened {GUIDES_URL} in your browser."
    window.on_action("back")                                        # nowhere to go on the tiles
    assert window.page == "front"
    window.on_action("menu")                                        # the information: about the app
    assert window.popup is not None and "DatStation Android app" in window.popup.text.toPlainText()
    window.on_action("back")
    assert window.popup is None
    window.close()


def answer_right(window) -> None:
    quiz = window.quiz_pane.quiz
    window.quiz_pane.answer(quiz.current.options.index(quiz.current.correct))
    window.quiz_pane.feedback_timer.stop()
    window.quiz_pane._advance()


def test_the_quiz_is_played_with_the_controller(qapp, monkeypatch, questions):
    store = ScoreStore()
    window = make(qapp, monkeypatch, questions=questions, store=store)
    pane = window.quiz_pane
    window.on_action("accept")                                      # the quiz's tile
    assert window.page == "quiz" and pane.screen() == "categories" and pane.quick_row.hasFocus()
    assert window.legend.items == [("A", "Start"), ("LB", "Music off"), MENU_INFO, BACK, EXIT]
    assert pane.status.text() == "Quick quiz: 6 questions from all 12."
    window.on_action("down")                                        # into the categories' grid
    pane.category_rows["ALL"].setFocus()
    window.on_action("right")
    assert pane.category_rows["TRUE/FALSE"].hasFocus() and pane.status.text() == "TRUE/FALSE: 2 questions."
    window.on_action("left")
    assert pane.status.text() == "ALL: 12 questions."
    window.on_action("accept")                                      # a round of ALL
    assert pane.screen() == "playing" and pane.option_rows[0].hasFocus()
    assert pane.music.playing and pane.title.text() == "PlayStation Quiz  ·  ALL"
    assert legend(window) == {"A": "Answer", "X": "Skip (−5 s)", "Y": "Pause", "LB": "Music off",
                              MENU_INFO[0]: "Info", "B": "Back", VIEW: "Exit"}
    question = pane.quiz.current
    wrong = next(n for n, option in enumerate(question.options) if option != question.correct)
    pane.option_rows[wrong].setFocus()
    window.on_action("accept")                                      # A on a wrong answer
    assert pane.option_rows[wrong].result == "wrong"
    assert pane.option_rows[question.options.index(question.correct)].result == "right"
    assert "is incorrect" in pane.feedback_label.text() or pane.feedback_label.text().startswith("Incorrect")
    window.on_action("x")                                           # no skip while the answer shows
    assert pane.status.text().startswith("The answer shows")
    pane.feedback_timer.stop()
    pane._advance()
    window.on_action("y")                                           # Y pauses: the clock and the music stop
    assert pane.screen() == "paused" and not pane.music.playing
    time_left = pane.quiz.time_left
    pane._tick()
    assert pane.quiz.time_left == time_left and legend(window)["Y"] == "Resume"
    window.on_action("y")
    assert pane.screen() == "playing" and pane.music.playing
    window.on_action("x")                                           # X skips: five seconds off
    assert pane.quiz.wrong == 2 and pane.quiz.time_left == time_left - 5
    window.on_action("previous")                                    # LB: the music off, kept
    assert not pane.music.playing and window.settings.value(MUTED_KEY, type=bool) and legend(window)["LB"] == \
        "Music on"
    window.on_action("previous")
    assert pane.music.playing
    window.on_action("back")                                        # B in a round asks first
    assert pane.screen() == "playing" and pane.status.text().startswith("Press B again")
    assert legend(window)["B"] == "Press again"
    window.on_action("back")
    assert pane.screen() == "categories" and pane.quiz.state is State.SELECTING and not pane.music.playing
    assert store.scores == []                                       # a round left is not saved
    window.on_action("back")                                        # B on the categories: the tiles
    assert window.page == "front" and window.tiles["quiz"].hasFocus()
    window.close()


def test_a_perfect_round_earns_a_trophy_and_the_next_round(qapp, monkeypatch, questions):
    store = ScoreStore()
    window = make(qapp, monkeypatch, questions=questions, store=store)
    pane = window.quiz_pane
    window.open("quiz")
    pane.start("ALL")
    for _ in range(10):
        answer_right(window)
    assert pane.screen() == "results" and pane.perfect_row.isVisible()
    assert pane.review_label.text() == "You are a PlayStation Genius!" and pane.star.isVisible()
    assert pane.trophy_label.text() == "Trophy earned: Perfect (ALL). Saved to your scores."
    assert [t.kind for t in store.trophies] == ["Perfect"] and store.best() == 100
    assert legend(window)["A"] == "Next round"
    window.on_action("accept")                                      # A: the next round, five questions more
    assert pane.screen() == "playing" and pane.quiz.round == 2 and pane.quiz.in_round == 15
    pane.quiz.time_left = 1
    pane._tick()                                                    # the clock runs out
    assert pane.screen() == "results" and pane.results_title.text() == "ROUND NOT FINISHED"
    assert legend(window)["A"] == "Retry"
    window.on_action("back")                                        # B on the results: the categories
    assert pane.screen() == "categories"
    window.close()


def test_the_quick_quiz_saves_nothing(qapp, monkeypatch, questions):
    store = ScoreStore()
    window = make(qapp, monkeypatch, questions=questions, store=store)
    window.open("quiz")
    window.on_action("accept")                                      # the quick quiz
    for _ in range(6):
        answer_right(window)
    assert window.quiz_pane.trophy_label.text() == "Quick quiz: nothing saved." and store.scores == []
    assert not window.quiz_pane.review_row.isVisible()
    window.on_action("accept")                                      # Retry
    assert window.quiz_pane.screen() == "playing" and window.quiz_pane.quiz.round == 1
    window.close()


def test_the_history_opens_pictures(qapp, monkeypatch):
    window = make(qapp, monkeypatch)
    window.open("history")
    pane = window.history_pane
    assert pane.list.focused() == "0" and pane.name.text() == "PlayStation (1994)"
    window.on_action("down")
    window.on_action("down")
    assert pane.name.text() == "Sony PSX (2003)" and pane.totals.text().startswith("160M sold • 3,482 titles")
    assert legend(window)["A"] == "Pictures"
    window.on_action("accept")
    assert window.opened == ["https://www.google.com/search?q=Sony%20PSX%20%282003%29&tbm=isch"]
    assert pane.status.text() == "Searching the web for pictures of Sony PSX (2003)."
    window.on_action("back")
    assert window.page == "front" and window.tiles["history"].hasFocus()
    window.close()


def test_the_versions_and_region_codes_are_read_in_their_text(qapp, monkeypatch):
    window = make(qapp, monkeypatch)
    window.open("versions")
    pane = window.versions_pane
    assert pane.list.focused() == "ps6_systemsoftware.json"
    window.on_action("down")                                        # PlayStation 5
    assert pane.view.toPlainText().startswith("PlayStation 5 System Software\n71 versions")
    assert legend(window)["A"] == "Read"
    window.on_action("accept")                                      # A: into the text
    assert pane.view.hasFocus() and "A" not in legend(window)
    window.on_action("down")                                        # the d-pad scrolls it
    assert pane.view.verticalScrollBar().value() > 0
    window.on_action("back")                                        # B: back on its row
    assert pane.list.focused() == "ps5_systemsoftware.json"
    window.on_action("back")
    assert window.page == "front"
    window.open("regions")
    regions = window.regions_pane
    for _ in range(5):
        window.on_action("down")
    assert regions.list.focused() == "5" and "SCPS\tJapan\tFirst-Party" in regions.view.toPlainText()
    window.on_action("right")                                       # right goes into the text too
    assert regions.view.hasFocus()
    window.close()


def test_the_news_loads_off_the_windows_thread(qapp, monkeypatch):
    calls = []

    def load():
        calls.append(True)
        return news.parse_rss((FIXTURES / "feed.xml").read_bytes())
    window = make(qapp, monkeypatch, load_news=load)
    assert calls == []                                              # nothing before the page is opened
    window.open("news")
    pane = window.news_pane
    assert wait_for(qapp, lambda: len(pane.items) == 10)
    assert pane.list.focused() == "0" and calls == [True]
    assert legend(window) == {"A": "Open", "X": "Upcoming games", "RB": "New releases", "Y": "Refresh",
                              MENU_INFO[0]: "Info", "B": "Back", VIEW: "Exit"}
    window.on_action("down")
    assert "•" in pane.status.text()                                # the date of the focused one
    window.on_action("accept")
    assert window.opened == [pane.items[1].link]
    window.on_action("x")
    window.on_action("next")
    assert window.opened[1:] == [news.UPCOMING_URL, news.NEW_RELEASES_URL]
    pane.items[2] = news.NewsItem("Elsewhere", "https://evil.example.com/x", None)
    window.open_news("2")
    assert pane.status.text() == "Blocked unexpected link." and len(window.opened) == 3
    window.on_action("back")
    window.open("news")                                             # loaded already: not again
    assert calls == [True]
    window.on_action("y")                                           # Y loads it again
    assert wait_for(qapp, lambda: len(calls) == 2 and not window.worker.busy)
    window.close()


def test_the_news_says_why_it_failed(qapp, monkeypatch):
    def broken():
        raise news.NewsError("Could not reach blog.playstation.com (no network).")
    window = make(qapp, monkeypatch, load_news=broken)
    window.open("news")
    assert wait_for(qapp, lambda: window.news_pane.status.text().startswith("Could not reach"))
    assert window.news_pane.summary.text().startswith("Could not load announcements")
    assert "A" not in legend(window)
    window.close()


def test_the_scores_are_cleared_on_a_second_press(qapp, monkeypatch, questions):
    store = ScoreStore()
    window = make(qapp, monkeypatch, questions=questions, store=store)
    window.open("scores")
    pane = window.scores_pane
    assert pane.top_empty.isVisible() and pane.trophies_empty.isVisible() and "X" not in legend(window)
    window.on_action("x")
    assert pane.status.text() == "There are no scores to clear."
    window.on_action("back")
    window.open("quiz")
    window.quiz_pane.start("ALL")
    for _ in range(10):
        answer_right(window)
    window.on_action("back")
    window.on_action("back")
    window.open("scores")
    assert pane.summary.text().startswith("Best score: 100. 1 rounds played, 1 trophies earned.")
    assert pane.top.pills["1"].label.text().startswith("1.  100  ·  ALL  ·  round 1  ·  ")
    assert pane.top.first().hasFocus() and legend(window)["X"] == "Clear scores"
    window.on_action("x")
    assert pane.status.text().startswith("Press X again") and legend(window)["X"] == "Press again"
    window.on_action("x")
    assert store.scores == [] and store.trophies == [] and pane.status.text() == "Scores and trophies removed."
    assert ScoreStore(store.path).scores == []
    window.close()


def test_a_second_press_runs_out(qapp, monkeypatch, questions):
    window = make(qapp, monkeypatch, questions=questions)
    window.open("quiz")
    window.quiz_pane.start("ALL")
    window.on_action("back")
    assert window.asked == "leave"
    window.confirm_timer.timeout.emit()                             # five seconds later
    assert window.asked == "" and window.quiz_pane.status.text() == ""
    window.on_action("back")
    assert window.quiz_pane.screen() == "playing"                  # the first press again
    window.close()


def test_the_app_in_steam_and_out_again(qapp, monkeypatch, tmp_path):
    folder = make_steam(tmp_path)
    closed = []

    def steam_closed(change):
        closed.append(True)
        change()
        return True
    window = make(qapp, monkeypatch, steam_dir=folder, steam_closed=steam_closed)
    assert legend(window)["Y"] == "Add to Steam" and "X" not in legend(window)
    window.on_action("y")
    assert wait_for(qapp, lambda: not window.worker.busy and window.in_steam)
    qapp.processEvents()
    assert closed == [True] and steam_shortcut.in_steam(folder)
    assert window.front_pane.status.text() == f"{APP_NAME} is in Steam's library. Steam was closed for it and starts " \
                                              "again."
    assert legend(window)["Y"] == "Update in Steam" and legend(window)["X"] == "Take out of Steam"
    window.on_action("x")                                           # X asks first
    assert window.front_pane.status.text().startswith("Press X again") and legend(window)["X"] == "Press again"
    window.on_action("x")
    assert wait_for(qapp, lambda: not window.worker.busy and not window.in_steam)
    qapp.processEvents()
    assert not steam_shortcut.in_steam(folder) and "X" not in legend(window)
    assert window.front_pane.status.text().startswith(f"{APP_NAME} is no longer in Steam.")
    window.close()


def test_a_steam_change_that_fails_says_why(qapp, monkeypatch, tmp_path):
    (tmp_path / "Steam" / "userdata").mkdir(parents=True)          # Steam without users
    window = make(qapp, monkeypatch, steam_dir=tmp_path / "Steam", steam_closed=lambda change: change())
    window.on_action("y")
    assert wait_for(qapp, lambda: window.front_pane.status.text().startswith("Steam was not changed"))
    window.close()


def test_view_while_steam_changes_asks_first(qapp, monkeypatch, tmp_path):
    import threading
    gate = threading.Event()

    def slow(change):
        gate.wait(10)
        change()
        return False
    window = make(qapp, monkeypatch, steam_dir=make_steam(tmp_path), steam_closed=slow)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("y")
    window.on_action("view")
    assert closed == [] and window.front_pane.status.text().startswith("Press View again")
    assert legend(window)[VIEW] == "Press again"
    window.on_action("view")
    assert closed == [True]
    gate.set()
    assert wait_for(qapp, lambda: not window.worker.busy)


def test_b_goes_back_and_view_exits(qapp, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(qapp, monkeypatch)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
