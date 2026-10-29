# SPDX-License-Identifier: GPL-3.0-or-later
"""The crypto primitives against reference implementations and the RSA keysets."""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from shadps4_manager.pkgxtractor import crypto
from shadps4_manager.pkgxtractor.keys import FAKE_KEYSET, PKG_DERIVED_KEY3_KEYSET


def _xts_mult(tweak: bytearray) -> None:
    feedback = 0
    for k in range(16):
        tmp = (tweak[k] >> 7) & 1
        tweak[k] = ((tweak[k] << 1) + feedback) & 0xFF
        feedback = tmp
    if feedback:
        tweak[0] ^= 0x87


def _reference_decrypt_pfs(data_key: bytes, tweak_key: bytes, src: bytes, sector: int) -> bytes:
    """Literal transcription of Crypto::decryptPFS using single-block ECB primitives."""
    ecb_enc = Cipher(algorithms.AES(tweak_key), modes.ECB()).encryptor()
    ecb_dec = Cipher(algorithms.AES(data_key), modes.ECB()).decryptor()
    out = bytearray(len(src))
    full = len(src) & ~0xFFF
    for i in range(0, full, 0x1000):
        tweak = bytearray(ecb_enc.update((sector + i // 0x1000).to_bytes(8, "little") + bytes(8)))
        for off in range(0, 0x1000, 16):
            block = src[i + off:i + off + 16]
            x = bytes(a ^ b for a, b in zip(block, tweak, strict=True))
            x = ecb_dec.update(x)
            out[i + off:i + off + 16] = bytes(a ^ b for a, b in zip(x, tweak, strict=True))
            _xts_mult(tweak)
    out[full:] = src[full:]
    return bytes(out)


def test_decrypt_pfs_matches_reference_implementation() -> None:
    data_key = os.urandom(16)
    tweak_key = os.urandom(16)
    src = os.urandom(0x3000 + 100)  # three sectors plus a partial tail
    got = crypto.decrypt_pfs(data_key, tweak_key, src, 0x1234)
    assert got == _reference_decrypt_pfs(data_key, tweak_key, src, 0x1234)
    assert got[-100:] == src[-100:]  # tail is copied through untouched


def test_aes_cbc_decrypt_copies_partial_tail() -> None:
    ivkey = os.urandom(32)
    plaintext = os.urandom(48)
    enc = Cipher(algorithms.AES(ivkey[16:32]), modes.CBC(ivkey[:16])).encryptor()
    ciphertext = enc.update(plaintext) + enc.finalize() + b"tail!"
    assert crypto.aes_cbc_cfb128_decrypt(ivkey, ciphertext) == plaintext + b"tail!"


def test_pfs_gen_crypto_key_layout() -> None:
    import hashlib
    import hmac

    ekpfs = os.urandom(32)
    seed = os.urandom(16)
    data_key, tweak_key = crypto.pfs_gen_crypto_key(ekpfs, seed)
    digest = hmac.new(ekpfs, b"\x01\x00\x00\x00" + seed, hashlib.sha256).digest()
    assert tweak_key == digest[:16]
    assert data_key == digest[16:32]


@pytest.mark.parametrize("keyset,is_dk3", [(FAKE_KEYSET, False), (PKG_DERIVED_KEY3_KEYSET, True)])
def test_rsa_pkcs1v15_roundtrip(keyset: dict, is_dk3: bool) -> None:
    message = os.urandom(32)
    padding = bytes(b or 1 for b in os.urandom(256 - 3 - len(message)))
    em = b"\x00\x02" + padding + b"\x00" + message
    ciphertext = pow(int.from_bytes(em, "big"), keyset["e"], keyset["n"]).to_bytes(256, "big")
    assert crypto.rsa2048_decrypt(ciphertext, is_dk3=is_dk3) == message


def test_rsa_invalid_padding_returns_none() -> None:
    assert crypto.rsa2048_decrypt(os.urandom(255) + b"\x01", is_dk3=False) is None
