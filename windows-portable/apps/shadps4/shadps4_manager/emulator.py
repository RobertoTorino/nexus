# SPDX-License-Identifier: GPL-3.0-or-later
"""The shadPS4 this version of the app installs: the Windows build of a tagged release on GitHub (shadPS4.exe alone in
a zip), pinned and checked against the SHA-256 this version of the app was tried with, the same release as the BC250
suite's shadPS4 Manager pins. A newer shadPS4 comes with a new version of the app; the suite's weekly upstream check
(windows-portable/tools/check_upstream.py) says when one is out.

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-shadps4\\emulator\\, one folder, in shadPS4's
portable mode: shadPS4 keeps its files in a folder named user in the folder it starts in (common/path_util.cpp in
0.20.0; without one, in %APPDATA%\\shadPS4), so the app makes user\\ beside shadPS4.exe and the Steam shortcuts start
shadPS4 there. user\\ holds its settings (config.json, users.json), the saves, the system modules (sys_modules\\), the
quit hotkeys (input_config\\global.ini), the play time (play_time.txt) and its log (log\\shad_log.txt). A newer
shadPS4 replaces shadPS4.exe and what the player made stays; installed.json beside it records the version and the
files the archive brought, and Remove deletes only those (install.ps1 --uninstall --purge removes the whole folder).

shadPS4 for Windows needs Microsoft's Visual C++ runtime (vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll and
msvcp140_atomic_wait.dll in System32: shadPS4.exe's imports), which Steam and most games bring; runtime_missing() says
when it is not there."""

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

VERSION = "0.20.0"
TAG = f"v.{VERSION}"                    # shadPS4 tags its releases "v.0.20.0"
ASSET = "shadps4-win64-sdl-2026-0.20.0.zip"
SHA256 = "d5cdc55c57e85e5fe44ff867b420246dc832077356d943ccc43c5d950c878b37"
SIZE = 31_574_011                       # bytes
REPO = "shadps4-emu/shadPS4"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
EXE = "shadPS4.exe"
USER = "user"                           # shadPS4's portable folder, beside the program
RECORD = "installed.json"
RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_atomic_wait.dll")
RUNTIME_PAGE = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
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


def user_folder(home: Path) -> Path:
    """shadPS4's own folder: its settings, saves, system modules and log."""
    return home / USER


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
    """The installed version ("0.20.0"), "" when shadPS4 is not installed (or its program is gone)."""
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
    """Download the pinned release, check it, unpack it into *home* with shadPS4's portable folder beside it and
    record it. Over an installed shadPS4 only its program changes; its folder stays. Returns the version installed."""
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
    user_folder(home).mkdir(exist_ok=True)
    data = {"version": VERSION, "files": sorted(set(files))}
    (home / RECORD).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return VERSION


def remove(home: Path) -> None:
    """Delete shadPS4's program (what the archive brought and the record), and the folders that are empty then;
    shadPS4's folder, with its settings, the saves and the system modules, stays."""
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


def runtime_missing(system32: Path | None = None) -> list[str]:
    """The Visual C++ runtime's files shadPS4 needs that are not in System32 (the names); [] when all are there, and
    off Windows."""
    if system32 is None:
        if sys.platform != "win32":
            return []
        system32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
    return [name for name in RUNTIME_DLLS if not (system32 / name).is_file()]


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def running(home: Path) -> bool:
    """Whether this folder's shadPS4 runs (its shadPS4.exe, not another one): Windows' process list and each
    shadPS4.exe's own path. shadPS4 writes its settings back when it ends, so the app writes none meanwhile (the
    BC250 suite's rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (shadPS4.exe); [] off Windows. A process whose path
    cannot be read (another user's) counts with ""."""
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


# A game full screen, shadPS4's own window (Big Picture) never shown (the suite's rule, as PCSX2 Manager's), as
# Steam's shortcuts start it (the app itself never does: owner, 29-10-2026, the games are played from Steam): -f true
# gives the game the whole screen, -g names the game's eboot.bin, as the BC250 suite's shadPS4 Manager starts it.
# shadPS4 ends when the game ends.
GAME_ARGS = ("-f", "true", "-g")
