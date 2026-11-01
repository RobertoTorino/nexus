# SPDX-License-Identifier: GPL-3.0-or-later
"""The two sides as lists of rows, browsed with the controller: the server's folders (RemoteFolder) and this
device's (LocalFolder, on core's browse.Browser: the places first, then the folders). A row's key is "up", "dir:<path>"
or "file:<path>"; a folder's text ends in › (A opens it), a file's has its size. The server's paths are shown from the
login's home as ~ (owner, 29-10-2026: no user name on the screen), this device's through platform.private().

Qt-free: the window lists a folder off its thread and turns the entries into its list."""

from __future__ import annotations

import os
import posixpath
import stat
from dataclasses import dataclass
from pathlib import Path

import paramiko

from bc250_core import browse
from bc250_core.platform import private

UP = browse.UP
OPENS = "  ›"                      # after a folder's name: A opens it
APART = "  ·  "                    # between a file's name and its size


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    is_dir: bool
    size: int = 0


def size_text(size: int) -> str:
    """Bytes for a person, 1024-based as the BC250 app's Auto: 512 B, 2.4 KB, 12.3 MB, 1.2 GB."""
    value = float(max(0, size))
    if value < 1024:
        return f"{int(value)} B"
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} GB"


def _sorted(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.casefold()))


def remote_entries(sftp: paramiko.SFTPClient, path: str, hidden: bool = False) -> list[Entry]:
    """A server's folder: its folders, then its files, by name; a name that starts with a dot only with *hidden*.
    A link counts as what it points to."""
    entries = []
    for attributes in sftp.listdir_attr(path):
        name = attributes.filename
        if name in (".", "..") or (not hidden and name.startswith(".")):
            continue
        full = posixpath.join(path, name)
        mode = attributes.st_mode or 0
        if stat.S_ISLNK(mode):
            try:
                target = sftp.stat(full)
                mode, attributes = target.st_mode or 0, target
            except OSError:
                continue                                # a broken link
        entries.append(Entry(name, full, stat.S_ISDIR(mode), 0 if stat.S_ISDIR(mode) else attributes.st_size or 0))
    return _sorted(entries)


def local_entries(folder: Path, hidden: bool = False) -> list[Entry]:
    """A folder of this device: its folders, then its files, by name. Without *hidden*, Windows' hidden and system
    files and the names that start with a dot are left out; $RECYCLE.BIN and the like always are."""
    entries = []
    try:
        listed = list(os.scandir(folder))
    except OSError:
        return []
    for entry in listed:
        try:
            if entry.name.startswith("$"):
                continue
            details = entry.stat(follow_symlinks=False)
            attributes = getattr(details, "st_file_attributes", 0)
            if not hidden and (entry.name.startswith(".") or attributes & 0x6):   # HIDDEN | SYSTEM
                continue
            is_dir = entry.is_dir()
            entries.append(Entry(entry.name, entry.path, is_dir, 0 if is_dir else entry.stat().st_size))
        except OSError:
            continue
    return _sorted(entries)


def entry_rows(entries: list[Entry]) -> list[tuple[str, str]]:
    return [(f"dir:{e.path}", f"{e.name}{OPENS}") if e.is_dir else
            (f"file:{e.path}", f"{e.name}{APART}{size_text(e.size)}") for e in entries]


class RemoteFolder:
    """Where the Server's files pane is: a folder of the server, from the login's home. B goes a level up, until the
    home (or /), then back to the card; the ‹ row goes up from anywhere."""

    def __init__(self, home: str):
        self.home = home or "/"
        self.path = self.home

    def shown(self, path: str | None = None) -> str:
        """*path* (default: where it is) as the pane shows it, the home as ~."""
        path = self.path if path is None else path
        if path == self.home:
            return "~"
        if self.home != "/" and path.startswith(self.home + "/"):
            return "~" + path[len(self.home):]
        return path

    def parent(self) -> str | None:
        return None if self.path == "/" else posixpath.dirname(self.path.rstrip("/")) or "/"

    def rows(self, entries: list[Entry]) -> list[tuple[str, str]]:
        parent = self.parent()
        return [*([(UP, f"‹ {self.shown(parent)}")] if parent is not None else []), *entry_rows(entries)]

    def open(self, key: str) -> bool:
        """A on a row: into a folder or up; whether it moved (a file does not)."""
        if key == UP:
            return self.go_up()
        if key.startswith("dir:"):
            self.path = key[4:]
            return True
        return False

    def go_up(self) -> bool:
        parent = self.parent()
        if parent is None:
            return False
        self.path = parent
        return True

    def back(self) -> bool:
        """B: a level up while above the home's level; False at the home or at / (the pane goes back to its card)."""
        if self.path in (self.home, "/"):
            return False
        return self.go_up()


class LocalFolder(browse.Browser):
    """Where the This device pane is: core's browser (the places, then folders; B goes up, from the places back to
    the card), with every file listed and its size."""

    def __init__(self, start: list[Path], path: Path | None = None, hidden: bool = False):
        super().__init__(start, (), path)
        self.hidden = hidden

    def rows(self) -> list[tuple[str, str]]:
        if self.path is None:
            return super().rows()
        parent = self.path.parent if self.path.parent != self.path else None
        back_to = private(parent) if parent is not None and self.path not in self.start else "The places"
        return [(UP, f"‹ {back_to}"), *entry_rows(local_entries(self.path, self.hidden))]

    def target(self, downloads: Path) -> Path:
        """Where a download goes: the folder open, else (at the places) *downloads*."""
        return self.path if self.path is not None else downloads


def downloads_folder(home: Path | None = None) -> Path:
    """The user's Downloads folder, the home when there is none."""
    home = home or Path.home()
    return home / "Downloads" if (home / "Downloads").is_dir() else home


def private_keys(home: Path | None = None) -> list[Path]:
    """The private keys in %USERPROFILE%\\.ssh, by name: a file id_<kind> or one with a .pub beside it."""
    folder = (home or Path.home()) / ".ssh"
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        return []
    names = {p.name for p in files}
    keys = [p for p in files if p.suffix != ".pub" and (p.name.startswith("id_") or f"{p.name}.pub" in names)
            and not p.name.startswith(("known_hosts", "authorized_keys", "config"))]
    return sorted(keys, key=lambda p: p.name.casefold())
