# SPDX-License-Identifier: GPL-3.0-or-later
"""Deciding what to keep before anything is deleted (owner, 01-11-2026: before deleting anything, let the user decide
what to keep): a page lists what would go, a row each (a game's folder, its update, a package, a BIOS file, a Steam
shortcut) with its size, every row marked Delete at first; A on a row turns it to Keep and back, X deletes the rows
still marked Delete, B goes back and deletes nothing. The game managers use it for Remove game, for the packages a
clean install leaves and for PCSX2's Remove BIOS.

Qt-free: the page turns rows() into its list and calls toggle(); the app's job calls delete() off the window's
thread with the paths of chosen()."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

DELETE, KEEP = "Delete", "Keep"


@dataclass
class Item:
    """One row: *key* names it for the app, *label* says what it is, *paths* are the files and folders that go with
    it (none for something that is not on the disk, a Steam shortcut); *delete* is the row's mark."""
    key: str
    label: str
    paths: tuple[Path, ...] = ()
    delete: bool = True
    size: int = field(default=-1, compare=False)    # bytes, measured once (measure)


def size_of(path: Path) -> int:
    """The bytes of a file, or of every file in a folder and below it; 0 for what cannot be read (a missing file, a
    removed SD card)."""
    try:
        if not path.is_dir():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    for top, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.stat(os.path.join(top, name)).st_size
            except OSError:
                pass
    return total


def measure(items: Sequence[Item]) -> None:
    """Each item's size, once (a large game folder takes a moment: call it off the window's thread)."""
    for item in items:
        if item.size < 0:
            item.size = sum(size_of(p) for p in item.paths)


def human(size: int) -> str:
    """A size as a person reads it: 512 B, 3.4 KB, 120 MB, 28.1 GB (powers of 1024, as Windows' Explorer shows)."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            break
        value /= 1024
    return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"


def row_text(item: Item) -> str:
    """The row: its mark, what it is and, for what is on the disk, its size."""
    parts = [DELETE if item.delete else KEEP, item.label]
    if item.paths and item.size >= 0:
        parts.append(human(item.size))
    return "  ·  ".join(parts)


def rows(items: Sequence[Item]) -> list[tuple[str, str]]:
    """(key, text) for the page's list."""
    return [(item.key, row_text(item)) for item in items]


def toggle(items: Sequence[Item], key: str) -> Item | None:
    """A on a row: Delete becomes Keep and Keep Delete; the item, or None for a key not on the page."""
    for item in items:
        if item.key == key:
            item.delete = not item.delete
            return item
    return None


def chosen(items: Sequence[Item]) -> list[Item]:
    """The items still marked Delete."""
    return [item for item in items if item.delete]


def total(items: Sequence[Item]) -> int:
    """The bytes the marked items free (the measured ones)."""
    return sum(max(item.size, 0) for item in chosen(items))


def delete(paths: Sequence[Path]) -> list[str]:
    """The files and folders deleted, read-only ones too (an unpacked game's may be); what could not be, each with
    why. A path that is gone already counts as deleted."""
    def writable(function, path, _error) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    failed = []
    for path in paths:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, onexc=writable)
            elif path.exists() or path.is_symlink():
                try:
                    path.unlink()
                except PermissionError:
                    os.chmod(path, stat.S_IWRITE)
                    path.unlink()
        except OSError as error:
            failed.append(f"{path.name} ({error.strerror or error})")
    return failed
