# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xenia this version of the app installs: the Windows build of one Xenia Canary build on GitHub, pinned and
checked against the SHA-256 this version of the app was tried with, the same build as the BC250 suite's Xenia Manager
pins (e6cd2e4). Xenia has no stable releases: Xenia Canary publishes a build for almost every change, a release of
xenia-canary/xenia-canary tagged with the commit it was built from. A newer Xenia comes with a new version of the app;
the Xenia pane says when a newer build is out (newer_release: a tag is a commit, not a number, so "newer" is a release
published after the pinned one), and the suite's weekly upstream check (windows-portable/tools/check_upstream.py)
checks only that the pinned file is still there (CADENCE: it would report a new build every week).

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-xenia\\emulator\\, one folder: Xenia on Windows is
portable by itself (app/xenia_main.cc in e6cd2e4: the portable cvar is true on Windows, so its storage root is the
program's folder; elsewhere it is so only with a portable.txt beside the program). Beside xenia_canary.exe it keeps
its settings (xenia-canary.config.toml), the content of your games and their saves (content\\), its caches and its log
(xenia_canary.log). A newer Xenia is unpacked over the older one and what the player made stays; installed.json beside
it records the version and the files the archive brought, and Remove deletes only those (install.ps1 --uninstall
--purge removes the whole folder).

The archive is a .7z (xenia_canary.exe and its LICENSE), which Windows' own tar (C:\\Windows\\System32\\tar.exe, bsdtar
built with liblzma on Windows 11) unpacks, as RPCS3 Manager's: no package for it. Xenia for Windows needs Microsoft's
Visual C++ runtime (vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll and msvcp140_atomic_wait.dll in System32:
xenia_canary.exe's imports), which Steam and most games bring; runtime_missing() says when it is not there."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from bc250_core.platform import suite_data
from bc250_core.updates import Fetch, ReleaseInfo, github_fetch

from . import APP_ID, SUITE, __version__

VERSION = "e6cd2e4"                     # the build's tag: the commit it was built from, the BC250 suite's pin
TAG = VERSION
COMMIT = "e6cd2e4bc998609ca25e24a24c8e32b66c5908ad"
PUBLISHED = "2026-10-20T19:30:12Z"      # when GitHub published it: a later release is a newer build
REPO = "xenia-canary/xenia-canary"
CADENCE = "daily"                       # for the weekly upstream check: a build for almost every change
ASSET = "xenia_canary_windows.7z"       # the same name in every build's release
SHA256 = "f60b6242c1a3b4ad787acc0a1bc85d44e45079150ac5c9ec0a30c5eff6ef0511"
SIZE = 3_677_214                        # bytes
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
EXE = "xenia_canary.exe"
CONFIG = "xenia-canary.config.toml"     # its settings, beside the program
LOG = "xenia_canary.log"                # its own log, beside the program, written anew at each start
RECORD = "installed.json"
TAR = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "tar.exe"
RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_atomic_wait.dll")
RUNTIME_PAGE = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
CHUNK = 1 << 20
TIMEOUT = 30
MB = 1_000_000                          # MB as the portal shows a download
NO_WINDOW = 0x08000000                  # CREATE_NO_WINDOW: tar runs without a console window of its own

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
    """The installed build ("e6cd2e4"), "" when Xenia is not installed (or its program is gone)."""
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
    """"" when Windows' tar can unpack Xenia's archive, else why not: it is not there (another system), or it was
    built without liblzma (Windows 10's), which the archive's LZMA needs."""
    if not TAR.is_file():
        return f"Windows' tar ({TAR}) is missing: it unpacks Xenia's archive."
    try:
        version = _tar("--version").stdout
    except OSError as error:
        return f"Windows' tar did not run: {error}"
    if "liblzma" not in version:
        return ("The tar of this Windows cannot unpack Xenia's archive (a .7z: it was built without liblzma); "
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
    """Download the pinned build, check it, unpack it into *home* and record it. Over an installed Xenia only its
    program changes; its settings, content and saves stay. Returns the build installed. Nothing is downloaded when the
    archive could not be unpacked afterwards (*unpacks* says why)."""
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
    """Delete Xenia's program (what the archive brought and the record), and the folders that are empty then; Xenia's
    own files, its settings, the content and the saves, stay."""
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
    """The Visual C++ runtime's files Xenia needs that are not in System32 (the names); [] when all are there, and
    off Windows."""
    if system32 is None:
        if sys.platform != "win32":
            return []
        system32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
    return [name for name in RUNTIME_DLLS if not (system32 / name).is_file()]


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """Xenia's newest build when it was published after the one this app brings (the BC250 app's); None when it was
    not, or when GitHub cannot be asked (nothing to say then). The builds are tagged with a commit, which core's
    latest_release does not read as a version, so the app reads the release itself."""
    fetch = fetch or github_fetch(f"{APP_ID}/{__version__}")
    try:
        data = fetch(f"https://api.github.com/repos/{REPO}/releases/latest")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name", "")).strip()
    published = str(data.get("published_at", ""))
    if not tag or tag == VERSION or published <= PUBLISHED:          # ISO 8601 in UTC: compared as text
        return None
    return ReleaseInfo(tag, tag, str(data.get("html_url") or f"https://github.com/{REPO}/releases/tag/{tag}"),
                       published[:10])


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def running(home: Path) -> bool:
    """Whether this folder's Xenia runs (its xenia_canary.exe, not another one): Windows' process list and each
    xenia_canary.exe's own path. Xenia writes its whole config file when it starts, so the app writes none meanwhile
    (the BC250 suite's rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (xenia_canary.exe); [] off Windows. A process whose
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


# A game full screen, as Steam's shortcuts start it (the app itself never does: owner, 29-10-2026, the games are played
# from Steam): Xenia's options take --name=value, and --fullscreen=true opens the game's window full screen, as the
# BC250 suite's Xenia Manager starts it; the game's file follows. A value given on the command line is not written into
# Xenia's config file. Xenia has no controller combination that ends a game: Steam's Exit game ends it.
GAME_ARGS = ("--fullscreen=true",)
