# SPDX-License-Identifier: GPL-3.0-or-later
"""The RPCS3 this version of the app installs: the Windows build of one of RPCS3's builds on GitHub, pinned, checked
against the SHA-256 this version of the app was tried with, as the BC250 suite's RPCS3 Manager pins its AppImage.
RPCS3 has no stable releases: it publishes a build for every change (RPCS3/rpcs3-binaries-win, one release
"build-<commit>" each) and now and then tags a version as a landmark (v0.0.43, in RPCS3/rpcs3). The app pins the
build of a landmark, the same build as the BC250 suite's app, so the launch line and the advice in the app are tried
with the build they are for. A newer RPCS3 comes with a new version of the app; the suite's weekly upstream check
(windows-portable/tools/check_upstream.py) says when a newer landmark is out.

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-rpcs3\\emulator\\, one folder: RPCS3 on Windows
keeps everything beside rpcs3.exe (Utilities/File.cpp, fs::get_config_dir: the program's folder, unless a portable\\
folder is beside it, which the app never makes): its settings in config\\ (config.yml, vfs.yml, games.yml, the
input_configs and custom_configs folders), the PS3's drives dev_hdd0\\ (the installed games and the saves) and
dev_flash\\ (the firmware), its GUI settings in GuiConfigs\\ and its log in log\\RPCS3.log. So a newer RPCS3 is
unpacked over the older one and what the player made stays; installed.json beside it records the version and the
files the archive brought, and Remove deletes only those (install.ps1 --uninstall --purge removes the whole folder).

The archive is a .7z (LZMA2 behind the BCJ2 filter, which Python's lzma does not read): Windows' own tar
(C:\\Windows\\System32\\tar.exe, bsdtar built with liblzma on Windows 11) unpacks it, so the app needs no package for
it; its exit code and its listing are the same in every language. RPCS3 for Windows needs Microsoft's Visual C++
runtime (vcruntime140.dll, vcruntime140_1.dll and msvcp140.dll in System32), which Steam and most games bring;
runtime_missing() says when it is not there. RPCS3 refuses to run from a temporary folder (%TEMP%); the suite's
folder is not one."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from bc250_core.platform import suite_data

from . import APP_ID, SUITE, __version__

LANDMARK = "0.0.43"                     # the tagged version (v0.0.43) the build is of
BUILD = 20395                           # RPCS3's build number, counted over its whole history: the BC250 suite's pin
VERSION = f"{LANDMARK}-{BUILD}"         # as RPCS3 names its builds
COMMIT = "46b7fb670b280d08036c7670270b713daef912c2"
REPO = "RPCS3/rpcs3"                    # the landmarks: what the weekly upstream check compares the pin with
TAG = f"v{LANDMARK}"
BUILDS = "RPCS3/rpcs3-binaries-win"     # the Windows builds, one release each: where the archive is
BUILD_TAG = f"build-{COMMIT}"
ASSET = "rpcs3-v0.0.43-20395-46b7fb67_win64_msvc.7z"
SHA256 = "96713bbac660a512e487224f517dcf70ee7c346e2ce52f31a7388918536ab228"
SIZE = 36_964_258                       # bytes
URL = f"https://github.com/{BUILDS}/releases/download/{BUILD_TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
EXE = "rpcs3.exe"
RECORD = "installed.json"
TAR = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "tar.exe"
RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
RUNTIME_PAGE = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
CHUNK = 1 << 20
TIMEOUT = 30
MB = 1_000_000                          # MB as the portal shows a download
NO_WINDOW = 0x08000000                  # CREATE_NO_WINDOW: tar and RPCS3 run without a console window of their own

Progress = Callable[[int], None]                        # bytes so far
Download = Callable[[str, Path, Progress], None]
Extract = Callable[[Path, Path], list[str]]             # archive, folder -> the files it brought (relative, "/")


class EmulatorError(Exception):
    pass


def emulator_home() -> Path:
    return suite_data(SUITE) / APP_ID / "emulator"


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
    """The installed build ("0.0.43-20395"), "" when RPCS3 is not installed (or its program is gone)."""
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


def _tar(*args: str) -> subprocess.CompletedProcess:
    flags = NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run([str(TAR), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, creationflags=flags, check=False)


def tar_unpacks_7z() -> str:
    """"" when Windows' tar can unpack RPCS3's archive, else why not: it is not there (another system), or it was built
    without liblzma (Windows 10's), which the archive's LZMA2 needs."""
    if not TAR.is_file():
        return f"Windows' tar ({TAR}) is missing: it unpacks RPCS3's archive."
    try:
        version = _tar("--version").stdout
    except OSError as error:
        return f"Windows' tar did not run: {error}"
    if "liblzma" not in version:
        return ("The tar of this Windows cannot unpack RPCS3's archive (a .7z: it was built without liblzma); "
                "Windows 11 brings one that can.")
    return ""


def _check_names(names: list[str]) -> None:
    for name in names:
        parts = PurePosixPath(name.replace("\\", "/")).parts
        if not parts or parts[0] in ("/", "") or ".." in parts or ":" in parts[0]:
            raise EmulatorError(f"the archive holds a file outside its folder: {name}")


def tar_extract(archive: Path, folder: Path) -> list[str]:
    """Unpack the .7z into *folder* with Windows' tar; the files it brought. A name that would land outside the folder
    (an absolute path, "..") stops it before anything is written."""
    listing = _tar("-tf", str(archive))
    if listing.returncode != 0:
        raise EmulatorError(f"the archive could not be read: {listing.stderr.strip() or 'tar failed'}")
    entries = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    names = [name for name in entries if not name.endswith("/")]
    _check_names(entries)
    folder.mkdir(parents=True, exist_ok=True)
    done = _tar("-xf", str(archive), "-C", str(folder))
    if done.returncode != 0:
        raise EmulatorError(f"the archive could not be unpacked: {done.stderr.strip() or 'tar failed'}")
    return names


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def install(home: Path, progress: Progress = lambda got: None, download: Download = http_download,
            extract: Extract = tar_extract, say: Callable[[str], None] = lambda text: None,
            url: str = URL, expected: str = SHA256, unpacks: Callable[[], str] = tar_unpacks_7z) -> str:
    """Download the pinned build, check it, unpack it into *home* and record it. Over an installed RPCS3 only its
    program files change; its settings, firmware, saves and installed games stay. Returns the build installed.
    Nothing is downloaded when the archive could not be unpacked afterwards (*unpacks* says why)."""
    reason = unpacks()
    if reason:
        raise EmulatorError(reason)
    home.mkdir(parents=True, exist_ok=True)
    part = home.parent / f"{ASSET}.part"
    try:
        download(url, part, progress)
        say("Checking the download…")
        if sha256(part) != expected:
            raise EmulatorError(f"{ASSET} is not the build this app was tried with (its SHA-256 differs)")
        say("Unpacking…")
        files = extract(part, home)
    except OSError as error:
        raise EmulatorError(str(getattr(error, "reason", "") or error) or type(error).__name__) from error
    finally:
        part.unlink(missing_ok=True)
    if not program(home).is_file():
        raise EmulatorError(f"the archive has no {EXE}")
    data = {"version": VERSION, "files": sorted(set(files))}
    (home / RECORD).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return VERSION


def remove(home: Path) -> None:
    """Delete RPCS3's program files (what the archive brought and the record), and the folders that are empty then;
    RPCS3's settings, firmware, saves and installed games stay."""
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
    """The Visual C++ runtime's files RPCS3 needs that are not in System32 (the names); [] when all are there, and
    off Windows."""
    if system32 is None:
        if sys.platform != "win32":
            return []
        system32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
    return [name for name in RUNTIME_DLLS if not (system32 / name).is_file()]


def command(home: Path, *args: str) -> list[str]:
    """RPCS3's program with *args*: the Steam shortcuts' line, and the app's headless runs."""
    return [str(program(home)), *args]


def run_headless(home: Path, *args: str) -> int:
    """RPCS3 without any window (--headless), for an install of the firmware or a package; its exit code, which says
    nothing of the outcome (this build ends a headless run with a fault of its own once the work is done): the
    caller reads RPCS3's log (userdata). OSError when it did not start."""
    flags = NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(command(home, "--headless", *args), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, creationflags=flags, check=False).returncode


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def running(home: Path) -> bool:
    """Whether this folder's RPCS3 runs (its rpcs3.exe, not another one): Windows' process list and each rpcs3.exe's
    own path. RPCS3 writes its settings back when it closes, so the app writes none meanwhile (the BC250 suite's
    rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (rpcs3.exe); [] off Windows. A process whose path
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


# A game alone and full screen, RPCS3's own window never shown (the suite's rule, as PCSX2 Manager's), as Steam's
# shortcuts start it (the app itself never does: owner, 29-10-2026, the games are played from Steam): --no-gui boots
# the game given without RPCS3's window and ends RPCS3 when the game ends, --fullscreen (only with it) gives the game
# the whole screen, as the BC250 suite's RPCS3 Manager starts it
GAME_ARGS = ("--no-gui", "--fullscreen")
