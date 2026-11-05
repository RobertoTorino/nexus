# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode with a game that is no longer there (owner, 01-11-2026: a game renamed after it was put in Steam):
core's gone screen instead of the emulator, and the game started as before when it is there."""

from __future__ import annotations

import sys

import pytest

from bc250_core import gone, play

from vita3k_manager import __main__ as entry


def test_a_game_no_longer_there_shows_the_gone_screen(tmp_path, monkeypatch):
    from vita3k_manager import emulator, userdata
    there = userdata.vita_fs(emulator.emulator_home()) / "ux0" / "app" / "PCSE00001"
    there.mkdir(parents=True)
    gone_game, game = "PCSB99999", "PCSE00001"
    started, shown = [], []
    monkeypatch.setattr(play, "run", lambda command, cwd, **more: started.append(command) or 0)
    monkeypatch.setattr(gone, "show", lambda info, name, version, path: shown.append((name, path)) or 1)
    assert entry.play_game([gone_game]) == 1
    assert started == [] and len(shown) == 1 and shown[0][0] == entry.APP_NAME and shown[0][1].name in gone_game
    assert entry.play_game([game]) == 0
    assert len(started) == 1 and started[0][-1] == game and len(shown) == 1


def test_the_play_mode_turns_vita3ks_exit_question_off_first(tmp_path, monkeypatch):
    """Owner, 05-11-2026: a game started from Steam gets Vita3K's settings as the window sets them, its exit question
    off, before Vita3K starts; never while Vita3K runs."""
    from vita3k_manager import emulator, userdata
    home = emulator.emulator_home()
    (userdata.vita_fs(home) / "ux0" / "app" / "PCSE00001").mkdir(parents=True)
    monkeypatch.setattr(play, "run", lambda command, cwd, **more: 0)
    monkeypatch.setattr(emulator, "running", lambda h: True)
    assert entry.play_game(["-r", "PCSE00001"]) == 0 and not userdata.gui_settings_path(home).exists()
    monkeypatch.setattr(emulator, "running", lambda h: False)
    assert entry.play_game(["-r", "PCSE00001"]) == 0
    assert b"confirmExitApp=false" in userdata.gui_settings_path(home).read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' windows")
def test_the_library_window_is_minimized_once_the_game_window_is_up():
    """Owner, 05-11-2026: Vita3K's library window stayed on the Ally's screen beside the game on the TV. Minimized
    without the focus once a game window shows beside it, left alone before that, and minimized again when shown."""
    pytest.importorskip("tkinter")
    import ctypes
    import subprocess
    import time

    from vita3k_manager import emulator
    script = ("import tkinter, sys; root = tkinter.Tk(); root.title('Vita3K v0.2.1 4186-f0273e4c'); "
              "root.after(int(sys.argv[1]), lambda: tkinter.Toplevel(root).title('Lumines | Vulkan')); "
              "root.after(20000, root.destroy); root.mainloop()")
    process = subprocess.Popen([sys.executable, "-c", script, "1500"])
    user32 = ctypes.windll.user32
    try:
        end = time.monotonic() + 10
        while time.monotonic() < end and not play.main_windows(process.pid):
            time.sleep(0.1)
        assert emulator.minimize_library(process.pid) == ""                 # the library alone: the game not up
        while time.monotonic() < end and len(play.main_windows(process.pid)) < 2:
            time.sleep(0.1)
        assert emulator.minimize_library(process.pid) == "Vita3K's library window minimized."
        library = next(h for h in play.main_windows(process.pid) if emulator._title(h).startswith("Vita3K v"))
        assert user32.IsIconic(library)
        assert emulator.minimize_library(process.pid) == ""                 # minimized already
        user32.ShowWindow(library, 9)                                       # SW_RESTORE: shown again
        assert emulator.minimize_library(process.pid) == "Vita3K's library window minimized."
    finally:
        process.kill()
