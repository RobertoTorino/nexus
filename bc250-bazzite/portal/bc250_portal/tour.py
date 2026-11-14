# SPDX-License-Identifier: GPL-3.0-or-later
"""The Portal Tour inside the portal (owner, 14-11-2026): a click on the suite's icon plays the video over the whole
screen. It is the wiki's copy, played from the wiki's address, so the portal does not carry it and the tour is
always the newest. A or Space pauses it and plays on, B or Esc closes it, and it closes by itself at its end. Its
sound follows the portal's Sound setting.

Without Qt's multimedia, without a connection, or when the video does not start within START_S seconds, the player
says so with failed(reason) and closes: the portal then opens the wiki's Portal Tour page in the browser."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from . import APP_NAME

START_S = 15                            # how long the video gets to start before the browser takes over
HINT = "A / Space  Pause      B / Esc  Close"


class TourPlayer(QDialog):
    """The video at *url*, fullscreen and modal over the portal; *sound* off plays it silent."""

    failed = pyqtSignal(str)            # why it could not be played; the player has closed

    def __init__(self, url: str, sound: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME}: Portal Tour")
        self.setModal(True)
        self.setStyleSheet("QDialog { background: black; }")
        self.url = url
        self.sound = sound
        self.player = None
        self.audio = None
        self.started = False
        self.gave_up = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.layout_ = layout
        self.hint = QLabel(HINT)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("color: #c0c0c0; background: black; padding: 8px; font-size: 16px;")
        self.watch = QTimer(self)
        self.watch.setSingleShot(True)
        self.watch.timeout.connect(lambda: self._fail("The video did not start."))

    def start(self) -> None:
        """Show the player and play; failed() when Qt cannot."""
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
        except ImportError as error:
            self._fail(f"Qt's multimedia is missing ({error}).")
            return
        self.video = QVideoWidget()
        self.video.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.layout_.addWidget(self.video, 1)
        self.layout_.addWidget(self.hint)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setMuted(not self.sound)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.errorOccurred.connect(lambda _error, text: self._fail(text or "The video could not be played."))
        self.player.mediaStatusChanged.connect(self._status)
        self.player.playbackStateChanged.connect(self._state)
        self.player.setSource(QUrl(self.url))
        self.showFullScreen()
        self.setFocus()
        self.watch.start(START_S * 1000)
        self.player.play()

    def toggle(self) -> None:
        """Pause, or play on."""
        if self.player is None:
            return
        from PyQt6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _state(self, state) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.started = True
            self.watch.stop()

    def _status(self, status) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.accept()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._fail("The video could not be read.")

    def _fail(self, reason: str) -> None:
        if self.gave_up:
            return                      # said already: a late error of the player says nothing new
        self.gave_up = True
        self._stop()
        self.reject()
        self.failed.emit(reason)

    def _stop(self) -> None:
        if self.player is not None:
            self.player.blockSignals(True)
            self.player.stop()

    def done(self, result: int) -> None:
        self.watch.stop()
        self._stop()
        super().done(result)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            return
        super().keyPressEvent(event)        # Esc closes

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
        super().mouseReleaseEvent(event)
