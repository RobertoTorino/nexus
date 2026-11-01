# SPDX-License-Identifier: GPL-3.0-or-later
"""Update check mechanism: the latest GitHub release of a repository, compared with what is installed, fetched
off the GUI thread. What each app compares (itself, the upstream governor RPM, the HelixSR payload) stays in the app.

In the suite repo every app has its own tags ("governor-v0.4.0"), so GitHub's /releases/latest would answer with
whichever app released last; with a tag_prefix the release list is searched for that app's newest release instead.

Nothing here touches Qt widgets; latest_release() takes a fetch function so it can be tested without a network."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .text import fmt

API = "https://api.github.com/repos/{repo}"
TIMEOUT = 15
PAGE_SIZE = 100                 # releases a page of GitHub's list
MAX_PAGES = 10                  # pages followed for a tag prefix before giving up
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

Fetch = Callable[[str], object]         # url -> decoded JSON


def version_tuple(version: str) -> tuple[int, ...]:
    match = _VERSION_RE.search(version or "")
    return tuple(int(p) for p in match.groups()) if match else ()


def repo_slug(repo_url: str) -> str:
    """"https://github.com/owner/name" -> "owner/name"."""
    return repo_url.rstrip("/").removesuffix(".git").split("github.com/", 1)[-1]


@dataclass
class ReleaseInfo:
    version: str = ""               # "1.2.0", "" when unknown
    tag: str = ""
    url: str = ""                   # release page
    published: str = ""             # YYYY-MM-DD
    asset_name: str = ""            # the first .zip asset, when there is one
    asset_url: str = ""
    asset_size: int = 0
    error: str = ""


def github_fetch(user_agent: str, timeout: int = TIMEOUT) -> Fetch:
    def fetch(url: str) -> object:
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    return fetch


def _release(data: dict, version: str, page_url: str) -> ReleaseInfo:
    info = ReleaseInfo(version, str(data.get("tag_name", "")), str(data.get("html_url") or page_url),
                       str(data.get("published_at", ""))[:10])
    zips = [a for a in data.get("assets", []) if str(a.get("name", "")).lower().endswith(".zip")]
    if zips:
        info.asset_name, info.asset_url = str(zips[0]["name"]), str(zips[0]["browser_download_url"])
        info.asset_size = int(zips[0].get("size") or 0)
    return info


def latest_release(repo: str, tag_prefix: str = "", *, fetch: Fetch | None = None,
                   user_agent: str = "bc250-bazzite-suite", page_url: str = "") -> ReleaseInfo:
    """The newest release of *repo* ("owner/name"); with *tag_prefix*, the newest whose tag starts with it.
    Drafts and pre-releases are skipped. Never raises: errors land in .error."""
    fetch = fetch or github_fetch(user_agent)
    page_url = page_url or f"https://github.com/{repo}/releases"
    base = API.format(repo=repo)
    try:
        if tag_prefix:
            # GitHub lists releases newest first, PAGE_SIZE a page. Another suite's releases can fill the first
            # pages (the Windows Portable Suite's did on 01-11-2026), so the pages are followed until one holds
            # this prefix, or the list ends, or MAX_PAGES are read.
            candidates = []
            for page in range(1, MAX_PAGES + 1):
                data = fetch(f"{base}/releases?per_page={PAGE_SIZE}&page={page}")
                if not isinstance(data, list):
                    raise ValueError("not a release list")
                for item in data:
                    tag = str(item.get("tag_name", ""))
                    if item.get("draft") or item.get("prerelease") or not tag.startswith(tag_prefix):
                        continue
                    version = version_tuple(tag[len(tag_prefix):])
                    if version:
                        candidates.append((version, item))
                if candidates or len(data) < PAGE_SIZE:
                    break
            if not candidates:
                return ReleaseInfo(url=page_url, error=fmt("no release tagged %1 yet", f"{tag_prefix}*"))
            version, item = max(candidates, key=lambda c: c[0])
            return _release(item, ".".join(map(str, version)), page_url)
        data = fetch(f"{base}/releases/latest")
        if not isinstance(data, dict):
            raise ValueError("not a release")
    except urllib.error.HTTPError as exc:
        return ReleaseInfo(url=page_url, error=fmt("GitHub answered %1", exc.code))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = str(getattr(exc, "reason", exc)).split(":")[0].strip() or exc.__class__.__name__
        return ReleaseInfo(url=page_url, error=fmt("no connection (%1)", reason[:60]))
    tag = str(data.get("tag_name", ""))
    match = _VERSION_RE.search(tag)
    if not match:
        return ReleaseInfo(tag=tag, url=page_url, error=fmt("unexpected tag %1", repr(tag)))
    return _release(data, match.group(0), page_url)


@dataclass
class UpdateStatus:
    """What the update check tells about one thing (this app, an upstream package, a payload)."""

    name: str
    installed: str                  # "" when nothing is installed
    latest: ReleaseInfo

    @property
    def update_available(self) -> bool:
        return bool(self.installed and self.latest.version) and \
            version_tuple(self.latest.version) > version_tuple(self.installed)

    @property
    def kind(self) -> str:
        """StatusPill kind: neutral (unknown), info (not installed), warn (update available), ok (up to date)."""
        if self.latest.error or not self.latest.version:
            return "neutral"
        if not self.installed:
            return "info"
        return "warn" if self.update_available else "ok"

    @property
    def summary(self) -> str:
        installed = self.installed or "not installed"
        latest = self.latest
        if latest.error:
            return fmt("%1 (latest: unknown, %2)", installed, latest.error)
        if not latest.version:
            return fmt("%1 (latest: unknown)", installed)
        if self.update_available:
            return fmt("%1 → %2 available (%3)", installed, latest.version, latest.published)
        if self.installed:
            return fmt("%1 (up to date, released %2)", installed, latest.published)
        return fmt("%1; latest release %2 (%3)", installed, latest.version, latest.published)


class UpdateChecker(QObject):
    """Runs a check function off the GUI thread; emits finished(result) on the GUI thread.

    The function is the app's own (e.g. lambda: {"app": UpdateStatus(...), "helixsr": ...}); it must not touch
    widgets. One check at a time: start() returns False while one is running."""

    finished = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: _Worker | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, job: Callable[[], object]) -> bool:
        if self._thread is not None:
            return False
        self._thread = _Worker(job)
        self._thread.result.connect(self._done)
        self._thread.start()
        return True

    def _done(self, result: object) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self.finished.emit(result)

    def stop(self, timeout_ms: int = TIMEOUT * 2000 + 1000) -> None:
        """Wait for a running check (on quit), at most *timeout_ms*; its result is dropped."""
        if self._thread is not None:
            thread, self._thread = self._thread, None
            thread.result.disconnect(self._done)
            if not thread.wait(timeout_ms):
                # Still blocked in the network call: keep a reference, a QThread destroyed while running aborts.
                _Worker.orphans.append(thread)


class _Worker(QThread):
    result = pyqtSignal(object)
    orphans: list[_Worker] = []

    def __init__(self, job: Callable[[], object]):
        super().__init__()
        self.job = job

    def run(self) -> None:
        self.result.emit(self.job())
