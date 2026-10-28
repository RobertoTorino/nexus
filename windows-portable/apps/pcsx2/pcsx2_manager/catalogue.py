# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's own catalog, as its Windows build brings it in resources\\ beside pcsx2-qt.exe: GameIndex.yaml, every PS2
game PCSX2 knows by its serial with its title, and patches.zip, the patches PCSX2 brings, one file per game named
<serial>_<CRC>.pnach (or <CRC>.pnach) with a widescreen patch under [Widescreen 16:9]. A PS2 disc carries no title,
so these give a game its name in the app and in Steam, and say whether it has a widescreen patch. The BC250 suite's
PCSX2 Manager reads the same two files (its catalogue.py, which first takes them out of the AppImage); here they are
plain files of the installed PCSX2, so a newer PCSX2 brings its own. Without them a game keeps its file's name.

GameIndex.yaml is read line by line rather than as YAML (the app's Python has no YAML library): a serial at the start
of a line, then its "name:" and "name-en:" (the English one, which Japanese games have, is preferred), each a string
in double quotes, possibly followed by a comment."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

GAME_INDEX = "GameIndex.yaml"
PATCHES = "patches.zip"
WIDESCREEN = "[Widescreen 16:9]"                    # the patch PCSX2 turns on with EnableWideScreenPatches

_NAME = re.compile(r'^  (name|name-en):\s*"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')
_titles: dict[Path, tuple[float, dict[str, str]]] = {}
_patches: dict[Path, tuple[float, dict[str, bool]]] = {}


def folder(home: Path) -> Path:
    """Where the installed PCSX2 keeps its catalog: resources\\ beside its program."""
    return home / "resources"


def _unquote(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def read_titles(path: Path) -> dict[str, str]:
    """{serial: title} from a GameIndex.yaml; the English name where a game has one."""
    names: dict[str, dict[str, str]] = {}
    serial = ""
    with path.open(encoding="utf-8", errors="replace") as file:
        for line in file:
            if line[:1] not in ("", " ", "\t", "\n", "#"):
                serial = line.split(":", 1)[0].strip()
                continue
            found = _NAME.match(line.rstrip("\n"))
            if found and serial:
                names.setdefault(serial, {})[found.group(1)] = _unquote(found.group(2)).strip()
    return {serial: n.get("name-en") or n.get("name", "") for serial, n in names.items() if any(n.values())}


def titles(where: Path) -> dict[str, str]:
    """The titles in *where*'s GameIndex.yaml, read once per change of the file; {} without one."""
    path = where / GAME_INDEX
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {}
    kept = _titles.get(path)
    if kept is None or kept[0] != stamp:
        try:
            kept = (stamp, read_titles(path))
        except OSError:
            return {}
        _titles[path] = kept
    return kept[1]


def _read_patches(path: Path) -> dict[str, bool]:
    """{file name in patches.zip: whether it has the widescreen patch}."""
    found = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".pnach"):
                found[name.upper()] = WIDESCREEN.encode() in archive.read(name)
    return found


def has_widescreen(where: Path, serial: str, crc: int) -> bool:
    """Whether PCSX2's patches have a widescreen patch for the game, looked up as PCSX2 does: <serial>_<CRC>.pnach,
    else <CRC>.pnach."""
    if not crc:
        return False
    path = where / PATCHES
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return False
    kept = _patches.get(path)
    if kept is None or kept[0] != stamp:
        try:
            kept = (stamp, _read_patches(path))
        except (OSError, zipfile.BadZipFile):
            return False
        _patches[path] = kept
    names = ([f"{serial}_{crc:08X}.PNACH".upper()] if serial else []) + [f"{crc:08X}.PNACH"]
    return next((kept[1][n] for n in names if n in kept[1]), False)
