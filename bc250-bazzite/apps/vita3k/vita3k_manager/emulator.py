# SPDX-License-Identifier: GPL-3.0-or-later
"""The Vita3K build this version of the app installs, pinned: the Linux AppImage of one build on GitHub, checked
against its SHA-256 before it is installed. Vita3K has no stable releases: it publishes a build for every change,
the newest under the rolling "continuous" tag of Vita3K/Vita3K and each one kept in Vita3K/Vita3K-builds (a release
per build, tagged with its number, 4186). The app pins one build there, so the launch line and the advice in the
app are tried with the build they are for. It looks up the newest build and says when there is a newer one than it
brings; it never installs one it was not tried with.

It goes to ~/.local/share/bc250-vita3k-manager/emulator/<build>/vita3k.AppImage, with "current" pointing to it. The
run wrapper (~/.local/bin/bc250-vita3k-run) starts "current", so the Steam shortcuts keep working when the build
changes. The AppImage can update itself in place (its 10-self-updater.hook: it asks on its second start, then
writes the newest continuous build over itself); the run wrapper turns that off, and should it happen all the same
(the AppImage started some other way) the app sees it by the file's size (replaced()) and Install puts the pinned
build back. Vita3K's own window only says when a newer build is out, with a link."""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import data_home
from bc250_core.updates import Fetch, ReleaseInfo, github_fetch

from . import APP_ID, __version__

BUILD = 4186                            # Vita3K's build number, counted over its whole history
VERSION = str(BUILD)                    # how the app names it; also the folder it is installed in
SEMVER = "0.2.1"                        # what it calls itself (Vita3K --version: v0.2.1 4186-f0273e4c)
COMMIT = "f0273e4cd9b860ea77c44c73d9f5c5b1ed5fa8ab"
ASSET = "Vita3K-x86_64.AppImage"        # the same name in every build's release
SHA256 = "1be29192ba81ef5ef40d30e65168da18786205d5bedd7bf4112940a5eb15a06a"
SIZE = 78489697                         # bytes: how the app tells that the AppImage was replaced by another build
SIZE_MB = round(SIZE / (1 << 20))       # for the question before downloading
MEMBER = "vita3k.AppImage"              # the name it is installed under, the same for every build
REPO = "Vita3K/Vita3K"
BUILDS = "Vita3K/Vita3K-builds"
URL = f"https://github.com/{BUILDS}/releases/download/{VERSION}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{BUILDS}/releases/tag/{VERSION}"
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
    """The installed Vita3K build ("4186"), "" when none is."""
    current = home / "current"
    if not (current / MEMBER).is_file():
        return ""
    return current.resolve().name


def replaced(home: Path) -> bool:
    """Whether the installed AppImage is no longer the pinned build: it updated itself (it writes the new build
    over the AppImage it runs from)."""
    try:
        return appimage(home).stat().st_size != SIZE
    except OSError:
        return False


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
    """Downloads the pinned build, checks it and installs it as "current"; other builds go. Returns what was
    done. Nothing changes when a step fails (EmulatorError)."""
    home.mkdir(parents=True, exist_ok=True)
    work = home / f".download-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        image = work / MEMBER
        try:
            fetch(URL, image, progress)
        except urllib.error.HTTPError as error:
            raise EmulatorError(f"GitHub answered {error.code} for {ASSET} of build {VERSION}.") from error
        except (urllib.error.URLError, OSError) as error:
            reason = str(getattr(error, "reason", error))
            raise EmulatorError(f"The download failed: {reason}.") from error
        if sha256(image) != SHA256:
            raise EmulatorError(f"{ASSET} of build {VERSION} is not the file this app was tested with (its SHA-256 "
                                "differs); nothing was installed.")
        image.chmod(0o755)
        target = home / VERSION
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir()
        image.replace(target / MEMBER)
        link = home / ".current-new"
        link.unlink(missing_ok=True)
        link.symlink_to(VERSION)
        link.replace(home / "current")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for other in home.iterdir():
        if other.is_dir() and not other.is_symlink() and other.name != VERSION and not other.name.startswith("."):
            shutil.rmtree(other, ignore_errors=True)
    return f"Vita3K build {VERSION} is installed."


def remove(home: Path) -> None:
    """The installed Vita3K goes; Vita3K's own folders (firmware, games, saves, settings) stay."""
    shutil.rmtree(home, ignore_errors=True)


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """Vita3K's newest build when it is newer than the one this app brings; None when it is not, or when GitHub
    cannot be asked (nothing to say then). The builds are tagged with their number alone, which core's
    latest_release does not read as a version, so the app reads the tag itself."""
    fetch = fetch or github_fetch(f"{APP_ID}/{__version__}")
    try:
        data = fetch(f"https://api.github.com/repos/{BUILDS}/releases/latest")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name", "")).strip()
    if not tag.isdigit() or int(tag) <= BUILD:
        return None
    return ReleaseInfo(tag, tag, str(data.get("html_url") or f"https://github.com/{BUILDS}/releases/tag/{tag}"),
                       str(data.get("published_at", ""))[:10])
