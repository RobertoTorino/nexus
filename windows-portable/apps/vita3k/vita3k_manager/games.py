# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS Vita games: Vita3K starts only what it has installed, each game a folder in its Vita FS, ux0\\app\\<title
ID>, with eboot.bin (the program) and sce_sys\\param.sfo (its title, title ID PCSB00245 and version), as build 4186
lists them (app::scan_apps). Vita3K starts one by that folder's name (-r PCSB00245). Updates and DLC are not games to
start: Vita3K installs them in ux0\\patch and ux0\\addcont. The reading is the BC250 suite's Vita3K Manager's (its
games.py), but for a game's pictures that cannot be read (Game.picture) and a text whose length is understated
(read_sfo, as build 4282 reads it).

param.sfo is the PSF format of the PlayStation consoles: a 20-byte header ("\\0PSF", version, start of the key
table, start of the data table, number of entries), then 16 bytes per entry (key offset u16, format u16, length
u32, room u32, data offset u32), little-endian. Format 0x0204 (and 0x0004) is UTF-8 text, 0x0404 a u32. Vita3K shows
TITLE with its line breaks as spaces, and APP_VER without its leading zero ("01.00" as "1.00")."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

TEXT, TEXT_SPECIAL, NUMBER = 0x0204, 0x0004, 0x0404


@dataclass(frozen=True)
class Game:
    folder: Path                        # ux0\app\<title ID>
    title: str
    title_id: str = ""
    version: str = ""

    @property
    def name(self) -> str:
        """What Vita3K starts it by (-r): the folder's name."""
        return self.folder.name

    def picture(self, name: str) -> Path | None:
        """One of the game's own pictures in sce_sys (icon0.png: 128 × 128, pic0.png: 960 × 544), if it has it. One
        that cannot be read is none: Update Steam still takes out the shortcut of a game whose folder is gone."""
        path = self.folder / "sce_sys" / name
        try:
            return path if path.is_file() else None
        except OSError:
            return None


def read_sfo(data: bytes) -> dict[str, str | int]:
    """The entries of a param.sfo; {} for anything that is not one."""
    if len(data) < 20 or data[:4] != b"\0PSF":
        return {}
    try:
        _version, keys, values, count = struct.unpack_from("<4I", data, 4)
        table = len(data) - values
        offsets = sorted(struct.unpack_from("<I", data, 20 + 16 * n + 12)[0] for n in range(count))
        found: dict[str, str | int] = {}
        for n in range(count):
            key_at, kind, length, room, value_at = struct.unpack_from("<HHIII", data, 20 + 16 * n)
            start = keys + key_at
            name = data[start:data.index(b"\0", start)].decode("utf-8", "replace")
            if kind == TEXT:
                # Some param.sfo files understate a text's length: its terminator is still within the entry's room,
                # before the next entry's data, so the text is read to there and cut at its first null (as Vita3K
                # reads it since build 4282, packages/src/sfo.cpp; 4269 refused such a file).
                following = min((at for at in offsets if at > value_at), default=table)
                length = min(room, table - value_at, following - value_at)
            raw = data[values + value_at:values + value_at + length]
            if kind == NUMBER:
                found[name] = struct.unpack("<I", raw[:4])[0]
            elif kind in (TEXT, TEXT_SPECIAL):
                found[name] = raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
        return found
    except (struct.error, ValueError):
        return {}


def read_game(folder: Path) -> Game | None:
    """The game installed in *folder*; None without its param.sfo or eboot.bin."""
    try:
        sfo = read_sfo((folder / "sce_sys" / "param.sfo").read_bytes())
    except OSError:
        return None
    if not sfo or not (folder / "eboot.bin").is_file():
        return None
    title = " ".join(str(sfo.get("TITLE") or sfo.get("STITLE") or "").split()) or folder.name
    version = str(sfo.get("APP_VER") or "")
    return Game(folder, title, str(sfo.get("TITLE_ID") or folder.name), version[1:] if version[:1] == "0" else version)


def installed(vita_fs: Path) -> list[Game]:
    """The games installed in Vita3K, sorted by title."""
    try:
        folders = sorted(p for p in (vita_fs / "ux0" / "app").iterdir() if p.is_dir())
    except OSError:
        return []
    games = [g for g in (read_game(folder) for folder in folders) if g is not None]
    return sorted(games, key=lambda g: (g.title.casefold(), g.title_id, g.name))
