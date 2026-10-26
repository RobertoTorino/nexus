# SPDX-License-Identifier: GPL-3.0-or-later
"""The PCSX2 this version of the app installs: the Linux AppImage of one stable release on GitHub, pinned, checked
against the SHA-256 this version of the app was tried with. A newer stable comes with a new version of the app, so
the launch line and the settings the app writes are tried with the release they are for; the app says when there is
a newer one. (The nightly channel of before went on the owner's decision, 24-10-2026: the app installs the release
it was tried with and nothing else.)

It goes to ~/.local/share/bc250-pcsx2-manager/emulator/<version>/pcsx2.AppImage, with "current" pointing to it and
the build's size beside it (.size), so replaced() knows the expected size. The run wrapper
(~/.local/bin/bc250-pcsx2-run) starts "current", so the Steam shortcuts keep working when the version changes.
Install also takes PCSX2's catalog out of the AppImage, beside it (catalogue.py). PCSX2's own window offers its
updates when it opens, and replaces the AppImage with another build when asked to; the app then says so
(replaced()), and Install puts the pinned release back."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import data_home
from bc250_core.updates import Fetch, ReleaseInfo, latest_release, version_tuple

from . import APP_ID, __version__, catalogue

VERSION = "2.8.2"
TAG = f"v{VERSION}"
ASSET = f"pcsx2-{TAG}-linux-appimage-x64-Qt.AppImage"
SHA256 = "0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea"
SIZE = 60119544                         # bytes: how the app tells that PCSX2 replaced itself with another build
SIZE_MB = round(SIZE / (1 << 20))       # for the question before downloading
MEMBER = "pcsx2.AppImage"               # the name it is installed under, the same for every version
REPO = "PCSX2/pcsx2"
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
    """The installed PCSX2 version ("2.8.2"), "" when none is."""
    current = home / "current"
    if not (current / MEMBER).is_file():
        return ""
    return current.resolve().name


def replaced(home: Path) -> bool:
    """Whether the installed AppImage is no longer the installed build: PCSX2 updated itself in its own window (it
    writes the new build over the AppImage it runs from). The expected size is the .size written at install; the
    pinned release's without it (an install from before the file was written)."""
    image = appimage(home)
    try:
        size = image.stat().st_size
    except OSError:
        return False
    try:
        expected = int((image.parent / ".size").read_text())
    except (OSError, ValueError):
        expected = SIZE
    return size != expected


def take_catalogue(home: Path) -> bool:
    """PCSX2's catalog (game titles, patches) out of the installed AppImage, beside it (catalogue.py); whether it
    is there afterwards. Without it the app goes on with the files' names."""
    image = appimage(home)
    try:
        catalogue.extract(image)
    except (OSError, subprocess.SubprocessError):
        pass
    return not catalogue.missing(image.parent)


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


def install(home: Path, fetch: Download = download, progress: Progress | None = None) -> str:
    """Downloads the pinned release, checks it against the SHA-256 this app was tried with and installs it as
    "current"; other versions go. Nothing changes when a step fails (EmulatorError). Returns what was done."""
    home.mkdir(parents=True, exist_ok=True)
    work = home / f".download-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        image = work / MEMBER
        try:
            fetch(URL, image, progress)
        except urllib.error.HTTPError as error:
            raise EmulatorError(f"GitHub answered {error.code} for {ASSET}.") from error
        except (urllib.error.URLError, OSError) as error:
            reason = str(getattr(error, "reason", error))
            raise EmulatorError(f"The download failed: {reason}.") from error
        if sha256(image) != SHA256:
            raise EmulatorError(f"{ASSET} is not the file this app was tested with (its SHA-256 differs); nothing "
                                "was installed.")
        image.chmod(0o755)
        target = home / VERSION
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir()
        (target / ".size").write_text(str(image.stat().st_size))    # replaced() compares against the installed build
        image.replace(target / MEMBER)
        link = home / ".current-new"
        link.unlink(missing_ok=True)
        link.symlink_to(VERSION)
        link.replace(home / "current")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    take_catalogue(home)
    for other in home.iterdir():
        if other.is_dir() and not other.is_symlink() and other.name != VERSION and not other.name.startswith("."):
            shutil.rmtree(other, ignore_errors=True)
    return f"PCSX2 {VERSION} is installed."


def remove(home: Path) -> None:
    """The installed PCSX2 goes; PCSX2's own folder (BIOS, memory cards, saves, settings) stays."""
    shutil.rmtree(home, ignore_errors=True)


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """PCSX2's newest stable release when it is newer than the one this app brings; None when it is not, or when
    GitHub cannot be asked (nothing to say then). GitHub's "latest" is the newest release not marked as a
    pre-release, which leaves PCSX2's nightlies out."""
    latest = latest_release(REPO, fetch=fetch, user_agent=f"{APP_ID}/{__version__}")
    if latest.error or version_tuple(latest.version) <= version_tuple(VERSION):
        return None
    return latest
