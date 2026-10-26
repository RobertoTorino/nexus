# SPDX-License-Identifier: GPL-3.0-or-later
"""One stream from start to end with a stand-in session and service: the states, the picture and the sound as Qt
signals, the end by the person and by an error."""

from __future__ import annotations

import time

import pytest
from test_peer import Service, service_candidates

from console_linkb.auth import AuthError
from console_linkb.session import SessionError, State
from console_linkb.stream import FrameConverter, Stream, state_text


class FakeSession:
    """Records the calls; exchanges with the stand-in service."""

    instances: list[FakeSession] = []

    def __init__(self, client, token, kind, target, locale, service=None, fail=None):
        self.args = (token, kind, target, locale)
        self.service, self.fail = service, fail
        self.calls: list[str] = []
        self.answer = ""
        FakeSession.instances.append(self)

    def play(self):
        self.calls.append("play")
        if self.fail == "play":
            raise SessionError("no servers")
        return "v5/sessions/cloud/X"

    def wait_until_ready(self, transfer_token, on_state, cancelled):
        self.calls.append(f"ready:{transfer_token()}")
        on_state(State("WaitingForResources", wait_s=120))
        on_state(State("Provisioned"))

    def exchange_sdp(self, offer):
        self.calls.append("sdp")
        self.answer = self.service.answer(offer)
        return self.answer

    def exchange_ice(self, candidates):
        self.calls.append(f"ice:{len(candidates)}")
        return service_candidates(self.answer)

    def keepalive(self):
        self.calls.append("keepalive")

    def stop(self):
        self.calls.append("stop")


class FakeAccount:
    client = object()

    def __init__(self, fail=False):
        self.fail = fail

    def home_token(self):
        return "HOME"

    def cloud_token(self):
        if self.fail:
            raise AuthError("Xbox Cloud Gaming is not open to this account")
        return "CLOUD"

    def transfer_token(self):
        return "LPT"


def process(qapp, condition, timeout=15.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_state_texts():
    assert state_text(State("WaitingForResources", wait_s=150)) == \
        "In the queue for a cloud server: about 2 minutes…"
    assert state_text(State("WaitingForResources", wait_s=30)) == "In the queue for a cloud server: about 1 minute…"
    assert state_text(State("WaitingForResources")) == "In the queue for a cloud server…"
    assert state_text(State("Provisioning")) == "Getting the Xbox ready…"
    assert state_text(State("Odd")) == "Odd…"


def test_the_converter_keeps_only_the_newest_frame():
    seen = []

    class Frame:
        def __init__(self, n):
            self.pts = n

    def slow(frame):
        time.sleep(0.05)
        return frame.pts
    converter = FrameConverter(lambda image, pts, arrived: seen.append(pts), slow)
    for n in range(10):
        converter.put(Frame(n), float(n))
    deadline = time.monotonic() + 3
    while 9 not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    converter.stop()
    assert seen[-1] == 9 and len(seen) < 10


def test_a_cloud_stream_from_start_to_the_persons_end(qapp):
    pytest.importorskip("aiortc")
    service = Service()
    FakeSession.instances.clear()
    stream = Stream(FakeAccount(), "cloud", "FORTNITE", "nl-NL",
                    session_factory=lambda *args: FakeSession(*args, service=service))
    got = {"status": [], "ready": 0, "image": [], "sound": [], "ended": []}
    stream.status.connect(got["status"].append)
    stream.ready.connect(lambda: got.__setitem__("ready", got["ready"] + 1))
    stream.image.connect(lambda image, pts, arrived: got["image"].append(image))
    stream.sound.connect(got["sound"].append)
    stream.ended.connect(got["ended"].append)
    try:
        stream.start()
        assert process(qapp, lambda: got["ready"] and got["image"] and got["sound"]), got["status"]
        session = FakeSession.instances[0]
        assert session.args == ("CLOUD", "cloud", "FORTNITE", "nl-NL")
        assert session.calls[:3] == ["play", "ready:LPT", "sdp"] and session.calls[3].startswith("ice:")
        assert "In the queue for a cloud server: about 2 minutes…" in got["status"]
        image = got["image"][-1]
        assert not image.isNull() and image.width() > 0
        assert len(got["sound"][-1]) % 4 == 0 and got["sound"][-1]
        stream.frame_shown(1, 1.0)
        stream.stop()
        assert process(qapp, lambda: got["ended"])
        assert got["ended"] == [""] and session.calls[-1] == "stop"
    finally:
        stream.stop()
        service.close()


def test_a_stream_that_cannot_start_says_why(qapp):
    FakeSession.instances.clear()
    stream = Stream(FakeAccount(fail=True), "cloud", "X")
    ended = []
    stream.ended.connect(ended.append)
    stream.start()
    assert process(qapp, lambda: ended)
    assert ended == ["Xbox Cloud Gaming is not open to this account"]
    assert not FakeSession.instances


def test_a_failed_session_is_ended_with_the_service(qapp):
    FakeSession.instances.clear()
    stream = Stream(FakeAccount(), "home", "F4001234ABCD5678",
                    session_factory=lambda *args: FakeSession(*args, fail="play"))
    ended = []
    stream.ended.connect(ended.append)
    stream.start()
    assert process(qapp, lambda: ended)
    assert ended == ["no servers"]
    assert FakeSession.instances[0].calls == ["play", "stop"]
    assert FakeSession.instances[0].args[:2] == ("HOME", "home")



class WaitingSession(FakeSession):
    """A session that waits for its console until the stream is stopped."""

    def wait_until_ready(self, transfer_token, on_state, cancelled):
        self.calls.append("waiting")
        while not cancelled():
            time.sleep(0.01)
        raise SessionError("cancelled")


def test_stopping_while_the_session_starts_still_ends_it(qapp):
    FakeSession.instances.clear()
    stream = Stream(FakeAccount(), "home", "F4001234ABCD5678", session_factory=lambda *args: WaitingSession(*args))
    ended = []
    stream.ended.connect(ended.append)
    stream.start()
    assert process(qapp, lambda: FakeSession.instances and "waiting" in FakeSession.instances[0].calls)
    stream.stop()
    assert process(qapp, lambda: ended and not stream.thread.is_alive())
    assert ended == [""]
    calls = FakeSession.instances[0].calls
    assert calls[:2] == ["play", "waiting"] and "stop" in calls
