# SPDX-License-Identifier: GPL-3.0-or-later
"""PARAM.SFO (PSF) parser. Port of ``src/core/file_format/psf.cpp`` (read side)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Union

PSF_MAGIC = b"\x00PSF"
PSF_VERSION_1_1 = 0x00000101
PSF_VERSION_1_0 = 0x00000100
PSF_HEADER_SIZE = 0x14
PSF_RAW_ENTRY_SIZE = 0x10


class PSFError(ValueError):
    """Raised when a PSF buffer cannot be parsed."""


class PSFEntryFmt(IntEnum):
    BINARY = 0x0004
    TEXT = 0x0204
    INTEGER = 0x0404


PSFValue = Union[bytes, str, int]


@dataclass
class PSFEntry:
    key: str
    fmt: PSFEntryFmt
    max_len: int
    value: PSFValue


class PSF:
    """Read-only view of the entries in a PARAM.SFO file."""

    def __init__(self) -> None:
        self.entries: list[PSFEntry] = []

    # -- construction -----------------------------------------------------

    @classmethod
    def from_bytes(cls, buffer: bytes) -> "PSF":
        psf = cls()
        psf._parse(bytes(buffer))
        return psf

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "PSF":
        return cls.from_bytes(Path(path).read_bytes())

    def _parse(self, data: bytes) -> None:
        size = len(data)
        if size < PSF_HEADER_SIZE:
            raise PSFError("PSF buffer too small")

        magic = data[0:4]
        version, key_table_offset, data_table_offset, index_table_entries = struct.unpack_from(
            "<IIII", data, 4)

        if magic != PSF_MAGIC:
            raise PSFError("Invalid PSF magic number")
        if version not in (PSF_VERSION_1_1, PSF_VERSION_1_0):
            raise PSFError(f"Unsupported PSF version: 0x{version:08x}")

        index_table_end = PSF_HEADER_SIZE + index_table_entries * PSF_RAW_ENTRY_SIZE
        if index_table_end > size:
            raise PSFError("PSF index table out of bounds")
        if (key_table_offset >= size or data_table_offset > size
                or key_table_offset > data_table_offset):
            raise PSFError("PSF table offsets out of bounds")

        key_table_end = data_table_offset
        entries: list[PSFEntry] = []

        for i in range(index_table_entries):
            raw_offset = PSF_HEADER_SIZE + i * PSF_RAW_ENTRY_SIZE
            # The C++ code declares param_fmt as u16_be but reads it with .Raw(), i.e. the
            # native little-endian value is compared against 0x0004/0x0204/0x0404.
            key_offset, param_fmt, param_len, param_max_len, data_offset = struct.unpack_from(
                "<HHIII", data, raw_offset)

            key_start = key_table_offset + key_offset
            if key_start >= key_table_end:
                raise PSFError(f"PSF key offset out of bounds for entry {i}")
            key_null = data.find(b"\x00", key_start, key_table_end)
            if key_null < 0:
                raise PSFError(f"PSF key missing terminator for entry {i}")
            key = data[key_start:key_null].decode("utf-8", "replace")

            data_start = data_table_offset + data_offset
            if data_start > size or param_len > size - data_start:
                raise PSFError(f"PSF data out of bounds for entry {i}")
            payload = data[data_start:data_start + param_len]

            try:
                fmt = PSFEntryFmt(param_fmt)
            except ValueError as exc:
                raise PSFError(f"Unknown PSF entry format for entry {i}") from exc

            value: PSFValue
            if fmt is PSFEntryFmt.BINARY:
                value = bytes(payload)
            elif fmt is PSFEntryFmt.TEXT:
                text_null = payload.find(b"\x00")
                text = payload if text_null < 0 else payload[:text_null]
                value = text.decode("utf-8", "replace")
            else:
                if param_len < 4:
                    raise PSFError(f"PSF integer entry size mismatch for entry {i}")
                value = struct.unpack_from("<i", payload, 0)[0]

            entries.append(PSFEntry(key=key, fmt=fmt, max_len=param_max_len, value=value))

        self.entries = entries

    # -- lookups ------------------------------------------------------------

    def _find(self, key: str, fmt: PSFEntryFmt) -> PSFEntry | None:
        for entry in self.entries:
            if entry.key == key and entry.fmt is fmt:
                return entry
        return None

    def get_string(self, key: str) -> str | None:
        entry = self._find(key, PSFEntryFmt.TEXT)
        return entry.value if entry is not None else None  # type: ignore[return-value]

    def get_integer(self, key: str) -> int | None:
        entry = self._find(key, PSFEntryFmt.INTEGER)
        return entry.value if entry is not None else None  # type: ignore[return-value]

    def get_binary(self, key: str) -> bytes | None:
        entry = self._find(key, PSFEntryFmt.BINARY)
        return entry.value if entry is not None else None  # type: ignore[return-value]

    def keys(self) -> list[str]:
        return [entry.key for entry in self.entries]

    def as_text(self) -> str:
        """Human readable dump of every entry, one ``KEY: value`` per line."""
        lines = []
        for entry in self.entries:
            if entry.fmt is PSFEntryFmt.BINARY:
                shown = entry.value.hex()  # type: ignore[union-attr]
            else:
                shown = str(entry.value)
            lines.append(f"{entry.key}: {shown}")
        return "\n".join(lines)
