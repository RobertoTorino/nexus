# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stream on the handheld: Console Link's stream window (stream_view.py), full screen, as the play mode shows a
game. Every button goes to the console, so the way out is the suite's (core's play mode, owner 30-10-2026): View, LB
and RB held together (gamepad.QuitChord, in the stream's controller reader), or the screen touched and held, the
touch screen being the handheld's own and no part of the stream; Escape too, on a keyboard. The status line shows
while the stream starts (waking the console, the network test) and when it ends, never over the game."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent

from bc250_core.play import HOLD

from .stream_options import StreamOptions
from .stream_view import StreamWindow

QUIT_HINT = "To end the stream, hold View, LB and RB together, or touch and hold the screen."


class Messenger(QObject):
    """Carries the stream thread's news to the window, on the window's thread."""
    status = pyqtSignal(str)
    quit = pyqtSignal()


class PlayWindow(StreamWindow):
    """The stream full screen. say() and end() may be called from any thread; *on_close* stops the stream when the
    window closes, however it closes."""

    def __init__(self, title: str, on_close: Callable[[], None], options: StreamOptions = StreamOptions(),
                 hold: float = HOLD):
        super().__init__(title, on_close, None, options)
        self.messenger = Messenger()
        self.messenger.status.connect(self.show_status)
        self.messenger.quit.connect(self.close)
        self.notifier.arrived.connect(self._first_picture)
        self.pictures = False
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("background:#000; color:#ddd; font-size: 16pt; padding: 12px;")
        self.touch = QTimer(self)
        self.touch.setSingleShot(True)
        self.touch.setInterval(round(hold * 1000))
        self.touch.timeout.connect(self.close)

    def say(self, text: str) -> None:
        """From any thread: *text* on the status line, with the way out."""
        self.messenger.status.emit(text)

    def end(self) -> None:
        """From any thread (the controller chord): the window closes, and with it the stream."""
        self.messenger.quit.emit()

    def show_status(self, text: str) -> None:
        self.status.setText(f"{text}\n{QUIT_HINT}")
        self.status.show()

    def _first_picture(self) -> None:
        if not self.pictures:
            self.pictures = True
            self.status.hide()                          # the game alone on the screen

    def stream_ended(self, text: str) -> None:
        """The stream is over without the window closing (the console ended it, or a fault): what happened."""
        self.pictures = False
        self.show_status(text)

    def _show_rate(self) -> None:
        """The status line is not a frame counter here: it says what happens, and hides with the first picture."""

    def toggle_full_screen(self) -> None:
        """Always full screen on the handheld."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_M:
            self.sound.set_muted(not self.sound.muted)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.touch.start()                              # a touch held for HOLD seconds ends the stream

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.touch.stop()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.touch.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.touch.stop()
        super().closeEvent(event)
