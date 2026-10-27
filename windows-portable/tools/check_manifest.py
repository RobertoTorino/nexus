#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI check for windows-portable/portal/apps.toml, the apps a portal release of the Windows Portable Suite pins:

    python3 windows-portable/tools/check_manifest.py [--base REF] [--require-tags]

The same rules as the BC250 suite's (bc250-bazzite/tools/check_manifest.py), with the suite's tags (wp-):

* The manifest parses and lists exactly the apps under apps/ (an app folder with a ``.standalone`` marker is not a
  portal app and must not be listed). There are no [checkout.*] apps: the suite has no development tab.
* Every pinned tag exists. Without --require-tags a tag that does not exist yet is accepted when its version equals
  the app's VERSION: the release that is about to be tagged. The portal release workflow passes --require-tags.
* With --base REF: when apps.toml differs from the last portal release (the newest wp-portal-v<x.y.z> tag; REF while
  there is none), portal/VERSION must have been bumped from that release at least as much as the largest app bump it
  pins. An added, removed or withdrawn app needs at least a minor bump; any other change at least a patch bump."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent      # the suite: windows-portable/; the repository is its parent
MANIFEST = "portal/apps.toml"
STANDALONE_MARKER = ".standalone"
LEVELS = {0: "none", 1: "patch", 2: "minor", 3: "major"}
PORTAL_TAG = "wp-portal-v"
_PORTAL_TAG = re.compile(r"^wp-portal-v(\d+\.\d+\.\d+)$")


def _manifest_module():
    spec = importlib.util.spec_from_file_location("portable_manifest",
                                                  SUITE / "portal" / "portable_portal" / "manifest.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module             # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


manifest = _manifest_module()


def bump_level(old: str, new: str) -> int:
    """3 major, 2 minor, 1 patch, 0 unchanged; negative when *new* is lower."""
    a, b = manifest.version_tuple(old), manifest.version_tuple(new)
    if b == a:
        return 0
    if b < a:
        return -1
    for level, (x, y) in zip((3, 2, 1), zip(a, b)):
        if y != x:
            return level
    return 0


def git(*args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=SUITE, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def tag_exists(tag: str) -> bool:
    return git("rev-parse", "-q", "--verify", f"refs/tags/{tag}") is not None


def check_entries(entries, require_tags: bool) -> list[str]:
    errors = []
    apps = {
        p.name for p in (SUITE / "apps").iterdir()
        if p.is_dir() and not (p / STANDALONE_MARKER).is_file()
    }
    listed = {e.key for e in entries}
    errors += [f"apps/{name} is not in {MANIFEST}" for name in sorted(apps - listed)]
    errors += [f"{MANIFEST} lists {name}, which has no apps/{name}" for name in sorted(listed - apps)]
    for entry in entries:
        if entry.key not in apps or tag_exists(entry.tag):
            continue
        version_file = SUITE / "apps" / entry.key / "VERSION"
        current = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "?"
        if require_tags:
            errors.append(f"{entry.tag} does not exist: release it before the portal")
        elif entry.version != current:
            errors.append(f"{entry.tag} does not exist and is not the next release either "
                          f"(apps/{entry.key}/VERSION is {current})")
    return errors


def latest_portal_tag(tags) -> str:
    """The newest wp-portal-v<x.y.z> among *tags* by version; "" when there is none."""
    found = [(manifest.version_tuple(m.group(1)), tag) for tag in tags if (m := _PORTAL_TAG.match(tag))]
    return max(found)[1] if found else ""


def reference(base: str) -> tuple[str, str | None, str]:
    """What apps.toml and portal/VERSION are compared with: the last portal release (its tag); *base* while there
    is no portal tag. Returns (ref, that apps.toml or None when the ref has none, that portal version)."""
    tag = latest_portal_tag((git("tag", "--list", f"{PORTAL_TAG}*") or "").split())
    ref = tag or base
    prefix = f"{SUITE.name}/"
    version = tag[len(PORTAL_TAG):] if tag else (git("show", f"{ref}:{prefix}portal/VERSION") or "0.0.0").strip()
    return ref, git("show", f"{ref}:{prefix}{MANIFEST}"), version


def check_bump(base: str) -> list[str]:
    ref, old_text, old_portal = reference(base)
    if old_text is None:
        return []                               # new file, or a base this clone does not have
    return bump_errors(old_text, (SUITE / MANIFEST).read_text(encoding="utf-8"), old_portal,
                       (SUITE / "portal" / "VERSION").read_text(encoding="utf-8").strip(), since=ref)


def required_bump(old_text: str, new_text: str) -> tuple[int, str]:
    """The smallest portal bump (LEVELS) the change from *old_text* to *new_text* needs, and why; -1 when an app
    moves back to an older release."""
    if old_text == new_text:
        return 0, ""
    old = {e.key: e for e in manifest.parse(old_text)}
    new = {e.key: e for e in manifest.parse(new_text)}
    need, why = 1, "apps.toml changed"
    for key in sorted(set(old) | set(new)):
        if key not in old or key not in new:
            if need < 2:
                need, why = 2, f"{key} was {'added' if key in new else 'removed'}"
            continue
        if new[key].withdrawn != old[key].withdrawn and need < 2:
            need, why = 2, f"{key} was {'withdrawn' if new[key].withdrawn else 'no longer withdrawn'}"
        level = bump_level(old[key].version, new[key].version)
        if level < 0:
            return -1, f"{key} moves back from {old[key].tag} to {new[key].tag}"
        if level > need:
            need, why = level, f"{key} {old[key].version} -> {new[key].version}"
    return need, why


def bump_errors(old_text: str, new_text: str, old_portal: str, new_portal: str, since: str = "") -> list[str]:
    need, why = required_bump(old_text, new_text)
    if need == 0:
        return []
    if need < 0:
        return [why]
    got = bump_level(old_portal, new_portal)
    if got < need:
        return [f"{MANIFEST} changed{f' since {since}' if since else ''} ({why}): portal/VERSION needs at least a "
                f"{LEVELS[need]} bump, but goes {old_portal} -> {new_portal}"]
    return []


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="git ref to compare apps.toml and portal/VERSION with while there is no "
                                       "portal tag (the previous commit, or the PR base)")
    parser.add_argument("--require-tags", action="store_true", help="every pinned tag must exist (portal release)")
    args = parser.parse_args(argv)
    try:
        entries = manifest.load(SUITE / MANIFEST)
    except (OSError, manifest.ManifestError) as exc:
        print(exc, file=sys.stderr)
        return 1
    errors = check_entries(entries, args.require_tags)
    if args.base and set(args.base) != {"0"}:   # GitHub sends 000… for a new branch
        errors += check_bump(args.base)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
