# SPDX-License-Identifier: GPL-3.0-or-later
"""Steam's own files, for apps that add non-Steam games for Game Mode: finding Steam and its users, closing it while
its files change, and the shortcuts in shortcuts.vdf with their artwork. Only the standard library here.

Steam keeps non-Steam games per user in userdata/<user>/config/shortcuts.vdf, a binary key-value file: a map is
0x00, its name and its entries up to 0x08; a string is 0x01, its name and its text; a number is 0x02, its name and
4 bytes, little-endian; names and texts end with a zero byte. A shortcut's appid is the one Steam gives a non-Steam
game, the CRC-32 of its program and name with the top bit set; its artwork goes into userdata/<user>/config/grid/
under that number: <id>p.png (the library's portrait, 2:3, 600 × 900), <id>.png (the wide one, 920 × 430),
<id>_hero.png (the banner, up to 3840 × 1240) and <id>_logo.png (on the banner, transparent, up to 1280 × 720).

Steam holds its settings in memory and rewrites its files when it exits, so a change while it runs would be lost:
with_steam_closed() closes Steam first (steam -shutdown) and starts it again in the background as the desktop starts
it at login (Bazzite's bazzite-steam -silent, elsewhere steam -silent). The other shortcuts in the file stay as they
are. Moved here from BC250 Console Link (14-10-2026), which wrote it first.

On Windows (the Windows Portable Suite's PCSX2 Manager, 29-10-2026) Steam's folder is the one its registry key names
(HKCU\\Software\\Valve\\Steam, SteamPath; only read), whether it runs is steam.exe in Windows' process list, and it is
closed and started again with its own steam.exe (-shutdown, -silent). The files are the same."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

STEAM_DIRS = (                          # the native Steam (Bazzite's), its older link, the Flatpak's
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
)
WINDOWS = sys.platform == "win32"
WINDOWS_STEAM = r"C:\Program Files (x86)\Steam"     # where Steam installs itself when the registry does not say
SHUTDOWN_TIMEOUT = 30.0
MAP, STRING, INT32, END = 0, 1, 2, 8
ART = {"p": (600, 900), "": (920, 430), "_hero": (3840, 1240), "_logo": (1280, 720)}

Run = Callable[[list[str]], None]


class SteamError(Exception):
    pass


class ShortcutError(Exception):
    pass


# --- Steam itself ----------------------------------------------------------------------------------------------

def windows_steam() -> Path | None:
    """Steam's folder on Windows, as its registry key names it, else where it installs itself; None off Windows."""
    if not WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(str(winreg.QueryValueEx(key, "SteamPath")[0]))
    except OSError:
        return Path(WINDOWS_STEAM)


def find_steam(home: Path | None = None) -> Path | None:
    """The Steam folder with users in it, or None when Steam was never used here."""
    if WINDOWS and home is None:
        folder = windows_steam()
        return folder.resolve() if folder is not None and (folder / "userdata").is_dir() else None
    for folder in STEAM_DIRS:
        path = Path(folder.replace("~", str(home), 1) if home else os.path.expanduser(folder))
        if (path / "userdata").is_dir():
            return path.resolve()
    return None


def user_folders(steam: Path) -> list[Path]:
    """userdata/<user>/config of every Steam user."""
    return sorted(p for p in (steam / "userdata").glob("*/config") if p.is_dir())


def _windows_running(name: str) -> bool:
    """Whether a process named *name* (steam.exe) is in Windows' process list."""
    import ctypes

    class Entry(ctypes.Structure):               # PROCESSENTRY32W
        _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                    ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                    ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                    ("exe", ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)    # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        more = k32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while more:
            if entry.exe.lower() == name:
                return True
            more = k32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snapshot))
    return False


def steam_running(proc: Path = Path("/proc")) -> bool:
    """Whether a Steam client process runs (its process name is steam). A finished one that its parent has not
    collected yet (a zombie, state Z) does not count: on the owner's board (13-10-2026) the app's own finished
    steam -shutdown was one, and Steam seemed not to close. On Windows: steam.exe in the process list."""
    if WINDOWS:
        return _windows_running("steam.exe")
    for folder in proc.glob("[0-9]*"):
        try:
            if (folder / "comm").read_text().strip() != "steam":
                continue
            state = (folder / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        if state not in ("Z", "X"):
            return True
    return False


def game_mode() -> bool:
    """Bazzite's Game Mode: Steam's gamescope session."""
    return "gamescope" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def _steam_program() -> str:
    """The Steam client to run: steam (on PATH) on Linux, the steam.exe in Steam's folder on Windows."""
    if WINDOWS:
        folder = windows_steam()
        return str(folder / "steam.exe") if folder is not None else "steam.exe"
    return "steam"


def start_command() -> list[str]:
    if WINDOWS:
        return [_steam_program(), "-silent"]
    return ["bazzite-steam" if shutil.which("bazzite-steam") else "steam", "-silent"]


def shutdown_command() -> list[str]:
    return [_steam_program(), "-shutdown"]


def _run(command: list[str]) -> None:
    """Starts a Steam command in the background; a thread collects it when it ends, so it leaves no zombie."""
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    threading.Thread(target=process.wait, name="steam-command", daemon=True).start()


def with_steam_closed(change: Callable[[], None], run: Run = _run, running: Callable[[], bool] = steam_running,
                      timeout: float = SHUTDOWN_TIMEOUT, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Runs *change* (an edit of Steam's files) with Steam closed: closed first when it runs, and started again after.
    Returns whether Steam was restarted. Nothing is changed when Steam does not close."""
    was_running = running()
    if was_running:
        run(shutdown_command())
        waited = 0.0
        while running():
            if waited >= timeout:
                raise SteamError(f"Steam did not close within {timeout:g} seconds; nothing was changed.")
            sleep(0.5)
            waited += 0.5
    try:
        change()
    finally:
        if was_running:
            run(start_command())
    return was_running


def write_atomic(path: Path, data: bytes) -> None:
    """Writes through a temporary file beside it, so Steam never finds half a file; the file's mode is kept."""
    temporary = path.with_name(path.name + ".bc250-tmp")
    temporary.write_bytes(data)
    if path.exists():
        os.chmod(temporary, path.stat().st_mode & 0o7777)
    temporary.replace(path)


# --- The binary key-value format -------------------------------------------------------------------------------

def _cstring(data: bytes, at: int) -> tuple[str, int]:
    end = data.index(b"\0", at)
    return data[at:end].decode("utf-8", errors="replace"), end + 1


def _read_map(data: bytes, at: int) -> tuple[dict, int]:
    result: dict = {}
    while True:
        kind = data[at]
        at += 1
        if kind == END:
            return result, at
        name, at = _cstring(data, at)
        if kind == MAP:
            result[name], at = _read_map(data, at)
        elif kind == STRING:
            result[name], at = _cstring(data, at)
        elif kind == INT32:
            result[name] = struct.unpack_from("<i", data, at)[0]
            at += 4
        else:
            raise ShortcutError(f"shortcuts.vdf: an entry of an unknown kind ({kind}).")


def read_vdf(data: bytes) -> dict:
    """The file as nested dicts: maps, texts (str) and numbers (int)."""
    if not data:
        return {}
    try:
        result, _at = _read_map(data, 0)
    except (IndexError, ValueError, struct.error) as error:
        raise ShortcutError("shortcuts.vdf is damaged.") from error
    return result


def _write_map(values: dict) -> bytes:
    out = bytearray()
    for name, value in values.items():
        key = name.encode("utf-8") + b"\0"
        if isinstance(value, dict):
            out += bytes([MAP]) + key + _write_map(value)
        elif isinstance(value, bool) or isinstance(value, int):
            out += bytes([INT32]) + key + struct.pack("<i", int(value))
        else:
            out += bytes([STRING]) + key + str(value).encode("utf-8") + b"\0"
    return bytes(out + bytes([END]))


def write_vdf(values: dict) -> bytes:
    return _write_map(values)


# --- Shortcuts -------------------------------------------------------------------------------------------------

def appid(exe: str, name: str) -> int:
    """Steam's number for a non-Steam game (unsigned): the CRC-32 of its program and name, top bit set."""
    return zlib.crc32((exe + name).encode("utf-8")) | 0x80000000


def as_int32(value: int) -> int:
    return value - (1 << 32) if value >= 1 << 31 else value


def shortcut_icon(logo: Path) -> Path:
    """The icon file for a shortcut: for an app's WebP icon the PNG beside it (images/<id>-128.png), as Steam may not
    read WebP; any other picture as it is."""
    png = logo.with_name(f"{logo.stem}-128.png")
    return png if logo.suffix.lower() == ".webp" and png.is_file() else logo


def shortcut_entry(exe: str, name: str, start_dir: str, icon: str, launch_options: str, tags: Sequence[str]) -> dict:
    """A shortcut's fields, in the order Steam writes them. *exe* and *start_dir* as Steam keeps them, in quotes."""
    return {
        "appid": as_int32(appid(exe, name)),
        "AppName": name,
        "Exe": exe,
        "StartDir": start_dir,
        "icon": icon,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {str(n): tag for n, tag in enumerate(tags)},
    }


Match = Callable[[dict], bool]


def put_shortcut(values: dict, new: dict, ours: Match) -> dict:
    """The file's contents with *new* added, or replacing the shortcut *ours* recognizes (its play time kept); the
    other shortcuts stay, numbered 0, 1, ... in their order."""
    shortcuts = list(values.get("shortcuts", {}).values())
    for n, item in enumerate(shortcuts):
        if ours(item):
            shortcuts[n] = {**new, "LastPlayTime": field(item, "LastPlayTime", 0)}
            break
    else:
        shortcuts.append(new)
    return {**values, "shortcuts": {str(n): item for n, item in enumerate(shortcuts)}}


def remove_shortcut(values: dict, ours: Match) -> dict:
    shortcuts = [item for item in values.get("shortcuts", {}).values() if not ours(item)]
    return {**values, "shortcuts": {str(n): item for n, item in enumerate(shortcuts)}}


def shortcuts(steam: Path) -> list[dict]:
    """Every Steam user's non-Steam games; a file that cannot be read is left out."""
    found = []
    for config in user_folders(steam):
        path = config / "shortcuts.vdf"
        try:
            values = read_vdf(path.read_bytes()) if path.is_file() else {}
        except (OSError, ShortcutError):
            continue
        found += values.get("shortcuts", {}).values()
    return found


def has_shortcut(steam: Path, ours: Match) -> bool:
    return any(ours(item) for item in shortcuts(steam))


@dataclass(frozen=True)
class Change:
    """One shortcut to add (or bring up to date) or, with *remove*, to take out. *ours* recognizes the one made
    before, whatever its name now; *art* holds the images by their suffix in ART, as PNG bytes."""
    entry: dict
    ours: Match
    art: dict[str, bytes] = field(default_factory=dict)
    remove: bool = False

    @property
    def number(self) -> int:
        return self.entry["appid"] & 0xFFFFFFFF


def field(item: dict, name: str, default="") -> object:
    """A shortcut's field by name, whatever its case in the file: Steam has written AppName as appname and Exe as exe
    in some versions (29-10-2026), and keeps a shortcut's fields as it found them."""
    if name in item:
        return item[name]
    wanted = name.lower()
    return next((value for key, value in item.items() if key.lower() == wanted), default)


def _number(item: dict) -> int:
    """The number a shortcut's artwork is filed under: from its program and name, as appid() gives it."""
    return appid(str(field(item, "Exe")), str(field(item, "AppName")))


def write_shortcuts(steam: Path, changes: Sequence[Change]) -> list[int]:
    """For every Steam user: the shortcuts in shortcuts.vdf and their artwork in grid/, each file written once.
    A shortcut renamed gets a new number, so the artwork under its old one goes. Steam must be closed. Returns the
    shortcuts' appids."""
    folders = user_folders(steam)
    if not folders:
        raise ShortcutError("Steam has no users on this system yet.")
    numbers = {change.number for change in changes if not change.remove}
    for config in folders:
        path = config / "shortcuts.vdf"
        values = read_vdf(path.read_bytes()) if path.is_file() else {}
        renamed = set()
        for change in changes:
            if not change.remove:
                renamed |= {_number(item) for item in values.get("shortcuts", {}).values() if change.ours(item)}
            values = remove_shortcut(values, change.ours) if change.remove else put_shortcut(values, change.entry,
                                                                                            change.ours)
        write_atomic(path, write_vdf(values))
        grid = config / "grid"
        for number in renamed - numbers:
            for suffix in ART:
                (grid / f"{number}{suffix}.png").unlink(missing_ok=True)
        for change in changes:
            for suffix in ART:
                image = grid / f"{change.number}{suffix}.png"
                if change.remove:
                    image.unlink(missing_ok=True)
                elif suffix in change.art:
                    grid.mkdir(exist_ok=True)
                    write_atomic(image, change.art[suffix])
    return [change.number for change in changes]
