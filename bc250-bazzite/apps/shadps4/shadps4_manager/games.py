# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS4 games in the chosen folders: an installed game is a folder with eboot.bin and, beside it,
sce_sys/param.sfo with its title, title ID (CUSA00001) and version.

The scan follows the owner's Windows launcher Nexus (an eboot.bin found below a folder, the folder's name as the
title without a leading "[PS4]", a path found twice counted once); here the title and ID come from param.sfo when it
is there. Updates and mods are not games to start: shadPS4 lays them over the game from a folder beside it, named
like the game's with "-UPDATE", "-patch" or "-mods" added (fs.cpp in 0.20.0). An update's param.sfo says category
"gp", but so does a game with its update already in it (dumped from a PS4 that had the update installed): a "gp"
folder is left out only when its game, with the same title ID, is found too.

param.sfo: a 20-byte header ("\\0PSF", version, start of the key table, start of the data table, number of entries),
then 16 bytes per entry (key offset u16, format u16, length u32, room u32, data offset u32), little-endian. Format
0x0204 (and 0x0004) is UTF-8 text, 0x0404 a u32."""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

MAX_DEPTH = 5                           # as deep as shadPS4 itself looks for a game in a game folder
TEXT, TEXT_SPECIAL, NUMBER = 0x0204, 0x0004, 0x0404
_PREFIX = re.compile(r"^\[PS4\]\s*", re.IGNORECASE)
OVERLAYS = ("-UPDATE", "-patch", "-mods")


@dataclass(frozen=True)
class Game:
    eboot: Path
    title: str
    title_id: str = ""
    version: str = ""
    patched: bool = field(default=False, compare=False)     # category "gp": an update, or a game with it in it

    @property
    def folder(self) -> Path:
        return self.eboot.parent

    def picture(self, name: str) -> Path | None:
        """One of the game's own pictures in sce_sys (icon0.png: 512 × 512, pic1.png: 1920 × 1080), if it has it."""
        path = self.folder / "sce_sys" / name
        return path if path.is_file() else None


def read_sfo(data: bytes) -> dict[str, str | int]:
    """The entries of a param.sfo; {} for anything that is not one."""
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


def read_game(eboot: Path) -> Game | None:
    """The game in eboot's folder; None for an update or mod in a folder of its own name, or an add-on."""
    if eboot.parent.name.endswith(OVERLAYS):
        return None
    try:
        sfo = read_sfo((eboot.parent / "sce_sys" / "param.sfo").read_bytes())
    except OSError:
        sfo = {}
    if sfo.get("CATEGORY") == "ac":
        return None
    title = str(sfo.get("TITLE") or "") or _PREFIX.sub("", eboot.parent.name).strip() or eboot.parent.name
    return Game(eboot, title, str(sfo.get("TITLE_ID") or ""), str(sfo.get("APP_VER") or sfo.get("VERSION") or ""),
                str(sfo.get("CATEGORY", "")).startswith("gp"))


def _eboots(root: Path, depth: int = MAX_DEPTH):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if entry.is_file() and entry.name.lower() == "eboot.bin":
            yield Path(entry.path)
    if depth > 0:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") and entry.name != "sce_sys":
                yield from _eboots(Path(entry.path), depth - 1)


def scan(folders: list[Path]) -> list[Game]:
    """Every game below the folders (a game found twice counted once, an update found beside its game left out),
    sorted by title."""
    seen: set[Path] = set()
    games = []
    for folder in folders:
        for eboot in _eboots(folder):
            key = eboot.resolve()
            if key in seen:
                continue
            seen.add(key)
            game = read_game(eboot)
            if game is not None:
                games.append(game)
    with_game = {g.title_id for g in games if not g.patched and g.title_id}
    games = [g for g in games if not (g.patched and g.title_id in with_game)]
    return sorted(games, key=lambda g: (g.title.casefold(), g.title_id, str(g.eboot)))
