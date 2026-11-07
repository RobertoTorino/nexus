# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
import json
import stat
import threading

from PyQt6.QtWidgets import QMessageBox

from consoles_link import discovery, history, jobs
from consoles_link.consoles import RegisteredConsole
from consoles_link.discovery import Console
from consoles_link.history import HistoryStore, Tracker, duration
from consoles_link.history_dialog import HistoryDialog
from consoles_link.target import Target

WHEN = datetime.datetime(2026, 10, 13, 21, 30)


def _answer(title_id: str = "", name: str = "") -> Console:
    return Console("192.168.1.21", False, "ready", host_name="PS4-728", running_app=name, running_title_id=title_id)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_store_adds_up_per_console_and_game(tmp_path):
    store = HistoryStore(tmp_path)
    assert store.load() == []
    store.add("ps4", "PS4-728", "CUSA00001", "Lumines Remastered", 600, WHEN)
    store.add("ps4", "PS4-728", "CUSA00001", "Lumines Remastered", 300, WHEN + datetime.timedelta(hours=1))
    store.add("ps4", "PS4-728", "CUSA00002", "", 60, WHEN)              # no name from the console: the title ID
    store.add("ps5", "Living room", "CUSA00001", "Lumines Remastered", 30, WHEN)
    games = {(g.console, g.title_id): g for g in store.load()}
    assert len(games) == 3
    lumines = games["ps4", "CUSA00001"]
    assert lumines.seconds == 900 and lumines.last_played == "2026-10-13T22:30:00"
    assert games["ps4", "CUSA00002"].title == "CUSA00002"
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600              # what was played when is personal
    store.clear()
    assert store.load() == [] and not store.path.exists()


def test_store_skips_a_broken_entry(tmp_path):
    (tmp_path / history.FILE_NAME).write_text(json.dumps({"games": [
        {"console": "ps4", "title_id": "CUSA00001", "name": "Lumines", "seconds": 5, "last_played": ""},
        {"console": "ps4", "seconds": "lots"}]}))
    assert [g.name for g in HistoryStore(tmp_path).load()] == ["Lumines"]
    (tmp_path / history.FILE_NAME).write_text("not json")
    assert HistoryStore(tmp_path).load() == []


def test_duration():
    assert duration(59) == "under a minute"
    assert duration(12 * 60 + 30) == "12 min"
    assert duration(3600 + 5 * 60) == "1 h 05 min"


def test_tracker_credits_the_time_between_answers(tmp_path):
    store, clock = HistoryStore(tmp_path), Clock()
    answers = iter([[_answer()],                                          # the home screen: not counted
                    [_answer("CUSA00001", "Lumines Remastered")],
                    [],                                                   # no answer: the same game goes on
                    [_answer("CUSA00002", "Astro Bot")]])
    tracker = Tracker(store, "ps4", "PS4-728", lambda: next(answers), clock=clock)
    tracker._since = clock()
    for at in (0, 30, 60, 90):
        clock.now = at
        tracker.poll()
    clock.now = 100
    tracker.stop()                                                        # never started: only the last credit
    games = {g.name: g.seconds for g in store.load()}
    assert games == {"Lumines Remastered": 60, "Astro Bot": 10}


def test_tracker_runs_beside_the_stream(tmp_path):
    store = HistoryStore(tmp_path)
    asked = threading.Event()

    def search():
        asked.set()
        return [_answer("CUSA00001", "Lumines Remastered")]
    tracker = Tracker(store, "ps4", "PS4-728", search, interval=60).start()
    assert asked.wait(2)
    tracker.stop()
    [game] = store.load()
    assert game.name == "Lumines Remastered" and game.console_name == "PS4-728" and game.seconds > 0


def test_watch_stream_keeps_the_history(tmp_path, monkeypatch):
    console = RegisteredConsole("001122334455", "PS4-728", "192.168.1.21", Target.PS4_10, b"k", b"r")
    asked = []
    monkeypatch.setattr(discovery, "search",
                        lambda address, timeout: asked.append(address) or [_answer("CUSA00001", "Lumines")])
    monkeypatch.setattr(jobs, "_session", lambda console, hold, **kwargs: jobs.Outcome(True, hold(None)))
    monkeypatch.setattr(jobs, "_run_stream", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(jobs, "_stream_summary", lambda connection, seconds: "fine")
    store = HistoryStore(tmp_path)
    watched = jobs.watch_stream(console, None, None, threading.Event(), played=store)
    assert watched.ok and asked == ["192.168.1.21"]
    [game] = store.load()
    assert (game.console, game.console_name, game.title_id, game.name) == ("001122334455", "PS4-728", "CUSA00001",
                                                                          "Lumines")


def test_dialog_lists_newest_first_and_clears(qapp, tmp_path, monkeypatch):
    store = HistoryStore(tmp_path)
    dialog = HistoryDialog(store)
    assert dialog.table.rowCount() == 0 and not dialog.clear_button.isEnabled()
    assert dialog.total.text() == "No games played through the app yet."
    store.add("ps4", "PS4-728", "CUSA00001", "Lumines Remastered", 3900, WHEN)
    store.add("ps4", "PS4-728", "CUSA00002", "Astro Bot", 600, WHEN + datetime.timedelta(days=1))
    dialog.refresh()
    rows = [[dialog.table.item(r, c).text() for c in range(4)] for r in range(dialog.table.rowCount())]
    assert rows == [["Astro Bot", "PS4-728", "10 min", "14-10-2026 21:30"],
                    ["Lumines Remastered", "PS4-728", "1 h 05 min", "13-10-2026 21:30"]]
    assert dialog.table.item(0, 0).toolTip() == "Title ID CUSA00002"
    assert dialog.total.text() == "2 games, 1 h 15 min in all."
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog.clear()
    assert dialog.table.rowCount() == 2
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog.clear()
    assert dialog.table.rowCount() == 0 and store.load() == []
    dialog.close()

