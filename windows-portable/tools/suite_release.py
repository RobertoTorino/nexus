#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The steps of a release of the Windows Portable Suite that its release workflow (release-windows-portable.yml)
runs besides the build, from the checkout of the release commit:

    python windows-portable/tools/suite_release.py plan [--tag TAG]   # what the run releases, for $GITHUB_OUTPUT
    python windows-portable/tools/suite_release.py pin DIR TAG...     # each TAG's sha256 into portal/apps.toml

plan prints three lines: apps=<JSON list of tags>, portal=<tag or nothing> and draft=<true|false>. With --tag (a
tag pushed by hand, the way of before the Nexus release) it is that one tag, published at once. Without it (a Nexus
release, started by the Nexus Release Tool): every app tag apps.toml pins that has no published release yet, and
wp-portal-v<portal/VERSION> when that has none, as a draft: the Nexus Release Tool publishes it after the device test.
A draft counts as not released, so a run started again makes it anew.

pin writes the sha256 of <TAG>.zip from DIR/<TAG>/SHA256SUMS (the release's own, downloaded) on the sha256 line of
that app in portal/apps.toml; the tag lines are the release commit's and stay. GitHub is asked with the gh CLI
(GH_TOKEN). This is the suite's own tool (owner, 27-10-2026: a change to one suite never touches another's
release)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent          # windows-portable/
MANIFEST = SUITE / "portal" / "apps.toml"
PREFIX = "wp-"
_TAG = re.compile(r"^wp-(?P<app>[a-z0-9-]+)-v\d+\.\d+\.\d+$")


def published(tag: str) -> bool:
    """Whether *tag* has a release on GitHub that is not a draft."""
    result = subprocess.run(["gh", "release", "view", tag, "--json", "isDraft", "--jq", ".isDraft"],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "false"


def pinned_tags(text: str) -> list[tuple[str, str]]:
    """(app, tag) of every [apps.<app>] in apps.toml that is not withdrawn, in the file's order."""
    import tomllib
    apps = tomllib.loads(text).get("apps", {})
    return [(key, entry["tag"]) for key, entry in apps.items() if not entry.get("withdrawn")]


def plan(text: str, portal_version: str, released: Callable[[str], bool] = published,
         tag: str | None = None) -> dict:
    """What a run releases: {"apps": [tags], "portal": tag or "", "draft": bool}. Raises ValueError for a tag that is
    not the suite's, and for apps to release without a portal release to bring them."""
    if tag:
        match = _TAG.match(tag)
        if not match:
            raise ValueError(f"{tag} is not {PREFIX}<app>-v<x.y.z>")
        portal = match["app"] == "portal"
        return {"apps": [] if portal else [tag], "portal": tag if portal else "", "draft": False}
    apps = [pinned for _key, pinned in pinned_tags(text) if not released(pinned)]
    portal = f"{PREFIX}portal-v{portal_version}"
    if released(portal):
        if apps:
            raise ValueError(f"{', '.join(apps)} would have no portal to bring them: {portal} is out already, bump "
                             "portal/VERSION")
        portal = ""
    return {"apps": apps, "portal": portal, "draft": True}


def output_lines(found: dict) -> list[str]:
    return [f"apps={json.dumps(found['apps'])}", f"portal={found['portal']}",
            f"draft={'true' if found['draft'] else 'false'}"]


def sha256_of(sums: str, asset: str) -> str:
    """The checksum SHA256SUMS lists for *asset*; ValueError when it lists none."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise ValueError(f"SHA256SUMS does not list {asset}")


def pin(text: str, tag: str, sha256: str) -> str:
    """apps.toml with the sha256 line of the app that pins *tag* set (one added after its tag line when it has
    none); everything else stays as it is. ValueError when no app pins *tag*."""
    match = _TAG.match(tag)
    start = re.search(rf"^\[apps\.{re.escape(match['app'])}\]\s*$", text, re.M) if match else None
    if start is None:
        raise ValueError(f"apps.toml has no app for {tag}")
    following = re.search(r"^\[", text[start.end():], re.M)
    end = start.end() + following.start() if following else len(text)
    block = text[start.end():end]
    if not re.search(rf'^tag = "{re.escape(tag)}"$', block, re.M):
        raise ValueError(f"[apps.{match['app']}] does not pin {tag}")
    block, count = re.subn(r'^sha256 = ".*"$', f'sha256 = "{sha256}"', block, count=1, flags=re.M)
    if count != 1:
        block = re.sub(r'^(tag = ".*"\n)', rf'\g<1>sha256 = "{sha256}"\n', block, count=1, flags=re.M)
    return text[:start.end()] + block + text[end:]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    steps = parser.add_subparsers(dest="step", required=True)
    planning = steps.add_parser("plan", help="what the run releases")
    planning.add_argument("--tag", help="the tag pushed by hand")
    pinning = steps.add_parser("pin", help="the sha256 of each tag into portal/apps.toml")
    pinning.add_argument("sums", type=Path, help="folder with <tag>/SHA256SUMS")
    pinning.add_argument("tags", nargs="+")
    args = parser.parse_args(argv)
    text = MANIFEST.read_text(encoding="utf-8")
    try:
        if args.step == "plan":
            version = (SUITE / "portal" / "VERSION").read_text(encoding="utf-8").strip()
            print("\n".join(output_lines(plan(text, version, tag=args.tag))))
            return 0
        for tag in args.tags:
            sha = sha256_of((args.sums / tag / "SHA256SUMS").read_text(encoding="utf-8"), f"{tag}.zip")
            text = pin(text, tag, sha)
            print(f"pinned {tag} ({sha[:16]}…)")
    except (OSError, ValueError) as exc:
        print(f"suite_release.py {args.step}: {exc}", file=sys.stderr)
        return 1
    MANIFEST.write_bytes(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
