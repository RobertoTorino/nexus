# SPDX-License-Identifier: GPL-3.0-or-later
"""The PPSSPP release this version of the app installs, pinned: the Linux AppImage of a tagged release on GitHub,
checked against its SHA-256 before it is installed. A newer PPSSPP comes with a new version of the app, so the
launch line and the advice in the app are tried with the release they are for. The app looks up PPSSPP's newest
release and says when there is a newer one than it brings; it never installs one it was not tried with.

It goes to ~/.local/share/bc250-ppsspp-manager/emulator/<version>/ppsspp.AppImage, with "current" pointing to it.
The run wrapper (~/.local/bin/bc250-ppsspp-run) starts "current", so the Steam shortcuts keep working when the
version changes. PPSSPP does not update itself on Linux: its own window only says when a new release is out."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from bc250_core.platform import data_home
from bc250_core.updates import Fetch, ReleaseInfo, github_fetch

from . import APP_ID, __version__

VERSION = "1.20.4"
TAG = f"v{VERSION}"
ASSET = f"PPSSPP-{TAG}-anylinux-x86_64.AppImage"
SHA256 = "661c098e6b7f7610171a57b7c533ce8bba6f2312b71e76d61e850461973eba21"
SIZE = 50689748                         # bytes of the AppImage
SIZE_MB = round(SIZE / (1 << 20))       # for the question before downloading
MEMBER = "ppsspp.AppImage"              # the name it is installed under, the same for every version
REPO = "hrydgard/ppsspp"
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
    """The installed PPSSPP version ("1.20.4"), "" when none is."""
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
    """Downloads the pinned release, checks it and installs it as "current"; other versions go. Returns what was
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
    return f"PPSSPP {VERSION} is installed."


def remove(home: Path) -> None:
    """The installed PPSSPP goes; PPSSPP's own folder (saves, settings, memory stick games) stays."""
    shutil.rmtree(home, ignore_errors=True)


# PPSSPP numbers the first release of a series 1.20 and its fixes 1.20.4: two or three numbers (core's
# version_tuple wants three, so the app reads the tag itself).
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def version_tuple(version: str) -> tuple[int, ...]:
    match = _VERSION.search(version or "")
    return tuple(int(part or 0) for part in match.groups()) if match else ()


def newer_release(fetch: Fetch | None = None) -> ReleaseInfo | None:
    """PPSSPP's newest release when it is newer than the one this app brings; None when it is not, or when GitHub
    cannot be asked (nothing to say then)."""
    fetch = fetch or github_fetch(f"{APP_ID}/{__version__}")
    try:
        data = fetch(f"https://api.github.com/repos/{REPO}/releases/latest")
        tag = str(data.get("tag_name", ""))
        url = str(data.get("html_url", "")) or f"https://github.com/{REPO}/releases"
        published = str(data.get("published_at", ""))[:10]
    except (urllib.error.URLError, OSError, ValueError, AttributeError):
        return None
    found = version_tuple(tag)
    if not found or found <= version_tuple(VERSION):
        return None
    return ReleaseInfo(".".join(map(str, found)), tag, url, published)
