# SPDX-License-Identifier: GPL-3.0-or-later
"""Pausing what plays while the TV is off: the media players on the session bus (MPRIS: browsers, mpv, VLC,
Spotify, …), through busctl. Only the players that were playing are paused, and only those continue when the TV is
on again. Games are not media players; they keep running."""

from __future__ import annotations

from typing import Callable

from .runner import Result

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"

Runner = Callable[[list[str]], Result]


def players(run: Runner) -> list[str]:
    result = run(["busctl", "--user", "list", "--no-legend"])
    return [line.split()[0] for line in result.out.splitlines() if line.startswith(PREFIX)] if result.ok else []


def playing(run: Runner, player: str) -> bool:
    """busctl prints the property as 's "Playing"'."""
    result = run(["busctl", "--user", "get-property", player, PATH, PLAYER, "PlaybackStatus"])
    return result.ok and result.out.strip() == 's "Playing"'


def pause_all(run: Runner) -> list[str]:
    """Pauses every player that plays; returns them, to continue later."""
    paused = [p for p in players(run) if playing(run, p)]
    for player in paused:
        run(["busctl", "--user", "call", player, PATH, PLAYER, "Pause"])
    return paused


def resume(run: Runner, paused: list[str]) -> None:
    """Continues the players pause_all() paused, those still there."""
    present = set(players(run))
    for player in paused:
        if player in present:
            run(["busctl", "--user", "call", player, PATH, PLAYER, "Play"])
