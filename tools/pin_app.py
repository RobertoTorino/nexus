#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin a released app in portal/apps.toml: its tag and the SHA-256 of its release tarball.

    python3 tools/pin_app.py <app>-v<x.y.z> [--sha256 HEX]

Without --sha256 the checksum is read from the release's SHA256SUMS on GitHub. Only the tag and sha256 lines of
that app's [apps.<app>] table change (a table without a sha256 line, a new app before its first release, gets one
after its tag line); comments and layout stay. Afterwards bump portal/VERSION as
tools/check_manifest.py asks (at least as much as the app moved) and add the app release to the portal CHANGELOG."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
MANIFEST = SUITE / "portal" / "apps.toml"
REPO_URL = "https://github.com/RobertoTorino/nexus"
_TAG = re.compile(r"^(?P<app>[a-z0-9-]+)-v\d+\.\d+\.\d+$")


def fetch_sha256(tag: str) -> str:
    url = f"{REPO_URL}/releases/download/{tag}/SHA256SUMS"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bc250-pin-app"}),
                                timeout=30) as response:
        sums = response.read().decode("utf-8", "replace")
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == f"{tag}.tar.gz":
            return parts[0].lower()
    raise SystemExit(f"{url} does not list {tag}.tar.gz")


def pin(text: str, app: str, tag: str, sha256: str) -> str:
    """apps.toml with the tag and sha256 of [apps.<app>] replaced."""
    start = re.search(rf"^\[apps\.{re.escape(app)}\]\s*$", text, re.M)
    if start is None:
        raise SystemExit(f"apps.toml has no [apps.{app}]")
    following = re.search(r"^\[", text[start.end():], re.M)
    end = start.end() + following.start() if following else len(text)
    block = text[start.end():end]
    block, count = re.subn(r'^tag = ".*"$', f'tag = "{tag}"', block, count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"[apps.{app}] has no tag line")
    block, count = re.subn(r'^sha256 = ".*"$', f'sha256 = "{sha256}"', block, count=1, flags=re.M)
    if count != 1:                              # a new app is listed without one until its first release
        block = re.sub(r'^(tag = ".*"\n)', rf'\g<1>sha256 = "{sha256}"\n', block, count=1, flags=re.M)
    return text[:start.end()] + block + text[end:]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag")
    parser.add_argument("--sha256", help="checksum of <tag>.tar.gz (default: from the release's SHA256SUMS)")
    args = parser.parse_args(argv)
    match = _TAG.match(args.tag)
    if not match:
        parser.error(f"{args.tag} is not <app>-v<x.y.z>")
    sha256 = (args.sha256 or fetch_sha256(args.tag)).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        parser.error("--sha256 must be 64 hex digits")
    text = MANIFEST.read_text(encoding="utf-8")
    MANIFEST.write_bytes(pin(text, match["app"], args.tag, sha256).encode("utf-8"))
    print(f"pinned {args.tag} ({sha256[:16]}…) in {MANIFEST.relative_to(SUITE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
