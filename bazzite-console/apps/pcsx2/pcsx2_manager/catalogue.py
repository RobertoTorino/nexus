# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's own catalog, out of the AppImage it comes in: GameIndex.yaml, every PS2 game PCSX2 knows by its serial
with its title, and patches.zip, the patches PCSX2 brings, one file per game named <serial>_<CRC>.pnach (or <CRC>.pnach)
with a widescreen patch under [Widescreen 16:9]. A PS2 disc carries no title, so these give a game its name in the
app and in Steam, and say whether it has a widescreen patch.

Install takes both files out of the installed AppImage with the AppImage's own --appimage-extract into the
version's folder beside it; a PCSX2 installed before is done when the window opens. They come from the PCSX2 that is
installed, so a newer PCSX2 brings its own. Without them a game keeps its file's name and no widescreen patch is
offered.

GameIndex.yaml is read line by line rather than as YAML (the suite's Python has no YAML library): a serial at the
start of a line, then its "name:" and "name-en:" (the English one, which Japanese games have, is preferred), each a
string in double quotes, possibly followed by a comment."""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

INSIDE = "usr/bin/resources"
GAME_INDEX = "GameIndex.yaml"
PATCHES = "patches.zip"
FILES = (GAME_INDEX, PATCHES)
WIDESCREEN = "[Widescreen 16:9]"                    # the patch PCSX2 turns on with EnableWideScreenPatches
TIMEOUT = 60

Run = Callable[..., subprocess.CompletedProcess]

_NAME = re.compile(r'^  (name|name-en):\s*"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')
_titles: dict[Path, tuple[float, dict[str, str]]] = {}
_patches: dict[Path, tuple[float, dict[str, bool]]] = {}


def missing(folder: Path) -> bool:
    return not all((folder / name).is_file() for name in FILES)


def extract(image: Path, run: Run = subprocess.run) -> None:
    """Takes GameIndex.yaml and patches.zip out of *image* into its folder. OSError or CalledProcessError when it
    cannot; what was there stays then."""
    work = image.parent / ".catalogue"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        for name in FILES:
            run([str(image), "--appimage-extract", f"{INSIDE}/{name}"], cwd=work, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT)
        for name in FILES:
            (work / "squashfs-root" / INSIDE / name).replace(image.parent / name)
    finally:
        shutil.rmtree(work, ignore_errors=True)


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


def titles(folder: Path) -> dict[str, str]:
    """The titles in *folder*'s GameIndex.yaml, read once per change of the file; {} without one."""
    path = folder / GAME_INDEX
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


def has_widescreen(folder: Path, serial: str, crc: int) -> bool:
    """Whether PCSX2's patches have a widescreen patch for the game, looked up as PCSX2 does: <serial>_<CRC>.pnach,
    else <CRC>.pnach."""
    if not crc:
        return False
    path = folder / PATCHES
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
