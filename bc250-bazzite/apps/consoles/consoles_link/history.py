# SPDX-License-Identifier: AGPL-3.0-or-later
"""The games played through the app and the time played (owner, 13-10-2026): during a stream the console is asked
what it runs every INTERVAL seconds (the discovery answer's running-app name and title ID, as the Console box shows
it), and the time since the last answer goes to the game that ran. Only streams to this board are counted: play on
the console itself is not seen.

Kept in ~/.config/bc250-console-link/history.json (mode 0600: which games were played when is personal), one entry
per console and game; History… in the window shows it and clears it."""

from __future__ import annotations

import datetime
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

from .discovery import Console

FILE_NAME = "history.json"
INTERVAL = 30.0
SEARCH_TIMEOUT = 1.0


@dataclass(frozen=True)
class Played:
    console: str                        # the registered console's key
    console_name: str
    title_id: str
    name: str                           # the game's name as the console reports it; "" when it gave none
    seconds: float
    last_played: str                    # ISO date and time, local

    @property
    def key(self) -> tuple[str, str]:
        return self.console, self.title_id or self.name

    @property
    def title(self) -> str:
        return self.name or self.title_id


class HistoryStore:
    def __init__(self, folder: Path):
        self.path = folder / FILE_NAME
        self._lock = threading.Lock()

    def load(self) -> list[Played]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        games = []
        for entry in data.get("games", []) if isinstance(data, dict) else []:
            try:
                games.append(Played(console=str(entry["console"]), console_name=str(entry.get("console_name", "")),
                                    title_id=str(entry.get("title_id", "")), name=str(entry.get("name", "")),
                                    seconds=float(entry["seconds"]), last_played=str(entry.get("last_played", ""))))
            except (KeyError, TypeError, ValueError):
                continue                                # one broken entry does not hide the others
        return games

    def save(self, games: list[Played]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"games": [asdict(game) for game in games]}, indent=2) + "\n"
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)

    def add(self, console: str, console_name: str, title_id: str, name: str, seconds: float,
            when: datetime.datetime | None = None) -> None:
        """*seconds* more for the game on *console*, played up to *when* (now)."""
        played = Played(console, console_name, title_id, name, seconds,
                        (when or datetime.datetime.now()).isoformat(timespec="seconds"))
        with self._lock:
            games = self.load()
            for i, game in enumerate(games):
                if game.key == played.key:
                    games[i] = replace(played, name=name or game.name, seconds=game.seconds + seconds)
                    break
            else:
                games.append(played)
            self.save(games)

    def clear(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)


def newest_first(games: list[Played]) -> list[Played]:
    return sorted(games, key=lambda game: game.last_played, reverse=True)


def duration(seconds: float) -> str:
    """1 h 05 min, 12 min, or under a minute."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return "under a minute"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


class Tracker:
    """Asks the console what it runs at the start and every *interval* seconds until stop(), and credits the time
    between two answers to the game of the first; a console that does not answer is taken to run the same game.
    *search* gives the discovery answers for the console's address (discovery.search)."""

    def __init__(self, store: HistoryStore, console_key: str, console_name: str,
                 search: Callable[[], list[Console]], interval: float = INTERVAL,
                 clock: Callable[[], float] = time.monotonic):
        self.store, self.console_key, self.console_name = store, console_key, console_name
        self.search, self.interval, self.clock = search, interval, clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._game: tuple[str, str] | None = None       # title ID and name of what runs, None: the home screen
        self._since = 0.0

    def start(self) -> Tracker:
        self._since = self.clock()
        self._thread = threading.Thread(target=self._run, name="history", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._credit()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(self.interval)

    def poll(self) -> None:
        try:
            answers = self.search()
        except OSError:
            answers = []
        if answers:
            answer = answers[0]
            game = ((answer.running_title_id, answer.running_app)
                    if answer.running_title_id or answer.running_app else None)
        else:
            game = self._game
        self._credit()
        self._game = game

    def _credit(self) -> None:
        now = self.clock()
        seconds, self._since = now - self._since, now
        if self._game is not None and seconds > 0:
            try:
                self.store.add(self.console_key, self.console_name, *self._game, seconds)
            except OSError:
                pass                                    # a full disk costs the history, not the stream
