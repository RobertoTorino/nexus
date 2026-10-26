# SPDX-License-Identifier: GPL-3.0-or-later
"""The quiz page: the categories, a round in play and the results, on the Quiz engine (quiz.py). The page owns the
clocks (a tick a second, the delay after an answer), the music (the Android app's sea_breeze, looped while a game
is on and not muted) and hands every finished round to the score store."""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import SOUNDS_DIR
from .pages import Page
from .quiz import CATEGORIES, QUICK, START_TIME, Question, Quiz, Result, State, load_questions, review
from .scores import ScoreStore, Trophy
from .style import BRONZE, GOLD, GREEN, MUTED, RED, SILVER, TEXT, card, flag, label, link_button, primary_button, quiet_button

MUSIC_FILE = SOUNDS_DIR / "sea_breeze.ogg"
MUSIC_VOLUME = 0.35
MUTED_KEY = "quiz/muted"
CATEGORY_COLUMNS = 3
MAX_OPTIONS = 4
STAR_COLOURS = {"bronze": BRONZE, "silver": SILVER, "gold": GOLD}


class Music:
    """The background music through Qt Multimedia; silent, without complaint, when the module or the file is not
    there (the tests, a system without an audio output)."""

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


def _stat(caption: str) -> tuple[QWidget, QLabel]:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    small = label(caption, muted=True, align=Qt.AlignmentFlag.AlignCenter)
    small.setStyleSheet("font-size:11px; font-weight:700;")
    value = label("0", align=Qt.AlignmentFlag.AlignCenter)
    value.setStyleSheet("font-size:22px; font-weight:900;")
    layout.addWidget(small)
    layout.addWidget(value)
    return box, value


def _button_text(text: str) -> str:
    return text.replace("&", "&&")      # a lone & would make a mnemonic of the letter after it


class QuizPage(Page):
    round_saved = pyqtSignal(object, list)  # the Result and the trophies it earned

    def __init__(self, store: ScoreStore, settings: QSettings, questions: list[Question] | None = None,
                 music: Music | None = None, parent: QWidget | None = None):
        super().__init__("PlayStation Quiz", parent)
        self.store = store
        self.settings = settings
        self.music = music or Music()
        self.quiz = Quiz(questions if questions is not None else load_questions(), on_finished=self._on_finished)
        self.earned: list[Trophy] = []
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick)
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self._advance)

        self.mute_button = quiet_button("", "Music on or off (kept for next time)")
        self.mute_button.clicked.connect(self.toggle_mute)
        self.header_row.addWidget(self.mute_button)

        self.screens = QStackedWidget()
        self.body.addWidget(self.screens, 1)
        self.screens.addWidget(self._build_categories())
        self.screens.addWidget(self._build_playing())
        self.screens.addWidget(self._build_results())
        self._show_mute()
        self.show_categories()

    # -- building -----------------------------------------------------------------------------------------------

    def _build_categories(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label("SELECT A CATEGORY", muted=True, align=Qt.AlignmentFlag.AlignCenter))
        self.quick_button = QPushButton()
        self.quick_button.setMinimumHeight(70)
        self.quick_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_button.setToolTip(f"{self.quiz.count(QUICK)} questions to draw from; nothing is saved.")
        quick = QVBoxLayout(self.quick_button)
        quick.setContentsMargins(8, 6, 8, 6)
        quick.setSpacing(0)
        for text, size in (("QUICK QUIZ", 18), ("(NO SAVE - NO TROPHIES)", 10)):
            line = QLabel(text)
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.setStyleSheet(f"color:{TEXT}; font-size:{size}px; font-weight:800;")
            line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            quick.addWidget(line)
        self.quick_button.clicked.connect(lambda: self.start(QUICK))
        layout.addWidget(self.quick_button)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.category_buttons: dict[str, QPushButton] = {}
        for n, category in enumerate(CATEGORIES):
            button = QPushButton(category)
            button.setMinimumHeight(56)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{self.quiz.count(category)} questions")
            button.clicked.connect(lambda _checked=False, c=category: self.start(c))
            grid.addWidget(button, n // CATEGORY_COLUMNS, n % CATEGORY_COLUMNS)
            self.category_buttons[category] = button
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _build_playing(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        stats = QHBoxLayout()
        boxes = {}
        for key, caption in (("score", "SCORE"), ("round", "ROUND"), ("question", "QUESTION"), ("time", "TIME")):
            box, value = _stat(caption)
            boxes[key] = value
            stats.addWidget(box, 1)
        self.score_value, self.round_value, self.question_value, self.time_value = (
            boxes["score"], boxes["round"], boxes["question"], boxes["time"])
        layout.addLayout(stats)
        self.time_bar = QProgressBar()
        self.time_bar.setRange(0, START_TIME)
        self.time_bar.setTextVisible(False)
        self.time_bar.setFixedHeight(8)
        layout.addWidget(self.time_bar)

        self.play_stack = QStackedWidget()
        layout.addWidget(self.play_stack, 1)

        question_page = QWidget()
        question_layout = QVBoxLayout(question_page)
        question_layout.setContentsMargins(0, 8, 0, 0)
        question_layout.setSpacing(12)
        frame = card()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 20, 20, 20)
        self.question_label = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.question_label.setStyleSheet("font-size:18px; font-weight:700;")
        self.question_label.setTextFormat(Qt.TextFormat.PlainText)
        frame_layout.addWidget(self.question_label)
        question_layout.addWidget(frame)
        self.option_buttons: list[QPushButton] = []
        for n in range(MAX_OPTIONS):
            button = QPushButton()
            button.setProperty("option", True)
            button.setMinimumHeight(52)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, index=n: self._answer(index))
            shortcut = QShortcut(QKeySequence(str(n + 1)), page)
            shortcut.activated.connect(lambda index=n: self._answer(index))
            question_layout.addWidget(button)
            self.option_buttons.append(button)
        self.feedback_label = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setStyleSheet("font-size:16px; font-weight:700;")
        self.feedback_label.setMinimumHeight(70)
        question_layout.addWidget(self.feedback_label)
        question_layout.addStretch(1)
        controls = QHBoxLayout()
        self.pause_button = quiet_button("Pause", "Stop the clock")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.skip_button = quiet_button("Skip (-5s)", "On to the next question; counts as a wrong answer")
        self.skip_button.clicked.connect(self._skip)
        self.exit_button = quiet_button("Exit quiz", "Back to the categories; the round is lost")
        self.exit_button.clicked.connect(self.show_categories)
        for button in (self.pause_button, self.skip_button, self.exit_button):
            controls.addWidget(button)
        question_layout.addLayout(controls)
        self.play_stack.addWidget(question_page)

        paused_page = QWidget()
        paused_layout = QVBoxLayout(paused_page)
        paused_layout.addStretch(1)
        paused_layout.addWidget(label("PAUSED", big=True, align=Qt.AlignmentFlag.AlignCenter))
        self.resume_button = primary_button("Resume")
        self.resume_button.setMinimumHeight(48)
        self.resume_button.clicked.connect(self.toggle_pause)
        paused_layout.addWidget(self.resume_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.paused_exit_button = link_button("Exit quiz")
        self.paused_exit_button.clicked.connect(self.show_categories)
        paused_layout.addWidget(self.paused_exit_button, 0, Qt.AlignmentFlag.AlignHCenter)
        paused_layout.addStretch(1)
        self.play_stack.addWidget(paused_page)
        return page

    def _build_results(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addStretch(1)
        self.perfect_label = label("★ PERFECT ROUND! ★", big=True, align=Qt.AlignmentFlag.AlignCenter)
        self.perfect_label.setStyleSheet(f"color:{GOLD}; font-size:26px; font-weight:900;")
        layout.addWidget(self.perfect_label)
        self.results_title = label("", muted=True, align=Qt.AlignmentFlag.AlignCenter)
        self.results_title.setStyleSheet("font-size:15px; font-weight:700;")
        layout.addWidget(self.results_title)
        self.results_category = label("", big=True, align=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.results_category)
        stats = QHBoxLayout()
        box, self.correct_value = _stat("CORRECT")
        self.correct_value.setStyleSheet(f"color:{GREEN}; font-size:22px; font-weight:900;")
        stats.addWidget(box, 1)
        box, self.wrong_value = _stat("WRONG")
        self.wrong_value.setStyleSheet(f"color:{RED}; font-size:22px; font-weight:900;")
        stats.addWidget(box, 1)
        box, self.left_value = _stat("TIME LEFT")
        stats.addWidget(box, 1)
        layout.addLayout(stats)
        layout.addWidget(label("TOTAL SCORE", muted=True, align=Qt.AlignmentFlag.AlignCenter))
        self.total_label = label("", huge=True, align=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.total_label)
        self.review_label = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.review_label.setStyleSheet("font-size:16px; font-weight:700;")
        layout.addWidget(self.review_label)
        self.star_label = label("★", align=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.star_label)
        self.trophy_label = label("", muted=True, wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.trophy_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.again_button = primary_button("")
        self.again_button.setMinimumSize(200, 48)
        self.again_button.clicked.connect(self._again)
        buttons.addWidget(self.again_button)
        self.change_button = QPushButton("Change")
        self.change_button.setMinimumSize(200, 48)
        self.change_button.setToolTip("Another category")
        self.change_button.clicked.connect(self.show_categories)
        buttons.addWidget(self.change_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.quit_button = link_button("Quit to menu")
        self.quit_button.clicked.connect(self.show_categories)
        layout.addWidget(self.quit_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page

    # -- the page -----------------------------------------------------------------------------------------------

    def activate(self) -> None:
        self.show_categories()
        self._music()

    def deactivate(self) -> None:
        self._stop_clocks()
        self.quiz.to_selection()
        self.music.stop()

    def first_focus(self) -> QWidget:
        return self.quick_button

    @property
    def muted(self) -> bool:
        return self.settings.value(MUTED_KEY, False, type=bool)

    def toggle_mute(self) -> None:
        self.settings.setValue(MUTED_KEY, not self.muted)
        self.settings.sync()
        self._show_mute()
        self._music()

    def _show_mute(self) -> None:
        self.mute_button.setText("Music off" if self.muted else "Music on")

    def _music(self) -> None:
        """The music plays while the page is open and a game is on, not paused and not muted."""
        on = self.isVisible() and self.quiz.state is not State.SELECTING and not self.quiz.paused and not self.muted
        if on:
            self.music.play()
        else:
            self.music.pause()

    # -- the categories -----------------------------------------------------------------------------------------

    def show_categories(self) -> None:
        self._stop_clocks()
        self.quiz.to_selection()
        self.screens.setCurrentIndex(0)
        self._music()
        self.quick_button.setFocus()

    def start(self, category: str) -> None:
        self.quiz.start(category)
        self.earned = []
        self._enter_playing()

    # -- a round ------------------------------------------------------------------------------------------------

    def _enter_playing(self) -> None:
        if self.quiz.state is State.RESULTS:      # a category with no question at all
            self._show_results()
            return
        self.screens.setCurrentIndex(1)
        self.play_stack.setCurrentIndex(0)
        self._show_question()
        self.tick_timer.start()
        self._music()

    def _show_question(self) -> None:
        question = self.quiz.current
        if question is None:
            return
        self.question_label.setText(question.text)
        for n, button in enumerate(self.option_buttons):
            if n < len(question.options):
                option = question.options[n]
                button.setText(_button_text(f"{self.quiz.letter(option)}: {option.upper()}"))
                button.setToolTip(f"Key {n + 1}")
                button.setEnabled(True)
                button.show()
                flag(button, "result", "")
            else:
                button.hide()
        self.feedback_label.setText("")
        self.skip_button.setEnabled(True)
        self._refresh_stats()
        self.option_buttons[0].setFocus()

    def _refresh_stats(self) -> None:
        quiz = self.quiz
        self.score_value.setText(str(quiz.score))
        self.round_value.setText(str(quiz.round))
        self.question_value.setText(f"{min(quiz.answered + 1, quiz.in_round)}/{quiz.in_round}")
        self.time_value.setText(f"{quiz.time_left}s")
        low = quiz.time_left < 10
        self.time_value.setStyleSheet(f"color:{RED if low else TEXT}; font-size:22px; font-weight:900;")
        self.time_bar.setValue(min(quiz.time_left, START_TIME))
        flag(self.time_bar, "low", low)

    def _tick(self) -> None:
        ended = self.quiz.tick()
        self._refresh_stats()
        if ended:
            self._show_results()

    def _answer(self, index: int) -> None:
        question = self.quiz.current
        if question is None or index >= len(question.options) or self.screens.currentIndex() != 1 \
                or self.play_stack.currentIndex() != 0:
            return
        option = question.options[index]
        right = self.quiz.submit(option)
        if right is None:
            return
        for n, button in enumerate(self.option_buttons[:len(question.options)]):
            button.setEnabled(False)
            if question.options[n] == question.correct:
                flag(button, "result", "right")
            elif n == index:
                flag(button, "result", "wrong")
        self.skip_button.setEnabled(False)
        self.feedback_label.setStyleSheet(f"color:{GREEN if right else TEXT}; font-size:16px; font-weight:700;")
        self.feedback_label.setText(self._feedback(question, option, right))
        self._refresh_stats()
        self.feedback_timer.start(self.quiz.delay_ms)

    def _feedback(self, question: Question, option: str, right: bool) -> str:
        if right:
            text = "Correct!"
        elif question.type == "TF":
            text = f"Incorrect: {question.text}"
        else:
            text = (f"{self.quiz.letter(option)} is incorrect. The correct answer is "
                    f"{self.quiz.letter(question.correct)}: {question.correct}.")
        if question.explanation and not right:
            text += f"\n{question.explanation}"
        return text

    def _advance(self) -> None:
        self.quiz.advance()
        if self.quiz.state is State.PLAYING:
            self._show_question()
        else:
            self._show_results()

    def _skip(self) -> None:
        if self.quiz.skip():
            if self.quiz.state is State.PLAYING:
                self._show_question()
            else:
                self._show_results()

    def toggle_pause(self) -> None:
        paused = self.quiz.toggle_pause()
        self.play_stack.setCurrentIndex(1 if paused else 0)
        if paused:
            self.feedback_timer.stop()
            self.resume_button.setFocus()
        elif self.quiz.feedback is not None:
            self.feedback_timer.start(self.quiz.delay_ms)
        else:
            self.option_buttons[0].setFocus()
        self._music()

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
        self.screens.setCurrentIndex(2)
        self.perfect_label.setVisible(result.perfect)
        self.results_title.setText("ROUND NOT FINISHED" if not result.completed and result.time_left == 0
                                   else "ROUND COMPLETE")
        self.results_category.setText(result.category)
        self.correct_value.setText(str(result.correct))
        self.wrong_value.setText(str(result.wrong))
        self.left_value.setText(f"{result.time_left}s")
        self.left_value.setStyleSheet(f"color:{TEXT if result.time_left else RED}; font-size:22px; "
                                      "font-weight:900;")
        self.total_label.setText(f"{result.score}  <span style='font-size:22px; color:{MUTED};'>"
                                 f"({quiz.percentage}%)</span>")
        reviewed = result.category != QUICK and result.completed
        text, star = review(quiz.percentage) if reviewed else ("", "")
        self.review_label.setText(text)
        self.review_label.setVisible(reviewed)
        self.star_label.setVisible(reviewed and bool(star))
        if star:
            self.star_label.setStyleSheet(f"color:{STAR_COLOURS[star]}; font-size:40px;")
        if self.earned:
            self.trophy_label.setText(f"Trophy earned: {', '.join(t.kind for t in self.earned)} "
                                      f"({html.escape(result.category)}). Saved to your scores.")
        elif result.saves:
            self.trophy_label.setText("Score saved.")
        else:
            self.trophy_label.setText("Quick quiz: nothing saved.")
        self.again_button.setText("Retry" if quiz.retry_needed else "Next round")
        self.again_button.setToolTip("A new game in this category" if quiz.retry_needed
                                     else "Five questions more, the score and the clock kept")
        self.again_button.setFocus()
        self._music()

    def _again(self) -> None:
        if self.quiz.retry_needed:
            self.quiz.restart()
        else:
            self.quiz.next_round()
        self.earned = []
        self._enter_playing()
