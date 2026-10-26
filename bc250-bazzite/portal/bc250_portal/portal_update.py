# SPDX-License-Identifier: GPL-3.0-or-later
"""What a newer portal release brings: its apps.toml, read from GitHub at its tag, compared with the running
portal's pins. App updates reach users through a portal update, so the portal's update button can name them."""

from __future__ import annotations

import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from bc250_core.updates import ReleaseInfo, latest_release

from .manifest import AppEntry, ManifestError, parse

# The newer portal's manifest at its tag: in the suite's folder (bc250-bazzite/, since the suite moved there on
# 26-10-2026), before that at the root of the repository, which keeps a copy for the portals installed before the move.
RAW_URLS = ("https://raw.githubusercontent.com/{repo}/{tag}/bc250-bazzite/portal/apps.toml",
            "https://raw.githubusercontent.com/{repo}/{tag}/portal/apps.toml")
TIMEOUT = 15


@dataclass(frozen=True)
class AppChange:
    name: str                           # "BC-250 Memory Manager"
    old: str                            # "0.1.0"; "" for an app the new portal adds
    new: str                            # "0.1.1"
    short: str = ""                     # the name on its tile, when apps.toml sets one ("HDMI-CEC")
    withdrawn: str = ""                 # why the new portal withdraws it (it removes the app from the board)


@dataclass(frozen=True)
class PortalUpdate:
    release: ReleaseInfo
    changes: list[AppChange] | None = field(default=None)  # None: the new pins could not be read

    def summary(self) -> str:
        """ "updates ACE Queues and Memory Manager", "updates 4 apps, adds BIOS Reader", or "" """
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
        """One line per app, for the tooltip."""
        return "\n".join(f"{c.name}: not available any more ({c.withdrawn}); removed from the board" if c.withdrawn
                         else f"{c.name}: {c.old} → {c.new}" if c.old else f"{c.name}: new, {c.new}"
                         for c in self.changes or [])


def short(name: str) -> str:
    return name.removeprefix("BC-250 ")


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


def check(repo: str, tag_prefix: str, current: list[AppEntry], user_agent: str,
          release_of: Callable[..., ReleaseInfo] = latest_release,
          read: Callable[[str, str], str] = fetch_text) -> PortalUpdate:
    """The newest portal release and, when there is one, what its pins change. Never raises."""
    release = release_of(repo, tag_prefix, user_agent=user_agent)
    if release.error or not release.tag:
        return PortalUpdate(release)
    changes = None                              # offline, or an apps.toml this portal cannot read: no details
    for url in RAW_URLS:
        try:
            changes = compare(current, parse(read(url.format(repo=repo, tag=release.tag), user_agent)))
            break
        except (OSError, ValueError, ManifestError):
            continue                            # a tag from before the move: the next address
    return PortalUpdate(release, changes)
