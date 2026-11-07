# SPDX-License-Identifier: AGPL-3.0-only
"""The Remote Play crypto of registration and the control connection, ported from the reference's lib/src/rpcrypt.c.

Both sides hold two 16-byte values: "bright" is the AES-128 key and "ambassador" goes into the IV. Each message is
AES-128-CFB with IV = HMAC-SHA256(hmac_key, ambassador || counter as 8 bytes big-endian)[:16], the counter counting
the messages in one direction. The names and the byte arithmetic are the reference's; the tests compare every function
with vectors printed by the reference's own C code."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import keys
from .target import Target

KEY_SIZE = 16


def _b(value: int) -> int:
    return value & 0xff


def _bright_ambassador_pre10(nonce: bytes, morning: bytes) -> tuple[bytes, bytes]:
    ambassador = bytes(_b((_b(nonce[i] - i - 0x27)) ^ keys.ECHO_A[i]) for i in range(KEY_SIZE))
    bright = bytes(_b(_b(morning[i] - i + 0x34) ^ keys.ECHO_B[i] ^ nonce[i]) for i in range(KEY_SIZE))
    return bright, ambassador


def bright_ambassador(target: Target, nonce: bytes, morning: bytes) -> tuple[bytes, bytes]:
    """The session's key and IV seed from the console's nonce (session request) and the registration key (morning)."""
    if target.pre10:
        return _bright_ambassador_pre10(nonce, morning)
    keys_a = keys.BRIGHT_AMBASSADOR_A_PS5 if target.ps5 else keys.BRIGHT_AMBASSADOR_A_PS4
    keys_b = keys.BRIGHT_AMBASSADOR_B_PS5 if target.ps5 else keys.BRIGHT_AMBASSADOR_B_PS4
    key = keys_a[(nonce[0] >> 3) * 0x70:]
    if target.ps5:
        ambassador = bytes(_b(_b(nonce[i] - 0x2d - i) ^ key[i]) for i in range(KEY_SIZE))
    else:
        ambassador = bytes(_b(_b(nonce[i] + 0x36 + i) ^ key[i]) for i in range(KEY_SIZE))
    key = keys_b[(nonce[7] >> 3) * 0x70:]
    if target.ps5:
        bright = bytes(_b(_b(morning[i] + 0x18 + i) ^ nonce[i] ^ key[i]) for i in range(KEY_SIZE))
    else:
        bright = bytes(_b(_b((key[i] ^ morning[i]) + 0x21 + i) ^ nonce[i]) for i in range(KEY_SIZE))
    return bright, ambassador


def aeropause(target: Target, key_1_off: int, ambassador: bytes) -> bytes:
    """The ambassador as the registration request carries it, so the console can derive the same IV."""
    if target.pre10:
        return bytes(_b(_b(ambassador[i] - i - 0x29) ^ keys.ECHO_B[i]) for i in range(KEY_SIZE))
    table = keys.AEROPAUSE_PS5 if target.ps5 else keys.AEROPAUSE_PS4
    wurzelbert = -0x2d if target.ps5 else 0x29
    return bytes(_b((ambassador[i] ^ table[i * 0x20 + key_1_off]) + wurzelbert + i) for i in range(KEY_SIZE))


def hmac_key(target: Target) -> bytes:
    # As the reference: only PS5 1.0 has its own key; an unknown PS5 version uses the PS4 one.
    if target == Target.PS5_1:
        return keys.HMAC_PS5
    if target.pre10 and not target.unknown:
        return keys.HMAC_PS4_PRE10
    return keys.HMAC_PS4


@dataclass
class RPCrypt:
    target: Target
    bright: bytes
    ambassador: bytes

    @classmethod
    def for_session(cls, target: Target, nonce: bytes, morning: bytes) -> RPCrypt:
        """The control connection's crypto (init_auth in the reference)."""
        bright, ambassador = bright_ambassador(target, nonce, morning)
        return cls(target, bright, ambassador)

    @classmethod
    def for_regist(cls, target: Target, ambassador: bytes, key_0_off: int, pin: int) -> RPCrypt:
        """The registration request's crypto: a key from the table (or the fixed pre-7.0 key) mixed with the PIN."""
        if target.pre10:
            bright = bytearray(keys.REGIST_PS4_PRE10)
            first = 0
            target = Target.PS4_9                       # the reference: representative, might not be the actual version
        else:
            if not 0 <= key_0_off < 0x20:
                raise ValueError("key_0_off must be below 0x20")
            table = keys.REGIST_PS5 if target.ps5 else keys.REGIST_PS4
            bright = bytearray(table[i * 0x20 + key_0_off] for i in range(KEY_SIZE))
            first = 0xc
        for i, shift in enumerate((0x18, 0x10, 0x08, 0x00)):
            bright[first + i] ^= (pin >> shift) & 0xff
        return cls(target, bytes(bright), bytes(ambassador))

    def iv(self, counter: int) -> bytes:
        message = self.ambassador + counter.to_bytes(8, "big")
        return hmac.new(hmac_key(self.target), message, hashlib.sha256).digest()[:KEY_SIZE]

    def encrypt(self, counter: int, data: bytes) -> bytes:
        return _cfb128(self.bright, self.iv(counter), data, encrypt=True)

    def decrypt(self, counter: int, data: bytes) -> bytes:
        return _cfb128(self.bright, self.iv(counter), data, encrypt=False)


def _cfb128(key: bytes, iv: bytes, data: bytes, encrypt: bool) -> bytes:
    """AES-128-CFB built on single-block AES: cryptography moves its CFB mode to the "decrepit" ciphers and drops it
    from the regular modes, and these messages are a few hundred bytes at most."""
    block = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    out = bytearray()
    register = iv
    for start in range(0, len(data), KEY_SIZE):
        chunk = data[start:start + KEY_SIZE]
        stream = block.update(register)
        result = bytes(a ^ b for a, b in zip(chunk, stream))
        out += result
        register = result if encrypt else chunk
    return bytes(out)
