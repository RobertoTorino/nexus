# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import struct

import pytest

from consoles_link import session
from consoles_link.target import Target
from fake_console import REGIST_KEY, RP_KEY, SESSION_ID, SessionConsole


def _session(console: SessionConsole, target: Target, login_pin: str = "") -> session.Session:
    return session.Session("127.0.0.1", target, REGIST_KEY.ljust(16, b"\0"), RP_KEY, login_pin=login_pin,
                           port=console.port, timeout=2.0, random=lambda n: bytes(n))


@pytest.mark.parametrize("target, server_type", [(Target.PS5_1, "PS5"), (Target.PS4_10, "PS4 Pro")])
def test_session_starts_and_answers_heartbeats(target, server_type):
    console = SessionConsole(target=target, server_type=1 if target == Target.PS4_10 else 2)
    try:
        with _session(console, target) as started:
            info = started.start()
            started.keep_alive(0.2)
    finally:
        console.close()
    assert console.errors == []
    assert info.session_id == SESSION_ID[1:].decode() and info.server_type == server_type
    assert not any("characters but has" in line for line in info.log)
    assert console.heartbeat_answered.is_set()
    init, ctrl = console.paths
    assert init.endswith("/sess/init") and ctrl.endswith("/sess/ctrl") and (("ps5" in init) == target.ps5)
    # RP-Auth is the registration key, padded to 16 bytes; RP-Did has the reference's prefix and suffix.
    assert console.decrypted["RP-Auth"] == REGIST_KEY.ljust(16, b"\0")
    did = console.decrypted["RP-Did"]
    assert len(did) == 32 and did.startswith(session.DID_PREFIX) and did.endswith(session.DID_SUFFIX)
    assert console.decrypted["RP-OSType"] == b"Win10.0.0\0"
    assert console.decrypted["RP-StartBitrate"] == bytes(4)
    if target.ps5:
        assert console.decrypted["RP-StreamingType"] == (1).to_bytes(4, "little")      # H.264
    else:
        assert "RP-StreamingType" not in console.decrypted
    # After the session ID: microphone off twice and no display devices, as the reference sends them.
    sent = [msg_type for msg_type, _payload in console.messages]
    assert sent[-3:] == [session.MIC_TOGGLE, session.MIC_TOGGLE, session.DISPLAY_DEVICES]


def test_version_mismatch_is_retried_with_the_consoles_version():
    console = SessionConsole(target=Target.PS4_10, wants_version="9.0", server_type=0)
    try:
        with _session(console, Target.PS4_10) as started:
            info = started.start()
    finally:
        console.close()
    assert console.errors == []
    assert info.target == Target.PS4_9 and info.server_type == "PS4"
    assert console.paths == ["/sie/ps4/rp/sess/init", "/sce/rp/session", "/sce/rp/session/ctrl"]
    assert any("9.0" in line for line in info.log)


def test_login_passcode_is_sent_when_asked():
    console = SessionConsole(login_pin="1234")
    try:
        with _session(console, Target.PS5_1, login_pin="1234") as started:
            started.start()
    finally:
        console.close()
    assert console.errors == []
    assert (session.LOGIN_PIN_REP, b"1234") in console.messages


def test_login_passcode_missing():
    console = SessionConsole(login_pin="1234")
    try:
        with _session(console, Target.PS5_1) as started, pytest.raises(session.SessionError, match="passcode"):
            started.start()
    finally:
        console.close()


def test_wrong_login_passcode():
    console = SessionConsole(login_pin="1234")
    try:
        with _session(console, Target.PS5_1, login_pin="9999") as started, \
                pytest.raises(session.SessionError, match="did not accept"):
            started.start()
    finally:
        console.close()


def test_unusual_session_id_gets_a_made_up_one():
    console = SessionConsole(session_id=b"\x4ashort")
    try:
        with _session(console, Target.PS5_1) as started:
            info = started.start()
    finally:
        console.close()
    assert info.session_id and info.session_id != "short"
    assert "The console sent an unusual session ID (6 bytes: 4a 73 68 6f 72 74); using a made-up one." in info.log
    assert "The session ID message says 74 characters but has 5." in info.log


def test_invalid_session_id_from_a_ps4():
    """Recorded from the owner's PS4 Pro: the length byte, then the text InvalidSessionId."""
    console = SessionConsole(target=Target.PS4_10, session_id=bytes.fromhex("10496e76616c696453657373696f6e4964"),
                             server_type=1)
    try:
        with _session(console, Target.PS4_10) as started:
            info = started.start()
    finally:
        console.close()
    assert info.session_id and info.session_id != "InvalidSessionId"
    assert any(line.startswith('The console sent no session ID ("InvalidSessionId")') for line in info.log)
    assert not any("characters but has" in line for line in info.log)


def test_goto_bed_reaches_the_console():
    console = SessionConsole()
    try:
        with _session(console, Target.PS5_1) as started:
            started.start()
            started.goto_bed()
            started.keep_alive(0.2)
    finally:
        console.close()
    assert (session.GOTO_BED, b"") in console.messages


def test_no_console():
    console = SessionConsole()
    console.close()
    with _session(console, Target.PS5_1) as started, pytest.raises(session.SessionError, match="rest mode"):
        started.start()


def test_frame_layout():
    assert session.frame(0x33, b"ab") == struct.pack(">IHH", 2, 0x33, 0) + b"ab"
