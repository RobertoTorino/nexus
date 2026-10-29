# SPDX-License-Identifier: GPL-3.0-or-later
"""The PPSSPP this version of the app installs: the Windows build of one release on GitHub, pinned, checked against
the SHA-256 this version of the app was tried with, as the BC250 suite's PPSSPP Manager pins its AppImage. A newer
PPSSPP comes with a new version of the app.

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-ppsspp\\emulator\\, one folder, in PPSSPP's portable
mode: without an installed.txt beside PPSSPPWindows64.exe, PPSSPP keeps its memory stick in memstick\\ beside it
(Windows\\main.cpp, InitMemstickDirectory), with its settings, the saves, the save states and the memory stick games,
not in Documents. So it is one folder rather than one per version: a newer PPSSPP is unpacked over the older one, and
what the player made stays. installed.json beside it records the version and the files the archive brought; Remove
deletes only those files, so the memory stick stays (install.ps1 --uninstall --purge removes the whole folder).

The archive is a .zip with the program and its assets\\ at its root, unpacked with Python's zipfile. PPSSPP on Windows
does not update itself: it only says on its own main screen that a newer release is out, a screen the app never
shows (ppsspp_settings turns the notice off as well)."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from bc250_core.platform import suite_data

from . import APP_ID, SUITE, __version__

VERSION = "1.20.4"
TAG = f"v{VERSION}"
ASSET = f"PPSSPP-{TAG}-Windows-x64.zip"
SHA256 = "fbc9cd2f5131b159a92424e5c458c35ce43ba603cdded64dfc98e4bd4f17ff93"
SIZE = 20_390_334                       # bytes
REPO = "hrydgard/ppsspp"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
EXE = "PPSSPPWindows64.exe"
PORTABLE_OFF = "installed.txt"          # beside the program, it would move the memory stick to Documents
MEMSTICK = "memstick"
RECORD = "installed.json"
CHUNK = 1 << 20
TIMEOUT = 30
MB = 1_000_000                          # MB as the portal shows a download

Progress = Callable[[int], None]                        # bytes so far
Download = Callable[[str, Path, Progress], None]
Extract = Callable[[Path, Path], list[str]]             # archive, folder -> the files it brought (relative, "/")


class EmulatorError(Exception):
    pass


def emulator_home() -> Path:
    return suite_data(SUITE) / APP_ID / "emulator"


def memstick(home: Path) -> Path:
    """PPSSPP's memory stick in portable mode: its settings, saves and memory stick games."""
    return home / MEMSTICK


def record(home: Path) -> dict:
    """What install() recorded: {"version", "files"}; {} when nothing is installed."""
    try:
        data = json.loads((home / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def program(home: Path) -> Path:
    return home / EXE


def installed(home: Path) -> str:
    """The installed version, "" when PPSSPP is not installed (or its program is gone)."""
    version = str(record(home).get("version") or "")
    return version if version and program(home).is_file() else ""


def http_download(url: str, dest: Path, progress: Progress) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__}"})
    got = 0
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
        while chunk := response.read(CHUNK):
            out.write(chunk)
            got += len(chunk)
            progress(got)


def zip_extract(archive: Path, folder: Path) -> list[str]:
    """Unpack *archive* into *folder*; the files it brought. A name that would land outside the folder (an absolute
    path, "..") stops it before anything is written."""
    try:
        with zipfile.ZipFile(archive) as zf:
            names = [info.filename for info in zf.infolist() if not info.is_dir()]
            for name in names:
                parts = PurePosixPath(name.replace("\\", "/")).parts
                if not parts or parts[0] in ("/", "") or ".." in parts or ":" in parts[0]:
                    raise EmulatorError(f"the archive holds a file outside its folder: {name}")
            zf.extractall(folder)
    except (zipfile.BadZipFile, EOFError) as error:
        raise EmulatorError(f"the archive could not be read: {error}") from error
    return names


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def install(home: Path, progress: Progress = lambda got: None, download: Download = http_download,
            extract: Extract = zip_extract, say: Callable[[str], None] = lambda text: None,
            url: str = URL, expected: str = SHA256) -> str:
    """Download the pinned release, check it, unpack it into *home* in portable mode and record it. Over an
    installed PPSSPP only its program files change; the memory stick stays. Returns the version installed."""
    home.mkdir(parents=True, exist_ok=True)
    part = home.parent / f"{ASSET}.part"
    try:
        download(url, part, progress)
        say("Checking the download…")
        if sha256(part) != expected:
            raise EmulatorError(f"{ASSET} is not the release this app was tried with (its SHA-256 differs)")
        say("Unpacking…")
        files = extract(part, home)
    except OSError as error:
        raise EmulatorError(str(getattr(error, "reason", "") or error) or type(error).__name__) from error
    finally:
        part.unlink(missing_ok=True)
    if not program(home).is_file():
        raise EmulatorError(f"the release has no {EXE}")
    (home / PORTABLE_OFF).unlink(missing_ok=True)
    memstick(home).mkdir(exist_ok=True)
    data = {"version": VERSION, "files": sorted(set(files))}
    (home / RECORD).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return VERSION


def remove(home: Path) -> None:
    """Delete PPSSPP's program files (what the archive brought and the record), and the folders that are empty then;
    the memory stick, with the settings, the saves and the save states, stays."""
    files = record(home).get("files") or []
    for name in [*files, RECORD]:
        path = home / name
        if path.is_file():
            path.unlink()
    for folder in sorted((p for p in home.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            folder.rmdir()                              # only when empty
        except OSError:
            pass
    try:
        home.rmdir()
    except OSError:
        pass


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def running(home: Path) -> bool:
    """Whether this folder's PPSSPP runs (its PPSSPPWindows64.exe, not another one): Windows' process list and each
    PPSSPPWindows64.exe's own path. PPSSPP writes its settings back when it closes, so the app writes none meanwhile
    (the BC250 suite's rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (PPSSPPWindows64.exe); [] off Windows. A process
    whose path cannot be read (another user's) counts with ""."""
    if sys.platform != "win32":
        return []
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.OpenProcess.restype = ctypes.c_void_p
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)    # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    found = []
    try:
        entry = _Entry()
        entry.size = ctypes.sizeof(_Entry)
        more = k32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while more:
            if entry.exe.lower() == name.lower():
                path = ""
                handle = k32.OpenProcess(0x1000, False, entry.pid)     # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    buffer, size = ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
                    if k32.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, buffer, ctypes.byref(size)):
                        path = buffer.value
                    k32.CloseHandle(ctypes.c_void_p(handle))
                found.append(path)
            more = k32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snapshot))
    return found


# A game alone and full screen, PPSSPP's own window never shown (the suite's rule, as PCSX2 Manager's), as Steam's
# shortcuts start it (the app itself never does: owner, 29-10-2026, the games are played from Steam): with a game on
# its command line PPSSPP goes straight to the game, and --pause-menu-exit makes its pause menu's Exit end PPSSPP, as
# the BC250 suite's PPSSPP Manager starts it (UI\NativeApp.cpp)
GAME_ARGS = ("--fullscreen", "--pause-menu-exit")
