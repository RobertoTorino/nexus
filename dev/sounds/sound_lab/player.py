# SPDX-License-Identifier: GPL-3.0-or-later
"""Playing a rendered sound with Qt's multimedia (QSoundEffect, as the portal plays its sounds): each render goes to
a WAV of its own in the cache folder, since QSoundEffect keeps a loaded file by its address and would play the old
sound again from a rewritten one. Without an audio output, or without Qt's multimedia, nothing plays and
available() says so.

Why a short sound can stay silent on a TV: PipeWire pauses the output when nothing plays, and an HDMI TV mutes a
few hundred milliseconds after the audio stream stops, then needs time to unmute when it starts again, so a 50 ms
tick is over before it is heard. keep_awake(True) plays a silent loop while the window is open: the output never
pauses and the tick is heard at once."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QObject, QUrl

from . import APP_ID
from .synth import silence, write_wav

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP_ID / "play"


class Player(QObject):
    """play(frames) plays them once, from the start, stopping the sound before; keep_awake(on) runs the silent
    loop; close() stops everything and removes the cache folder."""

    def __init__(self, folder: Path = CACHE, parent: QObject | None = None):
        super().__init__(parent)
        self.folder = folder
        self.count = 0
        self.effect = None                      # the sound that plays, or played last
        self.keeper = None                      # the silent loop
        self.volume = 1.0

    def available(self) -> bool:
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            return bool(QMediaDevices.audioOutputs())
        except Exception:  # noqa: BLE001  (any failure of the multimedia stack: no sound)
            return False

    def output_name(self) -> str:
        """The default output's name, "" without one."""
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            return QMediaDevices.defaultAudioOutput().description() if self.available() else ""
        except Exception:  # noqa: BLE001
            return ""

    def _effect(self, frames: list[float], loop: bool = False):
        from PyQt6.QtMultimedia import QSoundEffect
        self.folder.mkdir(parents=True, exist_ok=True)
        self.count += 1
        path = self.folder / f"sound-{self.count}.wav"
        write_wav(path, frames)
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        if loop:
            effect.setLoopCount(QSoundEffect.Loop.Infinite.value)
        effect.setVolume(0.0 if loop else self.volume)
        if effect.status() == QSoundEffect.Status.Loading:    # play() while loading would be lost
            effect.statusChanged.connect(lambda e=effect: e.play() if e.status() == QSoundEffect.Status.Ready
                                         else None)
        else:
            effect.play()
        return effect

    def play(self, frames: list[float]) -> bool:
        """False when nothing plays (no output, no multimedia)."""
        if not self.available():
            return False
        try:
            if self.effect is not None:
                last = Path(self.effect.source().toLocalFile())
                self.effect.stop()
                # deleted now, not later: on Windows the effect keeps its file open until then. One still loading
                # can hold it a moment longer; it stays, and close() removes the folder
                sip.delete(self.effect)
                self.effect = None
                try:
                    last.unlink(missing_ok=True)
                except OSError:
                    pass
            self.effect = self._effect(frames)
        except Exception:  # noqa: BLE001  (a sound that cannot play never gets in the way)
            self.effect = None
            return False
        return True

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        if self.effect is not None:
            self.effect.setVolume(volume)

    def keep_awake(self, on: bool) -> bool:
        """The silent loop on or off; False when it could not start."""
        if self.keeper is not None:
            self.keeper.stop()
            sip.delete(self.keeper)             # now: on Windows it keeps its file open until then
            self.keeper = None
        if not on or not self.available():
            return False
        try:
            self.keeper = self._effect(silence(), loop=True)
        except Exception:  # noqa: BLE001
            self.keeper = None
            return False
        return True

    def close(self) -> None:
        for effect in (self.effect, self.keeper):
            if effect is not None:
                effect.stop()
                sip.delete(effect)              # now, so their files are closed before the folder goes (Windows)
        self.effect = self.keeper = None
        shutil.rmtree(self.folder, ignore_errors=True)


__all__ = ["CACHE", "Player"]
