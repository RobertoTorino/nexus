# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode with a game that is no longer there (owner, 01-11-2026: a game renamed after it was put in Steam):
core's gone screen instead of the emulator, and the game started as before when it is there."""

from __future__ import annotations

from bc250_core import gone, play

from shadps4_manager import __main__ as entry


def test_a_game_no_longer_there_shows_the_gone_screen(tmp_path, monkeypatch):
    there = tmp_path / "Game.iso"
    there.write_bytes(b"game")
    gone_game, game = str(tmp_path / "Renamed.iso"), str(there)
    started, shown = [], []
    monkeypatch.setattr(play, "run", lambda command, cwd, **more: started.append(command) or 0)
    monkeypatch.setattr(gone, "show", lambda info, name, version, path: shown.append((name, path)) or 1)
    assert entry.play_game([gone_game]) == 1
    assert started == [] and len(shown) == 1 and shown[0][0] == entry.APP_NAME and shown[0][1].name in gone_game
    assert entry.play_game([game]) == 0
    assert len(started) == 1 and started[0][-1] == game and len(shown) == 1
