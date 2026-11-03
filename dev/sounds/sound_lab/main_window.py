# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: a preset and the waveform to start from, a slider for each number of the sound (synth.RANGES), the
sound drawn beside them, and a row of buttons to try it the way a window plays it, when the focus moves between
them (Tab, the arrow keys, or a controller's d-pad). Every change plays the sound at once; Save as WAV writes it
for a suite's sounds folder. The last sound, the preset and the save folder are remembered in the settings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, QStandardPaths, Qt
from PyQt6.QtGui import QCloseEvent, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bc250_core.gamepad import Gamepad
from bc250_core.nexus import EDGE, MAIN, TEAL
from bc250_core.widgets import AppHeader, InfoButton, accent_button, hint_label

from . import APP_NAME, LOGO_PATH, __version__
from .player import Player
from .synth import PRESETS, RANGES, WAVES, Sound, from_values, render, to_values, write_wav

SOUND_GROUP = "sound"                   # the settings: the sound's fields under it, and these keys
PRESET_KEY = "preset"
KEEP_AWAKE_KEY = "keep_awake"
SAVE_DIR_KEY = "save_dir"
CUSTOM = "Custom"                       # the preset box once a slider left the preset
NAV_LABELS = ("Home", "Library", "Settings", "Power")
NO_OUTPUT = "No audio output was found: the sound is drawn, not heard."
ABOUT = ("Each slider is one number of the sound: the pitch slides from its start to its end over the length of a "
         "tone, the attack is the rise to full volume, the decay how fast it dies away (per second), the noise a "
         "burst over the tone with a decay of its own; more tones follow the first, each the interval higher. The "
         "sound is drawn beside the sliders and plays when a slider is let go. Moving between the buttons below "
         "plays it as a window does while you navigate, from the keyboard or a controller's d-pad; A plays it "
         "again.<br><br><b>Silent on a TV?</b> PipeWire pauses the output when nothing plays, and an HDMI TV mutes "
         "a moment after the stream stops and needs time to unmute when it starts again: a 50 ms tick is over "
         "before it is heard. <b>Keep the audio link awake</b> plays a silent loop while this window is open, so "
         "the output never pauses. The preset Tick after silence shows the same from the other side: with the link "
         "asleep only its tick comes through. A window that plays such sounds needs the same loop.<br><br>"
         "<b>Save as WAV</b> writes the sound (16-bit mono, 44.1 kHz) for a suite's sounds folder, where its "
         "portal plays it by name.")


class WaveView(QWidget):
    """The sound drawn: its samples across the width, in the accent on the field color."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.frames: list[float] = []
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frames(self, frames: list[float]) -> None:
        self.frames = frames
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(EDGE), 1))
        painter.setBrush(QColor(MAIN))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        width, height = self.width() - 2, self.height() - 2
        middle = height / 2 + 1
        painter.setPen(QPen(QColor(EDGE), 1))
        painter.drawLine(1, int(middle), width, int(middle))
        if not self.frames or width < 2:
            return
        painter.setPen(QPen(QColor(TEAL), 1.5))
        step = len(self.frames) / width
        last = None
        for x in range(width):
            chunk = self.frames[int(x * step):max(int(x * step) + 1, int((x + 1) * step))]
            top, bottom = max(chunk), min(chunk)
            y1, y2 = middle - top * (height / 2 - 2), middle - bottom * (height / 2 - 2)
            painter.drawLine(x + 1, int(y1), x + 1, int(y2) + 1)
            if last is not None:
                painter.drawLine(x, last, x + 1, int(y1))
            last = int(y2)


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None, player: Player | None = None,
                 gamepad: Gamepad | None = None):
        """*settings* remembers the sound (None: this session only); *player* plays it (a Player by default);
        *gamepad* reads the controller (one is made and started; a test passes a quiet one)."""
        super().__init__()
        self.settings = settings
        self.player = player if player is not None else Player(parent=self)
        self.setWindowTitle(APP_NAME)
        self.resize(1050, 640)
        self.sound = Sound()
        self.frames: list[float] = []
        self._filling = False

        central = QWidget()
        layout = QVBoxLayout(central)
        header = AppHeader(LOGO_PATH, APP_NAME, __version__)
        header.add_action(InfoButton(ABOUT, "What this app does"))
        self.preset_box = QComboBox()
        self.preset_box.addItems([*PRESETS, CUSTOM])
        self.preset_box.setToolTip("A sound to start from; the box says Custom once a slider has left it")
        self.preset_box.currentTextChanged.connect(self.choose_preset)
        self.wave_box = QComboBox()
        self.wave_box.addItems(WAVES)
        self.wave_box.setToolTip("The waveform of the tone: a sine is the purest, a square the harshest, noise "
                                 "has no pitch")
        self.wave_box.currentTextChanged.connect(self.changed)
        self.play_button = accent_button("Play", "Play the sound as it is now (Space with a button focused, A on "
                                                 "a controller)")
        self.play_button.clicked.connect(self.play)
        self.save_button = QPushButton("Save as WAV…")
        self.save_button.setToolTip("Write the sound as a 16-bit mono WAV, for a suite's sounds folder")
        self.save_button.clicked.connect(self.save)
        header.add_second(QLabel("Preset:"))
        header.add_second(self.preset_box)
        header.add_second(QLabel("Waveform:"))
        header.add_second(self.wave_box)
        header.add_second(self.play_button)
        header.add_second(self.save_button)
        header.second_row.addStretch(1)
        layout.addLayout(header)

        body = QHBoxLayout()
        sliders = QGridLayout()
        sliders.setHorizontalSpacing(10)
        self.sliders: dict[str, QSlider] = {}
        self.values: dict[str, QLabel] = {}
        for row, (name, (least, most, unit, label)) in enumerate(RANGES.items()):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(least, most)
            slider.setToolTip(f"{label}: {least} to {most} {unit}".rstrip())
            slider.valueChanged.connect(lambda value, n=name: self.slider_moved(n, value))
            slider.sliderReleased.connect(self.changed)
            value = QLabel()
            value.setMinimumWidth(96)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sliders.addWidget(QLabel(label), row, 0)
            sliders.addWidget(slider, row, 1)
            sliders.addWidget(value, row, 2)
            self.sliders[name], self.values[name] = slider, value
        sliders.setColumnStretch(1, 1)
        left = QWidget()
        left.setLayout(sliders)
        body.addWidget(left, 3)

        right = QVBoxLayout()
        self.wave_view = WaveView()
        right.addWidget(self.wave_view, 1)
        self.length_label = hint_label("")
        right.addWidget(self.length_label)
        try_box = QGroupBox("Try it: move between the buttons")
        try_layout = QHBoxLayout(try_box)
        self.nav_buttons: list[QPushButton] = []
        for text in NAV_LABELS:
            button = QPushButton(text)
            button.setToolTip("Tab, the arrow keys or the d-pad move the focus here and play the sound")
            button.clicked.connect(self.play)
            try_layout.addWidget(button)
            self.nav_buttons.append(button)
        right.addWidget(try_box)
        self.keep_awake_box = QCheckBox("Keep the audio link awake (a silent loop while the window is open)")
        self.keep_awake_box.toggled.connect(self.set_keep_awake)
        right.addWidget(self.keep_awake_box)
        body.addLayout(right, 2)
        layout.addLayout(body, 1)
        self.setCentralWidget(central)

        from PyQt6.QtWidgets import QApplication
        QApplication.instance().focusChanged.connect(self.focus_moved)
        self.gamepad = gamepad if gamepad is not None else Gamepad(self)
        self.gamepad.action.connect(self.on_action)
        if gamepad is None:
            self.gamepad.start()

        self.restore()
        output = self.player.output_name()
        self.statusBar().showMessage(f"Playing on: {output}." if output else NO_OUTPUT)

    # --- the settings --------------------------------------------------------------------------------------------
    def restore(self) -> None:
        """The last sound, preset and keep-awake choice from the settings; the Tick preset without any."""
        preset, keep_awake, values = "Tick", True, {}
        if self.settings is not None:
            self.settings.beginGroup(SOUND_GROUP)
            values = {key: self.settings.value(key) for key in self.settings.childKeys()}
            self.settings.endGroup()
            preset = str(self.settings.value(PRESET_KEY, preset))
            keep_awake = self.settings.value(KEEP_AWAKE_KEY, keep_awake, type=bool)
        sound = from_values(values) if values else PRESETS[preset if preset in PRESETS else "Tick"]
        if preset not in PRESETS and preset != CUSTOM:
            preset = CUSTOM if values else "Tick"
        self._filling = True
        self.preset_box.setCurrentText(preset)
        self._filling = False
        self.show_sound(sound)
        self.keep_awake_box.blockSignals(True)
        self.keep_awake_box.setChecked(keep_awake)
        self.keep_awake_box.blockSignals(False)
        self.set_keep_awake(keep_awake)
        self.render()

    def remember(self) -> None:
        if self.settings is None:
            return
        self.settings.beginGroup(SOUND_GROUP)
        for key, value in to_values(self.sound).items():
            self.settings.setValue(key, value)
        self.settings.endGroup()
        self.settings.setValue(PRESET_KEY, self.preset_box.currentText())
        self.settings.setValue(KEEP_AWAKE_KEY, self.keep_awake_box.isChecked())

    # --- the sound -----------------------------------------------------------------------------------------------
    def show_sound(self, sound: Sound) -> None:
        """The sliders and the waveform box set to *sound*, without playing."""
        self._filling = True
        self.sound = sound
        self.wave_box.setCurrentText(sound.wave)
        for name, slider in self.sliders.items():
            slider.setValue(getattr(sound, name))
            self.show_value(name, getattr(sound, name))
        self._filling = False

    def show_value(self, name: str, value: int) -> None:
        unit = RANGES[name][2]
        self.values[name].setText(f"{value} {unit}".rstrip())

    def read_sound(self) -> Sound:
        return Sound(wave=self.wave_box.currentText(), **{name: slider.value() for name, slider in self.sliders.items()})

    def slider_moved(self, name: str, value: int) -> None:
        """The value beside the slider follows it; the sound changes when the slider is let go (or at once, moved
        from the keyboard)."""
        self.show_value(name, value)
        if not self._filling and not self.sliders[name].isSliderDown():
            self.changed()

    def changed(self) -> None:
        """A slider or the waveform changed: the preset box says Custom, the sound renders and plays."""
        if self._filling:
            return
        self.sound = self.read_sound()
        if self.preset_box.currentText() != CUSTOM and PRESETS.get(self.preset_box.currentText()) != self.sound:
            self._filling = True
            self.preset_box.setCurrentText(CUSTOM)
            self._filling = False
        self.render()
        self.play()

    def choose_preset(self, name: str) -> None:
        if self._filling or name not in PRESETS:
            return
        self.show_sound(PRESETS[name])
        self.render()
        self.play()

    def render(self) -> None:
        self.frames = render(self.sound)
        self.wave_view.set_frames(self.frames)
        self.length_label.setText(f"{len(self.frames)} samples, {self.sound.seconds() * 1000:.0f} ms at 44.1 kHz, "
                                  f"16-bit mono.")
        self.remember()

    def play(self) -> None:
        self.player.set_volume(1.0)                     # the volume is in the sound itself (its peak)
        self.player.play(self.frames)

    def set_keep_awake(self, on: bool) -> None:
        self.player.keep_awake(on)
        self.remember()

    # --- trying it -----------------------------------------------------------------------------------------------
    def focus_moved(self, _old: QWidget | None, new: QWidget | None) -> None:
        if isinstance(new, QPushButton) and new in self.nav_buttons:
            self.play()

    def on_action(self, action: str) -> None:
        """The controller: the d-pad moves the focus along the buttons (and so plays the sound), A plays it."""
        if action in ("left", "up", "right", "down"):
            focused = next((i for i, b in enumerate(self.nav_buttons) if b.hasFocus()), None)
            step = -1 if action in ("left", "up") else 1
            index = 0 if focused is None else (focused + step) % len(self.nav_buttons)
            self.nav_buttons[index].setFocus(Qt.FocusReason.OtherFocusReason)
        elif action == "accept":
            self.play()

    # --- saving --------------------------------------------------------------------------------------------------
    def save_dir(self) -> Path:
        default = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation) or Path.home())
        if self.settings is not None:
            return Path(str(self.settings.value(SAVE_DIR_KEY, str(default))))
        return default

    def save(self, path: Path | None = None) -> Path | None:
        """Write the sound as a WAV: *path*, or the one chosen in the dialog; None when canceled or failed."""
        if path is None:
            name = self.preset_box.currentText().lower().replace(" ", "-") + ".wav"
            chosen, _filter = QFileDialog.getSaveFileName(self, "Save the sound as WAV", str(self.save_dir() / name),
                                                          "WAV (*.wav)")
            if not chosen:
                return None
            path = Path(chosen)
        if path.suffix.lower() != ".wav":
            path = path.with_suffix(".wav")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_wav(path, self.frames)
        except OSError as error:
            QMessageBox.critical(self, APP_NAME, f"The sound could not be saved: {error}")
            return None
        if self.settings is not None:
            self.settings.setValue(SAVE_DIR_KEY, str(path.parent))
        self.statusBar().showMessage(f"Saved {path}")
        return path

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        self.gamepad.stop()
        self.player.close()
        event.accept()


__all__ = ["ABOUT", "CUSTOM", "KEEP_AWAKE_KEY", "NAV_LABELS", "NO_OUTPUT", "PRESET_KEY", "SAVE_DIR_KEY",
           "SOUND_GROUP", "MainWindow", "WaveView"]
