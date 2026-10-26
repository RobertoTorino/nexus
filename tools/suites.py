#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The suites of the repository: each a folder directly under the root with its portal's manifest,
<suite>/portal/apps.toml (bc250-bazzite/, the BC250 Bazzite Suite). The Nexus tools work on one suite at a time,
named with --suite. Without a name it is the one suite in the checkout or, with several, the one whose tags have no
prefix (bc250-bazzite: installed portals find its releases by those tags). Each suite names the system it is made for
in <suite>/SYSTEM (bazzite or windows): ./test.sh runs the suites of the system it runs on. A suite's release tags
are <prefix><app>-v<x.y.z>, the prefix in <suite>/TAG_PREFIX (windows-portable: wp-, so wp-portal-v0.1.0; none for
bc250-bazzite), so the suites' tags never mix.

    python3 tools/suites.py                       # the suite folders, one per line (relative to the root)
    python3 tools/suites.py --default             # the default suite, or an error when there is none
    python3 tools/suites.py --system windows      # only the suites made for that system
    python3 tools/suites.py --tag wp-portal-v0.1.0  # the tag's suite, app and version: windows-portable portal 0.1.0"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path("portal") / "apps.toml"
SYSTEMS = ("bazzite", "windows")          # what <suite>/SYSTEM may say
TAG = re.compile(r"^(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")      # a tag without the suite's prefix


def suites(root: Path = ROOT) -> list[Path]:
    """Every suite folder under *root*, sorted by name. A *root* laid out as a suite itself (its own portal/, as
    the test repositories are) and holding none is the one suite."""
    found = sorted(p for p in root.iterdir() if p.is_dir() and (p / MANIFEST).is_file())
    return found or ([root] if (root / MANIFEST).is_file() else [])


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def system(folder: Path) -> str:
    """The system the suite in *folder* is made for, from its SYSTEM file ("" without one)."""
    return _read(folder / "SYSTEM")


def tag_prefix(folder: Path) -> str:
    """What the release tags of the suite in *folder* start with, from its TAG_PREFIX file ("" without one)."""
    return _read(folder / "TAG_PREFIX")


def suite(name: str | None = None, root: Path = ROOT) -> Path:
    """The folder of the suite *name* names or, when *name* is None, the default: the one suite, or the one whose
    tags have no prefix. Raises LookupError when there is no such suite."""
    found = suites(root)
    names = ", ".join(p.name for p in found) or "none"
    if name:
        if (root / name) in found:
            return root / name
        raise LookupError(f"no suite {name!r} in {root} (the suites: {names})")
    if len(found) == 1:
        return found[0]
    if not found:
        raise LookupError(f"no suite in {root}: a folder with {MANIFEST.as_posix()}")
    plain = [p for p in found if not tag_prefix(p)]
    if len(plain) == 1:
        return plain[0]
    raise LookupError(f"{root} holds several suites ({names}): say which with --suite")


def of_tag(tag: str, root: Path = ROOT) -> tuple[Path, str, str]:
    """The suite folder, app key and version of the release tag *tag*: a suite's prefix picks it, a tag without one
    is the default suite's (an app of that suite never starts with another suite's prefix: tools/tests/
    test_layout.py). Raises LookupError for a tag that is not <prefix><app>-v<x.y.z> of a suite here."""
    found = suites(root)
    for folder in sorted(found, key=lambda p: -len(tag_prefix(p))):
        prefix = tag_prefix(folder)
        if prefix and tag.startswith(prefix) and (match := TAG.match(tag[len(prefix):])):
            return folder, match["app"], match["version"]
    match = TAG.match(tag)
    plain = [p for p in found if not tag_prefix(p)]
    if match and len(plain) == 1:
        return plain[0], match["app"], match["version"]
    raise LookupError(f"{tag} is not <app>-v<x.y.z> of a suite here (a suite's tags start with its TAG_PREFIX)")


def add_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--suite", metavar="NAME", help="the suite's folder, such as bc250-bazzite (default: the "
                                                        "one suite in the checkout, or the one whose tags have no "
                                                        "prefix)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--default", action="store_true", help="only the default suite (an error when there is none)")
    parser.add_argument("--system", choices=SYSTEMS, help="only the suites made for this system")
    parser.add_argument("--tag", help="the suite, app and version of this release tag, on one line")
    args = parser.parse_args(argv)
    try:
        if args.tag:
            folder, app, version = of_tag(args.tag)
            print(folder.name if folder != ROOT else ".", app, version)
            return 0
        folders = [suite()] if args.default else suites()
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.system:
        folders = [folder for folder in folders if system(folder) == args.system]
    for folder in folders:
        print(folder.name if folder != ROOT else ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
