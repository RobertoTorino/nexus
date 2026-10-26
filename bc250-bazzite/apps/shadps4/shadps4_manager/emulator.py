# SPDX-License-Identifier: GPL-3.0-or-later
"""The shadPS4 this version of the app installs: the Linux build of a tagged release on GitHub (an AppImage in a
zip), pinned and checked against the SHA-256 this version of the app was tried with. A newer stable comes with a new
version of the app, so the launch line and the advice in the app are tried with the release they are for; the app
says when there is a newer one. (The nightly channel went with the window rebuilt on PCSX2 Manager's, owner,
24-10-2026: the managers install the build they were tried with.)

It goes to ~/.local/share/bc250-shadps4-manager/emulator/<version>/, with "current" pointing to it. The run wrapper
(~/.local/bin/bc250-shadps4-run) starts "current", so the Steam shortcuts keep working when the version changes."""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import data_home
from bc250_core.updates import Fetch, ReleaseInfo, latest_release, version_tuple

from . import APP_ID, __version__

VERSION = "0.20.0"
TAG = "v.0.20.0"                        # shadPS4 tags its releases "v.0.20.0"
ASSET = "shadps4-linux-sdl-0.20.0.zip"
SHA256 = "be25d0324cd7b74068d32cdb66fa1b7b1e7bb499b062be51c7006d27d41d4255"
SIZE_MB = 31                            # the zip, for the question before downloading
MEMBER = "Shadps4-sdl.AppImage"         # the only file in the zip
REPO = "shadps4-emu/shadPS4"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
CHUNK = 1 << 20
TIMEOUT = 30

Progress = Callable[[int, int], None]                   # bytes so far, total (0 when unknown)
Download = Callable[[str, Path, Progress | None], None]


class EmulatorError(Exception):
    pass


def emulator_home() -> Path:
    return data_home() / APP_ID / "emulator"


def appimage(home: Path) -> Path:
    """The AppImage the run wrapper starts."""
    return home / "current" / MEMBER


def installed_version(home: Path) -> str:
    """The installed shadPS4 version ("0.20.0"), "" when none is."""
    current = home / "current"
    if not (current / MEMBER).is_file():
        return ""
    return current.resolve().name


def download(url: str, dest: Path, progress: Progress | None = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _install(home: Path, version: str, url: str, asset: str, checksum: str, refused: str,
             fetch: Download, progress: Progress | None) -> None:
    """Downloads one build (a zip), checks it against *checksum* and installs its AppImage as "current"; other
    versions go. Nothing changes when a step fails (EmulatorError)."""
    home.mkdir(parents=True, exist_ok=True)
    work = home / f".download-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        archive = work / asset
        try:
            fetch(url, archive, progress)
        except urllib.error.HTTPError as error:
            raise EmulatorError(f"GitHub answered {error.code} for {asset}.") from error
        except (urllib.error.URLError, OSError) as error:
            reason = str(getattr(error, "reason", error))
            raise EmulatorError(f"The download failed: {reason}.") from error
        if sha256(archive) != checksum:
            raise EmulatorError(f"{asset} is not the file {refused} (its SHA-256 differs); nothing was installed.")
        try:
            with zipfile.ZipFile(archive) as packed:
                if MEMBER not in packed.namelist():
                    raise EmulatorError(f"{asset} has no {MEMBER}.")
                with packed.open(MEMBER) as source, (work / MEMBER).open("wb") as out:
                    shutil.copyfileobj(source, out, CHUNK)
        except zipfile.BadZipFile as error:
            raise EmulatorError(f"{asset} is damaged.") from error
        (work / MEMBER).chmod(0o755)
        target = home / version
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir()
        (work / MEMBER).replace(target / MEMBER)
        link = home / ".current-new"
        link.unlink(missing_ok=True)
        link.symlink_to(version)
        link.replace(home / "current")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for other in home.iterdir():
        if other.is_dir() and not other.is_symlink() and other.name != version and not other.name.startswith("."):
            shutil.rmtree(other, ignore_errors=True)


def install(home: Path, fetch: Download = download, progress: Progress | None = None) -> str:
    """The pinned stable release, checked against the SHA-256 this app was tried with. Returns what was done."""
    _install(home, VERSION, URL, ASSET, SHA256, "this app was tested with", fetch, progress)
    return f"shadPS4 {VERSION} is installed."


def remove(home: Path) -> None:
    """The installed shadPS4 goes; shadPS4's own folder (saves, system modules, settings) stays."""
    shutil.rmtree(home, ignore_errors=True)


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """shadPS4's newest stable release when it is newer than the one this app brings; None when it is not, or when
    GitHub cannot be asked (nothing to say then)."""
    latest = latest_release(REPO, fetch=fetch, user_agent=f"{APP_ID}/{__version__}")
    if latest.error or version_tuple(latest.version) <= version_tuple(VERSION):
        return None
    return latest
