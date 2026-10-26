# SPDX-License-Identifier: GPL-3.0-or-later
"""Governor update check: installed RPM version versus the latest GitHub release of filippor's governor.

The network request runs in a QThread so a slow or absent connection never blocks the GUI."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import APP_ID, __version__, fmt
from .backends.process import run

RELEASES_API = "https://api.github.com/repos/filippor/cyan-skillfish-governor/releases/latest"
RELEASES_PAGE = "https://github.com/filippor/cyan-skillfish-governor/releases"
COPR = "copr.fedorainfracloud.org/coprs/filippor/bazzite"
TIMEOUT = 10
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass
class UpdateResult:
    package: str
    installed: str                  # "0.4.13" or "" when not installed
    installed_full: str             # rpm -q output, for display
    latest: str                     # "0.4.14" or "" when unknown
    latest_url: str
    published: str                  # YYYY-MM-DD
    error: str = ""

    @property
    def update_available(self) -> bool:
        return bool(self.installed and self.latest) and _tuple(self.latest) > _tuple(self.installed)

    @property
    def summary(self) -> str:
        if not self.installed:
            installed = "not installed"
        else:
            installed = self.installed
        if self.error:
            return fmt("%1 (latest: unknown — %2)",
                         installed, self.error)
        if not self.latest:
            return fmt("%1 (latest: unknown)", installed)
        if self.update_available:
            return fmt("%1 → %2 available (%3)",
                         installed, self.latest, self.published)
        if self.installed:
            return fmt("%1 (up to date, latest release %2)",
                         installed, self.published)
        return fmt("%1 (latest release: %2, %3)",
                     installed, self.latest, self.published)


def _tuple(version: str) -> tuple[int, ...]:
    match = _VERSION_RE.search(version)
    return tuple(int(part) for part in match.groups()) if match else ()


def installed_version(package: str) -> tuple[str, str]:
    """(x.y.z, full rpm -q output). Both empty when the package is not installed."""
    result = run(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", package], timeout=10)
    if result.returncode != 0:
        return "", ""
    full = result.stdout.strip()
    match = _VERSION_RE.search(full)
    return (match.group(0) if match else full), f"{package}-{full}"


def latest_release() -> tuple[str, str, str, str]:
    """(x.y.z, html url, published date, error)."""
    request = urllib.request.Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_ID}/{__version__}",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        return "", RELEASES_PAGE, "", fmt("GitHub answered %1",
                                           str(exc.code))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = str(getattr(exc, "reason", exc)).split(":")[0].strip() or exc.__class__.__name__
        return "", RELEASES_PAGE, "", fmt("no connection (%1)",
                                           reason[:60])
    tag = str(data.get("tag_name", ""))
    match = _VERSION_RE.search(tag)
    if not match:
        return "", RELEASES_PAGE, "", fmt("unexpected tag %1",
                                           repr(tag))
    return match.group(0), data.get("html_url", RELEASES_PAGE), str(data.get("published_at", ""))[:10], ""


def check(package: str) -> UpdateResult:
    installed, full = installed_version(package)
    latest, url, published, error = latest_release()
    return UpdateResult(package, installed, full, latest, url, published, error)


class UpdateChecker(QObject):
    """Runs check() off the GUI thread; emits finished(UpdateResult) on the GUI thread."""

    finished = pyqtSignal(object)

    def __init__(self, package: str, parent: QObject | None = None):
        super().__init__(parent)
        self.package = package
        self._thread: QThread | None = None

    def start(self) -> bool:
        if self._thread is not None:
            return False
        self._thread = _Worker(self.package)
        self._thread.result.connect(self._done)
        self._thread.start()
        return True

    def _done(self, result: UpdateResult) -> None:
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self.finished.emit(result)

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.wait(TIMEOUT * 1000 + 1000)
            self._thread = None


class _Worker(QThread):
    result = pyqtSignal(object)

    def __init__(self, package: str):
        super().__init__()
        self.package = package

    def run(self) -> None:
        self.result.emit(check(self.package))
