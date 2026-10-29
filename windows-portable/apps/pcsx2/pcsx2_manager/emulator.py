# SPDX-License-Identifier: GPL-3.0-or-later
"""The PCSX2 this version of the app installs: the Windows build of one stable release on GitHub, pinned, checked
against the SHA-256 this version of the app was tried with, as the BC250 suite's PCSX2 Manager pins its AppImage. A
newer stable comes with a new version of the app.

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-pcsx2\\emulator\\, one folder, in PCSX2's portable
mode (an empty portable.txt beside pcsx2-qt.exe): PCSX2 keeps its settings, the BIOS, the memory cards and the save
states in that folder too, not in Documents. So it is one folder rather than one per version: a newer PCSX2 is
unpacked over the older one, and what the player made stays. installed.json beside it records the version, the size
of pcsx2-qt.exe and the files the archive brought; Remove deletes only those files, so the BIOS, the memory cards
and the settings stay (install.ps1 --uninstall --purge removes the whole folder).

The archive is a .7z, unpacked by Windows' own tar.exe (bsdtar, libarchive: it reads 7z), so nothing else is needed.
PCSX2's own updater (the app keeps it off) would replace its program; when another build is there, the app says so
(replaced()), and Install puts the pinned release back."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import NO_WINDOW, suite_data

from . import APP_ID, SUITE, __version__

VERSION = "2.8.2"
TAG = f"v{VERSION}"
ASSET = f"pcsx2-{TAG}-windows-x64-Qt.7z"
SHA256 = "7dfc829ca1994cc1045ac49f05e39b6cf968b72e6a374c40e05c2a2b4ac200b4"
SIZE = 25_670_075                       # bytes
REPO = "PCSX2/pcsx2"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
EXE = "pcsx2-qt.exe"
MARKER = "portable.txt"                 # PCSX2 2.x: portable.txt or portable.ini beside the program
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


def record(home: Path) -> dict:
    """What install() recorded: {"version", "exe_size", "files"}; {} when nothing is installed."""
    try:
        data = json.loads((home / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def program(home: Path) -> Path:
    return home / EXE


def installed(home: Path) -> str:
    """The installed version, "" when PCSX2 is not installed (or its program is gone)."""
    version = str(record(home).get("version") or "")
    return version if version and program(home).is_file() else ""


def replaced(home: Path) -> bool:
    """PCSX2 replaced its program with another build (its own updater): pcsx2-qt.exe is not the size install()
    recorded."""
    size = record(home).get("exe_size")
    try:
        return bool(installed(home)) and program(home).stat().st_size != size
    except OSError:
        return False


def http_download(url: str, dest: Path, progress: Progress) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__}"})
    got = 0
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
        while chunk := response.read(CHUNK):
            out.write(chunk)
            got += len(chunk)
            progress(got)


def tar_extract(archive: Path, folder: Path) -> list[str]:
    """Unpack *archive* into *folder* with Windows' tar.exe (bsdtar reads 7z); the files it brought."""
    tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    if sys.platform != "win32" or not tar.is_file():
        tar = Path(shutil.which("bsdtar") or shutil.which("tar") or "tar")
    flags = NO_WINDOW if sys.platform == "win32" else 0
    listed = subprocess.run([str(tar), "-tf", str(archive)], capture_output=True, text=True, creationflags=flags)
    if listed.returncode != 0:
        raise EmulatorError(f"the archive could not be read: {listed.stderr.strip() or listed.returncode}")
    done = subprocess.run([str(tar), "-xf", str(archive), "-C", str(folder)], capture_output=True, text=True,
                          creationflags=flags)
    if done.returncode != 0:
        raise EmulatorError(f"the archive could not be unpacked: {done.stderr.strip() or done.returncode}")
    return [name.rstrip("/") for name in listed.stdout.splitlines() if name and not name.endswith("/")]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def install(home: Path, progress: Progress = lambda got: None, download: Download = http_download,
            extract: Extract = tar_extract, say: Callable[[str], None] = lambda text: None,
            url: str = URL, expected: str = SHA256) -> str:
    """Download the pinned release, check it, unpack it into *home* in portable mode and record it. Over an
    installed PCSX2 only its program files change. Returns the version installed."""
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
    (home / MARKER).write_text("", encoding="utf-8")
    data = {"version": VERSION, "exe_size": program(home).stat().st_size, "files": sorted(set(files))}
    (home / RECORD).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return VERSION


def remove(home: Path) -> None:
    """Delete PCSX2's program files (what the archive brought, the marker and the record), and the folders that
    are empty then; the BIOS, the memory cards, the save states and the settings stay."""
    files = record(home).get("files") or []
    for name in [*files, MARKER, RECORD]:
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
    """Whether this folder's PCSX2 runs (its pcsx2-qt.exe, not another one): Windows' process list and each
    pcsx2-qt.exe's own path. PCSX2 writes its settings back when it closes, so the app writes none meanwhile (the
    BC250 suite's rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (pcsx2-qt.exe); [] off Windows. A process whose
    path cannot be read (another user's) counts with ""."""
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


# A game alone and full screen, PCSX2's own window never shown (owner, 29-10-2026: "we don't want to see PCSX2 at
# all, the manager should take care of everything", the BC250 suite's rule): -nogui hides its main window, -batch
# ends PCSX2 when the game ends (back to the app or Steam), as PCSX2 2.8.2's -help says
GAME_ARGS = ("-nogui", "-fullscreen", "-batch")


def start(home: Path, game: Path) -> None:
    """The game in PCSX2, detached from this app, in PCSX2's own folder: pcsx2-qt.exe -nogui -fullscreen -batch --
    <game>. There is no way to PCSX2's own window."""
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0   # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(game_argv(home, game), cwd=str(home), creationflags=flags, close_fds=True, env=pcsx2_env())


def game_argv(home: Path, game: Path) -> list[str]:
    return [str(program(home)), *GAME_ARGS, "--", str(game)]


def pcsx2_env() -> dict[str, str]:
    """This process's environment without Qt's own variables: PCSX2 is a Qt program too, and the app's (its Qt
    plugin folder, a platform set for it) made PCSX2 stop with "no Qt platform plugin could be initialized" in its
    own message window (seen on the Ally, 29-10-2026)."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("QT_")}
