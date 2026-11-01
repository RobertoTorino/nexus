# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads a UEFI flash image: firmware volumes, their files and sections (LZMA-compressed volumes included) and the
AMI NVRAM stores (NVAR) with the UEFI variables and their defaults.

Only reads; nothing here writes a byte to the board. Formats: UEFI PI specification (volumes, FFS files, sections)
and AMI's NVAR layout as documented by UEFITool."""

from __future__ import annotations

import lzma
import struct
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

FV_SIGNATURE = b"_FVH"
FFS2 = uuid.UUID("8c8ce578-8a3d-4f1c-9935-896185c32dd3")
FFS3 = uuid.UUID("5473c07a-3dcb-4dca-bd6f-1e9689e7349a")
NVAR_STORE_FILE = uuid.UUID("cef5b9a3-476d-497f-9fdc-e98143e0422c")
NVRAM_DEFAULTS_FILE = uuid.UUID("9221315b-30bb-46b5-813e-1b1bf4712bd3")
LZMA_SECTION = uuid.UUID("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
LZMA_F86_SECTION = uuid.UUID("d42ae6bd-1352-4bfb-909a-ca72a6eae889")
STD_DEFAULTS = "StdDefaults"

# Section types
SEC_COMPRESSION, SEC_GUID_DEFINED, SEC_PE32, SEC_TE = 0x01, 0x02, 0x10, 0x12
SEC_USER_INTERFACE, SEC_FV_IMAGE, SEC_RAW = 0x15, 0x17, 0x19
FILE_RAW, FILE_PAD = 0x01, 0xF0
FFS_ATTRIB_LARGE_FILE = 0x01

# NVAR entry attributes
NVAR_RUNTIME, NVAR_ASCII_NAME, NVAR_GUID, NVAR_DATA_ONLY = 0x01, 0x02, 0x04, 0x08
NVAR_EXT_HEADER, NVAR_VALID = 0x10, 0x80
NVAR_LAST = 0xFFFFFF


def _guid(data: bytes, offset: int = 0) -> uuid.UUID:
    return uuid.UUID(bytes_le=bytes(data[offset:offset + 16]))


def _align(value: int, to: int) -> int:
    return (value + to - 1) & ~(to - 1)


@dataclass
class Section:
    type: int
    body: bytes
    children: list[Section] = field(default_factory=list)     # sections inside a compressed/GUID-defined one
    volumes: list[Volume] = field(default_factory=list)        # a volume-image section


@dataclass
class FfsFile:
    guid: uuid.UUID
    type: int
    body: bytes
    offset: int                                     # in the image, -1 inside a decompressed volume
    sections: list[Section] = field(default_factory=list)

    @property
    def name(self) -> str:
        """The file's user-interface name ("Setup"), or "" when it has none."""
        for sec in walk_sections(self.sections):
            if sec.type == SEC_USER_INTERFACE:
                return sec.body.decode("utf-16-le", "replace").split("\0", 1)[0]
        return ""

    def section(self, kind: int) -> bytes | None:
        """Body of the first section of *kind* (searching inside compressed sections too)."""
        return next((s.body for s in walk_sections(self.sections) if s.type == kind), None)


@dataclass
class Volume:
    guid: uuid.UUID                                 # file-system GUID
    offset: int                                     # in the image, -1 inside a decompressed section
    data: bytes
    files: list[FfsFile] = field(default_factory=list)


def walk_sections(sections: list[Section]) -> Iterator[Section]:
    for sec in sections:
        yield sec
        yield from walk_sections(sec.children)


class FirmwareError(ValueError):
    pass


# --- Volumes, files, sections --------------------------------------------------------------------------------

def find_volumes(image: bytes) -> list[Volume]:
    """The top-level firmware volumes of a flash image, by their _FVH signature."""
    volumes, pos = [], 0
    while (sig := image.find(FV_SIGNATURE, pos)) >= 0:
        start = sig - 0x28
        if start >= 0 and (vol := _volume(image, start)) is not None:
            vol.offset = start
            volumes.append(vol)
            pos = start + len(vol.data)
        else:
            pos = sig + 4
    return volumes


def _volume(data: bytes, start: int) -> Volume | None:
    if len(data) < start + 0x38 or data[start + 0x28:start + 0x2C] != FV_SIGNATURE:
        return None
    length = struct.unpack_from("<Q", data, start + 0x20)[0]
    header_len, _, ext_offset = struct.unpack_from("<HHH", data, start + 0x30)
    if length < header_len or start + length > len(data) or header_len < 0x38:
        return None
    fs = _guid(data, start + 0x10)
    body = bytes(data[start:start + length])
    vol = Volume(fs, -1, body)
    if fs in (FFS2, FFS3):
        first = header_len
        if ext_offset:
            ext_size = struct.unpack_from("<I", body, ext_offset + 16)[0]
            first = max(first, ext_offset + ext_size)
        vol.files = list(_files(body, _align(first, 8), start))
    return vol


def _files(vol: bytes, pos: int, base: int) -> Iterator[FfsFile]:
    while pos + 24 <= len(vol):
        header = vol[pos:pos + 24]
        if header == b"\xff" * 24:
            break
        ftype, attrs = header[18], header[19]
        size = int.from_bytes(header[20:23], "little")
        hdr = 24
        if attrs & FFS_ATTRIB_LARGE_FILE:
            size = struct.unpack_from("<Q", vol, pos + 24)[0]
            hdr = 32
        if size < hdr or pos + size > len(vol):
            break
        body = bytes(vol[pos + hdr:pos + size])
        f = FfsFile(_guid(header), ftype, body, base + pos if base >= 0 else -1)
        if ftype not in (FILE_RAW, FILE_PAD):
            f.sections = _sections(body)
        yield f
        pos = _align(pos + size, 8)


def _sections(data: bytes) -> list[Section]:
    out, pos = [], 0
    while pos + 4 <= len(data):
        size = int.from_bytes(data[pos:pos + 3], "little")
        stype = data[pos + 3]
        hdr = 4
        if size == 0xFFFFFF:
            if pos + 8 > len(data):
                break
            size = struct.unpack_from("<I", data, pos + 4)[0]
            hdr = 8
        if size < hdr or pos + size > len(data):
            break
        body = bytes(data[pos + hdr:pos + size])
        sec = Section(stype, body)
        try:
            _expand(sec)
        except (lzma.LZMAError, FirmwareError, struct.error):
            pass                                  # an unsupported or damaged section stays as it is
        out.append(sec)
        pos = _align(pos + size, 4)
    return out


def _expand(sec: Section) -> None:
    if sec.type == SEC_GUID_DEFINED and len(sec.body) >= 20:
        guid = _guid(sec.body)
        data_offset = struct.unpack_from("<H", sec.body, 16)[0]
        payload = sec.body[data_offset - 4:] if data_offset >= 4 else b""
        if guid in (LZMA_SECTION, LZMA_F86_SECTION):
            sec.body = lzma.decompress(payload, format=lzma.FORMAT_ALONE)
            if guid == LZMA_F86_SECTION:
                raise FirmwareError("x86-filtered LZMA is not supported")
            sec.children = _sections(sec.body)
    elif sec.type == SEC_COMPRESSION and len(sec.body) >= 5:
        if sec.body[4] == 0:                        # stored, not compressed
            sec.body = sec.body[5:]
            sec.children = _sections(sec.body)
    elif sec.type == SEC_FV_IMAGE:
        vol = _volume(sec.body, 0)
        if vol is not None:
            sec.volumes = [vol]


def all_files(volumes: list[Volume]) -> Iterator[FfsFile]:
    """Every file, also those in volumes nested in (compressed) sections."""
    for vol in volumes:
        for f in vol.files:
            yield f
            for sec in walk_sections(f.sections):
                yield from all_files(sec.volumes)


# --- NVRAM (AMI NVAR) ---------------------------------------------------------------------------------------

@dataclass
class Variable:
    name: str
    guid: uuid.UUID
    data: bytes
    attributes: int                                 # of the chain's first entry

    @property
    def runtime(self) -> bool:
        return bool(self.attributes & NVAR_RUNTIME)


@dataclass
class _Entry:
    offset: int
    attributes: int
    next: int
    name: str
    guid: uuid.UUID | None
    data: bytes


def _guid_store(store: bytes, index: int) -> uuid.UUID | None:
    end = len(store) - 16 * index
    return _guid(store, end - 16) if end - 16 >= 0 else None


def _nvar_entries(store: bytes) -> Iterator[_Entry]:
    pos = 0
    while pos + 10 <= len(store) and store[pos:pos + 4] == b"NVAR":
        size = struct.unpack_from("<H", store, pos + 4)[0]
        nxt = int.from_bytes(store[pos + 6:pos + 9], "little")
        attrs = store[pos + 9]
        if size < 10 or pos + size > len(store):
            break
        body = store[pos + 10:pos + size]
        if attrs & NVAR_EXT_HEADER and len(body) >= 2:
            ext = struct.unpack_from("<H", body, len(body) - 2)[0]
            if 0 < ext <= len(body):
                body = body[:len(body) - ext]
        name, guid = "", None
        if not attrs & NVAR_DATA_ONLY:
            if attrs & NVAR_GUID:
                guid, body = _guid(body), body[16:]
            elif body:
                guid, body = _guid_store(store, body[0]), body[1:]
            if attrs & NVAR_ASCII_NAME:
                end = body.find(b"\0")
                name, body = body[:end].decode("ascii", "replace"), body[end + 1:]
            else:
                end = 0
                while end + 1 < len(body) and body[end:end + 2] != b"\0\0":
                    end += 2
                name, body = body[:end].decode("utf-16-le", "replace"), body[end + 2:]
        yield _Entry(pos, attrs, nxt, name, guid, bytes(body))
        pos += size


def parse_nvar_store(store: bytes) -> dict[tuple[uuid.UUID, str], Variable]:
    """The variables of an NVAR store, each with its current value: the data of the last entry of its chain."""
    entries = list(_nvar_entries(store))
    by_offset = {e.offset: e for e in entries}
    out: dict[tuple[uuid.UUID, str], Variable] = {}
    for e in entries:
        if e.attributes & NVAR_DATA_ONLY or not e.attributes & NVAR_VALID or e.guid is None:
            continue
        last, seen = e, {e.offset}
        while last.next != NVAR_LAST and (nxt := by_offset.get(last.offset + last.next)) and nxt.offset not in seen:
            seen.add(nxt.offset)
            last = nxt
        out[(e.guid, e.name)] = Variable(e.name, e.guid, last.data, e.attributes)
    return out


@dataclass
class Firmware:
    """A parsed flash image."""
    image: bytes
    volumes: list[Volume]
    variables: dict[tuple[uuid.UUID, str], Variable]
    defaults: dict[tuple[uuid.UUID, str], Variable]

    def files(self) -> Iterator[FfsFile]:
        return all_files(self.volumes)

    def file_named(self, name: str) -> FfsFile | None:
        return next((f for f in self.files() if f.name == name), None)

    def variable(self, name: str, guid: uuid.UUID | None = None) -> Variable | None:
        return _lookup(self.variables, name, guid)

    def default(self, name: str, guid: uuid.UUID | None = None) -> Variable | None:
        return _lookup(self.defaults, name, guid)


def _lookup(table: dict[tuple[uuid.UUID, str], Variable], name: str, guid: uuid.UUID | None) -> Variable | None:
    if guid is not None:
        return table.get((guid, name))
    return next((v for (_, n), v in table.items() if n == name), None)


def parse_image(image: bytes) -> Firmware:
    volumes = find_volumes(image)
    if not volumes:
        raise FirmwareError("no UEFI firmware volume in this file: it is not a BIOS image")
    variables: dict[tuple[uuid.UUID, str], Variable] = {}
    defaults: dict[tuple[uuid.UUID, str], Variable] = {}
    for f in all_files(volumes):
        if f.guid == NVAR_STORE_FILE and not variables:
            variables = parse_nvar_store(f.body)
        elif f.guid == NVRAM_DEFAULTS_FILE and not defaults:
            raw = f.section(SEC_RAW)
            if raw is not None:
                defaults = _defaults_of(parse_nvar_store(raw))
    if not defaults:
        defaults = _defaults_of(variables)
    return Firmware(image, volumes, variables, defaults)


def _defaults_of(store: dict[tuple[uuid.UUID, str], Variable]) -> dict[tuple[uuid.UUID, str], Variable]:
    """The variables inside the StdDefaults entry: a nested NVAR store."""
    std = _lookup(store, STD_DEFAULTS, None)
    return parse_nvar_store(std.data) if std is not None else {}
