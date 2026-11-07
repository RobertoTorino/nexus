# SPDX-License-Identifier: AGPL-3.0-or-later
"""The crypto against vectors printed by the reference's own C code (lib/src/rpcrypt.c at commit c8bea2642d0e, built
with OpenSSL on 12-10-2026): five targets, three seeds each, every derived value and a whole encrypted message.
The consoles accept what the reference sends, so equal bytes are the proof the port is right."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consoles_link import keys
from consoles_link.rpcrypt import RPCrypt, aeropause, bright_ambassador, hmac_key
from consoles_link.target import Target

VECTORS = json.loads((Path(__file__).parent / "rpcrypt_vectors.json").read_text(encoding="utf-8"))
MESSAGE = (b"Client-Type: dabfa2ec873de5839bee8d3f4c0239c4282c07c25c6077a2931afcf0adc0d34f\r\n"
           b"Np-AccountId: AAECAwQFBgc=\r\n")


def _id(vector: dict) -> str:
    return f"{Target(vector['target']).name}-{vector['nonce'][:4]}"


@pytest.mark.parametrize("vector", VECTORS, ids=_id)
def test_session_crypto_matches_reference(vector):
    target = Target(vector["target"])
    crypt = RPCrypt.for_session(target, bytes.fromhex(vector["nonce"]), bytes.fromhex(vector["morning"]))
    assert crypt.bright.hex() == vector["auth_bright"]
    assert crypt.ambassador.hex() == vector["auth_ambassador"]
    assert crypt.iv(vector["counter"]).hex() == vector["auth_iv"]
    assert crypt.encrypt(vector["counter"], MESSAGE).hex() == vector["auth_encrypted"]


@pytest.mark.parametrize("vector", VECTORS, ids=_id)
def test_regist_crypto_matches_reference(vector):
    target = Target(vector["target"])
    ambassador = bytes.fromhex(vector["ambassador"])
    crypt = RPCrypt.for_regist(target, ambassador, vector["key_0_off"], vector["pin"])
    assert crypt.bright.hex() == vector["regist_bright"]
    assert aeropause(target, vector["key_1_off"], ambassador).hex() == vector["aeropause"]
    assert crypt.encrypt(0, MESSAGE).hex() == vector["regist_encrypted"]


def test_the_vectors_cover_every_known_target():
    assert {Target(v["target"]) for v in VECTORS} == set(Target) - {Target.PS4_UNKNOWN}


@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 100])
def test_decrypt_undoes_encrypt_for_any_length(size):
    crypt = RPCrypt.for_session(Target.PS5_1, bytes(range(16)), bytes(range(16, 32)))
    data = bytes(range(size))
    assert crypt.decrypt(7, crypt.encrypt(7, data)) == data
    assert len(crypt.encrypt(7, data)) == size


def test_each_counter_gives_its_own_keystream():
    crypt = RPCrypt.for_session(Target.PS4_10, bytes(16), bytes(16))
    assert crypt.encrypt(0, bytes(16)) != crypt.encrypt(1, bytes(16))


def test_hmac_key_per_target():
    # The reference: an unknown PS5 version uses the PS4 key, only PS5 1.0 its own.
    assert hmac_key(Target.PS5_1) == keys.HMAC_PS5
    assert hmac_key(Target.PS5_UNKNOWN) == keys.HMAC_PS4
    assert hmac_key(Target.PS4_10) == keys.HMAC_PS4
    assert hmac_key(Target.PS4_8) == hmac_key(Target.PS4_9) == keys.HMAC_PS4_PRE10


def test_table_sizes():
    for table in (keys.BRIGHT_AMBASSADOR_A_PS4, keys.BRIGHT_AMBASSADOR_A_PS5, keys.BRIGHT_AMBASSADOR_B_PS4,
                  keys.BRIGHT_AMBASSADOR_B_PS5):
        assert len(table) == 0x70 * 0x20
    for table in (keys.AEROPAUSE_PS4, keys.AEROPAUSE_PS5, keys.REGIST_PS4, keys.REGIST_PS5):
        assert len(table) == 0x200


def test_regist_key_offset_is_checked():
    with pytest.raises(ValueError):
        RPCrypt.for_regist(Target.PS5_1, bytes(16), 0x20, 12345678)


def test_bright_ambassador_uses_the_whole_nonce_range():
    # nonce[0] >> 3 and nonce[7] >> 3 pick one of 32 rows of 0x70 bytes: the last row is inside the table.
    bright, ambassador = bright_ambassador(Target.PS5_1, bytes([0xff] * 16), bytes(16))
    assert len(bright) == len(ambassador) == 16
