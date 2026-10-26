# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's two sounds (sounds/, made by tools/make_portal_sounds.py): the swoosh at start and the intro of Suite
Big Picture Mode. Without an audio output, or without Qt's multimedia, the portal stays silent and says nothing."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl

SOUNDS = Path(__file__).resolve().parent / "sounds"
SWOOSH = "swoosh"
INTRO = "bigpicture"
VOLUME = 0.7
NO_OUTPUT = "No audio output was found, so the portal stays silent."


class Sounds:
    """Plays the portal's sounds; *enabled* is the user's choice (the Sound pill), available() whether the board has
    an audio output to play on."""

    def __init__(self, folder: Path = SOUNDS):
        self.folder = folder
        self.enabled = True
        self._effects: dict[str, object] = {}

    def available(self) -> bool:
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            return bool(QMediaDevices.audioOutputs())
        except Exception:  # noqa: BLE001  (any failure of the multimedia stack: no sound)
            return False

    def _effect(self, name: str):
        if name not in self._effects:
            path = self.folder / f"{name}.wav"
            if not path.is_file():
                return None
            from PyQt6.QtMultimedia import QSoundEffect
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(path)))
            effect.setVolume(VOLUME)
            self._effects[name] = effect
        return self._effects[name]

    def play(self, name: str) -> bool:
        """Play *name* once, from its start; False when it did not (sound off, no output, no file)."""
        if not self.enabled or not self.available():
            return False
        try:
            effect = self._effect(name)
            if effect is None:
                return False
            effect.stop()
            effect.play()
        except Exception:  # noqa: BLE001  (a sound that cannot play never gets in the way)
            return False
        return True

    def stop(self) -> None:
        for effect in self._effects.values():
            effect.stop()
