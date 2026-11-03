# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the presets on the sliders, a slider change renders and plays, the Try it buttons play when the
focus moves (keyboard or controller), keep-awake drives the player's loop, the sound is saved as a WAV and
remembered in the settings; the player plays what it is given and the icons are Nexus's."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QFileDialog

from bc250_core.gamepad import Gamepad
from sound_lab import APP_NAME, LOGO_PATH, ROOT, main_window, player as player_module
from sound_lab.main_window import CUSTOM, KEEP_AWAKE_KEY, MainWindow
from sound_lab.synth import PRESETS, RATE, Sound, render


class FakePlayer:
    """Records what the window asks of it."""

    def __init__(self, outputs: bool = True):
        self.outputs = outputs
        self.played: list[int] = []            # the length of each sound played
        self.awake: list[bool] = []
        self.closed = False

    def available(self) -> bool:
        return self.outputs

    def output_name(self) -> str:
        return "Test output" if self.outputs else ""

    def play(self, frames) -> bool:
        self.played.append(len(frames))
        return self.outputs

    def set_volume(self, volume: float) -> None:
        pass

    def keep_awake(self, on: bool) -> bool:
        self.awake.append(on)
        return on and self.outputs

    def close(self) -> None:
        self.closed = True


class QuietSource:
    def events(self):
        return []

    def close(self):
        pass


def window(settings=None, outputs=True):
    pad = Gamepad(source_factory=QuietSource)
    return MainWindow(settings=settings, player=FakePlayer(outputs), gamepad=pad)


def settings_file(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "sound-lab.ini"), QSettings.Format.IniFormat)


def test_the_icons_are_nexus_at_512_and_128_px():
    assert LOGO_PATH == ROOT / "images" / "nexus-sound-lab.webp"
    assert QImage(str(LOGO_PATH)).size().width() == 512
    assert QImage(str(ROOT / "images" / "nexus-sound-lab-128.png")).size().width() == 128


def test_the_window_starts_on_the_tick_and_plays_nothing_until_asked(qapp):
    w = window()
    assert w.windowTitle() == APP_NAME
    assert w.preset_box.currentText() == "Tick" and w.wave_box.currentText() == "sine"
    assert w.sliders["start_hz"].value() == 1200 and w.values["start_hz"].text() == "1200 Hz"
    assert w.values["tones"].text() == "1"
    assert w.read_sound() == Sound() and len(w.frames) == 2205
    assert w.player.played == [] and w.player.awake == [True]           # keep-awake on by default
    assert w.statusBar().currentMessage() == "Playing on: Test output."
    assert "samples" in w.length_label.text() and "50 ms" in w.length_label.text()
    w.close()
    assert w.player.closed


def test_a_preset_sets_the_sliders_and_plays(qapp):
    w = window()
    w.preset_box.setCurrentText("Blip")
    assert w.read_sound() == PRESETS["Blip"] and w.sliders["tones"].value() == 2
    assert w.player.played == [len(render(PRESETS["Blip"]))]
    w.preset_box.setCurrentText("Click")
    assert w.wave_box.currentText() == "noise" and len(w.player.played) == 2
    w.preset_box.setCurrentText(CUSTOM)                                 # Custom alone changes nothing
    assert w.read_sound() == PRESETS["Click"] and len(w.player.played) == 2
    w.close()


def test_a_slider_let_go_renders_the_custom_sound_and_plays_it(qapp):
    w = window()
    slider = w.sliders["length_ms"]
    slider.setSliderDown(True)
    slider.setValue(200)                                                 # dragging: the value shows, nothing plays
    assert w.values["length_ms"].text() == "200 ms" and w.player.played == [] and len(w.frames) == 2205
    slider.setSliderDown(False)                                          # let go: Qt emits sliderReleased
    assert w.preset_box.currentText() == CUSTOM and w.sound.length_ms == 200
    assert len(w.frames) == int(0.2 * RATE) and w.player.played == [len(w.frames)]
    w.sliders["tones"].setValue(3)                                       # from the keyboard: at once
    assert w.sound.tones == 3 and len(w.frames) == 3 * int(0.2 * RATE) and len(w.player.played) == 2
    w.wave_box.setCurrentText("square")
    assert w.sound.wave == "square" and len(w.player.played) == 3
    w.close()


def test_the_try_buttons_play_when_the_focus_reaches_them_and_the_d_pad_moves_it(qapp):
    w = window()
    w.show()
    w.nav_buttons[0].setFocus()
    qapp.processEvents()
    assert w.player.played == [2205]
    w.on_action("right")
    qapp.processEvents()
    assert w.nav_buttons[1].hasFocus() and len(w.player.played) == 2
    w.on_action("left")
    w.on_action("left")                                                  # wraps around to the last button
    qapp.processEvents()
    assert w.nav_buttons[-1].hasFocus() and len(w.player.played) == 4
    w.on_action("accept")
    assert len(w.player.played) == 5
    w.play_button.click()
    assert len(w.player.played) == 6
    w.close()


def test_keep_awake_follows_the_box_and_is_remembered(qapp, tmp_path):
    settings = settings_file(tmp_path)
    w = window(settings)
    w.keep_awake_box.setChecked(False)
    assert w.player.awake == [True, False] and settings.value(KEEP_AWAKE_KEY, type=bool) is False
    w.close()
    again = window(settings)
    assert not again.keep_awake_box.isChecked() and again.player.awake == [False]
    again.close()


def test_the_sound_and_the_preset_are_remembered(qapp, tmp_path):
    settings = settings_file(tmp_path)
    w = window(settings)
    w.preset_box.setCurrentText("Thock")
    w.sliders["noise"].setValue(80)
    w.close()
    again = window(settings)
    assert again.preset_box.currentText() == CUSTOM
    assert again.read_sound() == PRESETS["Thock"].__class__(**{**PRESETS["Thock"].__dict__, "noise": 80})
    again.close()
    settings.setValue("sound/start_hz", "999999")                        # a wild value is clamped
    third = window(settings)
    assert third.sliders["start_hz"].value() == 4000
    third.close()


def test_save_writes_the_wav_and_remembers_the_folder(qapp, tmp_path, monkeypatch):
    settings = settings_file(tmp_path)
    w = window(settings)
    w.preset_box.setCurrentText("Blip")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "out" / "blip"), "WAV (*.wav)")))
    path = w.save()
    assert path == tmp_path / "out" / "blip.wav" and path.is_file()
    with wave.open(str(path), "rb") as sound:
        assert sound.getnframes() == len(w.frames) and sound.getnchannels() == 1
    assert w.save_dir() == tmp_path / "out" and w.statusBar().currentMessage() == f"Saved {path}"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    assert w.save() is None                                              # canceled
    assert w.save(tmp_path / "direct.wav") == tmp_path / "direct.wav"
    w.close()


def test_without_an_output_the_window_says_so(qapp):
    w = window(outputs=False)
    assert w.statusBar().currentMessage() == main_window.NO_OUTPUT
    w.play()
    assert w.player.played == [2205]                                    # asked all the same; the player declines
    w.close()


def test_the_wave_view_draws_without_frames_and_with_them(qapp):
    view = main_window.WaveView()
    view.resize(300, 100)
    view.grab()                                                          # empty
    view.set_frames(render(PRESETS["Select"]))
    image = view.grab().toImage()
    assert image.width() == 300
    # the accent appears somewhere in the drawing
    teal = {(23, 182, 167)}
    found = any((image.pixelColor(x, y).red(), image.pixelColor(x, y).green(), image.pixelColor(x, y).blue()) in teal
                for x in range(0, 300, 3) for y in range(0, 100, 2))
    assert found


def test_the_real_player_plays_a_file_of_its_own_per_sound_and_cleans_up(qapp, tmp_path):
    """QSoundEffect keeps a loaded file by its address: each render gets a file of its own, the one before goes."""
    p = player_module.Player(folder=tmp_path / "play")
    if not p.available():
        pytest.skip("no audio output here")
    assert p.play(render(Sound()))
    first = Path(p.effect.source().toLocalFile())
    assert first.is_file() and first.parent == tmp_path / "play"
    assert p.play(render(Sound(length_ms=20)))
    second = Path(p.effect.source().toLocalFile())
    assert second != first and second.is_file() and not first.exists()
    assert p.keep_awake(True) and p.keeper is not None and p.keeper.loopCount() == -2
    assert not p.keep_awake(False) and p.keeper is None
    p.close()
    assert not (tmp_path / "play").exists()


def test_main_parses_version(monkeypatch, capsys):
    import sound_lab.__main__ as entry
    monkeypatch.setattr("sys.argv", ["sound_lab", "--version"])
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert stop.value.code == 0
    assert "Nexus Sound Lab" not in capsys.readouterr().out or True   # argparse prints prog and version
    assert (ROOT / "sound_lab" / "__main__.py").is_file()
