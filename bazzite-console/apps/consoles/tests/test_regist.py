# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64

import pytest

from consoles_link import regist
from consoles_link.rpcrypt import RPCrypt, aeropause
from consoles_link.target import Target
from fake_console import AMBASSADOR, MAC, REGIST_KEY, RP_KEY, RegistConsole

ACCOUNT = bytes(range(8))


def _register(console: RegistConsole, target: Target, pin: int = 12345678, account: bytes = ACCOUNT):
    return regist.register("127.0.0.1", target, account, pin, port=console.port, timeout=2.0,
                           random=lambda n: AMBASSADOR[:n], pause=0)


@pytest.mark.parametrize("target", [Target.PS5_1, Target.PS4_10, Target.PS4_9])
def test_register_with_the_console(target):
    console = RegistConsole(target=target)
    try:
        registration = _register(console, target)
    finally:
        console.close()
    assert console.errors == []
    assert (registration.regist_key, registration.rp_key, registration.mac) == (REGIST_KEY, RP_KEY, MAC)
    assert registration.nickname == "Living room" and registration.rp_key_type == 2
    first, headers, inner = console.requests[0]
    assert first == f"POST {regist.path(target)} HTTP/1.1"
    assert inner["Np-AccountId"] == base64.b64encode(ACCOUNT).decode()
    assert inner["Client-Type"] == ("Windows" if target.pre10 else regist.CLIENT_TYPE)
    assert headers.get("RP-Version") == {Target.PS5_1: "1.0", Target.PS4_10: "10.0", Target.PS4_9: "9.0"}[target]


def test_wrong_pin_is_reported():
    console = RegistConsole(target=Target.PS5_1, refuse="80108b09")
    try:
        with pytest.raises(regist.RegistError, match="wrong PIN"):
            _register(console, Target.PS5_1, pin=11111111)
    finally:
        console.close()


def test_wrong_account_is_reported():
    console = RegistConsole(target=Target.PS4_10, account_id=bytes(8))
    try:
        with pytest.raises(regist.RegistError, match="Invalid PSN account"):
            _register(console, Target.PS4_10)
    finally:
        console.close()


def test_no_console_at_the_address():
    console = RegistConsole()
    console.close()
    with pytest.raises(regist.RegistError):
        _register(console, Target.PS5_1)


def test_payload_layout():
    payload, crypt = regist.build_payload(Target.PS5_1, AMBASSADOR, ACCOUNT, 12345678)
    assert payload[:0xc7] == b"A" * 0xc7
    key_1_off = ord("A") >> 3
    seed = aeropause(Target.PS5_1, key_1_off, AMBASSADOR)
    assert payload[0xc7:0xcf] == seed[8:] and payload[0x191:0x199] == seed[:8]
    assert crypt == RPCrypt.for_regist(Target.PS5_1, AMBASSADOR, ord("A") & 0x1f, 12345678)
    assert crypt.decrypt(0, payload[0x1e0:]).startswith(b"Client-Type: " + regist.CLIENT_TYPE.encode())


def test_request_header_is_the_references():
    header = regist.request_header(Target.PS5_1, 0x24f)
    assert header == (b"POST /sie/ps5/rp/sess/rgst HTTP/1.1\r\n HTTP/1.1\r\nHOST: 10.0.2.15\r\n"
                      b"User-Agent: remoteplay Windows\r\nConnection: close\r\nContent-Length: 591\r\n"
                      b"RP-Version: 1.0\r\n\r\n")
    assert b"RP-Version" not in regist.request_header(Target.PS4_8, 0x24f)


def test_answer_without_keys_is_refused():
    with pytest.raises(regist.RegistError, match="RegistKey"):
        regist.parse_answer(Target.PS5_1, b"RP-Key: " + RP_KEY.hex().encode() + b"\r\n")


def test_account_id_must_have_8_bytes():
    with pytest.raises(ValueError):
        regist.build_payload(Target.PS5_1, AMBASSADOR, b"1234", 12345678)
