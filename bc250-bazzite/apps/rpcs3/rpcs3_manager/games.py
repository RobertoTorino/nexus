# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS3 games: a game is a folder with PARAM.SFO (its title, title ID BLUS30443 and version) and USRDIR/EBOOT.BIN,
the program RPCS3 starts. There are two kinds, as RPCS3 0.0.43 lists them (game_enumeration.h):

* a disc game, copied from its disc: a folder with PS3_DISC.SFB and PS3_GAME/, which holds PARAM.SFO and USRDIR.
  RPCS3 starts it only with a valid PS3_DISC.SFB (its first four bytes ".SFB", IsValidSfb in System.cpp);
* an installed game (from a package): a folder in RPCS3's dev_hdd0/game with PARAM.SFO and USRDIR.

The games found are those in dev_hdd0/game, the disc games RPCS3 knows (its games.yml) and the disc games in the
folders chosen in the app (up to five folders deep). Updates are not games to start: they install into
dev_hdd0/game in a folder named by the game's ID, with category "GD" (game data), and RPCS3 starts the update's
EBOOT.BIN by itself when it starts the disc game.

PARAM.SFO is the PSF format of the PS3 and PS4: a 20-byte header ("\\0PSF", version, start of the key table, start
of the data table, number of entries), then 16 bytes per entry (key offset u16, format u16, length u32, room u32,
data offset u32), little-endian. Format 0x0204 (and 0x0004) is UTF-8 text, 0x0404 a u32."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

MAX_DEPTH = 5
TEXT, TEXT_SPECIAL, NUMBER = 0x0204, 0x0004, 0x0404
GAME_DATA = "GD"                        # an update or other game data, not a game


@dataclass(frozen=True)
class Game:
    eboot: Path                         # USRDIR/EBOOT.BIN, what RPCS3 starts
    title: str
    title_id: str = ""
    version: str = ""
    disc: bool = False                  # a disc game (PS3_GAME/ beside PS3_DISC.SFB)

    @property
    def content(self) -> Path:
        """The folder with PARAM.SFO and the game's pictures (PS3_GAME, or the installed game's folder)."""
        return self.eboot.parent.parent

    @property
    def folder(self) -> Path:
        """The game's own folder: the disc's, or the installed game's."""
        return self.content.parent if self.disc else self.content

    @property
    def startable(self) -> bool:
        """False for a disc game without a valid PS3_DISC.SFB, which RPCS3 does not start."""
        if not self.disc:
            return True
        try:
            with (self.folder / "PS3_DISC.SFB").open("rb") as sfb:
                return sfb.read(4) == b".SFB"
        except OSError:
            return False

    def picture(self, name: str) -> Path | None:
        """One of the game's own pictures (ICON0.PNG: 320 × 176, PIC1.PNG: 1920 × 1080), if it has it."""
        path = self.content / name
        return path if path.is_file() else None


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


def read_game(content: Path, disc: bool = False) -> Game | None:
    """The game whose PARAM.SFO and USRDIR are in *content*; None for game data (an update), or without either."""
    eboot = content / "USRDIR" / "EBOOT.BIN"
    try:
        sfo = read_sfo((content / "PARAM.SFO").read_bytes())
    except OSError:
        return None
    if not sfo or sfo.get("CATEGORY") == GAME_DATA or not eboot.is_file():
        return None
    folder = content.parent if disc else content
    title = " ".join(str(sfo.get("TITLE") or "").split()) or folder.name   # PS3 titles may hold line breaks
    return Game(eboot, title, str(sfo.get("TITLE_ID") or ""), str(sfo.get("APP_VER") or sfo.get("VERSION") or ""),
                disc)


def _disc_games(root: Path, depth: int = MAX_DEPTH):
    """The disc games below *root*: folders with PS3_GAME/PARAM.SFO. Not looked into further once found."""
    if (root / "PS3_GAME" / "PARAM.SFO").is_file():
        yield root
        return
    if depth <= 0:
        return
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") and entry.name != "USRDIR":
            yield from _disc_games(Path(entry.path), depth - 1)


def installed(hdd0_game: Path) -> list[Game]:
    """The games installed in RPCS3's dev_hdd0/game."""
    try:
        folders = sorted(p for p in hdd0_game.iterdir() if p.is_dir())
    except OSError:
        return []
    return [g for g in (read_game(folder) for folder in folders) if g is not None]


def known(paths: list[str]) -> list[Game]:
    """The disc games in RPCS3's games.yml (their folders; an ISO file is left out: its PARAM.SFO is inside it)."""
    games = []
    for path in paths:
        folder = Path(path.rstrip("/").removesuffix("/."))
        if (folder / "PS3_GAME").is_dir():
            game = read_game(folder / "PS3_GAME", disc=True)
        elif folder.name == "PS3_GAME":
            game = read_game(folder, disc=True)
        else:
            game = read_game(folder)            # an installed game outside dev_hdd0
        if game is not None:
            games.append(game)
    return games


def scan(folders: list[Path], hdd0_game: Path | None = None, known_paths: list[str] = ()) -> list[Game]:
    """Every game: installed in RPCS3, known to it, and below the chosen folders (a game found twice counted once),
    sorted by title."""
    found = installed(hdd0_game) if hdd0_game else []
    found += known(list(known_paths))
    for folder in folders:
        found += [g for g in (read_game(d / "PS3_GAME", disc=True) for d in _disc_games(folder)) if g is not None]
    seen: set[Path] = set()
    games = []
    for game in found:
        key = game.eboot.resolve()
        if key not in seen:
            seen.add(key)
            games.append(game)
    return sorted(games, key=lambda g: (g.title.casefold(), g.title_id, str(g.eboot)))
