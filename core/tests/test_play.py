# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode (play.py): the launcher a shortcut starts, View, LB and RB held to close the emulator, the grace before
it is ended, and a game without a controller reader."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from bc250_core import play


class Notice:
    """The closing notice, as heat.Banner is used: show(), tick() while it is up, hide() at the end."""

    def __init__(self, order: list | None = None):
        self.shown, self.ticks, self.hidden, self.order = [], 0, None, order if order is not None else []

    def show(self, now, title, line):
        self.shown.append((now, title, line))
        self.order.append("notice")

    def tick(self, now):
        self.ticks += 1

    def hide(self):
        self.hidden = True


@pytest.fixture(autouse=True)
def no_heat_guard(monkeypatch):
    """The chip is not read here (test_heat.py has the play mode's heat warning), and no notice opens a window."""
    monkeypatch.setattr(play, "_guard", lambda log: None)
    monkeypatch.setattr(play, "_notice", Notice)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Process:
    """An emulator that runs until it is closed (closes_after: polls after the close until it ends; None: never)."""

    def __init__(self, closes_after: int | None = 3):
        self.pid, self.returncode = 4242, None
        self.closes_after, self.asked, self.terminated = closes_after, False, False

    def poll(self):
        if self.asked and self.closes_after is not None:
            if self.closes_after == 0:
                self.returncode = 0
            self.closes_after -= 1
        return self.returncode

    def terminate(self):
        self.terminated, self.returncode = True, 1

    def wait(self):
        return self.returncode


class Pad:
    def __init__(self, script):
        self.script, self.closed = script, False       # {time: [events]}
        self.clock = None

    def events(self):
        due = [t for t in self.script if t <= self.clock.now]
        return [event for t in sorted(due) for event in self.script.pop(t)]

    def close(self):
        self.closed = True


def played(script, process, hold=2.0, grace=10.0):
    clock, lines, closed = Clock(), [], []
    pad = Pad(script)
    pad.clock = clock

    def close(pid):
        closed.append(pid)
        process.asked = True
        return 1
    code = play.run(["C:/emu/emu.exe", "-g", "game"], Path("C:/emu"), log=lines.append,
                    start=lambda command, cwd: process, pad=lambda: pad, close=close, clock=clock,
                    sleep=clock.sleep, hold=hold, grace=grace)
    return code, closed, lines, pad, clock


def test_view_lb_and_rb_held_close_the_emulator():
    """One way out of every game (owner, 30-10-2026): View, LB and RB held together for two seconds ask the emulator's
    windows to close; a shorter hold does nothing of ours."""
    script = {0.5: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)],
              1.0: [("button", "rightshoulder", False)], 3.0: [("button", "rightshoulder", True)],
              3.5: [("button", "back", True)]}
    process = Process()
    code, closed, lines, pad, clock = played(script, process)
    assert closed == [4242] and code == 0 and not process.terminated and pad.closed
    # both down from 3.0 (View since 0.5): two seconds, then the notice's least time
    assert 5.0 + play.SHOWN <= clock.now < 5.5 + play.SHOWN
    assert lines[0] == "Play: emu.exe started; View, LB and RB held for 2 s close it."
    assert lines[-1] == "Play: the emulator ended (exit code 0)."


def test_view_and_menu_alone_are_left_to_the_system():
    """View and Menu are Windows' and Steam's guide button (owner, 30-10-2026: they opened their overlays over the game,
    whose focus they took): held, they close nothing; the play mode's chord is View, LB and RB."""
    process = Process()
    process.returncode = None
    clock = Clock()
    process.poll = lambda: 0 if clock.now >= 6 else None
    pad = Pad({0.0: [("button", "back", True), ("button", "start", True), ("button", "leftshoulder", True)]})
    pad.clock = clock
    closed = []
    play.run(["emu.exe"], Path("."), start=lambda c, d: process, pad=lambda: pad, close=closed.append, clock=clock,
             sleep=clock.sleep)
    assert closed == [] and play.CHORD == ("back", "leftshoulder", "rightshoulder")


def test_an_emulator_that_does_not_close_is_ended():
    process = Process(closes_after=None)
    code, closed, lines, _, clock = played({0.0: [("button", "back", True), ("button", "leftshoulder", True),
                                                  ("button", "rightshoulder", True)]}, process)
    assert closed == [4242] and process.terminated and code == 1
    assert "did not close within 10 s; ended" in lines[-2] and 12.0 <= clock.now < 12.2


def test_an_unplugged_pad_lets_go_of_the_buttons():
    script = {0.0: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)],
              1.0: [("removed", "", False)]}
    process = Process()
    process.returncode = None

    def ends():                                                    # the player quits the game in it at 5 s
        return 0 if clock_ref[0].now >= 5 else None
    clock_ref = []
    clock, closed = Clock(), []
    clock_ref.append(clock)
    process.poll = ends
    pad = Pad(script)
    pad.clock = clock
    play.run(["emu.exe"], Path("."), start=lambda c, d: process, pad=lambda: pad, close=closed.append, clock=clock,
             sleep=clock.sleep)
    assert closed == []


def test_without_a_controller_reader_the_game_still_runs():
    process = Process()
    lines = []
    calls = iter([None, None, 0])
    process.poll = lambda: next(calls)

    def no_pad():
        raise ImportError("No module named 'pygame'")
    clock = Clock()
    assert play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=no_pad,
                    clock=clock, sleep=clock.sleep) == 0
    assert "without the quit chord" in lines[1]


def test_the_launcher_of_a_release_and_of_the_checkout(tmp_path):
    """A release's shortcut starts the app's own program with --play; from the checkout, its run.ps1 in a hidden
    PowerShell window (Steam cannot set PYTHONPATH). played() tells a shortcut made so from one made before."""
    exe, before = play.launcher(tmp_path, frozen=True, program=r"C:\Apps\shadPS4-Manager.exe")
    assert (exe, before) == (r"C:\Apps\shadPS4-Manager.exe", ["--play"])
    exe, before = play.launcher(tmp_path, frozen=False)
    assert exe == play.POWERSHELL and before[-3:] == ["-File", str(tmp_path / "run.ps1"), "--play"]
    assert "-WindowStyle" in before and before[before.index("-WindowStyle") + 1] == "Hidden"
    options = play.launch_options(before, '-f true -g "C:\\Games\\eboot.bin"')
    assert options.endswith(' --play -f true -g "C:\\Games\\eboot.bin"')
    assert play.played(f'"{exe}"', options, tmp_path)
    assert not play.played('"C:\\emu\\shadPS4.exe"', '-f true -g "C:\\Games\\eboot.bin"', tmp_path)
    assert play.programs("shadPS4-Manager") == {"shadps4-manager.exe", "powershell.exe"}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' windows")
def test_close_windows_closes_a_real_window(tmp_path):
    """WM_CLOSE to the windows of a process and its children: a Tk window (as an emulator's) closes as on Alt+F4."""
    pytest.importorskip("tkinter")
    marker = tmp_path / "closed"
    script = ("import tkinter, pathlib, sys; root = tkinter.Tk(); root.title('play-test'); "
              "root.protocol('WM_DELETE_WINDOW', lambda: (pathlib.Path(sys.argv[1]).write_text('x'), root.destroy())); "
              "root.after(20000, root.destroy); root.mainloop()")
    process = subprocess.Popen([sys.executable, "-c", script, str(marker)])
    try:
        end = time.monotonic() + 10
        while time.monotonic() < end and play.close_windows(process.pid) == 0:
            time.sleep(0.2)                                         # until its window is up
        process.wait(10)
        assert marker.read_text() == "x"                            # closed as a window is, not ended
    finally:
        if process.poll() is None:
            process.kill()


def test_an_emulator_that_asks_before_it_quits_is_answered():
    """shadPS4 asks "Are you sure you want to quit?" after a close (the owner's Ally, 30-10-2026): a second later,
    while it still runs, Enter answers it, once; it then ends as on its own Quit."""
    clock, lines, answered = Clock(), [], []
    process = Process(closes_after=None)
    pad = Pad({0.0: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)]})
    pad.clock = clock

    def confirm(pid):
        answered.append(clock.now)
        process.closes_after = 0
        return 1
    code = play.run(["shadPS4.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=lambda: pad,
                    close=lambda pid: setattr(process, "asked", True) or 1, clock=clock, sleep=clock.sleep,
                    confirm=confirm)
    assert len(answered) == 1 and 3.0 <= answered[0] < 3.2 and code == 0 and not process.terminated
    assert any("asks before it quits; answered in 1 window(s)" in line for line in lines)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' windows")
def test_only_the_main_window_is_closed(tmp_path):
    """Steam's overlay has windows in the game's process: a close goes to the main window alone, not to a tool
    window beside it (as the overlay's)."""
    pytest.importorskip("tkinter")
    marker = tmp_path / "closed"
    script = ("import tkinter, pathlib, sys; root = tkinter.Tk(); root.title('play-main'); "
              "tool = tkinter.Toplevel(root); tool.attributes('-toolwindow', True); "
              "tool.protocol('WM_DELETE_WINDOW', lambda: pathlib.Path(sys.argv[1]).write_text('tool')); "
              "root.protocol('WM_DELETE_WINDOW', lambda: (pathlib.Path(sys.argv[1]).write_text("
              "pathlib.Path(sys.argv[1]).read_text() + 'main' if pathlib.Path(sys.argv[1]).exists() else 'main'), "
              "root.destroy())); root.after(20000, root.destroy); root.mainloop()")
    process = subprocess.Popen([sys.executable, "-c", script, str(marker)])
    try:
        end = time.monotonic() + 10
        while time.monotonic() < end and len(play.main_windows(process.pid)) == 0:
            time.sleep(0.2)
        time.sleep(0.5)
        assert len(play.main_windows(process.pid)) == 1             # the tool window is not one
        play.close_windows(process.pid)
        process.wait(10)
        assert marker.read_text() == "main"
    finally:
        if process.poll() is None:
            process.kill()


def test_a_game_no_longer_there_is_missing(tmp_path):
    """A game renamed, moved or deleted after it was put in Steam (owner, 01-11-2026): the play mode shows core's gone
    screen instead of starting the emulator. A file or a folder (an unpacked game's) that is there is not missing."""
    game = tmp_path / "Game.iso"
    game.write_bytes(b"game")
    assert not play.missing(game) and not play.missing(str(tmp_path))
    assert play.missing(tmp_path / "Renamed.iso") and play.missing(str(tmp_path / "Gone" / "eboot.bin"))


def test_a_notice_says_the_game_closes_before_it_is_closed():
    """Owner, 05-11-2026: show that the game is being quit. The notice goes up when the hold is reached, before the
    close, stays at least SHOWN seconds when the emulator goes at once, and comes down when the play mode ends."""
    order, clock, lines = [], Clock(), []
    notice = Notice(order)
    process = Process(closes_after=0)
    pad = Pad({0.0: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)]})
    pad.clock = clock

    def close(pid):
        order.append("close")
        process.asked = True
        return 1
    assert play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=lambda: pad,
                    close=close, clock=clock, sleep=clock.sleep, notice=lambda: notice) == 0
    assert order == ["notice", "close"] and notice.shown == [(pytest.approx(2.0), *play.CLOSING)]
    assert notice.hidden and notice.ticks and clock.now >= 2.0 + play.SHOWN
    assert play.CLOSING == ("Closing the game", "View, LB and RB were held.")


def test_a_notice_that_cannot_show_never_stops_the_close():
    def broken():
        raise RuntimeError("no screen")
    clock, lines, closed = Clock(), [], []
    process = Process()
    pad = Pad({0.0: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)]})
    pad.clock = clock

    def close(pid):
        closed.append(pid)
        process.asked = True
        return 1
    assert play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=lambda: pad,
                    close=close, clock=clock, sleep=clock.sleep, notice=broken) == 0
    assert closed == [4242] and "the closing notice cannot show (no screen); the game closes all the same" in lines[1]


def test_the_emulators_windows_are_seen_to_every_half_second_until_the_quit():
    """What an emulator's windows need while the game runs (owner, 05-11-2026: Vita3K's library window minimized):
    windows() every WINDOWS_EVERY seconds with its process, what it says it did logged once, never after the quit."""
    asked, clock = [], Clock()
    process = Process()
    pad = Pad({3.0: [("button", "back", True), ("button", "leftshoulder", True), ("button", "rightshoulder", True)]})
    pad.clock = clock
    lines = []

    def close(pid):
        process.asked = True
        return 1

    def windows(pid):
        asked.append(round(clock.now, 2))
        return "Its library window minimized." if len(asked) in (2, 4) else ""   # up at the second look, and again
    play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=lambda: pad, close=close,
             clock=clock, sleep=clock.sleep, windows=windows)
    gaps = [b - a for a, b in zip(asked, asked[1:])]
    assert asked[0] == 0.0
    assert all(play.WINDOWS_EVERY - 1e-9 <= gap <= play.WINDOWS_EVERY + play.POLL + 1e-9 for gap in gaps)
    assert len(asked) >= 9 and all(t < 5.0 for t in asked)                    # the quit at 5 s: no more
    assert lines.count("Play: Its library window minimized.") == 1


def test_windows_that_fail_let_the_game_run():
    clock, lines = Clock(), []
    process = Process()
    process.poll = lambda: 0 if clock.now >= 2 else None
    called = []

    def broken(pid):
        called.append(pid)
        raise OSError("access denied")
    assert play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=lambda: Pad({}),
                    clock=clock, sleep=clock.sleep, windows=broken) == 0
    assert lines.count("Play: the emulator's windows cannot be seen to (access denied).") == 1 and len(called) == 1
