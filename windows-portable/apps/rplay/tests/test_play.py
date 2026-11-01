# SPDX-License-Identifier: AGPL-3.0-or-later
"""Playing on the handheld: the quit chord (View, LB and RB held, gamepad.QuitChord), the full-screen stream window
(stream_window.py: what it says, the first picture, the touch held and Escape), a console's Steam entry written into
a Steam folder and read back (steam_shortcuts.py, jobs.steam_entry) and the direct start its entry runs (direct.py)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from bc250_core import steam
from fake_console import MAC, REGIST_KEY, RP_KEY
from remote_play import LOGO_PATH, direct, jobs, steam_shortcuts
from remote_play.consoles import ConsoleStore, RegisteredConsole
from remote_play.gamepad import BACK, LEFT_SHOULDER, RIGHT_SHOULDER, SOUTH, PadInfo, QuitChord, Reading
from remote_play.jobs import Outcome
from remote_play.stream_window import QUIT_HINT, PlayWindow
from remote_play.target import Target
from remote_play.video import Picture

CONSOLE = RegisteredConsole("AABBCCDDEEFF", "Living room PS5", "192.168.1.20", Target.PS5_1, REGIST_KEY, RP_KEY, MAC)


def wait(qapp, until, seconds: float = 5) -> None:
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    assert until()


# The quit chord

def pads(*held: frozenset[int]) -> dict:
    return {n: (PadInfo("pad"), Reading(buttons=buttons), ("unknown", -1)) for n, buttons in enumerate(held)}


def test_view_lb_and_rb_held_quit_once():
    now = [0.0]
    quits = []
    chord = QuitChord(lambda: quits.append(now[0]), hold=2.0, clock=lambda: now[0])
    held = frozenset({BACK, LEFT_SHOULDER, RIGHT_SHOULDER, SOUTH})       # other buttons with it count too
    for now[0] in (0.0, 1.0, 1.9):
        chord.feed(pads(held))
    assert quits == []
    for now[0] in (2.0, 3.0, 4.0):
        chord.feed(pads(held))
    assert quits == [2.0]                               # once, however long it stays held
    now[0] = 5.0
    chord.feed(pads(frozenset()))
    for now[0] in (6.0, 8.0):
        chord.feed(pads(held))
    assert quits == [2.0, 8.0]


def test_a_shorter_hold_or_two_buttons_or_two_controllers_do_not_quit():
    now = [0.0]
    quits = []
    chord = QuitChord(lambda: quits.append(True), hold=2.0, clock=lambda: now[0])
    for now[0] in (0.0, 1.0, 1.5):
        chord.feed(pads(frozenset({BACK, LEFT_SHOULDER, RIGHT_SHOULDER})))
    now[0] = 1.6
    chord.feed(pads(frozenset({BACK, LEFT_SHOULDER})))  # let go of one: the hold starts again
    for now[0] in (2.0, 3.0, 4.0):
        chord.feed(pads(frozenset({BACK, LEFT_SHOULDER}), frozenset({RIGHT_SHOULDER})))
    assert quits == []


# The stream window

def picture() -> Picture:
    return Picture("yuv420p", 2, 2, bytes(4) + bytes(1) + bytes(1))


def test_the_window_says_what_happens_until_the_first_picture(qapp):
    closed = []
    window = PlayWindow("Living room PS5 · Remote Play", lambda: closed.append(True))
    window.show()
    window.say("Waking Living room PS5 from rest mode…")             # from the stream's thread, as signals
    wait(qapp, lambda: window.status.text().startswith("Waking"))
    assert window.status.text().endswith(QUIT_HINT) and window.status.isVisible()
    window.deliver(picture())
    wait(qapp, lambda: not window.status.isVisible())
    window.stream_ended("The console ended the stream.")
    assert window.status.isVisible() and window.status.text().startswith("The console ended")
    window.close()
    assert closed == [True]


def test_the_quit_chord_and_escape_close_it(qapp):
    closed = []
    window = PlayWindow("PS5", lambda: closed.append(True))
    window.show()
    threading.Thread(target=window.end).start()                       # the reader's thread
    wait(qapp, lambda: closed == [True])
    window = PlayWindow("PS5", lambda: closed.append(True))
    window.show()
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert closed == [True, True]


def test_a_touch_held_closes_it_a_short_one_does_not(qapp):
    closed = []
    window = PlayWindow("PS5", lambda: closed.append(True), hold=0.2)
    window.show()

    def mouse(kind):
        return QMouseEvent(kind, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    window.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease))
    time.sleep(0.3)
    qapp.processEvents()
    assert closed == []
    window.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    wait(qapp, lambda: closed == [True])


# The Steam entry

def steam_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "Steam"
    (folder / "userdata" / "170579662" / "config").mkdir(parents=True)
    return folder


def test_the_entry_runs_the_programs_direct_start():
    entry = steam_shortcuts.entry(CONSOLE, LOGO_PATH, frozen=True,
                                  program=r"C:\Users\u\AppData\Local\windows-portable-suite\windows-portable-rplay"
                                          r"\app\Remote-Play.exe")
    assert entry["AppName"] == "Living room PS5 (Remote Play)"
    assert entry["Exe"].startswith('"C:\\') and entry["Exe"].endswith('Remote-Play.exe"')
    assert entry["StartDir"].endswith('\\app\\"') and entry["LaunchOptions"] == "--stream AABBCCDDEEFF"
    assert steam_shortcuts.ours(CONSOLE)(entry)
    other = RegisteredConsole("001122334455", "PS4-Pro", "192.168.1.21", Target.PS4_10, b"k", b"r")
    assert not steam_shortcuts.ours(other)(entry)
    # From the checkout: run.ps1 in a hidden PowerShell window
    checkout = steam_shortcuts.entry(CONSOLE, LOGO_PATH, frozen=False)
    assert checkout["Exe"].lower().endswith('powershell.exe"') and "run.ps1" in checkout["LaunchOptions"]
    assert checkout["LaunchOptions"].endswith("--stream AABBCCDDEEFF") and steam_shortcuts.ours(CONSOLE)(checkout)


def test_the_job_writes_the_entry_with_its_art_and_takes_it_out(qapp, tmp_path):
    folder = steam_folder(tmp_path)
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    added = jobs.steam_entry(CONSOLE, folder, LOGO_PATH, closed=with_steam_closed)
    assert added.ok and "is in Steam's library" in added.message, added.message
    assert steam_shortcuts.in_steam(folder) == {"AABBCCDDEEFF"} and closed == [True]
    [item] = steam.shortcuts(folder)
    number = steam.appid(str(item["Exe"]), str(item["AppName"]))
    grid = folder / "userdata" / "170579662" / "config" / "grid"
    assert any(grid.glob(f"{number}*.png"))                           # the drawn artwork
    again = jobs.steam_entry(CONSOLE, folder, LOGO_PATH, closed=with_steam_closed)
    assert again.ok and len(steam.shortcuts(folder)) == 1             # brought up to date, not added twice
    gone = jobs.steam_entry(CONSOLE, folder, LOGO_PATH, remove=True, closed=with_steam_closed)
    assert gone.ok and "no longer in Steam" in gone.message and steam_shortcuts.in_steam(folder) == set()


def test_steam_that_does_not_close_changes_nothing(tmp_path):
    def refuses(change):
        raise steam.SteamError("Steam did not close within 30 seconds; nothing was changed.")
    outcome = jobs.steam_entry(CONSOLE, steam_folder(tmp_path), LOGO_PATH, closed=refuses)
    assert not outcome.ok and "did not close" in outcome.message


# The direct start

def test_find_console_by_key_name_or_address():
    assert direct.find_console([CONSOLE], "aabbccddeeff") is CONSOLE
    assert direct.find_console([CONSOLE], "living room ps5") is CONSOLE
    assert direct.find_console([CONSOLE], "192.168.1.20") is CONSOLE
    assert direct.find_console([CONSOLE], "PS4") is None


class DirectOps:
    def __init__(self):
        self.streamed = threading.Event()

    def wake_and_wait(self, console, progress):
        progress("Waking…")
        return Outcome(True, "Living room PS5 is on.", console)

    def watch_stream(self, console, deliver, wanted, stop, play, **kwargs):
        self.kwargs = kwargs
        self.streamed.set()
        stop.wait(5)
        return Outcome(True, "Stream ended.")


def test_the_direct_start_streams_until_the_window_closes(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(direct.stream_stats, "folder", lambda: tmp_path / "streams")
    ops = DirectOps()
    quits = []
    monkeypatch.setattr(qapp, "quit", lambda: quits.append(True))
    started = direct.DirectStream(CONSOLE, qapp, ops=ops, full_screen=False)
    assert ops.streamed.wait(5) and callable(ops.kwargs["on_quit"])
    ops.kwargs["on_quit"]()                                            # View, LB and RB held
    wait(qapp, lambda: quits == [True])
    assert not started.thread.is_alive() and started.outcome.ok


def test_the_direct_start_of_a_console_not_registered_says_so(qapp, tmp_path, monkeypatch):
    ConsoleStore(tmp_path).save([CONSOLE])
    shown = []
    monkeypatch.setattr(direct, "exec_app", lambda app: shown.append(app) or 0)
    windows = []
    real = direct.PlayWindow

    def keep(*args, **kwargs):
        windows.append(real(*args, **kwargs))
        return windows[-1]
    monkeypatch.setattr(direct, "PlayWindow", keep)
    assert direct.run("PS4-Pro", qapp, tmp_path) == 2
    qapp.processEvents()
    assert "No registered console is called 'PS4-Pro'" in windows[0].status.text()
    assert "Living room PS5" in windows[0].status.text()
    windows[0].close()
