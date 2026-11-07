# SPDX-License-Identifier: GPL-3.0-or-later
"""PKG header parsing and the PFS helper functions."""

from __future__ import annotations

import os
import struct
import zlib

from shadps4_manager.pkgxtractor.pkg import PKGHeader, decompress_pfsc, find_pfsc_offset, sanitize_file_name, sanitize_folder_name


def test_sanitize_file_name() -> None:
    assert sanitize_file_name('a<b>:c"/d\\e|f?g*h') == "a_b__c__d_e_f_g_h"
    assert sanitize_file_name("name.  ") == "name"
    assert sanitize_file_name("...") == "unnamed_file"
    assert sanitize_file_name("") == "unnamed_file"
    assert sanitize_file_name("ok\x01") == "ok_"
    assert sanitize_folder_name("") == "unknown_title"
    assert sanitize_folder_name("CUSA00038") == "CUSA00038"


def test_find_pfsc_offset_priorities() -> None:
    image = bytearray(0x40000)
    assert find_pfsc_offset(bytes(image)) == -1
    image[0x30000:0x30004] = b"PFSC"
    assert find_pfsc_offset(bytes(image)) == 0x30000
    image[0x2000:0x2004] = b"PFSC"  # 0x1000-aligned, but 0x10000-aligned wins
    assert find_pfsc_offset(bytes(image)) == 0x30000
    image[0x30000:0x30004] = b"\0\0\0\0"
    assert find_pfsc_offset(bytes(image)) == 0x2000
    image[0:4] = b"PFSC"
    assert find_pfsc_offset(bytes(image)) == 0
    assert find_pfsc_offset(b"\0" * 0x80) == -1
    assert find_pfsc_offset(b"\0" * 0x1000 + b"xPFSC" + b"\0" * 0x1000) == 0x1001


def test_decompress_pfsc_roundtrip() -> None:
    plain = os.urandom(0x8000) + bytes(0x8000)
    compressed = zlib.compress(plain)  # 2-byte zlib header + raw deflate + adler32
    out = bytearray(0x10000)
    assert decompress_pfsc(compressed, out)
    assert bytes(out) == plain
    assert not decompress_pfsc(compressed[:-40], bytearray(0x10000))  # truncated stream
    assert not decompress_pfsc(b"\x78\x9c", bytearray(0x10000))


def test_pkg_header_parse_offsets() -> None:
    raw = bytearray(0x1000)
    raw[0:4] = b"\x7fCNT"
    struct.pack_into(">I", raw, 0x10, 7)          # table entry count
    struct.pack_into(">I", raw, 0x18, 0x2A80)     # table entry offset
    raw[0x40:0x40 + 36] = b"UP9000-CUSA00038_00-ASTRONAUT0000002"
    struct.pack_into(">I", raw, 0x78, 0x2000000 | 0x4000000)
    struct.pack_into(">Q", raw, 0x410, 0x100000)  # pfs image offset
    struct.pack_into(">Q", raw, 0x430, 0x180000)  # pkg size
    struct.pack_into(">I", raw, 0x43C, 0x8000)    # pfs cache size
    header = PKGHeader.parse(bytes(raw))
    assert header.pkg_table_entry_count == 7
    assert header.pkg_table_entry_offset == 0x2A80
    assert header.pkg_content_id.rstrip(b"\0") == b"UP9000-CUSA00038_00-ASTRONAUT0000002"
    assert header.flag_names() == ["GD_AC", "NON_GAME"]
    assert header.pfs_image_offset == 0x100000
    assert header.pkg_size == 0x180000
    assert header.pfs_cache_size == 0x8000
