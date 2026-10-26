# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xbox 360 games: what Xenia opens, with the title ID (4D5307E6) where the app can read it, and the title a
package names. What is one game here:

* an .iso that is an Xbox 360 disc: "MICROSOFT*XBOX*MEDIA" in sector 32 of the game partition, at one of the places
  Xenia looks for it (the disc's video partition before it, or none: an ISO with the game partition alone). Named
  after its file.
* an .xex executable ("XEX2"), with the title ID from its execution info header (key 0x00040006). In a folder with a
  default.xex (a disc unpacked) that one is the game, named after its folder, and the other .xex files are its
  modules.
* a .zar, the ZArchive form of a disc Xenia reads: named after its file (the app does not look into it).
* a package of a game, in STFS (the console's "CON ", "LIVE" or "PIRS" containers): Games on Demand (content type
  0x00007000, a disc installed from the console's store) or an Arcade title (0x000D0000), in the folders the console
  keeps them in (<title ID>/00007000/<file>). Its header has the game's name (UTF-16 at 0x411) and title ID (0x360).
  Other packages (saves, downloadable content, title updates) are not games."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

MAX_DEPTH = 6                           # a package sits two folders below its game's folder
SECTOR = 2048
DISC_MAGIC = b"MICROSOFT*XBOX*MEDIA"
GAME_PARTITIONS = (0x00000000, 0x0000FB20, 0x00020600, 0x02080000, 0x0FD90000)   # Xenia's own list
XEX_MAGIC = b"XEX2"
EXECUTION_INFO = 0x00040006
PACKAGE_MAGICS = (b"CON ", b"LIVE", b"PIRS")
GAME_PACKAGES = {0x00007000: "god", 0x000D0000: "xbla"}
PACKAGE_FOLDERS = tuple(f"{kind:08X}" for kind in GAME_PACKAGES)


@dataclass(frozen=True)
class Game:
    file: Path                          # the ISO, XEX, ZAR or package
    title: str
    title_id: str = ""                  # 8 hexadecimal digits: 4D5307E6
    kind: str = "iso"                   # iso, xex, zar, god or xbla

    @property
    def folder(self) -> Path:
        return self.file.parent


def is_disc(path: Path) -> bool:
    """Whether an ISO is an Xbox 360 disc. OSError is the caller's."""
    with path.open("rb") as file:
        for partition in GAME_PARTITIONS:
            file.seek(partition + 32 * SECTOR)
            if file.read(len(DISC_MAGIC)) == DISC_MAGIC:
                return True
    return False


def xex_title_id(data: bytes) -> str | None:
    """The title ID in an XEX's headers ("" when it has none); None when *data* is no XEX."""
    if data[:4] != XEX_MAGIC or len(data) < 0x18:
        return None
    count = struct.unpack_from(">I", data, 0x14)[0]
    for n in range(min(count, 64)):
        at = 0x18 + n * 8
        if at + 8 > len(data):
            break
        key, value = struct.unpack_from(">II", data, at)
        if key == EXECUTION_INFO and value + 0x10 <= len(data):
            return f"{struct.unpack_from('>I', data, value + 0xC)[0]:08X}"
    return ""


def package(data: bytes) -> tuple[str, str, str] | None:
    """(kind, title, title ID) of a game's package; None when *data* is no STFS package of a game."""
    if data[:4] not in PACKAGE_MAGICS or len(data) < 0x511:
        return None
    kind = GAME_PACKAGES.get(struct.unpack_from(">I", data, 0x344)[0])
    if kind is None:
        return None
    title = data[0x411:0x511].decode("utf-16-be", "replace").split("\0", 1)[0].strip()
    return kind, title, f"{struct.unpack_from('>I', data, 0x360)[0]:08X}"


def read_game(path: Path) -> Game | None:
    """The game in one file; None when it is none."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".iso":
            return Game(path, path.stem, kind="iso") if is_disc(path) else None
        if suffix == ".zar":
            return Game(path, path.stem, kind="zar")
        with path.open("rb") as file:
            data = file.read(0x2000)
    except OSError:
        return None
    if suffix == ".xex":
        title_id = xex_title_id(data)
        if title_id is None:
            return None
        title = path.parent.name if path.name.lower() == "default.xex" else path.stem
        return Game(path, title, title_id, "xex")
    found = package(data)
    if found is None:
        return None
    kind, title, title_id = found
    return Game(path, title or path.name, title_id, kind)


def _found(root: Path, depth: int = MAX_DEPTH):
    """The files that may be games below *root*: the suffixes above, and the files without one in a folder for
    game packages. In a folder with a default.xex, its other .xex files are left out."""
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    names = {e.name.lower() for e in entries if e.is_file()}
    packages = root.name.upper() in PACKAGE_FOLDERS
    for entry in entries:
        if entry.is_file():
            name = entry.name.lower()
            if name.endswith((".iso", ".zar")) or (packages and "." not in name):
                yield Path(entry.path)
            elif name.endswith(".xex") and (name == "default.xex" or "default.xex" not in names):
                yield Path(entry.path)
        elif depth > 0 and entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
            yield from _found(Path(entry.path), depth - 1)


def scan(folders: list[Path]) -> list[Game]:
    """Every game below the chosen folders (a game found twice counted once), sorted by title."""
    seen: set[Path] = set()
    games = []
    for path in (p for folder in folders for p in _found(folder)):
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        game = read_game(path)
        if game is not None:
            games.append(game)
    return sorted(games, key=lambda g: (g.title.casefold(), g.title_id, str(g.file)))
