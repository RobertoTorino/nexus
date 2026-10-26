# SPDX-License-Identifier: GPL-3.0-or-later
"""The PSP games: disc images and EBOOT.PBP files, with the title, disc ID (ULUS10041) and version from the
PARAM.SFO inside them. There are two kinds, as PPSSPP lists them:

* a disc image, dumped from its UMD: an ISO (plain ISO 9660) or a CSO (the same ISO, compressed block by block),
  with /PSP_GAME/PARAM.SFO and the game's pictures (ICON0.PNG, PIC1.PNG) beside it. A CHD holds the same disc in
  MAME's archive format, which the app does not look into: it lists the file under its own name.
* a memory stick game (homebrew or bought digitally): a folder with an EBOOT.PBP, on PPSSPP's memory stick in
  PSP/GAME or in the chosen folders. A PBP is a container ("\\0PBP", a version and eight offsets, little-endian):
  PARAM.SFO first, then ICON0.PNG, ICON1.PMF, PIC0.PNG, PIC1.PNG, SND0.AT3 and the program itself. A folder whose
  PARAM.SFO says category "PG" is a game's update, not a game: PPSSPP lays it over the disc game by itself.

PPSSPP's memory stick is ~/.config/ppsspp (NativeApp.cpp: $XDG_CONFIG_HOME/ppsspp), with the PSP's own layout in
PSP/: GAME with the memory stick games, SAVEDATA, and the settings in SYSTEM/ppsspp.ini. The app reads it and
never writes it; PPSSPP does that. UMD video discs have no /PSP_GAME, so they are no games here either.

PARAM.SFO is the PSF format of the PSP (and the PS3 and PS4): a 20-byte header ("\\0PSF", version, start of the key
table, start of the data table, number of entries), then 16 bytes per entry (key offset u16, format u16, length u32,
room u32, data offset u32), little-endian. Format 0x0204 (and 0x0004) is UTF-8 text, 0x0404 a u32.

ISO 9660 is read directly: the volume descriptor in sector 16 names the root directory, whose records (length,
sector, size, flags, name, each little-endian where both byte orders are stored) lead to /PSP_GAME and its files.
A CSO (v1) starts "CISO" with the block size and an index of u32s: each block's position shifted by the alignment,
the top bit set when the block is stored as it is instead of deflated."""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import config_home

MAX_DEPTH = 5
TEXT, TEXT_SPECIAL, NUMBER = 0x0204, 0x0004, 0x0404
PATCH = "PG"                            # a game's update on the memory stick, not a game
DISC_SUFFIXES = (".iso", ".cso", ".chd")
SECTOR = 2048
PBP_PARTS = ("PARAM.SFO", "ICON0.PNG", "ICON1.PMF", "PIC0.PNG", "PIC1.PNG", "SND0.AT3", "DATA.PSP", "DATA.PSAR")


def ppsspp_home() -> Path:
    """PPSSPP's own folder, its memory stick: settings, saves and memory stick games."""
    return config_home() / "ppsspp"


def memstick_game(home: Path) -> Path:
    """The memory stick games, PSP/GAME on the memory stick."""
    return home / "PSP" / "GAME"


@dataclass(frozen=True)
class Game:
    file: Path                          # the disc image, or the memory stick game's EBOOT.PBP
    title: str
    disc_id: str = ""
    version: str = ""
    kind: str = "iso"                   # iso, cso, chd or pbp

    @property
    def folder(self) -> Path:
        return self.file.parent

    def picture(self, name: str) -> bytes | None:
        """One of the game's own pictures (ICON0.PNG: 144 × 80, PIC1.PNG: 480 × 272), from inside the image or the
        PBP; None without it (a CHD is not looked into)."""
        try:
            if self.kind in ("iso", "cso"):
                return iso_file(self.file, ("PSP_GAME", name))
            if self.kind == "pbp":
                return pbp_part(self.file.read_bytes(), name)
        except OSError:
            return None
        return None


def read_sfo(data: bytes) -> dict[str, str | int]:
    """The entries of a PARAM.SFO; {} for anything that is not one."""
    if len(data) < 20 or data[:4] != b"\0PSF":
        return {}
    try:
        _version, keys, values, count = struct.unpack_from("<4I", data, 4)
        found: dict[str, str | int] = {}
        for n in range(count):
            key_at, kind, length, _room, value_at = struct.unpack_from("<HHIII", data, 20 + 16 * n)
            start = keys + key_at
            name = data[start:data.index(b"\0", start)].decode("utf-8", "replace")
            raw = data[values + value_at:values + value_at + length]
            if kind == NUMBER:
                found[name] = struct.unpack("<I", raw[:4])[0]
            elif kind in (TEXT, TEXT_SPECIAL):
                found[name] = raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
        return found
    except (struct.error, ValueError):
        return {}


# --- The disc images --------------------------------------------------------------------------------------------

class _Cso:
    """Reads a CSO v1 as the ISO it holds: the index up front, each block inflated when it is asked for."""

    def __init__(self, file):
        self.file = file
        header = file.read(24)
        if len(header) < 24 or header[:4] != b"CISO":
            raise ValueError("not a CSO")
        _header_size, total, self.block, version, self.align = struct.unpack_from("<IQIBB", header, 4)
        if version > 1 or not self.block:
            raise ValueError(f"CSO version {version} is not read")
        count = -(-total // self.block) + 1
        self.index = struct.unpack(f"<{count}I", file.read(4 * count))

    def read_at(self, offset: int, size: int) -> bytes:
        parts = []
        while size > 0:
            n, skip = divmod(offset, self.block)
            if n + 1 >= len(self.index):
                break
            start = (self.index[n] & 0x7FFFFFFF) << self.align
            if self.index[n] & 0x80000000:              # stored as it is
                self.file.seek(start + skip)
                part = self.file.read(min(size, self.block - skip))
            else:
                end = (self.index[n + 1] & 0x7FFFFFFF) << self.align
                self.file.seek(start)
                block = zlib.decompress(self.file.read(end - start), -15)
                part = block[skip:skip + size]
            if not part:
                break
            parts.append(part)
            offset += len(part)
            size -= len(part)
        return b"".join(parts)


class _Iso:
    def __init__(self, file):
        self.file = file

    def read_at(self, offset: int, size: int) -> bytes:
        self.file.seek(offset)
        return self.file.read(size)


def _records(image, sector: int, size: int):
    """The records of one ISO 9660 directory: (name, sector, size, is a directory)."""
    data = image.read_at(sector * SECTOR, size)
    at = 0
    while at + 33 <= len(data):
        length = data[at]
        if length == 0:                                 # the rest of this sector is empty: the next one
            at = (at // SECTOR + 1) * SECTOR
            continue
        extent = struct.unpack_from("<I", data, at + 2)[0]
        file_size = struct.unpack_from("<I", data, at + 10)[0]
        flags, name_len = data[at + 25], data[at + 32]
        name = data[at + 33:at + 33 + name_len].decode("ascii", "replace").partition(";")[0]
        if name not in ("\0", "\x01"):                  # . and ..
            yield name.upper(), extent, file_size, bool(flags & 2)
        at += length


def _find(image, parts: tuple[str, ...]) -> bytes | None:
    """The file at /parts[0]/parts[1]/... in the image; None when the path is not there or it is no ISO 9660."""
    pvd = image.read_at(16 * SECTOR, SECTOR)
    if len(pvd) < 190 or pvd[0] != 1 or pvd[1:6] != b"CD001":
        return None
    sector, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    for depth, wanted in enumerate(parts):
        found = next((r for r in _records(image, sector, size) if r[0] == wanted.upper()), None)
        if found is None or found[3] != (depth < len(parts) - 1):
            return None
        _name, sector, size, _directory = found
    return image.read_at(sector * SECTOR, size)


def iso_file(path: Path, parts: tuple[str, ...]) -> bytes | None:
    """One file out of a disc image (ISO, or the ISO in a CSO); None when it is not there. OSError is the
    caller's."""
    with path.open("rb") as file:
        try:
            image = _Cso(file) if path.suffix.lower() == ".cso" else _Iso(file)
            return _find(image, parts)
        except (ValueError, struct.error, zlib.error, EOFError):
            return None


def read_disc(path: Path) -> Game | None:
    """The game in a disc image; a CHD under its own name (not looked into); None for an image without
    /PSP_GAME/PARAM.SFO (a UMD video, something else entirely)."""
    kind = path.suffix.lower().lstrip(".")
    if kind == "chd":
        return Game(path, path.stem, kind="chd")
    try:
        data = iso_file(path, ("PSP_GAME", "PARAM.SFO"))
    except OSError:
        return None
    sfo = read_sfo(data) if data else {}
    if not sfo:
        return None
    title = " ".join(str(sfo.get("TITLE") or "").split()) or path.stem      # PSP titles may hold line breaks
    return Game(path, title, str(sfo.get("DISC_ID") or ""), str(sfo.get("DISC_VERSION") or ""), kind)


# --- The memory stick games -------------------------------------------------------------------------------------

def pbp_part(data: bytes, name: str) -> bytes | None:
    """One part of a PBP by its name in PBP_PARTS; None when the PBP does not hold it."""
    if len(data) < 40 or data[:4] != b"\0PBP":
        return None
    offsets = struct.unpack_from("<8I", data, 8) + (len(data),)
    n = PBP_PARTS.index(name)
    part = data[offsets[n]:offsets[n + 1]]
    return part or None


def read_pbp(path: Path) -> Game | None:
    """The memory stick game of an EBOOT.PBP; None for a game's update (category "PG"), or anything unreadable."""
    try:
        sfo = read_sfo(pbp_part(path.read_bytes(), "PARAM.SFO") or b"")
    except OSError:
        return None
    if not sfo or sfo.get("CATEGORY") == PATCH:
        return None
    title = " ".join(str(sfo.get("TITLE") or "").split()) or path.parent.name
    return Game(path, title, str(sfo.get("DISC_ID") or ""), str(sfo.get("DISC_VERSION") or ""), "pbp")


# --- The scan ---------------------------------------------------------------------------------------------------

def _found(root: Path, depth: int = MAX_DEPTH):
    """The disc images and EBOOT.PBPs below *root*."""
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        if entry.is_file():
            if entry.name.lower().endswith(DISC_SUFFIXES) or entry.name.upper() == "EBOOT.PBP":
                yield Path(entry.path)
        elif depth > 0 and entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
            yield from _found(Path(entry.path), depth - 1)


def _read(path: Path) -> Game | None:
    return read_pbp(path) if path.suffix.lower() == ".pbp" else read_disc(path)


def installed(game_dir: Path) -> list[Game]:
    """The memory stick games in PPSSPP's PSP/GAME (one folder each, updates left out)."""
    try:
        folders = sorted(p for p in game_dir.iterdir() if p.is_dir())
    except OSError:
        return []
    games = (read_pbp(folder / "EBOOT.PBP") for folder in folders)
    return [g for g in games if g is not None]


def scan(folders: list[Path], game_dir: Path | None = None) -> list[Game]:
    """Every game: on PPSSPP's memory stick and below the chosen folders (a game found twice counted once), sorted
    by title."""
    found = installed(game_dir) if game_dir else []
    for folder in folders:
        found += [g for g in (_read(path) for path in _found(folder)) if g is not None]
    seen: set[Path] = set()
    games = []
    for game in found:
        key = game.file.resolve()
        if key not in seen:
            seen.add(key)
            games.append(game)
    return sorted(games, key=lambda g: (g.title.casefold(), g.disc_id, str(g.file)))
