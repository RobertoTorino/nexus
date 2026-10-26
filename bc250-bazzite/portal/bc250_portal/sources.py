# SPDX-License-Identifier: GPL-3.0-or-later
"""Where an app's installer comes from, and what the portal remembers about it.

* Release (an installed portal): <tag>.tar.gz from the suite's GitHub release, checked against the sha256 pinned in
  apps.toml (or, when none is pinned yet, the release's SHA256SUMS) and unpacked without ever writing outside the
  target folder.
* Checkout (development): the app staged from the local suite repo with tools/stage_app.py, exactly as the release
  workflow builds it, so the portal can be tried before anything is released.
* A checkout-only app ([checkout.<key>] in apps.toml): its own folder in the suite's folder of the checkout
  (bc250-bazzite/apps/<key>, or the folder apps.toml names, relative to the suite's folder; relative to the
  repository for a Nexus app, nexus = true: dev/releases), as it is, since it runs
  from there. Never staged, never removed.

The extracted folder is kept under the portal's state dir, so the matching uninstaller is at hand later; after an
install the app's other folders there (older releases) are removed.
Nothing here is Qt: the GUI runs prepare() in a worker thread."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250_core.appinfo import SUITE_REPO_URL
from bc250_core.platform import expand

from . import suite_folder
from .manifest import AppEntry, RENAMED

Download = Callable[[str, Path], None]          # url, destination file
_RELEASE_FOLDER = re.compile(r"^(?P<key>[a-z0-9-]+)-v\d+\.\d+\.\d+$")
TIMEOUT = 30


class SourceError(RuntimeError):
    pass


def http_download(user_agent: str) -> Download:
    def download(url: str, dest: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, dest.open("wb") as out:
            shutil.copyfileobj(response, out)
    return download


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
    """Unpack a release tarball into *dest*. Absolute paths, '..', links pointing outside and device files are
    refused: the archive comes from the network and is unpacked as the user."""
    dest = dest.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if dest != target and dest not in target.parents:
                raise SourceError(f"{archive.name}: {member.name} points outside the folder")
            if member.issym() or member.islnk():
                link = (target.parent / member.linkname).resolve()
                if dest != link and dest not in link.parents:
                    raise SourceError(f"{archive.name}: link {member.name} points outside the folder")
            elif not (member.isfile() or member.isdir()):
                raise SourceError(f"{archive.name}: {member.name} is not a file or folder")
        # The "data" filter (Python 3.12+, backported to 3.11.4) also drops setuid bits and odd permissions.
        tar.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


@dataclass
class Sources:
    """Prepares the folder an app's install/uninstall commands run in."""

    work: Path                                  # <state dir>/releases
    checkout: Path | None = None                # the suite repo, in development
    apps_checkout: Path | None = None           # a release portal: the repo its checkout-only apps run from
    repo_url: str = SUITE_REPO_URL
    download: Download | None = None

    @property
    def local(self) -> bool:
        return self.checkout is not None

    @property
    def checkout_for_apps(self) -> Path | None:
        """Where the checkout-only apps run from: the portal's own checkout, else the one it was shown."""
        return self.checkout or self.apps_checkout

    def folder(self, entry: AppEntry) -> Path:
        if entry.checkout_only:
            if self.checkout_for_apps is None:
                raise SourceError(f"{entry.name} runs from a suite checkout, and this portal has none")
            if entry.nexus:
                return self.checkout_for_apps / entry.folder
            return suite_folder(self.checkout_for_apps) / (entry.folder or f"apps/{entry.key}")
        return self.work / ("local-" + entry.key if self.local else entry.tag)

    def prepare(self, entry: AppEntry) -> Path:
        """The folder with the app's installer, fetched or staged when needed. A checkout is staged afresh every
        time (it may have changed); a release folder is reused, since a tag never changes."""
        folder = self.folder(entry)
        if entry.checkout_only:
            if not folder.is_dir():
                raise SourceError(f"{folder} is missing from the checkout")
            return folder
        if self.local:
            if folder.exists():
                shutil.rmtree(folder)
            self.work.mkdir(parents=True, exist_ok=True)
            _stage_module(self.checkout).stage(entry.key, folder, suite_folder(self.checkout))
            return folder
        if (folder / ".complete").is_file():
            return folder
        return self._fetch(entry, folder)

    def _fetch(self, entry: AppEntry, folder: Path) -> Path:
        if self.download is None:
            raise SourceError("no download function configured")
        base = f"{self.repo_url}/releases/download/{entry.tag}"
        tmp = self.work / f".{entry.tag}.part"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        try:
            archive = tmp / entry.asset
            try:
                self.download(f"{base}/{entry.asset}", archive)
            except OSError as exc:
                raise SourceError(f"could not download {entry.asset}: {exc}") from exc
            want = entry.sha256
            if not want:
                sums = tmp / "SHA256SUMS"
                try:
                    self.download(f"{base}/SHA256SUMS", sums)
                except OSError as exc:
                    raise SourceError(f"could not download SHA256SUMS of {entry.tag}: {exc}") from exc
                want = expected_sha256(sums.read_text(encoding="utf-8", errors="replace"), entry.asset)
                if not want:
                    raise SourceError(f"SHA256SUMS of {entry.tag} does not list {entry.asset}")
            got = sha256_of(archive)
            if got != want:
                raise SourceError(f"{entry.asset} does not match its checksum (got {got[:16]}…, expected "
                                  f"{want[:16]}…): not installed")
            unpacked = tmp / "x"
            safe_extract(archive, unpacked)
            inner = unpacked / entry.tag
            if not inner.is_dir():
                raise SourceError(f"{entry.asset} has no {entry.tag}/ folder")
            if folder.exists():
                shutil.rmtree(folder)
            inner.rename(folder)
            (folder / ".complete").write_text(got + "\n", encoding="utf-8")
            return folder
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def prune(self, entry: AppEntry) -> None:
        """After an install: the app's other folders here (older releases, or a staged checkout copy) go; only the
        one it was installed from stays, for its uninstaller."""
        if entry.checkout_only or not self.work.is_dir():
            return
        keep = self.folder(entry)
        for path in self.work.iterdir():
            match = _RELEASE_FOLDER.match(path.name)
            mine = (match is not None and match["key"] == entry.key) or path.name == f"local-{entry.key}"
            if mine and path != keep and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def forget(self, entry: AppEntry) -> None:
        if not entry.checkout_only:                 # that folder is the checkout's own
            shutil.rmtree(self.folder(entry), ignore_errors=True)


def _stage_module(checkout: Path):
    path = checkout / "tools" / "stage_app.py"
    spec = importlib.util.spec_from_file_location("bc250_stage_app", path)
    if spec is None or spec.loader is None:
        raise SourceError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_installed(entry: AppEntry) -> bool:
    return any(expand(path).exists() for path in entry.detect)


LOCAL = "local"                     # the record of a checkout-only app, or of an older portal's checkout install
_LOCAL_VERSION = re.compile(r"^local-v(\d+\.\d+\.\d+)$")


def local_record(version: str = "") -> str:
    """The record of an install from a checkout: "local" with the staged app's version, so a portal from a release
    can tell the version it pins from it; "local" alone for a checkout-only app (it has no release), or when the
    version is not known."""
    return f"local-v{version}" if re.fullmatch(r"\d+\.\d+\.\d+", version) else LOCAL


def is_local(record: str) -> bool:
    return record == LOCAL or _LOCAL_VERSION.match(record) is not None


def local_version(record: str) -> str:
    """The version an install from a checkout recorded; "" for a checkout-only app, or for a record from before the
    portal kept it (9.2.0 and earlier)."""
    match = _LOCAL_VERSION.match(record)
    return match[1] if match else ""


def installed_from(record: str) -> str:
    """The record in a sentence: "from <tag>", or "from the suite checkout", with the version when it kept one."""
    if not is_local(record):
        return f"from {record}"
    version = local_version(record)
    return "from the suite checkout" + (f" (v{version})" if version else "")


class Records:
    """installed.json: which tag of each app the portal installed; "local-v<version>" when it installed the app from
    a checkout, "local" for a checkout-only app (and in the records of portal 9.2.0 and earlier, every checkout
    install). Apps installed some other way are still detected through apps.toml's detect paths; they just have no
    known tag."""

    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._data = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._data = {}
        # An app renamed in the suite: its record moves to the new key, the tag's prefix with it (ace-queues-v0.2.0
        # under "ace-queues" is ace-v0.2.0 under "ace"), so the copy needs no reinstall and gets no update it has.
        moved = False
        for old, new in RENAMED.items():
            tag = self._data.pop(old, None)
            if tag is None:
                continue
            moved = True
            if new not in self._data:
                self._data[new] = f"{new}-v{tag[len(old) + 2:]}" if tag.startswith(f"{old}-v") else tag
        if moved:
            self._save()

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
