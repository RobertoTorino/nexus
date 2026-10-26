# SPDX-License-Identifier: GPL-3.0-or-later
"""A stream session with the streaming service: start, the states up to Provisioned, the exchanges, the end."""

from __future__ import annotations

import json

import pytest
from conftest import FakeTransport

from console_linkb.auth import Region, StreamToken
from console_linkb.net import Client
from console_linkb.session import Session, SessionError

BASE = "https://weu.core.gssv-play-prod.xboxlive.com"
TOKEN = StreamToken("xhome", "HOME", "NL", [Region("WestEurope", BASE, True)], 0)
PATH = f"{BASE}/v5/sessions/home/ABC"


def session(transport, kind="home", target="F4001234ABCD5678") -> Session:
    s = Session(Client(transport), TOKEN, kind, target, "nl-NL", sleep=lambda s: None)
    return s


def test_play_starts_a_home_session_with_the_console():
    transport = FakeTransport({("POST", f"{BASE}/v5/sessions/home/play"):
                               (200, {"sessionPath": "v5/sessions/home/ABC", "sessionId": "ABC"})})
    s = session(transport)
    assert s.play() == "v5/sessions/home/ABC"
    sent = transport.sent("POST", f"{BASE}/v5/sessions/home/play")[0]
    assert sent["serverId"] == "F4001234ABCD5678" and sent["titleId"] == ""
    assert sent["settings"]["locale"] == "nl-NL" and sent["settings"]["nanoVersion"] == "V3;WebrtcTransport.dll"
    headers = transport.headers("POST", f"{BASE}/v5/sessions/home/play")[0]
    assert headers["Authorization"] == "Bearer HOME" and headers["X-Gssv-Client"] == "XboxComBrowser"
    assert json.loads(headers["X-MS-Device-Info"])["dev"]["os"]["platform"] == "desktop"


def test_play_starts_a_cloud_session_with_the_title():
    transport = FakeTransport({("POST", f"{BASE}/v5/sessions/cloud/play"):
                               (200, {"sessionPath": "/v5/sessions/cloud/XYZ/"})})
    s = session(transport, "cloud", "FORTNITE")
    assert s.play() == "v5/sessions/cloud/XYZ"
    sent = transport.sent("POST", f"{BASE}/v5/sessions/cloud/play")[0]
    assert sent["titleId"] == "FORTNITE" and sent["serverId"] == ""


def test_play_without_a_session_is_an_error():
    with pytest.raises(SessionError):
        session(FakeTransport({("POST", f"{BASE}/v5/sessions/home/play"): (200, {})})).play()
    with pytest.raises(ValueError):
        Session(Client(FakeTransport()), TOKEN, "elsewhere", "x")


def test_the_states_up_to_provisioned_with_the_queue_and_one_connect():
    transport = FakeTransport()
    transport.add("GET", f"{PATH}/state", (200, {"state": "Provisioning"}), (200, {"state": "WaitingForResources"}),
                  (200, {"state": "WaitingForResources"}), (200, {"state": "ReadyToConnect"}),
                  (200, {"state": "ReadyToConnect"}), (200, {"state": "Provisioned"}))
    transport.add("GET", f"{BASE}/v1/waittime/F4001234ABCD5678", (200, {"estimatedTotalWaitTimeInSeconds": 150}))
    transport.add("POST", f"{PATH}/connect", (200, b""))
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    seen = []
    s.wait_until_ready(lambda: "LPT", on_state=lambda state: seen.append((state.name, state.wait_s)))
    assert seen == [("Provisioning", 0), ("WaitingForResources", 150), ("WaitingForResources", 150),
                    ("ReadyToConnect", 0), ("ReadyToConnect", 0), ("Provisioned", 0)]
    assert transport.sent("POST", f"{PATH}/connect") == [{"userToken": "LPT"}]
    assert len(transport.sent("GET", f"{BASE}/v1/waittime/")) == 1


def test_a_failed_session_says_why():
    transport = FakeTransport({("GET", f"{PATH}/state"): (200, {"state": "Failed", "errorDetails": {
        "code": "NoAvailableServers", "message": "Try again later"}})})
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    with pytest.raises(SessionError, match="NoAvailableServers Try again later"):
        s.wait_until_ready(lambda: "LPT")


def test_a_session_gone_or_cancelled_ends_the_wait():
    s = session(FakeTransport())
    s.path = "v5/sessions/home/ABC"
    with pytest.raises(SessionError, match="ended the session"):
        s.wait_until_ready(lambda: "LPT")
    with pytest.raises(SessionError, match="cancelled"):
        s.wait_until_ready(lambda: "LPT", cancelled=lambda: True)


def test_the_sdp_exchange_waits_for_the_answer():
    transport = FakeTransport()
    transport.add("POST", f"{PATH}/sdp", (202, b""))
    transport.add("GET", f"{PATH}/sdp", (204, b""), (200, {"exchangeResponse": json.dumps(
        {"sdp": "v=0 answer", "sdpType": "answer", "status": "success"}), "errorDetails": {}}))
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    assert s.exchange_sdp("v=0 offer") == "v=0 answer"
    sent = transport.sent("POST", f"{PATH}/sdp")[0]
    assert sent["messageType"] == "offer" and sent["sdp"] == "v=0 offer"
    assert sent["configuration"]["input"] == {"minVersion": 1, "maxVersion": 8}


def test_an_exchange_error_is_said():
    transport = FakeTransport({("POST", f"{PATH}/sdp"): (202, b""), ("GET", f"{PATH}/sdp"): (
        200, {"exchangeResponse": None, "errorDetails": {"code": "Offer", "message": "bad codec"}})})
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    with pytest.raises(SessionError, match="sdp: Offer bad codec"):
        s.exchange_sdp("v=0")


def test_an_exchange_without_an_answer_gives_up():
    transport = FakeTransport({("POST", f"{PATH}/ice"): (202, b""), ("GET", f"{PATH}/ice"): (204, b"")})
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    with pytest.raises(SessionError, match="no answer"):
        s.exchange_ice([])


def test_the_ice_exchange():
    remote = [{"candidate": "a=candidate:1 1 UDP 1 203.0.113.5 9002 typ host", "sdpMid": "0",
               "sdpMLineIndex": "0"}, {"candidate": "a=end-of-candidates", "sdpMid": "0"}, {"nothing": 1}]
    transport = FakeTransport({("POST", f"{PATH}/ice"): (202, b""),
                               ("GET", f"{PATH}/ice"): (200, {"exchangeResponse": json.dumps(remote)})})
    s = session(transport)
    s.path = "v5/sessions/home/ABC"
    mine = [{"candidate": "candidate:9 1 udp 2130706431 192.0.2.10 50000 typ host", "sdpMid": "0",
             "sdpMLineIndex": 0}]
    assert s.exchange_ice(mine) == remote[:2]
    assert transport.sent("POST", f"{PATH}/ice") == [{"messageType": "iceCandidate", "candidate": mine}]


def test_keepalive_and_stop():
    transport = FakeTransport({("POST", f"{PATH}/keepalive"): (200, b""), ("DELETE", PATH): (500, b"")})
    s = session(transport)
    s.stop()                                    # not started: nothing to end
    s.path = "v5/sessions/home/ABC"
    s.keepalive()
    s.stop()                                    # an error at the end is not the person's problem
    assert s.path == ""
    assert [m for m, *_ in transport.calls] == ["POST", "DELETE"]
