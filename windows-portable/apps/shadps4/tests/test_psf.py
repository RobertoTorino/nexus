# SPDX-License-Identifier: GPL-3.0-or-later
"""The param.sfo reader."""

from __future__ import annotations

import struct

import pytest

from shadps4_manager.pkgxtractor.psf import PSF, PSFEntryFmt, PSFError


def _build_sfo(entries: list[tuple[str, int, bytes, int]]) -> bytes:
    """entries: (key, fmt, data, max_len) -> minimal valid PARAM.SFO buffer."""
    header_size = 0x14
    index_size = 0x10 * len(entries)
    key_table = b""
    data_table = b""
    index = b""
    for key, fmt, data, max_len in entries:
        key_offset = len(key_table)
        key_table += key.encode() + b"\0"
        data_offset = len(data_table)
        data_table += data.ljust(max_len, b"\0")
        index += struct.pack("<HHIII", key_offset, fmt, len(data), max_len, data_offset)
    key_table_offset = header_size + index_size
    key_table = key_table.ljust((len(key_table) + 3) & ~3, b"\0")
    data_table_offset = key_table_offset + len(key_table)
    header = b"\x00PSF" + struct.pack("<IIII", 0x101, key_table_offset, data_table_offset, len(entries))
    return header + index + key_table + data_table


def test_psf_parse() -> None:
    buf = _build_sfo([
        ("APP_VER", PSFEntryFmt.TEXT, b"01.00\0", 8),
        ("CATEGORY", PSFEntryFmt.TEXT, b"ac\0", 4),
        ("CONTENT_TYPE", PSFEntryFmt.INTEGER, struct.pack("<i", 8), 4),
        ("TITLE", PSFEntryFmt.TEXT, "Résogun\0".encode(), 128),
        ("BLOB", PSFEntryFmt.BINARY, b"\x01\x02\x03", 4),
    ])
    psf = PSF.from_bytes(buf)
    assert psf.get_string("APP_VER") == "01.00"
    assert psf.get_string("CATEGORY") == "ac"
    assert psf.get_integer("CONTENT_TYPE") == 8
    assert psf.get_string("TITLE") == "Résogun"
    assert psf.get_binary("BLOB") == b"\x01\x02\x03"
    assert psf.get_string("MISSING") is None
    assert psf.keys() == ["APP_VER", "CATEGORY", "CONTENT_TYPE", "TITLE", "BLOB"]


def test_psf_rejects_garbage() -> None:
    with pytest.raises(PSFError):
        PSF.from_bytes(b"\x00PSF" + b"\0" * 8)
    with pytest.raises(PSFError):
        PSF.from_bytes(b"XXXX" + b"\0" * 32)
