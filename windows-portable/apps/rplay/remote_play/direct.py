# SPDX-License-Identifier: AGPL-3.0-or-later
"""The direct start (Remote-Play.exe --stream <console>), as a console's Steam entry runs it: no main window, only the
stream, full screen. Console Link's direct.py: the console is found among the registered ones by its key, host id,
name or address, woken from rest mode when it is there, and streamed with the handheld's controllers; what happens
shows on the stream window's status line. Closing the window (View, LB and RB held, or the screen touched and held)
ends the program, once the stream has told the console."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from bc250_core.app import exec_app
from bc250_core.platform import suite_data

from . import APP_ID, APP_NAME, SUITE, jobs, stream_stats
from .consoles import ConsoleStore, RegisteredConsole
from .history import HistoryStore
from .stream_window import PlayWindow

CLOSE_TIMEOUT = 5.0                     # s the app waits, after the window closes, for the stream to close


def find_console(consoles: list[RegisteredConsole], wanted: str) -> RegisteredConsole | None:
    wanted = wanted.strip().lower()
    for console in consoles:
        if wanted in (console.key.lower(), console.host_id.lower(), console.nickname.lower(), console.address):
            return console
    return None


class DirectStream:
    """The window and the thread that wakes the console and runs the stream. *ops* is jobs (a stand-in in tests)."""

    def __init__(self, console: RegisteredConsole, app: QApplication, ops=jobs, full_screen: bool = True,
                 played: HistoryStore | None = None):
        self.console, self.app, self.ops, self.played = console, app, ops, played
        self.stop = threading.Event()
        self.window = PlayWindow(f"{console.nickname or 'Console'} · {APP_NAME}", self._closed, console.options)
        self.outcome = None
        if full_screen:
            self.window.showFullScreen()
        else:
            self.window.show()
        self.window.bring_forward()
        self.window.say("Starting…")
        self.thread = threading.Thread(target=self._run, name="direct", daemon=True)
        self.thread.start()

    def _closed(self) -> None:
        """The window closed: the stream stops, and the app quits once the stream has closed the session (the
        console is told), within CLOSE_TIMEOUT."""
        self.stop.set()
        self._quit_when_done(time.monotonic() + CLOSE_TIMEOUT)

    def _quit_when_done(self, deadline: float) -> None:
        if self.thread.is_alive() and time.monotonic() < deadline:
            QTimer.singleShot(50, lambda: self._quit_when_done(deadline))
            return
        self.app.quit()

    def _run(self) -> None:
        window = self.window
        on = self.ops.wake_and_wait(self.console, window.say)
        if not on.ok:
            self.outcome = on
            window.say(on.message)
            return
        window.say(f"{on.message} Starting the stream…")
        self.outcome = self.ops.watch_stream(on.value, window.deliver, window.wanted, self.stop, window.play,
                                             figures=window.figures, stats_dir=stream_stats.folder(),
                                             on_quit=window.end,
                                             **({"played": self.played} if self.played is not None else {}))
        if not self.stop.is_set():                      # ended by the console or a fault, not by closing
            window.messenger.status.emit(self.outcome.message)


def run(wanted: str, app: QApplication, folder: Path | None = None) -> int:
    """The direct start: 2 when no registered console matches *wanted* (the window says so until it is closed)."""
    folder = folder or suite_data(SUITE) / APP_ID
    consoles = ConsoleStore(folder).load()
    console = find_console(consoles, wanted)
    if console is None:
        names = ", ".join(c.nickname or c.address for c in consoles) or "none yet"
        window = PlayWindow(APP_NAME, lambda: None)
        window.showFullScreen()
        window.say(f"No registered console is called {wanted!r}. Registered: {names}. Remove its entry from Steam, "
                   f"or add it again from {APP_NAME}'s My consoles.")
        exec_app(app)
        return 2
    direct = DirectStream(console, app, played=HistoryStore(folder))     # noqa: F841 (kept alive while it runs)
    return exec_app(app)
