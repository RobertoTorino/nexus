# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a small but structurally faithful PKG for integration tests.

The package is encrypted the same way real retail/fake-signed packages are:

* DK3 is RSA-PKCS1v15 encrypted with the "pkg derived key 3" public key,
* EKPFS is RSA-PKCS1v15 encrypted with the fake keyset public key and that
  block is AES-CBC encrypted with the IV key derived from the entry header,
* the PFS image is AES-XTS encrypted per 0x1000 sector with keys derived
  from EKPFS and the seed stored at ``pfs_image_offset + 0x370``,
* PFSC metadata/data sectors are zlib compressed when that is smaller.

Only the structures the extractor reads are populated.
"""

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from shadps4_manager.pkgxtractor import crypto
from shadps4_manager.pkgxtractor.keys import FAKE_KEYSET, PKG_DERIVED_KEY3_KEYSET

BLOCK = 0x10000
SECTOR = 0x1000
INODE_STRIDE = 0xA8
MODE_DIR = 0x416D
MODE_FILE = 0x816D


# -- primitives ---------------------------------------------------------------

def rsa_pkcs1v15_encrypt(message: bytes, keyset: dict[str, int]) -> bytes:
    padding = bytes(b or 1 for b in os.urandom(256 - 3 - len(message)))
    em = b"\x00\x02" + padding + b"\x00" + message
    return pow(int.from_bytes(em, "big"), keyset["e"], keyset["n"]).to_bytes(256, "big")


def aes_cbc_encrypt(ivkey: bytes, plaintext: bytes) -> bytes:
    full = len(plaintext) // 16 * 16
    enc = Cipher(algorithms.AES(ivkey[16:32]), modes.CBC(ivkey[:16])).encryptor()
    return enc.update(plaintext[:full]) + enc.finalize() + plaintext[full:]


def xts_encrypt_image(data_key: bytes, tweak_key: bytes, image: bytes, first_sector: int = 0) -> bytes:
    assert len(image) % SECTOR == 0
    out = bytearray()
    algorithm = algorithms.AES(data_key + tweak_key)
    for index in range(len(image) // SECTOR):
        tweak = (first_sector + index).to_bytes(16, "little")
        enc = Cipher(algorithm, modes.XTS(tweak)).encryptor()
        out += enc.update(image[index * SECTOR:(index + 1) * SECTOR]) + enc.finalize()
    return bytes(out)


def build_sfo(entries: list[tuple[str, int, bytes, int]]) -> bytes:
    """entries: (key, fmt, data, max_len). fmt: 0x0204 text, 0x0404 int, 0x0004 binary."""
    key_table = b""
    data_table = b""
    index = b""
    for key, fmt, data, max_len in entries:
        key_offset = len(key_table)
        key_table += key.encode() + b"\0"
        data_offset = len(data_table)
        data_table += data.ljust(max_len, b"\0")
        index += struct.pack("<HHIII", key_offset, fmt, len(data), max_len, data_offset)
    key_table_offset = 0x14 + len(index)
    key_table = key_table.ljust((len(key_table) + 3) & ~3, b"\0")
    data_table_offset = key_table_offset + len(key_table)
    header = b"\x00PSF" + struct.pack("<IIII", 0x101, key_table_offset, data_table_offset, len(entries))
    return header + index + key_table + data_table


def tiny_png() -> bytes:
    """A valid 2x2 RGBA PNG."""
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))
    raw = b"".join(b"\x00" + bytes([255, 0, 0, 255, 0, 255, 0, 255]) for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# -- PFS model -------------------------------------------------------------------

@dataclass
class PfsDir:
    name: str
    files: dict[str, bytes] = field(default_factory=dict)
    dirs: list["PfsDir"] = field(default_factory=list)


def _dirent(ino: int, dtype: int, name: bytes) -> bytes:
    entsize = (16 + len(name) + 7) & ~7
    return struct.pack("<iiii", ino, dtype, len(name), entsize) + name.ljust(entsize - 16, b"\0")


def _inode(mode: int, size: int, blocks: int, loc: int, nlink: int = 1) -> bytes:
    body = struct.pack("<HHIqqqqqqIIIIIIQQII", mode, nlink, 0x10, size, size, 0, 0, 0, 0,
                       0, 0, 0, 0, 0, 0, 0, 0, blocks, loc)
    return body.ljust(INODE_STRIDE, b"\0")


def _sector_for(block_data: bytes) -> bytes:
    compressed = zlib.compress(block_data, 6)
    return compressed if len(compressed) < BLOCK else block_data


def build_pfsc(root: PfsDir) -> tuple[bytes, dict[str, bytes]]:
    """Return (pfsc_buffer, {relative_path: content}) for the given tree."""
    inodes: list[bytes] = []
    sectors: list[bytes] = []
    expected: dict[str, bytes] = {}

    def add_block(data: bytes) -> int:
        sectors.append(_sector_for(data))
        return len(sectors) - 1

    # Blocks 0 (superblock) and 1 (inode table) are filled in afterwards.
    sectors.append(b"")
    sectors.append(b"")

    flat_path_table = b"\x00" * 8
    inodes.append(b"")  # 0: superroot (filled below)
    inodes.append(b"")  # 1: flat_path_table
    inodes.append(b"")  # 2: uroot

    # Assign inode numbers breadth-first so parents precede children.
    dir_entries: list[tuple[int, int, PfsDir, str]] = []  # (ino, parent_ino, dir, relative path)
    file_entries: list[tuple[int, str, bytes]] = []        # (ino, relative path, content)
    ino_of: dict[tuple[int, str], int] = {}
    pending: list[tuple[PfsDir, int, int, str]] = [(root, 2, 2, "")]
    while pending:
        directory, ino, parent_ino, rel = pending.pop(0)
        dir_entries.append((ino, parent_ino, directory, rel))
        for sub in directory.dirs:
            sub_ino = len(inodes)
            inodes.append(b"")
            ino_of[(id(directory), sub.name)] = sub_ino
            pending.append((sub, sub_ino, ino, f"{rel}{sub.name}/"))
        for name, content in directory.files.items():
            file_ino = len(inodes)
            inodes.append(b"")
            ino_of[(id(directory), name)] = file_ino
            file_entries.append((file_ino, f"{rel}{name}", content))

    # Metadata blocks first (superroot listing, then every directory listing in BFS order),
    # exactly like real images: the extractor only loads the first few MB of the PFSC image
    # and walks blocks sequentially until all inodes have been named.
    uroot_block = (_dirent(1, 2, b"flat_path_table") + _dirent(2, 3, b"uroot")).ljust(BLOCK, b"\0")
    inodes[0] = _inode(MODE_DIR, BLOCK, 1, add_block(uroot_block))
    for ino, parent_ino, directory, _rel in dir_entries:
        entries = _dirent(ino, 4, b".") + _dirent(parent_ino, 5, b"..")
        for sub in directory.dirs:
            entries += _dirent(ino_of[(id(directory), sub.name)], 3, sub.name.encode())
        for name in directory.files:
            entries += _dirent(ino_of[(id(directory), name)], 2, name.encode())
        listing_index = add_block(entries.ljust(BLOCK, b"\0"))
        inodes[ino] = _inode(MODE_DIR, BLOCK, 1, listing_index, nlink=2 + len(directory.dirs))

    # Then the file payload blocks.
    for file_ino, rel, content in file_entries:
        expected[rel] = content
        nblocks = (len(content) + BLOCK - 1) // BLOCK
        first = len(sectors)
        for b in range(nblocks):
            add_block(content[b * BLOCK:(b + 1) * BLOCK].ljust(BLOCK, b"\0"))
        inodes[file_ino] = _inode(MODE_FILE, len(content), nblocks, first if nblocks else 0)

    flat_index = add_block(flat_path_table.ljust(BLOCK, b"\0"))
    inodes[1] = _inode(MODE_FILE, len(flat_path_table), 1, flat_index)

    inode_table = b"".join(inodes)
    assert len(inode_table) <= BLOCK, "test tree too large for one inode block"
    sectors[1] = _sector_for(inode_table.ljust(BLOCK, b"\0"))

    superblock = bytearray(BLOCK)
    struct.pack_into("<q", superblock, 0x00, 1)
    struct.pack_into("<q", superblock, 0x30, len(inodes))  # dinode_count
    sectors[0] = _sector_for(bytes(superblock))

    # PFSC header + sector map at 0x400, data starting at 0x10000 (as in real packages).
    data_start = 0x10000
    offsets = [data_start]
    for sector in sectors:
        offsets.append(offsets[-1] + len(sector))
    header = struct.pack("<4siiiqqQq", b"PFSC", 0, 0, BLOCK, BLOCK, 0x400, data_start, len(sectors) * BLOCK)
    pfsc = bytearray(data_start)
    pfsc[:len(header)] = header
    struct.pack_into(f"<{len(offsets)}Q", pfsc, 0x400, *offsets)
    pfsc += b"".join(sectors)
    pfsc += b"\0" * (-len(pfsc) % SECTOR)
    return bytes(pfsc), expected


# -- PKG assembly ------------------------------------------------------------------

@dataclass
class BuiltPkg:
    path: Path
    content_id: str
    title_id: str
    expected_files: dict[str, bytes]
    sce_sys_plain: dict[str, bytes]
    dk3: bytes = b""
    ekpfs: bytes = b""
    seed: bytes = b""


def build_pkg(target: Path, root: PfsDir, *, content_id: str = "UP9000-CUSA99999_00-SYNTHETICPKG0001",
              title: str = "Synthetic Test Title", category: str = "gd", app_ver: str = "01.00") -> BuiltPkg:
    dk3 = os.urandom(32)
    ekpfs = os.urandom(32)
    seed = os.urandom(16)

    sfo = build_sfo([
        ("APP_VER", 0x0204, app_ver.encode() + b"\0", 8),
        ("ATTRIBUTE", 0x0404, struct.pack("<i", 0), 4),
        ("CATEGORY", 0x0204, category.encode() + b"\0", 4),
        ("CONTENT_ID", 0x0204, content_id.encode() + b"\0", 48),
        ("TITLE", 0x0204, title.encode() + b"\0", 128),
        ("TITLE_ID", 0x0204, content_id[7:16].encode() + b"\0", 12),
        ("VERSION", 0x0204, b"01.00\0", 8),
    ])
    icon = tiny_png()
    license_plain = b"LICENSE-TEST-" + os.urandom(16).hex().encode()
    license_plain = license_plain.ljust(1024, b"\0")

    entry_keys = bytearray(os.urandom(32 + 7 * 32))
    for i in range(7):
        entry_keys += rsa_pkcs1v15_encrypt(dk3, PKG_DERIVED_KEY3_KEYSET) if i == 3 else os.urandom(255) + b"\x01"
    image_key_plain = rsa_pkcs1v15_encrypt(ekpfs, FAKE_KEYSET)

    # Layout: header (0x1000) | entry table @0x2000 | entry data @0x3000... | PFS image.
    table_offset = 0x2000
    entries: list[tuple[int, bytes]] = [
        (0x0010, bytes(entry_keys)),
        (0x0020, image_key_plain),       # replaced by its encrypted form below
        (0x0400, license_plain),         # replaced by its encrypted form below
        (0x1000, sfo),
        (0x1200, icon),
    ]
    data_offset = 0x3000
    placed: list[tuple[int, int, int]] = []  # (id, offset, size)
    for entry_id, payload in entries:
        placed.append((entry_id, data_offset, len(payload)))
        data_offset += (len(payload) + 0xF) & ~0xF

    def raw_entry(entry_id: int, offset: int, size: int) -> bytes:
        return struct.pack(">IIIIIIQ", entry_id, 0, 0, 0, offset, size, 0)

    final_payloads: list[bytes] = []
    for (entry_id, payload), (_, offset, size) in zip(entries, placed, strict=True):
        raw = raw_entry(entry_id, offset, size)
        if entry_id == 0x20:
            payload = aes_cbc_encrypt(hashlib.sha256(raw + dk3).digest(), payload)
        elif entry_id == 0x400:
            payload = aes_cbc_encrypt(hashlib.sha256(raw + dk3).digest(), payload)
        final_payloads.append(payload)

    pfs_image_offset = (data_offset + 0xFFFF) & ~0xFFFF
    pfsc, expected = build_pfsc(root)
    pfsc_offset = 0x20000  # found by the "fast path" scan starting at 0x20000
    pfs_plain = bytearray(pfsc_offset) + pfsc
    pfs_plain[0x370:0x380] = seed
    data_key, tweak_key = crypto.pfs_gen_crypto_key(ekpfs, seed)
    # The PFS superblock sector (which carries the seed) is stored in the clear; everything
    # after it is XTS encrypted with the sector number (relative to the image start) as tweak.
    pfs_encrypted = bytes(pfs_plain[:SECTOR]) + xts_encrypt_image(
        data_key, tweak_key, bytes(pfs_plain[SECTOR:]), first_sector=1)

    pkg_size = pfs_image_offset + len(pfs_encrypted)
    header = bytearray(0x1000)
    header[0:4] = b"\x7fCNT"
    struct.pack_into(">I", header, 0x04, 0x00000001)
    struct.pack_into(">I", header, 0x0C, len(entries))
    struct.pack_into(">I", header, 0x10, len(entries))
    struct.pack_into(">H", header, 0x16, len(entries))
    struct.pack_into(">I", header, 0x18, table_offset)
    struct.pack_into(">Q", header, 0x20, table_offset)
    struct.pack_into(">Q", header, 0x28, pfs_image_offset - table_offset)
    struct.pack_into(">Q", header, 0x30, pfs_image_offset)
    struct.pack_into(">Q", header, 0x38, len(pfs_encrypted))
    header[0x40:0x40 + len(content_id)] = content_id.encode()
    struct.pack_into(">I", header, 0x74, 0x1A)
    struct.pack_into(">I", header, 0x78, 0x0)
    struct.pack_into(">I", header, 0x404, 1)                    # pfs_image_count
    struct.pack_into(">Q", header, 0x410, pfs_image_offset)
    struct.pack_into(">Q", header, 0x418, len(pfs_encrypted))
    struct.pack_into(">Q", header, 0x430, pkg_size)
    struct.pack_into(">I", header, 0x43C, 0x80000)              # pfs_cache_size

    pkg = bytearray(pkg_size)
    pkg[:0x1000] = header
    table = b"".join(raw_entry(entry_id, offset, size) for entry_id, offset, size in placed)
    pkg[table_offset:table_offset + len(table)] = table
    for (_, offset, size), payload in zip(placed, final_payloads, strict=True):
        pkg[offset:offset + size] = payload
    pkg[pfs_image_offset:] = pfs_encrypted

    target.write_bytes(bytes(pkg))
    return BuiltPkg(path=target, content_id=content_id, title_id=content_id[7:16],
                    expected_files=expected,
                    sce_sys_plain={"param.sfo": sfo, "icon0.png": icon, "license.dat": license_plain},
                    dk3=dk3, ekpfs=ekpfs, seed=seed)


def default_tree() -> PfsDir:
    """A tree that exercises compressed, raw, multi-block, exact-size and empty files."""
    data = PfsDir("data", files={
        "big.bin": os.urandom(2 * BLOCK),                 # exactly two raw blocks
        "empty.bin": b"",                                 # zero blocks
        "zeros.dat": bytes(BLOCK + 123),                  # highly compressible, partial last block
    })
    root = PfsDir("", files={
        "eboot.bin": os.urandom(BLOCK) + b"A" * (BLOCK // 2) + os.urandom(1000),  # raw + compressed mix
        "readme.txt": b"hello from a synthetic pkg\n" * 40,
        "bad:name?.txt": b"needs sanitizing",
    }, dirs=[data])
    return root
