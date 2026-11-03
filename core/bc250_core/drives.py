# SPDX-License-Identifier: GPL-3.0-or-later
"""The removable drives on a Bazzite system, for the game managers' own game folders (owner, 03-11-2026, from the
Windows Portable Suite's managers: fixed folders, no folder choosing): a USB drive or an SD card is mounted under
/run/media (udisks: /run/media/<user>/<drive>; Bazzite's media-automount: /run/media/system/<drive>, which
media-automount links to) or /media. A game folder of an app (Games/PS2, Games/PSP, ...) lies in the home folder
and, when the user made one, on such a drive."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

MEDIA_ROOTS = (Path("/run/media"), Path("/media"))


def removable_drives(roots: tuple[Path, ...] = MEDIA_ROOTS) -> list[Path]:
    """The mounted removable drives: every mount point right under the media folders, or one folder below them,
    each once; a link among them (media-automount) is left to the folder it points at."""
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            entries = sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            continue
        for entry in entries:
            places = [entry] if os.path.ismount(entry) else []
            if not places:
                try:
                    places = [p for p in sorted(entry.iterdir())
                              if p.is_dir() and not p.is_symlink() and os.path.ismount(p)]
                except OSError:
                    continue
            for place in places:
                key = place.resolve()
                if key not in seen:
                    seen.add(key)
                    found.append(place)
    return found


def game_folders(home: Path, games_home: Path, drives: Callable[[], list[Path]] = removable_drives,
                 make: tuple[str, ...] = ()) -> list[Path]:
    """An app's own game folders: *games_home* (Games/PS2) in the home folder, made with the subfolders *make* when
    it is missing, then the same folder on each removable drive that has one."""
    own = home / games_home
    try:
        own.mkdir(parents=True, exist_ok=True)
        for name in make:
            (own / name).mkdir(exist_ok=True)
    except OSError:
        pass
    return [own, *[d / games_home for d in drives() if _is_dir(d / games_home)]]


def _is_dir(place: Path) -> bool:
    try:
        return place.is_dir()
    except OSError:
        return False
