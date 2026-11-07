# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stream settings…: the selected console's stream settings (stream_options.py) in a dialog. They apply from the
next stream, the Game Mode shortcut's included."""

from __future__ import annotations

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox,
                             QVBoxLayout, QWidget)

from .consoles import RegisteredConsole
from .stream_options import AUDIO_DELAY_MAX, AUTO, BITRATE_RANGE, FRAME_RATES, RESOLUTIONS, SCREENS, StreamOptions


class StreamOptionsDialog(QDialog):
    def __init__(self, console: RegisteredConsole, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.console = console
        self.setWindowTitle(f"Stream settings · {name}")
        form = QFormLayout()

        self.resolution = QComboBox()
        self.resolution.addItem("Automatic (1080p from a PS5 or PS4 Pro, 720p from a PS4)", AUTO)
        for height in RESOLUTIONS:
            self.resolution.addItem(f"{height}p", height)
        self.resolution.setToolTip("What the console streams. Lower is lighter for the network and the board, and "
                                   "decodes faster. A PS4 that is not a Pro streams at most 720p.")
        form.addRow("Resolution", self.resolution)

        self.fps = QComboBox()
        for fps in sorted(FRAME_RATES, reverse=True):
            self.fps.addItem(f"{fps} frames per second", fps)
        self.fps.setToolTip("30 halves the work for the network and the board; most games look smoother at 60.")
        form.addRow("Frame rate", self.fps)

        self.bitrate = QSpinBox()
        self.bitrate.setRange(0, BITRATE_RANGE[1] // 1000)
        self.bitrate.setSuffix(" Mbit/s")
        self.bitrate.setSpecialValueText("Automatic (2 to 15 Mbit/s by resolution)")
        self.bitrate.setToolTip("How much picture data the console may send. More is sharper in busy scenes and "
                                "needs a better network; on Wi-Fi less is safer.")
        form.addRow("Bitrate", self.bitrate)

        self.screen = QComboBox()
        for key, text in SCREENS.items():
            self.screen.addItem(text, key)
        self.screen.setToolTip("How the picture fills the window or the screen. The console always sends 16:9.")
        form.addRow("Picture", self.screen)

        self.audio_delay = QSpinBox()
        self.audio_delay.setRange(0, AUDIO_DELAY_MAX)
        self.audio_delay.setSingleStep(10)
        self.audio_delay.setSuffix(" ms")
        self.audio_delay.setSpecialValueText("None")
        self.audio_delay.setToolTip("Plays the sound later, for a TV or audio system whose picture comes later than "
                                    "its sound. Sound cannot come earlier than it arrives.")
        form.addRow("Audio delay", self.audio_delay)

        self.low_latency = QCheckBox("Low latency")
        self.low_latency.setToolTip("A shorter sound buffer and the decoder's low-delay mode: a little less delay, "
                                    "with more risk of short gaps in the sound on a busy network or board.")
        form.addRow("", self.low_latency)

        hint = QLabel("They apply from the next stream, the Game Mode shortcut's too.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:palette(placeholder-text);")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self.show_options(StreamOptions()))
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(buttons)
        self.show_options(console.options)

    @staticmethod
    def _select(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))

    def show_options(self, options: StreamOptions) -> None:
        self._select(self.resolution, options.resolution)
        self._select(self.fps, options.fps)
        self.bitrate.setValue(options.bitrate // 1000)
        self._select(self.screen, options.screen)
        self.audio_delay.setValue(options.audio_delay)
        self.low_latency.setChecked(options.low_latency)

    def options(self) -> StreamOptions:
        mbit = self.bitrate.value()
        return StreamOptions(resolution=self.resolution.currentData(), fps=self.fps.currentData(),
                             bitrate=max(mbit * 1000, BITRATE_RANGE[0]) if mbit else AUTO,
                             audio_delay=self.audio_delay.value(), low_latency=self.low_latency.isChecked(),
                             screen=self.screen.currentData())
