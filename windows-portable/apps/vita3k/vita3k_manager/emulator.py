# SPDX-License-Identifier: GPL-3.0-or-later
"""The Vita3K this version of the app installs: the Windows build of one of Vita3K's builds on GitHub, pinned and
checked against the SHA-256 this version of the app was tried with, the same build as the BC250 suite's Vita3K Manager
pins (4186). Vita3K has no stable releases: it publishes a build for every change, almost daily, each one kept in
Vita3K/Vita3K-builds (a release per build, tagged with its number). A newer Vita3K comes with a new version of the app;
the Vita3K pane says when a newer build is out (newer_release), and the suite's weekly upstream check
(windows-portable/tools/check_upstream.py) checks only that the pinned file is still there (CADENCE: it would report
a new build every week).

It goes to %LOCALAPPDATA%\\windows-portable-suite\\windows-portable-vita3k\\emulator\\, one folder, in Vita3K's
portable mode: Vita3K keeps everything in a folder named portable beside Vita3K.exe when there is one
(app::init_paths in build 4186; without one, its settings and log beside the program and the PS Vita's storage in
%APPDATA%\\Vita3K\\Vita3K), so the app makes portable\\ at install. portable\\ holds its settings (config.yml), its log
(vita3k.log) and the PS Vita's storage, its "Vita FS", in portable\\fs\\ (in portable mode config.yml's pref-path
does not move it): the firmware, the installed games and the saves. A newer Vita3K is unpacked over the older one
and what the player made stays; installed.json beside it records the version and the files the archive brought, and
Remove deletes only those (install.ps1 --uninstall --purge removes the whole folder).

The archive is a .7z, which Windows' own tar (C:\\Windows\\System32\\tar.exe, bsdtar built with liblzma on Windows 11)
unpacks, as RPCS3 Manager's: no package for it. Vita3K for Windows needs Microsoft's Visual C++ runtime
(vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll and msvcp140_atomic_wait.dll in System32: Vita3K.exe's imports),
which Steam and most games bring; runtime_missing() says when it is not there.

Vita3K.exe is a program without a console: what it did is read from the files it wrote (userdata). It installs a
firmware file (--firmware) and a .pkg with its license key (--pkg, --zrif) and quits, without a window
(run_quiet). A .vpk, a .zip or a dumped game folder it installs only when it is started with the file, and then it
starts the game; the app starts it with its plain SDL window and closes it as soon as that window opens, after the
install (owner, 29-10-2026: install_content)."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from bc250_core.platform import suite_data
from bc250_core.updates import Fetch, ReleaseInfo, github_fetch

from . import APP_ID, SUITE, __version__

VERSION = "4186"                        # Vita3K's build number, counted over its whole history: the BC250 suite's pin
TAG = VERSION                           # each build's release is tagged with its number alone
SEMVER = "0.2.1"                        # what the build calls itself (v0.2.1 4186-f0273e4c)
COMMIT = "f0273e4cd9b860ea77c44c73d9f5c5b1ed5fa8ab"
REPO = "Vita3K/Vita3K-builds"           # a release per build; Vita3K/Vita3K has only the rolling "continuous"
CADENCE = "daily"                       # for the weekly upstream check: a build for every change
ASSET = "vita3k-4186-f0273e4c-windows-x86_64.7z"
SHA256 = "a26120e62aaad28df8502b8de0fd143564a0e1bc10582dc215746229b980adc4"
SIZE = 24_522_324                       # bytes
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
EXE = "Vita3K.exe"
PORTABLE = "portable"                   # Vita3K's portable folder, beside the program
RECORD = "installed.json"
TAR = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "tar.exe"
RUNTIME_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_atomic_wait.dll")
RUNTIME_PAGE = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
CHUNK = 1 << 20
TIMEOUT = 30
MB = 1_000_000                          # MB as the portal shows a download
NO_WINDOW = 0x08000000                  # CREATE_NO_WINDOW: tar runs without a console window of its own
INSTALL_TIMEOUT = 900                   # seconds for Vita3K to install a firmware file or a game
WATCH_S = 0.2                           # how often install_content looks for Vita3K's window

Progress = Callable[[int], None]                        # bytes so far
Download = Callable[[str, Path, Progress], None]
Extract = Callable[[Path, Path], list[str]]             # archive, folder -> the files it brought (relative, "/")


class EmulatorError(Exception):
    pass


def emulator_home() -> Path:
    return suite_data(SUITE) / APP_ID / "emulator"


def portable_folder(home: Path) -> Path:
    """Vita3K's own folder: its settings, its log and the PS Vita's storage."""
    return home / PORTABLE


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
    """The installed build ("4186"), "" when Vita3K is not installed (or its program is gone)."""
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
    """"" when Windows' tar can unpack Vita3K's archive, else why not: it is not there (another system), or it was
    built without liblzma (Windows 10's), which the archive's LZMA needs."""
    if not TAR.is_file():
        return f"Windows' tar ({TAR}) is missing: it unpacks Vita3K's archive."
    try:
        version = _tar("--version").stdout
    except OSError as error:
        return f"Windows' tar did not run: {error}"
    if "liblzma" not in version:
        return ("The tar of this Windows cannot unpack Vita3K's archive (a .7z: it was built without liblzma); "
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
    """Download the pinned build, check it, unpack it into *home* with Vita3K's portable folder beside it and record
    it. Over an installed Vita3K only its program files change; its folder, with the firmware, the games and the
    saves, stays. Returns the build installed. Nothing is downloaded when the archive could not be unpacked afterwards
    (*unpacks* says why)."""
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
    portable_folder(home).mkdir(exist_ok=True)
    data = {"version": VERSION, "files": sorted(set(files))}
    (home / RECORD).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return VERSION


def remove(home: Path) -> None:
    """Delete Vita3K's program files (what the archive brought and the record), and the folders that are empty then;
    Vita3K's folder, with its settings, the firmware, the games and the saves, stays."""
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
    """The Visual C++ runtime's files Vita3K needs that are not in System32 (the names); [] when all are there, and
    off Windows."""
    if system32 is None:
        if sys.platform != "win32":
            return []
        system32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
    return [name for name in RUNTIME_DLLS if not (system32 / name).is_file()]


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """Vita3K's newest build when it is newer than the one this app brings (the BC250 app's); None when it is not, or
    when GitHub cannot be asked (nothing to say then). The builds are tagged with their number alone, which core's
    latest_release does not read as a version, so the app reads the tag itself."""
    fetch = fetch or github_fetch(f"{APP_ID}/{__version__}")
    try:
        data = fetch(f"https://api.github.com/repos/{REPO}/releases/latest")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name", "")).strip()
    if not tag.isdigit() or int(tag) <= int(VERSION):
        return None
    return ReleaseInfo(tag, tag, str(data.get("html_url") or f"https://github.com/{REPO}/releases/tag/{tag}"),
                       str(data.get("published_at", ""))[:10])


def command(home: Path, *args: str) -> list[str]:
    """Vita3K's program with *args*: the Steam shortcuts' line, and the app's installs."""
    return [str(program(home)), *args]


def run_quiet(home: Path, *args: str, timeout: float = INSTALL_TIMEOUT) -> int:
    """Vita3K for an install it does without a window and then quits (--firmware; --pkg with --zrif); its exit code,
    which says nothing of the outcome: the caller reads the files it wrote (userdata). OSError when it did not start,
    subprocess.TimeoutExpired when it did not end in time."""
    return subprocess.run(command(home, *args), cwd=home, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=timeout, check=False).returncode


def install_content(home: Path, content: Path, timeout: float = INSTALL_TIMEOUT,
                    has_window: Callable[[int], bool] | None = None,
                    popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> bool:
    """A .vpk, a .zip or a dumped game folder installed by Vita3K: started with the file and its SDL frontend, Vita3K
    installs it, then opens its window to start the game (main.cpp in build 4186: --frontend sdl, the content path,
    then the game it installed). The app closes Vita3K as soon as a window of it shows, so the game is not started
    (owner, 29-10-2026); an update or extra content, which starts no game, ends Vita3K by itself. Whether the app
    closed it; the caller reads what was installed from Vita3K's storage (userdata.content_written). OSError when it
    did not start, EmulatorError when it did not end in time."""
    has_window = has_window or window_shows
    process = popen(command(home, "--frontend", "sdl", str(content)), cwd=home, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if has_window(process.pid):
                process.kill()
                process.wait(30)
                return True
            if time.monotonic() > end:
                raise EmulatorError(f"Vita3K did not finish installing {content.name} in {timeout // 60:.0f} "
                                    "minutes")
            time.sleep(WATCH_S)
    finally:
        if process.poll() is None:
            process.kill()
    return False


def window_shows(pid: int) -> bool:
    """Whether the process *pid* has a visible window (Windows' list of top-level windows); False off Windows."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    found = []
    owner = ctypes.c_ulong()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)  # type: ignore[attr-defined]
    def each(hwnd, _param):
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(each, None)
    return bool(found)


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def running(home: Path) -> bool:
    """Whether this folder's Vita3K runs (its Vita3K.exe, not another one): Windows' process list and each
    Vita3K.exe's own path. Vita3K writes its config.yml when it starts and from its own settings, so the app writes
    none meanwhile (the BC250 suite's rule)."""
    target = os.path.normcase(str(program(home)))
    return any(os.path.normcase(path) == target for path in processes(EXE))


def processes(name: str) -> list[str]:
    """The programs' paths of the running processes named *name* (Vita3K.exe); [] off Windows. A process whose path
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


# A game alone and full screen, as the app's play mode starts it for Steam's shortcuts (owner, 29-10-2026, the games
# are played from Steam; 30-10-2026, the play mode, and without Steam the app): -r names the installed game by its
# title ID, and Vita3K's own frontend (owner, 29-10-2026: not the SDL frontend, whose window never goes full screen on
# Windows) boots it at once, full screen as config.yml's boot-apps-full-screen says (userdata.prepare). View, LB and
# RB held close Vita3K (core's play), as Steam's Exit game ends it; Vita3K's own pause menu (its PS button) has Exit, which
# ends the game and leaves Vita3K's window.
GAME_ARGS = ("-r",)
