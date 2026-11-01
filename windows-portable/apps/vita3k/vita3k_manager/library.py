# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games, as the BC250 suite's Vita3K Manager keeps them: the games Vita3K has installed (games.installed: Vita3K
starts only what is in its storage), which have a Steam shortcut of this app, and the plan Update Steam carries out:
the marked games in Steam, the others out, and the shortcuts of games no longer installed out too (the BC250 app's
steam_plan). The suite's SteamGridDB key and the pictures found are in the suite's folders
(%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's covers\\).

The app's own folders (owner, 30-10-2026: the games and what the emulator needs are put there, nothing is browsed
to): Games\\Vita in your user folder, made when it is missing, and Games\\Vita on a removable drive (an SD card, a USB
stick) that has one (fixed), with Games\\Vita\\Firmware in your user folder for the firmware files (firmware_home,
firmware_files). What waits there to be installed in Vita3K (waiting): a .vpk, a .zip, a .pkg or a dumped game's
folder. Remove game lists what of a game would go from Vita3K's storage (removal, removal_items), for the page where
the user decides what to keep (core's keep; owner, 01-11-2026: before deleting anything, let the user decide what
to keep)."""

from __future__ import annotations

import ctypes
import os
import string
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250_core import covers, keep, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts, userdata
from .games import Game, read_sfo

GAMES_HOME = Path("Games") / "Vita"     # the app's own game folder, in the user's folder and on a removable drive
FIRMWARE = "Firmware"                   # the firmware files' folder in it
DRIVE_REMOVABLE = 2                     # GetDriveTypeW
DEPTH = 3                               # how far below a game folder the waiting games are looked for
SFO = "sce_sys/param.sfo"
CONTENT_ID_AT = 0x30                    # a PS Vita .pkg's content ID ("UP0001-PCSB00245_00-..."), its title ID at 7


def key_file() -> Path:
    """The suite's SteamGridDB API key, the Windows Portable Suite's own (BC250's is in its ~/.config folder)."""
    return suite_config(SUITE) / "steamgriddb-key"


def covers_home() -> Path:
    return suite_data(SUITE) / APP_ID / "covers"


def removable_drives() -> list[Path]:
    """The removable drives' roots (an SD card, a USB stick); [] off Windows."""
    if sys.platform != "win32":
        return []
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    mask = k32.GetLogicalDrives()
    found = []
    for n, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << n) and k32.GetDriveTypeW(f"{letter}:\\") == DRIVE_REMOVABLE:
            found.append(Path(f"{letter}:\\"))
    return found


def firmware_home(home: Path | None = None) -> Path:
    """Where the firmware files are put: Games\\Vita\\Firmware in the user's folder."""
    return (home or Path.home()) / GAMES_HOME / FIRMWARE


def fixed(home: Path | None = None, drives: Callable[[], list[Path]] = removable_drives) -> list[Path]:
    """The app's own game folders (owner, 30-10-2026: drop the games there, no browsing): Games\\Vita in the user's
    folder, made with its Firmware folder when they are missing, then Games\\Vita on each removable drive that has
    one."""
    own = (home or Path.home()) / GAMES_HOME
    try:
        firmware_home(home).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return [own, *[d / GAMES_HOME for d in drives() if _is_dir(d / GAMES_HOME)]]


def _is_dir(place: Path) -> bool:
    """Whether the place is a folder; a removable drive without a card (an empty SD slot keeps its letter) makes
    Windows raise rather than answer, and is no place."""
    try:
        return place.is_dir()
    except OSError:
        return False


def _entries(folder: Path) -> list[Path]:
    try:
        return sorted(folder.iterdir())
    except OSError:
        return []


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def firmware_files(home: Path | None = None) -> list[Path]:
    """The .PUP files in Games\\Vita\\Firmware and in a folder right below it (Sony names each one PSP2UPDAT.PUP, so the
    font package is renamed or put in a folder of its own), the largest first: the system software before the
    fonts."""
    folder = firmware_home(home)
    places = [folder, *[p for p in _entries(folder) if _is_dir(p)]]
    found = [p for place in places for p in _entries(place)
             if p.suffix.lower() in userdata.FIRMWARE_SUFFIXES and p.is_file()]
    return sorted(found, key=lambda p: (-_size(p), str(p).casefold()))


def stamp(path: Path) -> str:
    """What tells that a file changed: its size and its time; "" when it cannot be read."""
    try:
        there = path.stat()
    except OSError:
        return ""
    return f"{there.st_size}:{int(there.st_mtime)}"


@dataclass(frozen=True)
class Waiting:
    """A game put in a game folder and not installed in Vita3K yet: a .vpk, .zip or .pkg file, or a dumped game's
    folder (with sce_sys\\param.sfo)."""
    path: Path
    kind: str                           # "VPK", "ZIP", "PKG" or "Folder", as its row says
    title: str = ""
    title_id: str = ""
    update: bool = False                # its param.sfo says an update (category gp)

    @property
    def package(self) -> bool:
        """A .pkg, which installs only with its license key (a zRIF)."""
        return self.kind == "PKG"


def _from_sfo(data: bytes) -> tuple[str, str, bool]:
    """(title, title ID, whether it is an update) of a param.sfo's bytes."""
    sfo = read_sfo(data)
    title = " ".join(str(sfo.get("TITLE") or sfo.get("STITLE") or "").split())
    return title, str(sfo.get("TITLE_ID") or ""), str(sfo.get("CATEGORY") or "").startswith("gp")


def _archive_sfo(path: Path) -> bytes:
    """The param.sfo of a .vpk or .zip, the one nearest its top; b"" without one."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = sorted((n for n in archive.namelist() if n.replace("\\", "/").lower().endswith(SFO)),
                           key=lambda n: n.count("/"))
            return archive.read(names[0]) if names else b""
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError, ValueError):
        return b""


def package_id(path: Path) -> str:
    """A PS Vita .pkg's title ID, from the content ID in its header; "" for a file that is no package."""
    try:
        with path.open("rb") as file:
            head = file.read(CONTENT_ID_AT + 36)
    except OSError:
        return ""
    if head[:4] != b"\x7fPKG":
        return ""
    content_id = head[CONTENT_ID_AT:CONTENT_ID_AT + 36].split(b"\0", 1)[0].decode("ascii", "replace")
    return content_id[7:16] if len(content_id) >= 16 and content_id[6] == "-" else ""


def _read(path: Path, kind: str) -> Waiting:
    if kind == "PKG":
        return Waiting(path, kind, "", package_id(path))
    if kind == "Folder":
        try:
            data = (path / "sce_sys" / "param.sfo").read_bytes()
        except OSError:
            data = b""
    else:
        data = _archive_sfo(path)
    return Waiting(path, kind, *_from_sfo(data))


_read_before: dict[tuple[str, str], Waiting] = {}  # each file read once while it stays the same


def _remembered(path: Path, kind: str) -> Waiting:
    key = (os.path.normcase(str(path)), stamp(path / "sce_sys" / "param.sfo" if kind == "Folder" else path))
    if key not in _read_before:
        _read_before[key] = _read(path, kind)
    return _read_before[key]


def _kind(path: Path) -> str:
    """What a file is to install: "PKG", "VPK" or "ZIP"; "" for another file."""
    suffix = path.suffix.lower()
    if suffix in userdata.PACKAGE_SUFFIXES:
        return "PKG"
    return suffix[1:].upper() if suffix in userdata.ARCHIVE_SUFFIXES else ""


def waiting(folders: list[Path], installed: set[str], depth: int = DEPTH) -> list[Waiting]:
    """What waits in the game folders (and up to *depth* folders below them) to be installed in Vita3K (owner,
    30-10-2026: drop the games in the folder, the manager takes care of them): each .vpk, .zip and .pkg file and each
    dumped game's folder (userdata.is_dump; nothing below one is looked at). A game whose title ID is in *installed*
    is left out; an update is not, nor a .pkg (it may hold an update or extra content, and goes once installed). The
    Firmware folder is not looked in. Sorted by title."""
    found: dict[str, Waiting] = {}
    skip = {os.path.normcase(str(f / FIRMWARE)) for f in folders}

    def look(folder: Path, left: int) -> None:
        for entry in _entries(folder):
            if _is_dir(entry):
                if os.path.normcase(str(entry)) in skip or entry.name.startswith("."):
                    continue
                if not userdata.is_dump(entry):
                    if left > 0:
                        look(entry, left - 1)
                    continue
                item = _remembered(entry, "Folder")
            else:
                kind = _kind(entry)
                if not kind:
                    continue
                item = _remembered(entry, kind)
            if not item.package and not item.update and item.title_id and item.title_id in installed:
                continue
            found.setdefault(os.path.normcase(str(entry)), item)

    for folder in folders:
        look(folder, depth)
    return sorted(found.values(), key=lambda w: ((w.title or w.path.name).casefold(), str(w.path)))


def plan(found: list[Game], marked: set[str], in_steam: dict[str, str]) -> tuple[list[Game], list[Game]]:
    """(games to add or bring up to date, games to take out): the marked ones in, the others out, and the shortcuts
    of games no longer installed out too."""
    add = [g for g in found if g.name in marked]
    names = {g.name for g in found}
    remove = [g for g in found if g.name in in_steam and g.name not in marked]
    remove += [Game(Path(name), title) for name, title in in_steam.items() if name not in names]
    return add, remove


def pending(found: list[Game], marked: set[str], in_steam: dict[str, str], outdated: set[str] = frozenset()) -> bool:
    """Whether Update Steam would change anything: a game in or out, a name in Steam that differs, or a shortcut that
    does not start the play mode yet (*outdated*, shortcuts.outdated)."""
    add, remove = plan(found, marked, in_steam)
    named = shortcuts.names(add)
    return bool(remove) or any(in_steam.get(g.name) != named[g.name] or g.name in outdated for g in add)


def update_steam(steam_dir: Path, add: list[Game], remove: list[Game], program: Path, logo: Path,
                 existing: dict[str, str], closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 key: str = "", home: Path | None = None, get=None) -> tuple[bool, str, dict[str, str] | None]:
    """Steam's shortcuts made to match (off the window's thread): the pictures from SteamGridDB first when there is
    a key, then the shortcuts with Steam closed. (ok, what to tell, the app's games in Steam's file as read back
    right after the write, while Steam is still closed; None when nothing was written). Reading the file back then
    rather than once Steam starts again (29-10-2026: "it still says 0 games in Steam") tells whether the shortcuts
    were written as the app reads them, before Steam touches the file."""
    home = home or covers_home()
    notes = (covers.fetch([(shortcuts.cover_name(g), g.title) for g in add], shortcuts.COVERS, key, home,
                          *([get] if get else [])) if key else [])
    changes = shortcuts.changes(add, remove, program, logo, existing,
                                found=lambda g: covers.art(home, shortcuts.cover_name(g), shortcuts.COVERS))
    found: dict[str, str] = {}

    def change() -> None:
        steam.write_shortcuts(steam_dir, changes)
        found.update(shortcuts.in_steam(steam_dir))

    try:
        restarted = closed(change)
    except (steam.SteamError, steam.ShortcutError, OSError) as error:
        return False, "\n".join([*notes, f"Steam was not changed: {error}"]), None
    again = " Steam was closed for it and started again, signed in." if restarted else ""
    return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in its library"
                                      f"{f'; {len(remove)} taken out' if remove else ''}.{again}"]), found


STEAM_ITEM = "steam"                    # the keep page's row of a game's Steam shortcut
PARTS = {"app": "The game", "patch": "Its update", "addcont": "Its extra content"}


def removal(game: Game, vita_fs: Path) -> list[Path]:
    """What Remove game offers to delete (owner, 30-10-2026: a game that no longer plays goes, files and all): the
    game in Vita3K's storage (ux0\\app\\<title ID>), then its update and extra content (ux0\\patch, ux0\\addcont)
    when they are there. The saves (ux0\\user\\00\\savedata) are never offered. [] for a game that is not in
    ux0\\app."""
    app = vita_fs / "ux0" / "app"
    if os.path.normcase(str(game.folder.parent)) != os.path.normcase(str(app)) or not game.name:
        return []
    more = [vita_fs / "ux0" / kind / game.name for kind in ("patch", "addcont")]
    return [game.folder, *[f for f in more if _is_dir(f)]]


def removal_items(folders: list[Path], in_steam: bool) -> list[keep.Item]:
    """The keep page's rows for Remove game: each of *folders* (removal) a row of its own, then the game's Steam
    shortcut when it is in Steam; every row marked Delete at first."""
    items = [keep.Item(str(f), f"{PARTS.get(f.parent.name, f.parent.name)}, ux0\\{f.parent.name}\\{f.name}", (f,))
             for f in folders]
    if in_steam:
        items.append(keep.Item(STEAM_ITEM, "Its shortcut in Steam"))
    return items
