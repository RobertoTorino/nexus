# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network test (senkusha.py): its messages against vectors from the reference's code (nanopb, as senkusha.c builds
them: tests/stream_vectors.json), then whole runs against the console's side in fake_stream.py, which stands in for
the network's MTU limits. The runs need the native core and are skipped without it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consoles_link import senkusha, tkproto
from consoles_link.target import Target

MESSAGES = json.loads((Path(__file__).parent / "stream_vectors.json").read_text(encoding="utf-8"))["messages"]
h = bytes.fromhex


@pytest.mark.parametrize("name, built", [
    ("senkusha_protocol_request", tkproto.protocol_request([9])),
    ("senkusha_big", tkproto.senkusha_big()),
    ("senkusha_echo_on", tkproto.echo_command(True)),
    ("senkusha_echo_off", tkproto.echo_command(False)),
    ("senkusha_mtu_command", tkproto.mtu_command(3, 1015)),          # no num: the reference never sets its has-flag
    ("senkusha_client_mtu", tkproto.client_mtu_command(1, True, 1453, 1453)),
    ("senkusha_client_mtu_final", tkproto.client_mtu_command(2, False, 1454, 1453)),
])
def test_messages_match_reference(name, built):
    assert built == h(MESSAGES[name])


def test_console_answers_decode():
    assert tkproto.protocol_ack(tkproto.parse(h(MESSAGES["senkusha_protocol_ack"]))) == 9
    assert tkproto.senkusha_client_mtu(tkproto.parse(h(MESSAGES["senkusha_client_mtu"]))) == 1
    assert tkproto.senkusha_client_mtu(tkproto.parse(h(MESSAGES["senkusha_mtu_command"]))) is None
    assert tkproto.protocol_ack(tkproto.parse(h(MESSAGES["heartbeat"]))) is None


def test_rtt_for_the_launch_spec():
    assert senkusha.Measurement(1454, 1454, 999).rtt_ms == 0           # whole milliseconds, rounded down
    assert senkusha.Measurement(1454, 1454, 2500).rtt_ms == 2


@pytest.fixture
def console_factory():
    pytest.importorskip("bc250_console_link_core", reason="the native core is not built: see native/pyproject.toml")
    from fake_stream import SenkushaConsole
    made = []

    def make(**behaviour):
        console = SenkushaConsole(Target.PS4_10, b"", b"", **behaviour)
        made.append(console)
        return console
    yield make
    for console in made:
        console.close()


def test_full_run(console_factory):
    console = console_factory()
    measured = senkusha.Senkusha("127.0.0.1", console.port, timeout=2.0).run()
    assert (measured.mtu_in, measured.mtu_out, measured.pongs) == (1454, 1454, 10)
    assert 0 < measured.rtt_us < 1_000_000
    assert console.received[:2] == [tkproto.TAKIONPROTOCOLREQUEST, tkproto.BIG]
    assert console.mtu_requests == [1454]                              # the first try fits: done
    assert console.client_mtu == [(1, True, 1454, 1454), (2, False, 1454, 1454)]
    assert console.pings == 11 and not console.echo                     # 10 for the round trip, 1 for MTU out
    assert console.wait_until(lambda: console.disconnect_reason == "Client Disconnecting") and console.errors == []
    assert measured.log[-1] == "Network test: MTU 1454 in, 1454 out."


def test_mtu_search_finds_the_limits(console_factory):
    console = console_factory(mtu_in_limit=1200, mtu_out_limit=1000)
    measured = senkusha.Senkusha("127.0.0.1", console.port, timeout=2.0).run()
    assert (measured.mtu_in, measured.mtu_out) == (1200, 1000)
    assert console.mtu_requests[:4] == [1454] * 3 + [1015]             # three tries at 1454, then halfway
    assert console.client_mtu[0] == (1, True, 1200, 1200) and console.client_mtu[-1][:2] == (2, False)


def test_no_pongs(console_factory, monkeypatch):
    monkeypatch.setattr(senkusha, "PONG_TIMEOUT", 0.05)
    console = console_factory(answer_pings=False)
    with pytest.raises(senkusha.SenkushaError, match="none of the network test's pings"):
        senkusha.Senkusha("127.0.0.1", console.port, timeout=2.0).run()


def test_no_client_mtu_answer(console_factory):
    console = console_factory(answer_client_mtu=False)
    with pytest.raises(senkusha.SenkushaError, match="client MTU command"):
        senkusha.Senkusha("127.0.0.1", console.port, timeout=0.3).run()


def test_nothing_on_the_port(console_factory):
    console = console_factory(silent=True)
    with pytest.raises(senkusha.SenkushaError, match="network test port"):
        senkusha.Senkusha("127.0.0.1", console.port, timeout=0.1).run()
