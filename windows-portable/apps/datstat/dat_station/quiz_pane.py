# SPDX-License-Identifier: GPL-3.0-or-later
"""The quiz page: the categories, a round in play (or paused) and the results, on the Quiz engine (quiz.py), as the
BC250 app's quiz page plays it. The pane owns the clocks (a tick a second, the delay after an answer), the music (the
Android app's sea_breeze, looped while a game is on and not muted) and hands every finished round to the score store.

On the handheld the d-pad goes through the categories and the answers and A picks one; the window's legend has the
rest (legend()): X Skip, Y Pause and Resume, LB the music, A Retry or Next round on the results, and B goes back (from
a round in play only on a second press: the round is lost). The keys 1 to 4 answer too, as on the BC250 app."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QProgressBar, QStackedWidget, QVBoxLayout, QWidget

from bc250_core.portable import AMBER, BODY, DIM, DOT, RAISED, TEXT, InfoPill, Pane, Row, px, text_label

from . import SOUNDS_DIR
from .panes import BRONZE, GOLD, SILVER, TRIANGLE, Symbol
from .quiz import (BONUS, CATEGORIES, PENALTY, QUICK, QUICK_QUESTIONS, ROUND_GROWTH, START_TIME, Question, Quiz,
                   Result, State, load_questions, review)
from .scores import ScoreStore, Trophy

MUSIC_FILE = SOUNDS_DIR / "sea_breeze.ogg"
MUSIC_VOLUME = 0.35
MUTED_KEY = "quiz/muted"
CATEGORY_COLUMNS = 4
MAX_OPTIONS = 4
GREEN, RED = TRIANGLE, DOT
STAR_COLORS = {"bronze": BRONZE, "silver": SILVER, "gold": GOLD}
LOW_TIME = 10                   # seconds: the clock turns red under this
CATEGORIES_SCREEN, PLAYING_SCREEN, RESULTS_SCREEN = 0, 1, 2

QUIZ_INFO = (
    f"Pick a category, or the Quick Quiz: {QUICK_QUESTIONS} questions, nothing saved. A round starts with "
    f"{START_TIME} seconds on the clock. A right answer adds {BONUS} seconds and the question's points; a wrong "
    f"answer or a skip (X) takes {PENALTY} seconds. The clock stops while an answer is shown and while the game is "
    "paused (Y). The right answer turns green, a wrong choice red, and for a wrong answer the right one is named, "
    "with an explanation where the question has one. A question is not asked twice in one game until the category's "
    "questions are used up.\n\n"
    "The round ends when all its questions are answered, or when the clock runs out. A complete round gets a review, "
    "with a bronze (50 % and more), silver (75 %) or gold (95 %) star. A round with every answer right is a Perfect "
    f"round: Next round (A) then asks {ROUND_GROWTH} questions more, with the score and the clock kept. Otherwise "
    "Retry (A) starts the category again from zero, and B picks another category.\n\n"
    "Every finished round of a saved game adds a score to Scores & Trophies; a perfect round adds a Perfect trophy. "
    "LB turns the music on or off; the choice is kept. B in a round asks for a second press: the round is lost.")


class Music:
    """The background music through Qt Multimedia; silent, without complaint, when the module or the file is not
    there (the tests, a handheld without an audio output)."""

    def __init__(self, path: Path = MUSIC_FILE):
        self.path = path
        self.player = None
        self.output = None
        self.failed = False

    def _ensure(self) -> bool:
        if self.player is not None:
            return True
        if self.failed or not self.path.is_file():
            return False
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.output = QAudioOutput()
            self.output.setVolume(MUSIC_VOLUME)
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.output)
            self.player.setSource(QUrl.fromLocalFile(str(self.path)))
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
        except Exception:  # noqa: BLE001  (any failure of the multimedia stack: the quiz plays without music)
            self.failed = True
            self.player = self.output = None
            return False
        return True

    def play(self) -> None:
        if self._ensure():
            self.player.play()

    def pause(self) -> None:
        if self.player is not None:
            self.player.pause()

    def stop(self) -> None:
        if self.player is not None:
            self.player.stop()

    @property
    def playing(self) -> bool:
        if self.player is None:
            return False
        from PyQt6.QtMultimedia import QMediaPlayer
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState


class OptionRow(Row):
    """An answer: a row, green once it shows the right answer, red for a wrong choice (result)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("", parent)
        self.result = ""                                # "", "right" or "wrong"

    def set_result(self, result: str) -> None:
        self.result = result
        self.update()

    def paintEvent(self, event) -> None:
        if not self.result:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(GREEN if self.result == "right" else RED)
        painter.setBrush(color.darker(160))
        painter.setPen(QPen(color, px(2)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(px(1), px(1), -px(1), -px(1)), px(10), px(10))


def _stat(caption: str) -> tuple[QWidget, QLabel]:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    small = text_label(caption, BODY - 2, QFont.Weight.Bold, DIM)
    small.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value = text_label("0", 20, QFont.Weight.Black)
    value.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(small)
    layout.addWidget(value)
    return box, value


def _centered(text: str, size: float, weight: QFont.Weight = QFont.Weight.Normal, color: str = TEXT,
              wrap: bool = False) -> QLabel:
    label = text_label(text, size, weight, color, wrap)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _color(label: QLabel, color: str) -> None:
    label.setStyleSheet(f"color: {color}; background: transparent;")


def feedback_text(quiz: Quiz, question: Question, option: str, right: bool) -> str:
    """What an answer's feedback says, as the BC250 app says it."""
    if right:
        text = "Correct!"
    elif question.type == "TF":
        text = f"Incorrect: {question.text}"
    else:
        text = (f"{quiz.letter(option)} is incorrect. The correct answer is "
                f"{quiz.letter(question.correct)}: {question.correct}.")
    if question.explanation and not right:
        text += f"\n{question.explanation}"
    return text


class QuizPane(Pane):
    round_saved = pyqtSignal(object, list)              # the Result and the trophies it earned
    changed = pyqtSignal()                              # another screen, or the music: the legend changes

    def __init__(self, store: ScoreStore, settings: QSettings, questions: list[Question] | None = None,
                 music: Music | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # holds the focus on the results, which have no row
        self.store = store
        self.settings = settings
        self.music = music or Music()
        self.quiz = Quiz(questions if questions is not None else load_questions(), on_finished=self._on_finished)
        self.earned: list[Trophy] = []
        self.answer_index = 0                           # the answer the focus was on, again after a pause
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick)
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self._advance)

        heading = QHBoxLayout()
        self.title = text_label("PlayStation Quiz", 24, QFont.Weight.ExtraBold)
        heading.addWidget(self.title)
        heading.addStretch()
        self.info = InfoPill("PlayStation Quiz", QUIZ_INFO)
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.screens = QStackedWidget()
        self.screens.addWidget(self._build_categories())
        self.screens.addWidget(self._build_playing())
        self.screens.addWidget(self._build_results())
        self.column.addWidget(self.screens, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        for n in range(MAX_OPTIONS):                    # the keys 1 to 4, as on the BC250 app
            shortcut = QShortcut(QKeySequence(str(n + 1)), self)
            shortcut.activated.connect(lambda index=n: self.answer(index))
        self.show_categories()

    # -- building -----------------------------------------------------------------------------------------------

    def _build_categories(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, px(4), 0, 0)
        layout.setSpacing(px(10))
        layout.addWidget(text_label("SELECT A CATEGORY", BODY, QFont.Weight.Bold, DIM))
        self.quick_row = Row("QUICK QUIZ  ·  no save, no trophies")
        self.quick_row.activated.connect(lambda: self.start(QUICK))
        self.quick_row.focused_text = f"Quick quiz: {QUICK_QUESTIONS} questions from all {self.quiz.count(QUICK):,}."
        layout.addWidget(self.quick_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(10))
        grid.setVerticalSpacing(px(8))
        self.category_rows: dict[str, Row] = {}
        for n, category in enumerate(CATEGORIES):
            row = Row(category)
            row.activated.connect(lambda c=category: self.start(c))
            row.focused_text = f"{category}: {self.quiz.count(category):,} questions."
            grid.addWidget(row, n // CATEGORY_COLUMNS, n % CATEGORY_COLUMNS)
            self.category_rows[category] = row
        layout.addLayout(grid)
        layout.addStretch()
        for row in (self.quick_row, *self.category_rows.values()):
            row.installEventFilter(self)
        return page

    def eventFilter(self, obj, event) -> bool:
        """A category with the focus says how many questions it has, on the status line."""
        if event.type() == event.Type.FocusIn and hasattr(obj, "focused_text"):
            self.status.setText(obj.focused_text)
        return super().eventFilter(obj, event)

    def _build_playing(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(8))
        stats = QHBoxLayout()
        values = {}
        for key, caption in (("score", "SCORE"), ("round", "ROUND"), ("question", "QUESTION"), ("time", "TIME")):
            box, value = _stat(caption)
            values[key] = value
            stats.addWidget(box, 1)
        self.score_value, self.round_value, self.question_value, self.time_value = (
            values["score"], values["round"], values["question"], values["time"])
        layout.addLayout(stats)
        self.time_bar = QProgressBar()
        self.time_bar.setRange(0, START_TIME)
        self.time_bar.setTextVisible(False)
        self.time_bar.setFixedHeight(px(8))
        layout.addWidget(self.time_bar)

        self.play_stack = QStackedWidget()
        layout.addWidget(self.play_stack, 1)
        question_page = QWidget()
        question_layout = QVBoxLayout(question_page)
        question_layout.setContentsMargins(0, px(6), 0, 0)
        question_layout.setSpacing(px(8))
        self.question_label = _centered("", 17, QFont.Weight.Bold, wrap=True)
        self.question_label.setTextFormat(Qt.TextFormat.PlainText)
        question_layout.addWidget(self.question_label)
        question_layout.addSpacing(px(4))
        self.option_rows: list[OptionRow] = []
        for n in range(MAX_OPTIONS):
            row = OptionRow()
            row.activated.connect(lambda index=n: self.answer(index))
            question_layout.addWidget(row)
            self.option_rows.append(row)
        self.feedback_label = _centered("", BODY + 1, QFont.Weight.Bold, wrap=True)
        question_layout.addWidget(self.feedback_label)
        question_layout.addStretch()
        self.play_stack.addWidget(question_page)

        paused_page = QWidget()
        paused_layout = QVBoxLayout(paused_page)
        paused_layout.addStretch()
        paused_layout.addWidget(_centered("PAUSED", 30, QFont.Weight.Black))
        paused_layout.addWidget(_centered("The clock stands still. Y resumes the round; B leaves it.", BODY + 1,
                                          color=DIM))
        paused_layout.addStretch()
        self.play_stack.addWidget(paused_page)
        self._style_bar(False)
        return page

    def _build_results(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(10))
        layout.addStretch()
        self.perfect_row = QWidget()
        perfect = QHBoxLayout(self.perfect_row)
        perfect.setContentsMargins(0, 0, 0, 0)
        perfect.addStretch()
        perfect.addWidget(Symbol("star", GOLD, 26))
        perfect.addWidget(text_label("PERFECT ROUND!", 22, QFont.Weight.Black, GOLD))
        perfect.addWidget(Symbol("star", GOLD, 26))
        perfect.addStretch()
        layout.addWidget(self.perfect_row)
        self.results_title = _centered("", BODY + 1, QFont.Weight.Bold, DIM)
        layout.addWidget(self.results_title)
        self.results_category = _centered("", 20, QFont.Weight.ExtraBold)
        layout.addWidget(self.results_category)
        stats = QHBoxLayout()
        box, self.correct_value = _stat("CORRECT")
        _color(self.correct_value, GREEN)
        stats.addWidget(box, 1)
        box, self.wrong_value = _stat("WRONG")
        _color(self.wrong_value, RED)
        stats.addWidget(box, 1)
        box, self.left_value = _stat("TIME LEFT")
        stats.addWidget(box, 1)
        box, self.total_value = _stat("TOTAL SCORE")
        stats.addWidget(box, 1)
        layout.addLayout(stats)
        layout.addSpacing(px(6))
        self.review_row = QWidget()
        review_line = QHBoxLayout(self.review_row)
        review_line.setContentsMargins(0, 0, 0, 0)
        review_line.addStretch()
        self.star = Symbol("star", GOLD, 34)
        review_line.addWidget(self.star)
        self.review_label = text_label("", 16, QFont.Weight.Bold)
        review_line.addWidget(self.review_label)
        review_line.addStretch()
        layout.addWidget(self.review_row)
        self.trophy_label = _centered("", BODY + 1, color=DIM, wrap=True)
        layout.addWidget(self.trophy_label)
        layout.addStretch()
        return page

    def _style_bar(self, low: bool) -> None:
        self.time_bar.setStyleSheet(f"QProgressBar {{ background: {RAISED}; border: none; border-radius: {px(4)}px; }}"
                                    f" QProgressBar::chunk {{ background: {RED if low else AMBER};"
                                    f" border-radius: {px(4)}px; }}")

    # -- the page -----------------------------------------------------------------------------------------------

    def screen(self) -> str:
        """Which screen shows: categories, playing, paused or results."""
        index = self.screens.currentIndex()
        if index == PLAYING_SCREEN:
            return "paused" if self.quiz.paused else "playing"
        return "results" if index == RESULTS_SCREEN else "categories"

    def legend(self) -> list[tuple[str, str]]:
        """The screen's buttons for the window's legend, before core's Info, Back and Exit."""
        music = ("LB", "Music on" if self.muted else "Music off")
        return {"categories": [("A", "Start"), music],
                "playing": [("A", "Answer"), ("X", "Skip (−5 s)"), ("Y", "Pause"), music],
                "paused": [("Y", "Resume"), music],
                "results": [("A", "Retry" if self.quiz.retry_needed else "Next round"), music]}[self.screen()]

    def activate(self) -> None:
        self.show_categories()

    def deactivate(self) -> None:
        self._stop_clocks()
        self.quiz.to_selection()
        self.music.stop()

    def first_focus(self) -> QWidget:
        return {"categories": self.quick_row, "playing": self.option_rows[0]}.get(self.screen(), self)

    @property
    def muted(self) -> bool:
        return self.settings.value(MUTED_KEY, False, type=bool)

    def toggle_mute(self) -> None:
        self.settings.setValue(MUTED_KEY, not self.muted)
        self.settings.sync()
        self.status.setText("Music off: the choice is kept." if self.muted else "Music on.")
        self._music()
        self.changed.emit()

    def _music(self) -> None:
        """The music plays while the page shows and a game is on, not paused and not muted."""
        on = self.isVisible() and self.quiz.state is not State.SELECTING and not self.quiz.paused and not self.muted
        if on:
            self.music.play()
        else:
            self.music.pause()

    # -- the categories -----------------------------------------------------------------------------------------

    def show_categories(self) -> None:
        self._stop_clocks()
        self.quiz.to_selection()
        self.title.setText("PlayStation Quiz")
        self.screens.setCurrentIndex(CATEGORIES_SCREEN)
        self.status.setText(self.quick_row.focused_text)    # the row the focus goes to (it may have it already)
        self._music()
        if self.isVisible():
            self.quick_row.setFocus()
        self.changed.emit()

    def start(self, category: str) -> None:
        self.quiz.start(category)
        self.earned = []
        self.title.setText(f"PlayStation Quiz  ·  {category}")
        self._enter_playing()

    # -- a round ------------------------------------------------------------------------------------------------

    def _enter_playing(self) -> None:
        if self.quiz.state is State.RESULTS:      # a category with no question at all
            self._show_results()
            return
        self.screens.setCurrentIndex(PLAYING_SCREEN)
        self.play_stack.setCurrentIndex(0)
        self.status.setText("")
        self._show_question()
        self.tick_timer.start()
        self._music()
        self.changed.emit()

    def _show_question(self) -> None:
        question = self.quiz.current
        if question is None:
            return
        self.question_label.setText(question.text)
        for n, row in enumerate(self.option_rows):
            if n < len(question.options):
                option = question.options[n]
                row.set_text(f"{self.quiz.letter(option)}: {option.upper()}")
                row.set_result("")
                row.show()
            else:
                row.hide()
        self.feedback_label.setText("")
        self._refresh_stats()
        self.answer_index = 0
        self.option_rows[0].setFocus()

    def _refresh_stats(self) -> None:
        quiz = self.quiz
        self.score_value.setText(str(quiz.score))
        self.round_value.setText(str(quiz.round))
        self.question_value.setText(f"{min(quiz.answered + 1, quiz.in_round)}/{quiz.in_round}")
        self.time_value.setText(f"{quiz.time_left}s")
        low = quiz.time_left < LOW_TIME
        _color(self.time_value, RED if low else TEXT)
        self.time_bar.setValue(min(quiz.time_left, START_TIME))
        self._style_bar(low)

    def _tick(self) -> None:
        ended = self.quiz.tick()
        self._refresh_stats()
        if ended:
            self._show_results()

    def answer(self, index: int) -> None:
        """The answer *index* (A on its row, a tap, or the keys 1 to 4); nothing while an answer shows or paused."""
        question = self.quiz.current
        if question is None or index >= len(question.options) or self.screen() != "playing":
            return
        option = question.options[index]
        right = self.quiz.submit(option)
        if right is None:
            return
        self.answer_index = index
        for n, row in enumerate(self.option_rows[:len(question.options)]):
            if question.options[n] == question.correct:
                row.set_result("right")
            elif n == index:
                row.set_result("wrong")
        _color(self.feedback_label, GREEN if right else TEXT)
        self.feedback_label.setText(feedback_text(self.quiz, question, option, right))
        self._refresh_stats()
        self.feedback_timer.start(self.quiz.delay_ms)

    def _advance(self) -> None:
        self.quiz.advance()
        if self.quiz.state is State.PLAYING:
            self._show_question()
        else:
            self._show_results()

    def skip(self) -> None:
        """X: on to the next question, counted as a wrong answer; not while an answer shows."""
        if self.screen() != "playing":
            return
        if not self.quiz.skip():
            self.status.setText("The answer shows: the next question follows by itself.")
            return
        self.status.setText(f"Skipped: {PENALTY} seconds off the clock.")
        if self.quiz.state is State.PLAYING:
            self._show_question()
        else:
            self._show_results()

    def toggle_pause(self) -> None:
        if self.screen() not in ("playing", "paused"):
            return
        paused = self.quiz.toggle_pause()
        self.play_stack.setCurrentIndex(1 if paused else 0)
        if paused:
            self.feedback_timer.stop()
            self.setFocus()
        else:
            if self.quiz.feedback is not None:
                self.feedback_timer.start(self.quiz.delay_ms)
            self.option_rows[self.answer_index].setFocus()
        self.status.setText("")
        self._music()
        self.changed.emit()

    def _stop_clocks(self) -> None:
        self.tick_timer.stop()
        self.feedback_timer.stop()

    # -- the results --------------------------------------------------------------------------------------------

    def _on_finished(self, result: Result) -> None:
        self.earned = self.store.add(result)
        self.round_saved.emit(result, self.earned)

    def _show_results(self) -> None:
        self._stop_clocks()
        quiz = self.quiz
        result = quiz.result
        if result is None:
            return
        self.screens.setCurrentIndex(RESULTS_SCREEN)
        self.perfect_row.setVisible(result.perfect)
        self.results_title.setText("ROUND NOT FINISHED" if not result.completed and result.time_left == 0
                                   else "ROUND COMPLETE")
        self.results_category.setText(result.category)
        self.correct_value.setText(str(result.correct))
        self.wrong_value.setText(str(result.wrong))
        self.left_value.setText(f"{result.time_left}s")
        _color(self.left_value, TEXT if result.time_left else RED)
        self.total_value.setText(f"{result.score} ({quiz.percentage}%)")
        reviewed = result.category != QUICK and result.completed
        text, star = review(quiz.percentage) if reviewed else ("", "")
        self.review_label.setText(text)
        self.review_row.setVisible(reviewed)
        self.star.setVisible(bool(star))
        if star:
            self.star.set_color(STAR_COLORS[star])
        if self.earned:
            self.trophy_label.setText(f"Trophy earned: {', '.join(t.kind for t in self.earned)} "
                                      f"({result.category}). Saved to your scores.")
        elif result.saves:
            self.trophy_label.setText("Score saved.")
        else:
            self.trophy_label.setText("Quick quiz: nothing saved.")
        self.status.setText("A starts a new game in this category; B picks another one." if quiz.retry_needed
                            else f"A: {ROUND_GROWTH} questions more, the score and the clock kept.")
        if self.isVisible():
            self.setFocus()
        self._music()
        self.changed.emit()

    def again(self) -> None:
        """A on the results: Retry (a new game) or Next round (after a perfect one)."""
        if self.screen() != "results":
            return
        if self.quiz.retry_needed:
            self.quiz.restart()
        else:
            self.quiz.next_round()
        self.earned = []
        self._enter_playing()

    def in_round(self) -> bool:
        """Whether a round is in play (or paused): B asks before it leaves."""
        return self.screen() in ("playing", "paused")
