# SPDX-License-Identifier: GPL-3.0-or-later
"""The stream's window: the picture (scaled to fit, black around it), the sound on the default output, and the
controller and the keyboard as the Xbox's pad.

Full screen from the start. F11 switches between full screen and a window. The stream ends when the window is
closed, with Ctrl+Q, or by holding View and Menu on the controller for 2 s (the Xbox button stays the console's).
The keyboard as a pad: the arrow keys are the d-pad, Enter A, Backspace B, X and Y their buttons, Tab View, M Menu
and Home the Xbox button."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QIODevice, QRect, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QColor, QFont, QImage, QKeyEvent, QPainter, QPaintEvent
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
from PyQt6.QtWidgets import QMessageBox, QWidget

from bc250_core import window_title

from . import pads
from .channels import Dialog
from .inputs import PadState
from .stream import Stream

POLL_MS = 16
QUIT_HOLD_S = 2.0
QUIT_BUTTONS = frozenset({"view", "menu"})
SOUND_MAX_MS = 120                          # more sound waiting than this is dropped: the stream stays live
KEYS = {Qt.Key.Key_Up: "dpad_up", Qt.Key.Key_Down: "dpad_down", Qt.Key.Key_Left: "dpad_left",
        Qt.Key.Key_Right: "dpad_right", Qt.Key.Key_Return: "a", Qt.Key.Key_Enter: "a", Qt.Key.Key_Backspace: "b",
        Qt.Key.Key_X: "x", Qt.Key.Key_Y: "y", Qt.Key.Key_Tab: "view", Qt.Key.Key_M: "menu", Qt.Key.Key_Home: "nexus"}


class SoundOut:
    """48 kHz stereo 16-bit PCM to the default audio output, pushed as it comes."""

    RATE, CHANNELS, BYTES = 48000, 2, 2

    def __init__(self, parent):
        fmt = QAudioFormat()
        fmt.setSampleRate(self.RATE)
        fmt.setChannelCount(self.CHANNELS)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt, parent)
        self.sink.setBufferSize(self.RATE * self.CHANNELS * self.BYTES * SOUND_MAX_MS // 1000)
        self.device: QIODevice | None = self.sink.start()

    def write(self, data: bytes) -> None:
        if self.device is None:
            return
        room = self.sink.bytesFree()
        if room <= 0:
            return
        self.device.write(data[:room - room % (self.CHANNELS * self.BYTES)])

    def stop(self) -> None:
        self.sink.stop()
        self.device = None


def merge(pad: PadState | None, keys: frozenset[str]) -> PadState | None:
    """The controller's state with the keyboard's buttons added; None when there is neither."""
    if pad is None and not keys:
        return None
    pad = pad or PadState()
    return PadState(0, pad.buttons | keys, pad.left_x, pad.left_y, pad.right_x, pad.right_y, pad.left_trigger,
                    pad.right_trigger)


class StreamWindow(QWidget):
    def __init__(self, stream: Stream, title: str, source_factory: Callable[[], object] = pads.PygameSource,
                 sound: bool = True, clock: Callable[[], float] = time.monotonic):
        super().__init__()
        self.setWindowTitle(window_title(title))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(640, 360)
        self.stream, self.title, self.clock = stream, title, clock
        self.picture: QImage | None = None
        self.shown: tuple[int, float] | None = None     # the frame drawn last: RTP timestamp, arrival
        self.message = "Starting…"
        self.keys: set[str] = set()
        self.held_since: float | None = None            # View and Menu held since
        self.source = pads.open_source(source_factory)
        self.sound = SoundOut(self) if sound else None
        self.closing = False
        stream.status.connect(self._status)
        stream.ready.connect(self._ready)
        stream.image.connect(self._image)
        stream.sound.connect(self._sound)
        stream.dialog.connect(self._dialog)
        stream.vibration.connect(self._vibration)
        stream.ended.connect(self._ended)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    # --- From the stream ----------------------------------------------------------------------------------------

    def _status(self, text: str) -> None:
        self.message = text
        self.update()

    def _ready(self) -> None:
        self._status("")

    def _image(self, image: QImage, rtp_timestamp: int, arrived_ms: float) -> None:
        self.picture = image
        self.shown = (rtp_timestamp, arrived_ms)
        self.update()

    def _sound(self, data: bytes) -> None:
        if self.sound is not None:
            self.sound.write(data)

    def _dialog(self, dialog: Dialog) -> None:
        answer = QMessageBox.question(self, window_title(dialog.title or self.title), dialog.text or dialog.title)
        self.stream.answer_dialog(dialog, answer == QMessageBox.StandardButton.Yes)

    def _vibration(self, vibration) -> None:
        if self.source is not None:
            self.source.rumble(vibration)

    def _ended(self, reason: str) -> None:
        if reason:
            self.picture = None
            self.message = f"The stream ended: {reason}"
            self.update()
        else:
            self.close()

    # --- The pad ------------------------------------------------------------------------------------------------

    def poll(self) -> None:
        pad = self.source.read() if self.source is not None else None
        state = merge(pad, frozenset(self.keys))
        self.stream.set_pads([state] if state is not None else [])
        if state is not None and QUIT_BUTTONS <= state.buttons:
            if self.held_since is None:
                self.held_since = self.clock()
            elif self.clock() - self.held_since >= QUIT_HOLD_S:
                self.close()
        else:
            self.held_since = None

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.close()
        elif event.key() in KEYS and not event.isAutoRepeat():
            self.keys.add(KEYS[event.key()])
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() in KEYS and not event.isAutoRepeat():
            self.keys.discard(KEYS[event.key()])
        else:
            super().keyReleaseEvent(event)

    # --- Drawing ------------------------------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))
        if self.picture is not None and not self.picture.isNull():
            size = self.picture.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(0, 0, size.width(), size.height())
            target.moveCenter(self.rect().center())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(target, self.picture)
        if self.message:
            font = QFont(self.font())
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QColor("white"))
            painter.drawText(self.rect().adjusted(40, 40, -40, -40),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             f"{self.title}\n\n{self.message}\n\nCtrl+Q or hold View and Menu to leave")
        painter.end()
        if self.shown is not None:
            self.stream.frame_shown(*self.shown)
            self.shown = None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        if not self.closing:
            self.closing = True
            self.timer.stop()
            self.stream.stop()
            if self.sound is not None:
                self.sound.stop()
            if self.source is not None:
                self.source.close()
        super().closeEvent(event)
