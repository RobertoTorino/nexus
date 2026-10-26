# SPDX-License-Identifier: GPL-3.0-or-later
"""The RPCS3 build this version of the app installs, pinned: the Linux AppImage of one build on GitHub, checked
against its SHA-256 before it is installed. RPCS3 has no stable releases: it publishes a build for every change
(RPCS3/rpcs3-binaries-linux, one release "build-<commit>" each) and now and then tags a version as a landmark
(v0.0.43). The app pins the build of a landmark, so the launch line and the advice in the app are tried with the
build they are for. It looks up RPCS3's newest landmark and says when there is a newer one than it brings; it never
installs one it was not tried with.

It goes to ~/.local/share/bc250-rpcs3-manager/emulator/<version>/rpcs3.AppImage, with "current" pointing to it. The
run wrapper (~/.local/bin/bc250-rpcs3-run) starts "current", so the Steam shortcuts keep working when the version
changes. RPCS3's own window offers its newest build when it opens, and replaces the AppImage with it when asked to;
the app then says so (replaced()), and Install puts the pinned build back."""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import data_home
from bc250_core.updates import Fetch, ReleaseInfo, latest_release, version_tuple

from . import APP_ID, __version__

LANDMARK = "0.0.43"                     # the tagged version (v0.0.43) the build is of
BUILD = 20395                           # RPCS3's build number, counted over its whole history (24-10-2026: the
#                                         first pin after 19-10-2026, when RPCS3 began to re-attach a controller
#                                         that reconnects with a new device path; owner)
VERSION = f"{LANDMARK}-{BUILD}"         # as RPCS3 names its builds; also the folder it is installed in
COMMIT = "46b7fb670b280d08036c7670270b713daef912c2"
ASSET = f"rpcs3-v{VERSION}-{COMMIT[:8]}_linux64.AppImage"
SHA256 = "9df18bd0af25e94c5a03936b04b3e5a332a5c22e6fa61e6ab93376b027817a5c"
SIZE = 83180532                         # bytes: how the app tells that RPCS3 replaced it with another build
SIZE_MB = round(SIZE / (1 << 20))       # for the question before downloading
MEMBER = "rpcs3.AppImage"               # the name it is installed under, the same for every version
REPO = "RPCS3/rpcs3"
BUILDS = "RPCS3/rpcs3-binaries-linux"
URL = f"https://github.com/{BUILDS}/releases/download/build-{COMMIT}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/v{LANDMARK}"
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
    """The installed RPCS3 build ("0.0.43-20133"), "" when none is."""
    current = home / "current"
    if not (current / MEMBER).is_file():
        return ""
    return current.resolve().name


def replaced(home: Path) -> bool:
    """Whether the installed AppImage is no longer the pinned build: RPCS3 updated itself in its own window (it
    writes the new build over the AppImage it runs from)."""
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
    """Downloads the pinned build, checks it and installs it as "current"; other versions go. Returns what was
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
    return f"RPCS3 {VERSION} is installed."


def remove(home: Path) -> None:
    """The installed RPCS3 goes; RPCS3's own folder (firmware, saves, settings, installed games) stays."""
    shutil.rmtree(home, ignore_errors=True)


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """RPCS3's newest landmark when it is newer than the one this app brings; None when it is not, or when GitHub
    cannot be asked (nothing to say then)."""
    latest = latest_release(REPO, fetch=fetch, user_agent=f"{APP_ID}/{__version__}")
    if latest.error or version_tuple(latest.version) <= version_tuple(LANDMARK):
        return None
    return latest
