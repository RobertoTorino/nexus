# SPDX-License-Identifier: GPL-3.0-or-later
"""The newest DirectMesh release on GitHub, compared with the one this version of the app builds. The app only says
so: a new release reaches the board with a new version of the app, which bundles its patch.

DirectMesh tags its releases "directmesh-v1.3" and "directmesh-v1.3.1", two or three numbers, so core's
latest_release() (three numbers) does not fit; the request goes through core's github_fetch()."""

from __future__ import annotations

import re
import urllib.error
from dataclasses import dataclass

from bc250_core.updates import Fetch, github_fetch

REPO = "lonewolf0622/bc250meshtaskwork"
RELEASES_URL = f"https://github.com/{REPO}/releases"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
TAG_PREFIX = "directmesh-"
_VERSION = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?$")


def version_tuple(text: str) -> tuple[int, int, int] | None:
    """"v1.3" -> (1, 3, 0), "v1.3.1" -> (1, 3, 1); None for anything else."""
    found = _VERSION.match(text.strip())
    return (int(found[1]), int(found[2]), int(found[3] or 0)) if found else None


@dataclass(frozen=True)
class Release:
    version: str = ""           # "v1.3.1", as DirectMesh writes it
    url: str = RELEASES_URL     # the release page
    published: str = ""         # YYYY-MM-DD
    error: str = ""


def latest_release(fetch: Fetch | None = None) -> Release:
    """The newest DirectMesh release; drafts, pre-releases and other tags are skipped. Never raises: errors land in
    .error."""
    fetch = fetch or github_fetch("bc250-mesh-shaders")
    try:
        data = fetch(API_URL)
        if not isinstance(data, list):
            raise ValueError("not a release list")
    except urllib.error.HTTPError as exc:
        return Release(error=f"GitHub answered {exc.code}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = str(getattr(exc, "reason", exc)).split(":")[0].strip() or exc.__class__.__name__
        return Release(error=f"no connection ({reason[:60]})")
    candidates = []
    for item in data:
        tag = str(item.get("tag_name", ""))
        if item.get("draft") or item.get("prerelease") or not tag.startswith(TAG_PREFIX):
            continue
        version = version_tuple(tag[len(TAG_PREFIX):])
        if version:
            candidates.append((version, item))
    if not candidates:
        return Release(error="no DirectMesh release found")
    _, item = max(candidates, key=lambda c: c[0])
    return Release(str(item["tag_name"])[len(TAG_PREFIX):], str(item.get("html_url") or RELEASES_URL),
                   str(item.get("published_at", ""))[:10])


def is_newer(release: Release, pinned: str) -> bool:
    """True when *release* is newer than *pinned* ("v1.3.1", or the status line's "v1.3.1, Mesa 26.2.1")."""
    have, latest = version_tuple(pinned.split(",")[0]), version_tuple(release.version)
    return bool(have and latest and latest > have)
