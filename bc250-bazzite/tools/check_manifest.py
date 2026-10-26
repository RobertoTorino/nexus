#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI check for portal/apps.toml, the apps a portal release pins (owner decision 4, proposal §7.2):

    python3 tools/check_manifest.py [--base REF] [--require-tags]

* The manifest parses and lists exactly the portal apps under apps/. An app folder with a ``.standalone`` marker
  is not a portal app and must not be listed. The [checkout.<name>] tables list exactly the app folders with a
  ``.checkout-only`` marker (they run from the checkout and are never released); a table whose ``folder`` lies
  outside apps/ needs that marker there too, in the repository for a Nexus app (``nexus = true``: dev/releases).
  Every app has a category (its tab in the portal); the parser accepts none only to read the manifests of earlier
  portal releases.
* The copy at the repository root, portal/apps.toml, which the portals installed before the suite moved into
  bc250-bazzite/ read at a tag for their update notice, is identical (while the root keeps one).
* Every pinned tag exists. Without --require-tags a tag that does not exist yet is accepted when its version equals
  the app's VERSION: the release that is about to be tagged. The portal release workflow passes --require-tags.
* With --base REF (the previous commit, or the PR base): when apps.toml differs from the last portal release (the
  newest portal-v<x.y.z> tag; REF while there is no portal tag yet), portal/VERSION must have been bumped from that
  release at least as much as the largest app bump it pins: an app patch release needs at least a portal patch
  release, an app minor release at least a portal minor release, and so on. An added, removed or withdrawn app
  needs at least a minor bump (a withdrawn one is removed from the boards); any other change to apps.toml (a new
  checksum, other commands) at least a patch bump. The comparison is with the release, not the push: a portal
  version that is not tagged yet may still change what it pins (the apps' checksums come once GitHub has built
  them), without a bump for every push."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent      # the suite: bc250-bazzite/; the repository is its parent
MANIFEST = "portal/apps.toml"
STANDALONE_MARKER = ".standalone"
CHECKOUT_ONLY_MARKER = ".checkout-only"
LEVELS = {0: "none", 1: "patch", 2: "minor", 3: "major"}
_PORTAL_TAG = re.compile(r"^portal-v(\d+\.\d+\.\d+)$")


def _manifest_module():
    spec = importlib.util.spec_from_file_location("bc250_manifest", SUITE / "portal" / "bc250_portal" / "manifest.py")
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
    errors += [f"[apps.{e.key}] needs a category: one of {', '.join(manifest.CATEGORIES)}"
               for e in entries if not e.category]
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


def check_checkout_entries(entries) -> list[str]:
    """Every app folder with the marker is listed, and every listed folder has it: in the suite, or in the
    repository for a Nexus app."""
    marked = {f"apps/{p.name}" for p in (SUITE / "apps").iterdir() if (p / CHECKOUT_ONLY_MARKER).is_file()}
    listed = {e.folder or f"apps/{e.key}": e for e in entries if not e.nexus}
    nexus = {e.folder: e for e in entries if e.nexus}
    return ([f"{folder} has {CHECKOUT_ONLY_MARKER} but no [checkout.{folder.removeprefix('apps/')}] in {MANIFEST}"
             for folder in sorted(marked - set(listed))] +
            [f"{MANIFEST} [checkout.{e.key}]: {folder} has no {CHECKOUT_ONLY_MARKER}"
             for folder, e in sorted(listed.items()) if not (SUITE / folder / CHECKOUT_ONLY_MARKER).is_file()] +
            [f"{MANIFEST} [checkout.{e.key}]: {folder} (nexus = true) has no {CHECKOUT_ONLY_MARKER} in the repository"
             for folder, e in sorted(nexus.items()) if not (SUITE.parent / folder / CHECKOUT_ONLY_MARKER).is_file()])


def check_root_copy() -> list[str]:
    """The root's copy of apps.toml, for the portals released before the move, equals the suite's."""
    copy = SUITE.parent / MANIFEST
    if copy.is_file() and copy.read_bytes() != (SUITE / MANIFEST).read_bytes():
        return [f"{MANIFEST} at the root differs from {SUITE.name}/{MANIFEST}: copy the suite's over it"]
    return []


def latest_portal_tag(tags) -> str:
    """The newest portal-v<x.y.z> among *tags* by version; "" when there is none."""
    found = [(manifest.version_tuple(m.group(1)), tag) for tag in tags if (m := _PORTAL_TAG.match(tag))]
    return max(found)[1] if found else ""


def reference(base: str) -> tuple[str, str | None, str]:
    """What apps.toml and portal/VERSION are compared with: the last portal release (its tag), since a portal
    version that is not tagged yet may still change what it pins; *base* while there is no portal tag. Returns
    (ref, that apps.toml or None when the ref has none, that portal version)."""
    tag = latest_portal_tag((git("tag", "--list", "portal-v*") or "").split())
    ref = tag or base
    version = tag[len("portal-v"):] if tag else (git("show", f"{ref}:portal/VERSION") or "0.0.0").strip()
    return ref, git("show", f"{ref}:{MANIFEST}"), version


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
        checkout_entries = manifest.load_checkout(SUITE / MANIFEST)
    except (OSError, manifest.ManifestError) as exc:
        print(exc, file=sys.stderr)
        return 1
    errors = check_entries(entries, args.require_tags) + check_checkout_entries(checkout_entries) + check_root_copy()
    if args.base and set(args.base) != {"0"}:   # GitHub sends 000… for a new branch
        errors += check_bump(args.base)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
