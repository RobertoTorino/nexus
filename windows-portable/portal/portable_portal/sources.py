# SPDX-License-Identifier: GPL-3.0-or-later
"""Where an app's installer comes from, and what the portal remembers about it.

A release: <tag>.zip from the suite's GitHub release, checked against the sha256 pinned in apps.toml (or, when none
is pinned yet, the release's SHA256SUMS) and unpacked without ever writing outside the target folder. The extracted
folder is kept under the portal's state folder, so the matching uninstaller is at hand later; after an install the
app's other folders there (older releases) are removed. The portal installs from releases only (owner, 28-10-2026):
from a checkout an app would need a PyInstaller build per install.

After the BC250 portal's sources.py, for zips. Nothing here is Qt: the GUI runs prepare() in a worker thread."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250_core.appinfo import SUITE_REPO_URL
from bc250_core.platform import expand

from .manifest import AppEntry

Download = Callable[[str, Path], None]          # url, destination file
_RELEASE_FOLDER = re.compile(r"^wp-(?P<key>[a-z0-9-]+)-v\d+\.\d+\.\d+$")
TIMEOUT = 30
COMPLETE = ".complete"                          # in an extracted release folder: its zip's sha256


class SourceError(RuntimeError):
    pass


def http_download(user_agent: str) -> Download:
    def download(url: str, dest: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
            shutil.copyfileobj(response, out)
    return download


def downloaded(work: Path, tag: str, asset: str) -> int:
    """How many bytes of *asset* fetch_release has downloaded so far into *work*; 0 before it starts and once it is
    done (its folder is gone then)."""
    try:
        return (work / f".{tag}.part" / asset).stat().st_size
    except OSError:
        return 0


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 18), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha256(sums_text: str, asset: str) -> str:
    """The checksum of *asset* in a `sha256sum` style SHA256SUMS file; "" when it is not listed."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset:
            return parts[0].lower()
    return ""


def safe_extract(archive: Path, dest: Path) -> None:
    """Unpack a release zip into *dest*. Absolute paths, '..' and drive letters are refused: the archive comes from
    the network and is unpacked as the user."""
    dest = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            target = (dest / name).resolve()
            if dest != target and dest not in target.parents:
                raise SourceError(f"{archive.name}: {info.filename} points outside the folder")
        zf.extractall(dest)


def fetch_release(download: Download, repo_url: str, tag: str, asset: str, work: Path, want: str = "") -> Path:
    """<asset> of release *tag* downloaded into a fresh folder under *work*, checked against *want* (its sha256) or
    the release's SHA256SUMS, and unpacked: the folder <work>/<tag> it unpacked into. Raises SourceError."""
    base = f"{repo_url}/releases/download/{tag}"
    tmp = work / f".{tag}.part"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        archive = tmp / asset
        try:
            download(f"{base}/{asset}", archive)
        except OSError as exc:
            raise SourceError(f"could not download {asset}: {exc}") from exc
        if not want:
            sums = tmp / "SHA256SUMS"
            try:
                download(f"{base}/SHA256SUMS", sums)
            except OSError as exc:
                raise SourceError(f"could not download SHA256SUMS of {tag}: {exc}") from exc
            want = expected_sha256(sums.read_text(encoding="utf-8", errors="replace"), asset)
            if not want:
                raise SourceError(f"SHA256SUMS of {tag} does not list {asset}")
        got = sha256_of(archive)
        if got != want:
            raise SourceError(f"{asset} does not match its checksum (got {got[:16]}…, expected {want[:16]}…): "
                              "not installed")
        unpacked = tmp / "x"
        safe_extract(archive, unpacked)
        inner = unpacked / tag
        if not inner.is_dir():
            raise SourceError(f"{asset} has no {tag}/ folder")
        folder = work / tag
        if folder.exists():
            shutil.rmtree(folder)
        inner.rename(folder)
        (folder / COMPLETE).write_text(got + "\n", encoding="utf-8")
        return folder
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@dataclass
class Sources:
    """Prepares the folder an app's install/uninstall commands run in."""

    work: Path                                  # <state dir>/releases
    repo_url: str = SUITE_REPO_URL
    download: Download | None = None

    def folder(self, entry: AppEntry) -> Path:
        return self.work / entry.tag

    def prepare(self, entry: AppEntry) -> Path:
        """The folder with the app's installer, fetched when needed; a release folder is reused, since a tag never
        changes."""
        folder = self.folder(entry)
        if (folder / COMPLETE).is_file():
            return folder
        if self.download is None:
            raise SourceError("no download function configured")
        return fetch_release(self.download, self.repo_url, entry.tag, entry.asset, self.work, entry.sha256)

    def prune(self, entry: AppEntry) -> None:
        """After an install: the app's other folders here (older releases) go; only the one it was installed from
        stays, for its uninstaller."""
        if not self.work.is_dir():
            return
        keep = self.folder(entry)
        for path in self.work.iterdir():
            match = _RELEASE_FOLDER.match(path.name)
            if match is not None and match["key"] == entry.key and path != keep and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def forget(self, entry: AppEntry) -> None:
        shutil.rmtree(self.folder(entry), ignore_errors=True)


def is_installed(entry: AppEntry) -> bool:
    return any(expand(path).exists() for path in entry.detect)


class Records:
    """installed.json: which tag of each app the portal (or its installer, for the bundled test app) installed. Apps
    installed some other way are still detected through apps.toml's detect paths; they just have no known tag."""

    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._data = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._data = {}

    def get(self, key: str) -> str:
        return self._data.get(key, "")

    def set(self, key: str, tag: str) -> None:
        self._data[key] = tag
        self._save()

    def remove(self, key: str) -> None:
        if self._data.pop(key, None) is not None:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
