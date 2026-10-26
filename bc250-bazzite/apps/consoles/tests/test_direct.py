# SPDX-License-Identifier: AGPL-3.0-or-later
"""The direct start (--stream): finding the console, waking it and waiting for it (jobs.wake_and_wait), and the
stream window with stand-ins for the network steps."""

from __future__ import annotations

import threading
import time

from consoles_link import direct, jobs
from consoles_link.consoles import ConsoleStore, RegisteredConsole
from consoles_link.discovery import Console
from consoles_link.jobs import Outcome
from consoles_link.target import Target

PS4 = RegisteredConsole(host_id="001122334455", nickname="PS4-728", address="192.168.1.21", target=Target.PS4_10,
                        regist_key=bytes(16), rp_key=bytes(16), mac=bytes(6))


def answer(state: str, address: str = "192.168.1.21") -> Console:
    return Console(address, False, state, host_name="PS4-728", host_id="001122334455", host_type="PS4")


def test_find_console():
    consoles = [PS4]
    for wanted in ("PS4-728", "ps4-728 ", "001122334455", "192.168.1.21"):
        assert direct.find_console(consoles, wanted) is PS4
    assert direct.find_console(consoles, "PS5") is None


class Network:
    """search() answers from a list of states, one per call; wake() is recorded."""

    def __init__(self, *states, everywhere=None):
        self.states, self.everywhere, self.woken, self.searched = list(states), everywhere, [], []

    def search(self, address=None):
        self.searched.append(address)
        if address is None:
            return self.everywhere or []
        state = self.states.pop(0) if self.states else None
        return [answer(state)] if state else []

    def wake(self, address, regist_key, ps5):
        self.woken.append(address)


def wait(network, **kwargs):
    news = []
    clock = iter(range(0, 1000, 2))
    outcome = jobs.wake_and_wait(PS4, news.append, timeout=10, search=network.search, wake=network.wake,
                                 sleep=lambda s: None, clock=lambda: next(clock), **kwargs)
    return outcome, news


def test_a_console_that_is_on():
    outcome, news = wait(Network("ready"))
    assert outcome.ok and outcome.value.address == "192.168.1.21" and news == ["Looking for PS4-728…"]


def test_a_console_in_rest_mode_is_woken():
    network = Network("standby", "standby", "ready")
    outcome, news = wait(network)
    assert outcome.ok and network.woken == ["192.168.1.21"]
    assert news == ["Looking for PS4-728…", "Waking PS4-728 from rest mode…"]


def test_a_console_that_stays_in_rest_mode():
    outcome, _ = wait(Network("standby", *["standby"] * 20))
    assert not outcome.ok and "did not come out of rest mode" in outcome.message


def test_a_console_at_another_address_is_found_by_its_host_id():
    network = Network(None, everywhere=[answer("ready", "192.168.1.40")])
    outcome, _ = wait(network)
    assert outcome.ok and outcome.value.address == "192.168.1.40" and network.searched == ["192.168.1.21", None]


def test_a_console_that_does_not_answer():
    outcome, _ = wait(Network(None))
    assert not outcome.ok and "does not answer" in outcome.message


class FakeOps:
    def __init__(self, on: Outcome, streamed: Outcome | None = None):
        self.on, self.streamed, self.stopped = on, streamed, None

    def wake_and_wait(self, console, progress):
        progress("Waking PS4-728 from rest mode…")
        return self.on

    def watch_stream(self, console, deliver, wanted, stop, play, figures=None, stats_dir=None, played=None):
        self.console = console
        stop.wait(0.2)
        self.stopped = stop.is_set()
        return self.streamed


def _until(qapp, condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


def test_the_direct_stream(qapp):
    moved = PS4.__class__(**{**PS4.__dict__, "address": "192.168.1.40"})
    ops = FakeOps(Outcome(True, "PS4-728 is on.", moved), Outcome(False, "The console ended the stream."))
    stream = direct.DirectStream(PS4, qapp, ops, full_screen=False)
    try:
        assert stream.window.windowTitle() == "PS4-728 · Console Link"
        assert _until(qapp, lambda: stream.window.status.text().startswith("The console ended the stream."))
        assert ops.console.address == "192.168.1.40" and ops.stopped is False
        assert stream.window.status.text().endswith("Close this window to go back.")
    finally:
        stream.window.close()
    assert stream.stop.is_set()


def test_the_direct_stream_without_the_console(qapp):
    ops = FakeOps(Outcome(False, "PS4-728 does not answer."))
    stream = direct.DirectStream(PS4, qapp, ops, full_screen=False)
    assert stream.window.status.text() == f"Starting… ({direct.KEYS})"            # how to get out, from the start
    try:
        assert _until(qapp, lambda: stream.window.status.text() == "PS4-728 does not answer. Close this window to "
                                                                    "go back.")
    finally:
        stream.window.close()


def test_run_with_an_unknown_console(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: shown.append(a[2]))
    ConsoleStore(tmp_path / "bc250-console-link").put(PS4)
    assert direct.run("Living room", qapp, config_dir=tmp_path) == 2
    assert shown == ["No registered console is called 'Living room'. Registered: PS4-728."]


def test_closing_waits_for_the_stream_to_close(qapp):
    class App:
        quits = 0

        def quit(self):
            App.quits += 1

    ops = FakeOps(Outcome(True, "PS4-728 is on.", PS4), Outcome(True, "Stream ended."))
    closing = threading.Event()

    def watch_stream(console, deliver, wanted, stop, play, **kwargs):
        stop.wait(5)
        closing.wait(5)                                     # the session closing, after the stop
        return ops.streamed
    ops.watch_stream = watch_stream
    stream = direct.DirectStream(PS4, App(), ops, full_screen=False)
    stream.window.close()
    assert not _until(qapp, lambda: App.quits, timeout=0.3)     # the stream has not closed yet: no quit
    closing.set()
    assert _until(qapp, lambda: App.quits == 1) and not stream.thread.is_alive()
