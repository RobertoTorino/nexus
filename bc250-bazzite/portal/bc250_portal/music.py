# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's background music (owner, 14-11-2026): a track that plays quietly, over and over, while the portal is
in front. The portal's own is sounds/background.ogg (BUILT_IN: the owner's remix of DAT Station's Sea Breeze, made in
Audacity, the suite's own, GPL-3.0-or-later as the rest). The user can put a track of their own in its place
(choose): the portal keeps a copy in its state folder (the original may be moved or deleted later), which the
portal's --purge removes.

The music has a switch of its own (the Music pill), apart from the Sound pill's: either can be off while the other
plays. It waits while the intro or the Portal Tour plays and while another window has the focus (a game, an app),
and plays on from where it was. Without an audio output, or without Qt's multimedia, the portal plays none and says
nothing."""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import QUrl

from . import state_dir
from .audio import SOUNDS

BUILT_IN = SOUNDS / "background.ogg"
SUFFIXES = (".ogg", ".oga", ".opus", ".mp3", ".flac", ".wav", ".m4a")
NAME = "music"                          # music.<suffix> in the portal's state folder
VOLUME = 0.35                           # under the action's sound (audio.VOLUME)
RULES = "A track must be an Ogg, Opus, MP3, FLAC, WAV or M4A sound file."
FILTER = "Sound files (" + " ".join(f"*{suffix}" for suffix in SUFFIXES) + ")"


def problem(path: Path) -> str:
    """Why *path* cannot be the track, or "" when it can."""
    if path.suffix.lower() not in SUFFIXES:
        return f"{path.name} is not an Ogg, Opus, MP3, FLAC, WAV or M4A sound file."
    if not path.is_file():
        return f"{path.name} was not found."
    return ""


def current(folder: Path | None = None) -> Path | None:
    """The track chosen (the copy of the user's file), or None."""
    folder = folder or state_dir()
    return next((p for p in sorted(folder.glob(f"{NAME}.*")) if p.suffix.lower() in SUFFIXES), None)


def track(folder: Path | None = None, built_in: Path = BUILT_IN) -> Path | None:
    """The track the portal plays: the user's own, else the portal's; None when neither is there."""
    if (chosen := current(folder)) is not None:
        return chosen
    return built_in if built_in.is_file() else None


def remove(folder: Path | None = None) -> None:
    """The portal's own track again: the user's copy goes."""
    for old in (folder or state_dir()).glob(f"{NAME}.*"):
        old.unlink(missing_ok=True)


def choose(path: Path, folder: Path | None = None) -> Path:
    """Make *path* the track: a copy in the state folder, in place of the one before. Raises ValueError with the
    reason when the file cannot be one (OSError when it cannot be copied)."""
    reason = problem(path)
    if reason:
        raise ValueError(f"{reason}\n\n{RULES}")
    folder = folder or state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{NAME}{path.suffix.lower()}"
    staged = folder / f".{NAME}-new{path.suffix.lower()}"
    shutil.copyfile(path, staged)
    remove(folder)
    staged.replace(target)
    return target


class Player:
    """Plays one track over and over through Qt Multimedia; silent, without complaint, when the module or the
    file is not there, or the file cannot be played."""

    def __init__(self):
        self.path: Path | None = None
        self.player = None
        self.output = None
        self.failed = False
        self.wanted = False                             # play() was the last word, not pause()

    def _ensure(self) -> bool:
        if self.player is not None:
            return True
        if self.failed:
            return False
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.output = QAudioOutput()
            self.output.setVolume(VOLUME)
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.output)
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
        except Exception:  # noqa: BLE001  (any failure of the multimedia stack: the portal plays no music)
            self.failed = True
            self.player = self.output = None
            return False
        return True

    def set_track(self, path: Path | None) -> None:
        """*path* as the track, from its start; it plays at once when the music was playing. The same path again
        is read again: the user's copy has one name, whatever was chosen."""
        self.path = path
        if self.player is None:
            return
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path is not None else QUrl())
        if self.wanted and path is not None:
            self.player.play()

    def play(self) -> None:
        """Play, or play on from where pause() left it."""
        self.wanted = True
        if self.path is None or not self.path.is_file():
            return
        fresh = self.player is None
        if not self._ensure():
            return
        if fresh:
            self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.play()

    def pause(self) -> None:
        self.wanted = False
        if self.player is not None:
            self.player.pause()

    def stop(self) -> None:
        self.wanted = False
        if self.player is not None:
            self.player.stop()

    @property
    def playing(self) -> bool:
        if self.player is None:
            return False
        from PyQt6.QtMultimedia import QMediaPlayer
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState


class Silent(Player):
    """A player that plays nothing, for the tools that draw the portal (the Portal Tour, the wiki's picture)."""

    def play(self) -> None:
        self.wanted = True
