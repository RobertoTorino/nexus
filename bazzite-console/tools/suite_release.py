#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan a Bazzite Console Suite release and pin its app checksums."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
MANIFEST = SUITE / "portal" / "apps.toml"
PREFIX = (SUITE / "TAG_PREFIX").read_text(encoding="utf-8").strip()
_TAG = re.compile(rf"^{re.escape(PREFIX)}(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")


def published(tag: str) -> bool:
    """Whether *tag* has a GitHub release that is not a draft."""
    result = subprocess.run(["gh", "release", "view", tag, "--json", "isDraft", "--jq", ".isDraft"],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "false"


def pinned_tags(text: str) -> list[str]:
    apps = tomllib.loads(text).get("apps", {})
    return [entry["tag"] for entry in apps.values() if not entry.get("withdrawn")]


def plan(text: str, portal_version: str, released: Callable[[str], bool] = published,
         tag: str | None = None) -> dict:
    """Return the app and portal tags a release run will build."""
    if tag:
        match = _TAG.fullmatch(tag)
        if not match:
            raise ValueError(f"{tag} is not {PREFIX}<app>-v<x.y.z>")
        portal = match["app"] == "portal"
        return {"apps": [] if portal else [tag], "portal": tag if portal else "", "draft": False}
    apps = [app_tag for app_tag in pinned_tags(text) if not released(app_tag)]
    portal = f"{PREFIX}portal-v{portal_version}"
    if released(portal):
        if apps:
            raise ValueError(f"{', '.join(apps)} would have no portal to bring them: {portal} is out already; "
                             "bump portal/VERSION")
        portal = ""
    return {"apps": apps, "portal": portal, "draft": True}


def output_lines(found: dict) -> list[str]:
    return [f"apps={json.dumps(found['apps'])}", f"portal={found['portal']}",
            f"draft={'true' if found['draft'] else 'false'}"]


def sha256_of(sums: str, asset: str) -> str:
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise ValueError(f"SHA256SUMS does not list {asset}")


def pin(text: str, tag: str, sha256: str) -> str:
    match = _TAG.fullmatch(tag)
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
    parser = argparse.ArgumentParser(description=__doc__)
    steps = parser.add_subparsers(dest="step", required=True)
    planning = steps.add_parser("plan", help="what the run releases")
    planning.add_argument("--tag", help="the tag pushed by hand")
    pinning = steps.add_parser("pin", help="write each app release checksum into apps.toml")
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
            asset = f"{tag}.tar.gz"
            digest = sha256_of((args.sums / tag / "SHA256SUMS").read_text(encoding="utf-8"), asset)
            text = pin(text, tag, digest)
            print(f"pinned {tag} ({digest[:16]}…)")
    except (OSError, ValueError) as exc:
        print(f"suite_release.py {args.step}: {exc}", file=sys.stderr)
        return 1
    MANIFEST.write_bytes(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
