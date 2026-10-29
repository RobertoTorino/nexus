# SPDX-License-Identifier: GPL-3.0-or-later
"""Browsing the device's folders with the controller (owner, 29-10-2026: Windows' own folder and file windows cannot
be used with the controller, so a game folder or a BIOS dump could not be chosen): a list a page shows as rows, A
opens a folder or picks a file, B goes up a level. It starts at the places: the user's Games, Downloads, Documents and
Desktop folders that are there, then every drive (an SD card, a USB stick); a folder lists its folders (and, when
asked for, its files of the given kinds), by name, without the hidden and system ones.

Qt-free: the page turns rows() into its list and calls open() and up()."""

from __future__ import annotations

import ctypes
import os
import string
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .platform import private

UP = "up"
PLACES = ("Games", "Downloads", "Documents", "Desktop")


def mounted(root: Path) -> bool:
    """Whether a drive's root can be read: a card reader or an SD slot without a card keeps its letter, and asking
    Windows about it raises (WinError 1005, no recognized file system) or answers no, rather than listing it."""
    try:
        return root.is_dir()
    except OSError:
        return False


def drives(there: Callable[[Path], bool] = mounted) -> list[Path]:
    """Every drive's root that is there (C:\\, an SD card's E:\\), an empty slot left out; the filesystem's root off
    Windows."""
    if sys.platform != "win32":
        return [Path("/")]
    mask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
    roots = [Path(f"{letter}:\\") for n, letter in enumerate(string.ascii_uppercase) if mask & (1 << n)]
    return [root for root in roots if there(root)]


def places(home: Path | None = None, roots: Callable[[], list[Path]] = drives) -> list[Path]:
    """Where browsing starts: the user's usual folders that are there, then the drives."""
    home = home or Path.home()
    return [*(home / name for name in PLACES if (home / name).is_dir()), *roots()]


def _hidden(entry: os.DirEntry) -> bool:
    if entry.name.startswith((".", "$")):
        return True
    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & 0x6)                       # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM


def listing(folder: Path, suffixes: Sequence[str] = ()) -> tuple[list[Path], list[Path]]:
    """(the folders, the files with one of *suffixes*) in *folder*, by name; ([], []) when it cannot be read."""
    folders, files = [], []
    wanted = tuple(s.lower() for s in suffixes)
    try:
        for entry in os.scandir(folder):
            try:
                if _hidden(entry):
                    continue
                if entry.is_dir():
                    folders.append(Path(entry.path))
                elif wanted and entry.is_file() and entry.name.lower().endswith(wanted):
                    files.append(Path(entry.path))
            except OSError:
                continue
    except OSError:
        return [], []
    key = lambda p: p.name.casefold()                    # noqa: E731
    return sorted(folders, key=key), sorted(files, key=key)


def remembered(settings, key: str) -> Path | None:
    """The folder a browser for *key* was last left in (remember()), while it is still there: a browser opens
    there again (owner, 29-10-2026). *settings*: the app's QSettings, or anything with value()."""
    value = settings.value(f"browse/{key}", "")
    if not value:
        return None
    folder = Path(str(value))
    return folder if mounted(folder) else None


def remember(settings, key: str, folder: Path | None) -> None:
    """Keep *folder* (a folder added, the one a file was picked in) for the next browser for *key*."""
    if folder is not None:
        settings.setValue(f"browse/{key}", str(folder))


class Browser:
    """Where the page is: the places (path None) or a folder. rows() are (key, text): a folder "dir:<path>", a file
    "file:<path>", and, in a folder, "up" first (‹ and where it leads, for a finger)."""

    def __init__(self, start: Sequence[Path], suffixes: Sequence[str] = (), path: Path | None = None):
        self.start, self.suffixes, self.path = list(start), tuple(suffixes), path

    def rows(self) -> list[tuple[str, str]]:
        if self.path is None:
            return [(f"dir:{p}", self.place_text(p)) for p in self.start]
        parent = self.path.parent if self.path.parent != self.path else None
        back_to = private(parent) if parent is not None and self.path not in self.start else "The places"
        rows = [(UP, f"\u2039 {back_to}")]
        folders, files = listing(self.path, self.suffixes)
        rows += [(f"dir:{f}", f"{f.name}") for f in folders]
        rows += [(f"file:{f}", f"{f.name}") for f in files]
        return rows

    @staticmethod
    def place_text(path: Path) -> str:
        """A place as its row shows it: a drive by its root, a folder by its name and where it is, the user's folder
        by its variable (platform.private: never the user's name)."""
        return str(path) if path.parent == path else f"{path.name}  \u00b7  {private(path)}"

    def open(self, key: str) -> Path | None:
        """A on a row: into a folder (None), up for "up" (None), or the file picked (its path)."""
        if key == UP:
            self.up()
        elif key.startswith("dir:"):
            self.path = Path(key[4:])
        elif key.startswith("file:"):
            return Path(key[5:])
        return None

    def up(self) -> bool:
        """B: a level up; from a place (or a drive's root) back to the places. False at the places already: the page
        leaves the browser then."""
        if self.path is None:
            return False
        if self.path in self.start or self.path.parent == self.path:
            self.path = None
        else:
            self.path = self.path.parent
        return True
