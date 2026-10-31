# SPDX-License-Identifier: GPL-3.0-or-later
"""What a newer portal release brings: its apps.toml, read from GitHub at its tag, compared with the running
portal's pins. App updates reach users through a portal update, so the Settings page can name them. After the BC250
portal's portal_update.py, with the suite's tags and manifest path. The release's SHA256SUMS tells a new build of the
running portal's own version (owner, 31-10-2026): a release built again under the same version, which the version
alone never offers; install.ps1 writes the sha256 of the zip a portal came from beside its program (build.sha256)."""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bc250_core.updates import ReleaseInfo, latest_release

from .manifest import AppEntry, ManifestError, parse
from .sources import expected_sha256

RAW_URL = "https://raw.githubusercontent.com/{repo}/{tag}/windows-portable/portal/apps.toml"
SUMS_URL = "https://github.com/{repo}/releases/download/{tag}/SHA256SUMS"
BUILD_FILE = "build.sha256"                 # beside the installed program: the sha256 of the zip it came from
TIMEOUT = 15


@dataclass(frozen=True)
class AppChange:
    name: str                           # "Windows Portable Test"
    old: str                            # "0.1.0"; "" for an app the new portal adds
    new: str                            # "0.1.1"
    short: str = ""                     # the name on its tile, when apps.toml sets one
    withdrawn: str = ""                 # why the new portal withdraws it (it removes the app)


@dataclass(frozen=True)
class PortalUpdate:
    release: ReleaseInfo
    changes: list[AppChange] | None = field(default=None)  # None: the new pins could not be read
    sha256: str = ""                    # of the release's zip, from its SHA256SUMS; "" when it could not be read

    def summary(self) -> str:
        """ "updates Test and PCSX2 Manager", "updates 4 apps, adds Steam Deck Tools", or "" """
        if not self.changes:
            return ""
        updated = [c.short or short(c.name) for c in self.changes if c.old and not c.withdrawn]
        added = [c.short or short(c.name) for c in self.changes if not c.old]
        withdrawn = [c.short or short(c.name) for c in self.changes if c.withdrawn]
        parts = []
        if withdrawn:
            parts.append("withdraws " + (and_list(withdrawn) if len(withdrawn) <= 2 else f"{len(withdrawn)} apps"))
        if updated:
            parts.append("updates " + (and_list(updated) if len(updated) <= 2 else f"{len(updated)} apps"))
        if added:
            parts.append("adds " + (and_list(added) if len(added) <= 2 else f"{len(added)} apps"))
        return ", ".join(parts)

    def details(self) -> str:
        """One line per app, for the Settings page."""
        return "\n".join(f"{c.name}: not available any more ({c.withdrawn}); removed" if c.withdrawn
                         else f"{c.name}: {c.old} → {c.new}" if c.old else f"{c.name}: new, {c.new}"
                         for c in self.changes or [])


def short(name: str) -> str:
    return name.removeprefix("Windows Portable ")


def and_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def compare(current: list[AppEntry], new: list[AppEntry]) -> list[AppChange]:
    """The apps whose pinned release differs or that the new portal withdraws, in the new portal's order; removed
    apps are left out."""
    pinned = {e.key: e for e in current}
    out = []
    for entry in new:
        old = pinned.get(entry.key)
        if entry.withdrawn:
            if old is not None and not old.withdrawn:
                out.append(AppChange(entry.name, old.version, entry.version, entry.short, entry.withdrawn))
        elif old is None:
            out.append(AppChange(entry.name, "", entry.version, entry.short))
        elif old.tag != entry.tag:
            out.append(AppChange(entry.name, old.version, entry.version, entry.short))
    return out


def fetch_text(url: str, user_agent: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8")


def running_build(exe: str) -> str | None:
    """The sha256 of the zip the running portal was installed from: None from a checkout (*exe* is ""), where there
    is no build to compare; "" for an installed portal without build.sha256 (installed before it was written, or
    unpacked without its zip), which the newest build is offered to once."""
    if not exe:
        return None
    try:
        text = (Path(exe).parent / BUILD_FILE).read_text(encoding="utf-8")
    except OSError:
        return ""
    sha = (text.split() or [""])[0].lower()
    return sha if re.fullmatch(r"[0-9a-f]{64}", sha) else ""


def check(repo: str, tag_prefix: str, current: list[AppEntry], user_agent: str,
          release_of: Callable[..., ReleaseInfo] = latest_release,
          read: Callable[[str, str], str] = fetch_text) -> PortalUpdate:
    """The newest portal release, what its pins change and the sha256 of its zip. Never raises."""
    release = release_of(repo, tag_prefix, user_agent=user_agent)
    if release.error or not release.tag:
        return PortalUpdate(release)
    try:
        changes = compare(current, parse(read(RAW_URL.format(repo=repo, tag=release.tag), user_agent)))
    except (OSError, ValueError, ManifestError):
        changes = None                          # offline, or an apps.toml this portal cannot read: no details
    try:
        sha256 = expected_sha256(read(SUMS_URL.format(repo=repo, tag=release.tag), user_agent), f"{release.tag}.zip")
    except (OSError, ValueError):
        sha256 = ""                             # no build to compare: the version alone decides
    return PortalUpdate(release, changes, sha256)
