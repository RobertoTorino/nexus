# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

import pytest

from consoles_link import discovery
from consoles_link.target import Target
from fake_console import DiscoveryConsole, free_port

# Written for these tests in the format the reference parses (lib/src/discovery.c: the status line, then key:value lines
# ending in "\n"); not recorded from a console yet. Replace them with recorded answers after the board check.
STANDBY_PS5 = (b"HTTP/1.1 620 Server Standby\nhost-id:A1B2C3D4E5F6\nhost-type:PS5\nhost-name:PS5-123\n"
               b"host-request-port:997\ndevice-discovery-protocol-version:00030010\nsystem-version:09060004\n")
READY_PS4 = (b"HTTP/1.1 200 Ok\nhost-id:001122334455\nhost-type:PS4\nhost-name:PS4-Pro\nhost-request-port:997\n"
             b"device-discovery-protocol-version:00020020\nsystem-version:11008001\nrunning-app-titleid:CUSA00001\n"
             b"running-app-name:Bloodborne\n")


def test_srch_packets_are_the_references():
    assert discovery.srch_packet(False) == b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00020020\n\0"
    assert discovery.srch_packet(True) == b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n\0"


def test_wakeup_packet_carries_the_key_as_a_number():
    packet = discovery.wakeup_packet(discovery.wakeup_credential(b"1a2b3c4d\0\0\0\0\0\0\0\0"), True)
    assert b"user-credential:439041101\n" in packet
    assert packet.startswith(b"WAKEUP * HTTP/1.1\nclient-type:vr\nauth-type:R\nmodel:w\napp-type:r\n")
    assert packet.endswith(b"device-discovery-protocol-version:00030010\n\0")


@pytest.mark.parametrize("key", [b"", b"\0" * 16, b"123456789"])
def test_wakeup_needs_a_usable_key(key):
    with pytest.raises(ValueError):
        discovery.wakeup_credential(key)


def test_parse_standby_ps5():
    console = discovery.parse_answer(STANDBY_PS5, "192.168.1.20")
    assert (console.state, console.ps5, console.host_name, console.request_port) == ("standby", True, "PS5-123", 997)
    assert console.target == Target.PS5_1
    assert console.model == "PS5"


def test_parse_ready_ps4():
    console = discovery.parse_answer(READY_PS4, "192.168.1.21")
    assert (console.state, console.ps5, console.running_app) == ("ready", False, "Bloodborne")
    assert console.target == Target.PS4_10


@pytest.mark.parametrize("version, ps5, target", [
    ("08050001", True, Target.PS5_1), ("08050000", True, Target.PS5_UNKNOWN), ("07020001", False, Target.PS4_9),
    ("06500000", False, Target.PS4_8), ("", False, Target.PS4_UNKNOWN), ("garbage", True, Target.PS4_UNKNOWN),
])
def test_target_from_system_version(version, ps5, target):
    assert discovery.Console("x", ps5, "ready", system_version=version).target == target


def test_search_finds_a_ps5_through_its_own_port():
    console = DiscoveryConsole(ps5=True)
    try:
        found = discovery.search("127.0.0.1", timeout=0.5, local_ports=[0], **console.ports)
    finally:
        console.close()
    assert len(found) == 1 and found[0].host_name == "Living room PS5" and found[0].address == "127.0.0.1"
    assert found[0].ps5 and found[0].state == "ready"
    # Both packets went out: a PS4 search to the PS4 port and a PS5 search to the PS5 port.
    assert discovery.srch_packet(False) in console.received and discovery.srch_packet(True) in console.received


def test_search_finds_a_ps4_in_rest_mode():
    console = DiscoveryConsole(ps5=False, state=620, name="PS4", system_version="11008001")
    try:
        found = discovery.search("127.0.0.1", timeout=0.5, local_ports=[0], **console.ports)
    finally:
        console.close()
    assert [(c.ps5, c.state, c.target) for c in found] == [(False, "standby", Target.PS4_10)]


def test_search_with_nobody_there_returns_nothing():
    ports = {"ps4_port": free_port(), "ps5_port": free_port()}      # nothing listens there
    start = time.monotonic()
    assert discovery.search("127.0.0.1", timeout=0.3, local_ports=[0], **ports) == []
    assert time.monotonic() - start < 2


def test_wake_sends_the_packet_to_the_console():
    console = DiscoveryConsole(ps5=True)
    try:
        discovery.wake("127.0.0.1", b"1a2b3c4d", True, port=console.ps5_port)
        deadline = time.monotonic() + 2
        while not console.received and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        console.close()
    assert console.received and console.received[0].startswith(b"WAKEUP")


def test_software_version_of_a_ps4():
    from consoles_link.target import software_version
    assert software_version("14008001", False) == "14.00"           # the owner's PS4 Pro on 14.00
    assert software_version("09508001", False) == "9.50"
    assert software_version("08050001", True) == ""                 # a PS5 reports a Remote Play generation there
    assert software_version("", False) == software_version("1400", False) == software_version("x4008001", False) == ""
