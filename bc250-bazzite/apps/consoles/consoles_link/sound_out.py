# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sound on the board's default audio output (Qt Multimedia's QAudioSink, pulling from a SoundBuffer). The
stream's thread calls push(); the first push with a rate and channel count starts the sink, in the GUI thread
(a queued signal), as Qt wants it."""

from __future__ import annotations

from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

from .sound import LOW_LATENCY_MAX_MS, LOW_LATENCY_TARGET_MS, MAX_MS, TARGET_MS, SoundBuffer

SINK_BUFFER_MS = 30
LOW_LATENCY_SINK_BUFFER_MS = 20


class SoundDevice(QIODevice):
    """What the sink reads: the buffer, or silence."""

    def __init__(self, buffer: SoundBuffer, parent: QObject | None = None):
        super().__init__(parent)
        self.buffer = buffer

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        return max(self.buffer.buffered, self.buffer.frame_bytes) + super().bytesAvailable()

    def readData(self, maxlen: int) -> bytes:
        return self.buffer.read(maxlen)

    def writeData(self, data: bytes) -> int:
        return -1


class SoundPlayer(QObject):
    start_requested = pyqtSignal(int, int)

    def __init__(self, parent: QObject | None = None, delay_ms: int = 0, low_latency: bool = False):
        super().__init__(parent)
        self.delay_ms, self.low_latency = delay_ms, low_latency       # the stream settings
        self.buffer: SoundBuffer | None = None
        self.sink: QAudioSink | None = None
        self.device: SoundDevice | None = None
        self.error: str | None = None
        self.muted = False
        self.output_name = ""
        self._requested = False
        self.start_requested.connect(self._start)

    def push(self, pcm: bytes, rate: int, channels: int) -> None:
        """From the stream's thread: 16-bit PCM, interleaved."""
        if self.buffer is None:
            if not self._requested:
                self._requested = True
                self.start_requested.emit(rate, channels)
            return
        if not self.muted:
            self.buffer.push(pcm)

    def _start(self, rate: int, channels: int) -> None:
        output = QMediaDevices.defaultAudioOutput()
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if output.isNull() or not output.isFormatSupported(fmt):
            self.error = "no audio output takes 16-bit sound at this rate" if not output.isNull() else "no audio output"
            return
        if self.low_latency:
            buffer = SoundBuffer(rate, channels, LOW_LATENCY_MAX_MS, LOW_LATENCY_TARGET_MS, self.delay_ms)
        else:
            buffer = SoundBuffer(rate, channels, MAX_MS, TARGET_MS, self.delay_ms)
        self.device = SoundDevice(buffer, self)
        self.device.open(QIODevice.OpenModeFlag.ReadOnly)
        self.sink = QAudioSink(output, fmt, self)
        sink_ms = LOW_LATENCY_SINK_BUFFER_MS if self.low_latency else SINK_BUFFER_MS
        self.sink.setBufferSize(buffer.frame_bytes * rate * sink_ms // 1000)
        self.sink.start(self.device)
        if self.sink.error() != QAudio.Error.NoError:
            self.error = f"the audio output did not start ({self.sink.error().name})"
            return
        self.output_name = output.description()
        self.buffer = buffer

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def stop(self) -> None:
        if self.sink is not None:
            self.sink.stop()
        if self.device is not None:
            self.device.close()
