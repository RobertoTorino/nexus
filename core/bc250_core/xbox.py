# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xbox app's library on Windows (owner, 30-10-2026: the Windows Portable Suite in the Xbox menu, Xbox mode's
home): an app added there with My Library's + is kept in the Xbox app's own file, read here and added to the same way.

The file is the Xbox app's and undocumented. As the Xbox app 2611.1001.9.0 wrote it on the owner's Ally (30-10-2026):
LocalState\\ThirdPartyLibraries\\CustomLibraryManagement\\CustomLibraryManagement.manifest in its package folder, JSON:
{"version": 1, "provider": {"version": 1, "enabled": true}, "gameCache": {"version": 1, "{<guid>}": {"id": "{<guid>}",
"lastPlayedDate": "<ms>", "addedDate": "<ms>", "imagePath": "...", "title": "...", "installLocation": "<folder>\\\\",
"executableName": "<name>.exe", "executableCommandArgs": ""}}}. A file in another shape is never written (FormatError):
a later Xbox app may keep it otherwise. The file is backed up beside it first (.bak), an app already listed is not
added again, and the Xbox app is closed while it changes (it keeps the file in memory) and started again after.
Only the standard library here."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path

PACKAGE = "Microsoft.GamingApp_8wekyb3d8bbwe"
APP_ID = f"{PACKAGE}!Microsoft.Xbox.App"               # its Start-menu app, what starts it again
PROCESSES = ("XboxPcApp.exe", "XboxPcAppCE.exe", "XboxPcAppFT.exe")     # the Xbox app, and Xbox mode's
EMPTY = {"version": 1, "provider": {"version": 1, "enabled": True}, "gameCache": {"version": 1}}


class FormatError(Exception):
    """The Xbox app's file is not in the shape known: nothing is written."""


def package_folder(local: Path | None = None) -> Path:
    return (local or Path(os.environ.get("LOCALAPPDATA", ""))) / "Packages" / PACKAGE


def manifest_path(local: Path | None = None) -> Path:
    return (package_folder(local) / "LocalState" / "ThirdPartyLibraries" / "CustomLibraryManagement"
            / "CustomLibraryManagement.manifest")


def installed(local: Path | None = None) -> bool:
    """Whether the Xbox app is here (its package folder): without it there is no Xbox menu to add to."""
    return package_folder(local).is_dir()


def read(path: Path) -> dict:
    """The file as the Xbox app keeps it; EMPTY when there is none yet (or it is empty). FormatError otherwise."""
    text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    if not text.strip():
        return json.loads(json.dumps(EMPTY))
    try:
        data = json.loads(text)
    except ValueError as error:
        raise FormatError(f"the Xbox app's library file is not JSON: {error}") from error
    cache = data.get("gameCache") if isinstance(data, dict) else None
    if not isinstance(cache, dict):
        raise FormatError("the Xbox app's library file has no gameCache: a newer Xbox app keeps it otherwise")
    for key, entry in cache.items():
        if key != "version" and not (isinstance(entry, dict) and "executableName" in entry
                                     and "installLocation" in entry):
            raise FormatError(f"an entry of the Xbox app's library is not as known ({key})")
    return data


def _same(entry: dict, program: Path) -> bool:
    folder = os.path.normcase(os.path.normpath(str(entry.get("installLocation", ""))))
    return (folder == os.path.normcase(os.path.normpath(str(program.parent)))
            and str(entry.get("executableName", "")).lower() == program.name.lower())


def listed(program: Path, local: Path | None = None) -> bool:
    """Whether *program* is in the Xbox app's library (False also when its file is not as known)."""
    try:
        cache = read(manifest_path(local))["gameCache"]
    except (OSError, FormatError):
        return False
    return any(key != "version" and _same(entry, program) for key, entry in cache.items())


def entry(program: Path, title: str, image: Path | None = None, now: float | None = None,
          new_id: Callable[[], str] = lambda: f"{{{uuid.uuid4()}}}") -> dict:
    """The library entry of *program*, as the Xbox app writes one it was given."""
    stamp = str(int((time.time() if now is None else now) * 1000))
    key = new_id()
    return {"id": key, "lastPlayedDate": stamp, "addedDate": stamp, "imagePath": str(image or ""),
            "title": title, "installLocation": str(program.parent) + "\\", "executableName": program.name,
            "executableCommandArgs": ""}


def add(program: Path, title: str, image: Path | None = None, local: Path | None = None,
        closed: Callable[[Callable[[], None]], None] | None = None, now: float | None = None) -> bool:
    """*program* added to the Xbox app's library as *title*: False when it is there already (nothing written).
    The file is backed up (.bak) and written with the Xbox app closed (*closed*: with_xbox_closed). FormatError
    when the file is not as known; OSError when it cannot be written."""
    path = manifest_path(local)
    data = read(path)                                   # FormatError before anything is closed or written
    if any(key != "version" and _same(item, program) for key, item in data["gameCache"].items()):
        return False
    new = entry(program, title, image, now)

    def change() -> None:
        current = read(path)                            # as the Xbox app left it once closed
        current["gameCache"][new["id"]] = new
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            backup = path.with_name(path.name + ".bak")
            backup.write_bytes(path.read_bytes())
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8", newline="")
        os.replace(part, path)
    (closed or with_xbox_closed)(change)
    return True


def _running() -> list[int]:
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    names = {name.lower() for name in PROCESSES}
    found = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].strip('"').lower() in names and parts[1].isdigit():
            found.append(int(parts[1]))
    return found


def with_xbox_closed(change: Callable[[], None], running: Callable[[], list[int]] = _running,
                     end: Callable[[int], None] = lambda pid: subprocess.run(
                         ["taskkill", "/pid", str(pid), "/f"], capture_output=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                     start: Callable[[], None] = lambda: subprocess.Popen(
                         ["explorer.exe", f"shell:AppsFolder\\{APP_ID}"]),
                     sleep: Callable[[float], None] = time.sleep) -> None:
    """*change* with the Xbox app closed: ended when it runs (it writes its library back when it ends), started
    again after."""
    was = running()
    for pid in was:
        end(pid)
    for _ in range(40):
        if not running():
            break
        sleep(0.25)
    try:
        change()
    finally:
        if was:
            start()
