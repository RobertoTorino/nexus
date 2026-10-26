# SPDX-License-Identifier: GPL-3.0-or-later
"""The candidates: read from the board's offer, the service's with their Teredo addresses, put in the answer."""

from __future__ import annotations

from console_linkb import ice

OFFER = "\r\n".join([
    "v=0", "o=- 1 1 IN IP4 0.0.0.0", "s=-", "t=0 0", "a=group:BUNDLE 0 1 2",
    "m=audio 50000 UDP/TLS/RTP/SAVPF 96", "a=mid:0",
    "a=candidate:aa 1 udp 2130706431 192.0.2.10 50000 typ host",
    "a=candidate:bb 1 udp 1694498815 198.51.100.7 50000 typ srflx raddr 192.0.2.10 rport 50000",
    "a=end-of-candidates",
    "m=video 50000 UDP/TLS/RTP/SAVPF 99", "a=mid:1",
    "a=candidate:aa 1 udp 2130706431 192.0.2.10 50000 typ host", ""])
TEREDO = "2001:0:4136:e378:8000:63bf:3fff:fdd2"          # RFC 4380's example: 192.0.2.45, port 40000


def test_local_candidates_of_the_first_section():
    assert ice.local_candidates(OFFER) == [
        {"candidate": "candidate:aa 1 udp 2130706431 192.0.2.10 50000 typ host", "sdpMid": "0", "sdpMLineIndex": 0},
        {"candidate": "candidate:bb 1 udp 1694498815 198.51.100.7 50000 typ srflx raddr 192.0.2.10 rport 50000",
         "sdpMid": "0", "sdpMLineIndex": 0}]


def test_teredo_addresses():
    assert ice.teredo(TEREDO) == ("192.0.2.45", 40000)
    assert ice.teredo("2a02::1") is None and ice.teredo("192.0.2.1") is None


def test_remote_candidates_with_teredo():
    remote = ice.remote_candidates([
        {"candidate": f"a=candidate:1 1 UDP 100 {TEREDO} 9002 typ host", "sdpMid": "0", "sdpMLineIndex": "0"},
        {"candidate": "a=candidate:2 1 UDP 50 203.0.113.5 9002 typ host", "sdpMid": "0", "sdpMLineIndex": "0"},
        {"candidate": "a=end-of-candidates", "sdpMid": "0"}])
    assert [c["candidate"] for c in remote] == [
        "candidate:10 1 UDP 1 192.0.2.45 9002 typ host", "candidate:11 1 UDP 1 192.0.2.45 40000 typ host",
        f"candidate:1 1 UDP 100 {TEREDO} 9002 typ host", "candidate:2 1 UDP 50 203.0.113.5 9002 typ host"]
    assert all(c["sdpMid"] == "0" and c["sdpMLineIndex"] == 0 for c in remote)


def test_the_answer_gets_the_candidates_once_in_every_section():
    answer = "v=0\r\nm=audio 9 UDP 96\r\na=mid:0\r\na=candidate:2 1 UDP 50 203.0.113.5 9002 typ host\r\n" \
             "a=end-of-candidates\r\nm=video 9 UDP 99\r\na=mid:1\r\n"
    remote = ice.remote_candidates([{"candidate": "a=candidate:2 1 UDP 50 203.0.113.5 9002 typ host"},
                                    {"candidate": "a=candidate:3 1 UDP 40 203.0.113.6 9002 typ host"}])
    lines = ice.with_candidates(answer, remote).split("\r\n")
    assert lines == ["v=0", "m=audio 9 UDP 96", "a=mid:0",
                     "a=candidate:2 1 UDP 50 203.0.113.5 9002 typ host",
                     "a=candidate:3 1 UDP 40 203.0.113.6 9002 typ host", "a=end-of-candidates",
                     "m=video 9 UDP 99", "a=mid:1", "a=candidate:2 1 UDP 50 203.0.113.5 9002 typ host",
                     "a=candidate:3 1 UDP 40 203.0.113.6 9002 typ host", "a=end-of-candidates", ""]
