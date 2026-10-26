# SPDX-License-Identifier: GPL-3.0-or-later
"""Cryptographic primitives used by the PKG extractor.

Port of ``src/core/crypto/crypto.cpp``. RSA is done with plain Python big
integers (it only runs twice per package); AES-CBC and AES-XTS go through
the ``cryptography`` package so the bulk PFS decryption runs in OpenSSL.
"""

from __future__ import annotations

import hashlib
import hmac

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .keys import FAKE_KEYSET, PKG_DERIVED_KEY3_KEYSET

AES_BLOCK_SIZE = 16
PFS_SECTOR_SIZE = 0x1000


def rsa2048_decrypt_pkcs1v15(ciphertext: bytes, keyset: dict[str, int]) -> bytes | None:
    """RSAES-PKCS1-v1_5 decryption of one 256-byte block.

    Returns the recovered message, or ``None`` when the padding is invalid
    (which is what happens when the package was not encrypted for this key).
    """
    if len(ciphertext) != 256:
        raise ValueError("RSA-2048 ciphertext must be exactly 256 bytes")

    c = int.from_bytes(ciphertext, "big")
    if c >= keyset["n"]:
        return None

    # Decrypt using the Chinese remainder theorem (same parameters Crypto++ uses).
    m1 = pow(c, keyset["dp"], keyset["p"])
    m2 = pow(c, keyset["dq"], keyset["q"])
    h = (keyset["qinv"] * (m1 - m2)) % keyset["p"]
    m = m2 + h * keyset["q"]
    em = m.to_bytes(256, "big")

    # EM = 0x00 || 0x02 || PS (>= 8 non-zero bytes) || 0x00 || M
    if em[0] != 0x00 or em[1] != 0x02:
        return None
    separator = em.find(b"\x00", 2)
    if separator < 10:
        return None
    return em[separator + 1:]


def rsa2048_decrypt(ciphertext: bytes, is_dk3: bool) -> bytes | None:
    """Decrypt a 256-byte block and return the first 32 bytes of the message.

    ``is_dk3`` selects the "pkg derived key 3" keyset, otherwise the fake
    keyset used for the EKPFS key is used. Returns ``None`` on bad padding.
    """
    keyset = PKG_DERIVED_KEY3_KEYSET if is_dk3 else FAKE_KEYSET
    message = rsa2048_decrypt_pkcs1v15(ciphertext, keyset)
    if message is None:
        return None
    return message[:32].ljust(32, b"\x00")


def ivkey_hash256(cipher_input: bytes) -> bytes:
    """SHA-256 over the concatenated PKG entry header and DK3 (64 bytes)."""
    return hashlib.sha256(cipher_input).digest()


def aes_cbc_cfb128_decrypt(ivkey: bytes, ciphertext: bytes) -> bytes:
    """AES-128-CBC decrypt using key = ivkey[16:32] and IV = ivkey[0:16].

    Only whole 16-byte blocks are decrypted; any trailing partial block is
    copied through unchanged, matching the C++ implementation.
    """
    key = bytes(ivkey[16:32])
    iv = bytes(ivkey[0:16])
    full = (len(ciphertext) // AES_BLOCK_SIZE) * AES_BLOCK_SIZE
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(bytes(ciphertext[:full])) + decryptor.finalize()
    return plain + bytes(ciphertext[full:])


def pfs_gen_crypto_key(ekpfs: bytes, seed: bytes) -> tuple[bytes, bytes]:
    """Derive the PFS (data_key, tweak_key) pair from EKPFS and the image seed."""
    message = (1).to_bytes(4, "little") + bytes(seed[:16])
    digest = hmac.new(bytes(ekpfs), message, hashlib.sha256).digest()
    tweak_key = digest[:16]
    data_key = digest[16:32]
    return data_key, tweak_key


def decrypt_pfs(data_key: bytes, tweak_key: bytes, src: bytes, sector: int) -> bytes:
    """AES-128-XTS decrypt ``src`` sector by sector (0x1000 bytes per data unit).

    ``sector`` is the data-unit number of the first sector; the tweak is the
    little-endian 64-bit sector number zero-extended to 128 bits, exactly as
    the PFS layer of the console (and the C++ port) compute it. Trailing bytes that do
    not fill a whole sector are copied through undecrypted.
    """
    src = memoryview(src)
    total = len(src)
    full = total & ~(PFS_SECTOR_SIZE - 1)
    out = bytearray(total)
    algorithm = algorithms.AES(bytes(data_key) + bytes(tweak_key))

    for offset in range(0, full, PFS_SECTOR_SIZE):
        tweak = (sector + offset // PFS_SECTOR_SIZE).to_bytes(16, "little")
        decryptor = Cipher(algorithm, modes.XTS(tweak)).decryptor()
        chunk = src[offset:offset + PFS_SECTOR_SIZE]
        out[offset:offset + PFS_SECTOR_SIZE] = decryptor.update(bytes(chunk)) + decryptor.finalize()

    if total > full:
        out[full:] = src[full:]
    return bytes(out)
