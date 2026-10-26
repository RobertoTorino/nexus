# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xenia build this version of the app installs, pinned: the Linux AppImage of one Xenia Canary build on GitHub,
checked against its SHA-256 before it is installed. Xenia has no stable releases: Xenia Canary publishes a build for
almost every change, a release of xenia-canary/xenia-canary tagged with the commit it was built from (e6cd2e4), all
of them marked experimental, the Linux build more so than the Windows one. The app pins one build there, so the
launch line and the advice in the app are tried with the build they are for. It looks up the newest build and says
when there is a newer one than it brings; it never installs one it was not tried with. A tag is a commit, not a
number, so "newer" is the latest release published after the pinned one.

It goes to ~/.local/share/bc250-xenia-manager/emulator/<build>/xenia.AppImage, with "current" pointing to it. The
run wrapper (~/.local/bin/bc250-xenia-run) starts "current", so the Steam shortcuts keep working when the build
changes. The AppImage does not update itself (its AppRun is the program).

Xenia keeps its settings (xenia-canary.config.toml), saves and installed content in $XDG_DATA_HOME/Xenia,
~/.local/share/Xenia by default."""

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

BUILD = "e6cd2e4"                       # the build's tag: the commit it was built from
COMMIT = "e6cd2e4bc998609ca25e24a24c8e32b66c5908ad"
PUBLISHED = "2026-10-20T19:30:12Z"      # when GitHub published it: a later release is a newer build
VERSION = BUILD                         # how the app names it; also the folder it is installed in
ASSET = "xenia_canary_linux.AppImage"   # the same name in every build's release
SHA256 = "bdb83b3b30b9c0a84db4a36aa9c4b08bfaa0968ccb0e8e95bc52da88b1406b63"
SIZE = 18790904                         # bytes of the AppImage
SIZE_MB = round(SIZE / (1 << 20))       # for the question before downloading
MEMBER = "xenia.AppImage"               # the name it is installed under, the same for every build
REPO = "xenia-canary/xenia-canary"
URL = f"https://github.com/{REPO}/releases/download/{BUILD}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{BUILD}"
CHUNK = 1 << 20
TIMEOUT = 30

Progress = Callable[[int, int], None]                   # bytes so far, total (0 when unknown)
Download = Callable[[str, Path, Progress | None], None]


class EmulatorError(Exception):
    pass


def emulator_home() -> Path:
    return data_home() / APP_ID / "emulator"


def xenia_home() -> Path:
    """Xenia's own folder: its settings, saves and installed content."""
    return data_home() / "Xenia"


def appimage(home: Path) -> Path:
    """The AppImage the run wrapper starts."""
    return home / "current" / MEMBER


def installed_version(home: Path) -> str:
    """The installed Xenia build ("e6cd2e4"), "" when none is."""
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


def install(home: Path, fetch: Download = download, progress: Progress | None = None) -> str:
    """Downloads the pinned build, checks it and installs it as "current"; other builds go. Returns what was done.
    Nothing changes when a step fails (EmulatorError)."""
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
            raise EmulatorError(f"{ASSET} is not the file this app was tested with (its SHA-256 differs); "
                                "nothing was installed.")
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
    return f"Xenia {BUILD} is installed."


def remove(home: Path) -> None:
    """The installed Xenia goes; Xenia's own folder (settings, saves, installed content) stays."""
    shutil.rmtree(home, ignore_errors=True)


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """Xenia's newest build when it was published after the one this app brings; None when it was not, or when
    GitHub cannot be asked (nothing to say then). The builds are tagged with a commit, which core's latest_release
    does not read as a version, so the app reads the release itself."""
    fetch = fetch or github_fetch(f"{APP_ID}/{__version__}")
    try:
        data = fetch(f"https://api.github.com/repos/{REPO}/releases/latest")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name", "")).strip()
    published = str(data.get("published_at", ""))
    if not tag or tag == BUILD or published <= PUBLISHED:          # ISO 8601 in UTC: compared as text
        return None
    return ReleaseInfo(tag, tag, str(data.get("html_url") or f"https://github.com/{REPO}/releases/tag/{tag}"),
                       published[:10])
