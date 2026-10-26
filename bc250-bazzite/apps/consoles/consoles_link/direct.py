# SPDX-License-Identifier: AGPL-3.0-or-later
"""The direct start (bc250-console-link --stream <console>), as a Steam shortcut in Game Mode runs it: no main
window, only the stream, full screen. The console is found among the registered ones by its name, host id or
address, woken from rest mode when it is there, and streamed with the board's controllers; what happens shows in the
stream window's status line. Closing the window ends the program."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from bc250_core.app import exec_app
from bc250_core.platform import config_home

from . import APP_ID, APP_NAME, jobs, stream_stats
from .consoles import ConsoleStore, RegisteredConsole
from .history import HistoryStore
from .stream import PlayerExperiment
from .stream_view import KEYS, StreamWindow


class Messenger(QObject):
    """Carries the stream thread's news to the window, on the GUI thread."""
    status = pyqtSignal(str)


def find_console(consoles: list[RegisteredConsole], wanted: str) -> RegisteredConsole | None:
    wanted = wanted.strip().lower()
    for console in consoles:
        if wanted in (console.key.lower(), console.host_id.lower(), console.nickname.lower(), console.address):
            return console
    return None


CLOSE_TIMEOUT = 5.0                     # s the app waits, after the window closes, for the stream to close

class DirectStream:
    """The window and the thread that wakes the console and runs the stream. *ops* is jobs (a stand-in in tests)."""

    def __init__(self, console: RegisteredConsole, app: QApplication, ops=jobs, full_screen: bool = True,
                 players: PlayerExperiment = PlayerExperiment(), simulated_loss: float = 0.0,
                 played: HistoryStore | None = None):
        self.console, self.app, self.ops, self.players = console, app, ops, players
        self.simulated_loss, self.played = simulated_loss, played
        self.stop = threading.Event()
        self.messenger = Messenger()
        self.window = StreamWindow(f"{console.nickname or 'Console'} · {APP_NAME}", self._closed,
                                   options=console.options)
        self.messenger.status.connect(self._show)
        self.outcome = None
        if full_screen:
            self.window.showFullScreen()
        else:
            self.window.show()
        self.window.bring_forward()
        self.window.status.setText(f"Starting… ({KEYS})")
        self.thread = threading.Thread(target=self._run, name="direct", daemon=True)
        self.thread.start()

    def _show(self, text: str) -> None:
        self.window.status.setText(text)

    def _closed(self) -> None:
        """The window closed: the stream stops, and the app quits once the stream has closed the session (the
        console is told), within CLOSE_TIMEOUT. Quitting at once cut that short (owner's board, 13-10-2026)."""
        self.stop.set()
        self._quit_when_done(time.monotonic() + CLOSE_TIMEOUT)

    def _quit_when_done(self, deadline: float) -> None:
        if self.thread.is_alive() and time.monotonic() < deadline:
            QTimer.singleShot(50, lambda: self._quit_when_done(deadline))
            return
        self.app.quit()

    def _run(self) -> None:
        on = self.ops.wake_and_wait(self.console, self.messenger.status.emit)
        if not on.ok:
            self.outcome = on
            self.messenger.status.emit(f"{on.message} Close this window to go back.")
            return
        self.messenger.status.emit(f"{on.message} Starting the stream…")
        window = self.window
        self.outcome = self.ops.watch_stream(on.value, window.deliver, window.wanted, self.stop, window.play,
                                             figures=window.figures, stats_dir=stream_stats.folder(),
                                             **({"players": self.players} if self.players.on else {}),
                                             **({"simulated_loss": self.simulated_loss} if self.simulated_loss else {}),
                                             **({"played": self.played} if self.played is not None else {}))
        if not self.stop.is_set():                      # ended by the console or a fault, not by closing
            self.messenger.status.emit(f"{self.outcome.message} Close this window to go back.")


def run(wanted: str, app: QApplication, config_dir: Path | None = None,
        players: PlayerExperiment = PlayerExperiment(), simulated_loss: float = 0.0) -> int:
    """The direct start: 2 when no registered console matches *wanted*. *players*: the several-players experiment;
    *simulated_loss*: the share of video packets dropped on purpose, in percent, to try the recovery."""
    folder = (config_dir or config_home()) / APP_ID
    consoles = ConsoleStore(folder).load()
    console = find_console(consoles, wanted)
    if console is None:
        from PyQt6.QtWidgets import QMessageBox
        names = ", ".join(c.nickname or c.address for c in consoles) or "none yet"
        QMessageBox.critical(None, APP_NAME, f"No registered console is called {wanted!r}. Registered: {names}.")
        return 2
    direct = DirectStream(console, app, players=players,     # noqa: F841 (kept alive while the app runs)
                          simulated_loss=simulated_loss, played=HistoryStore(folder))
    return exec_app(app)
