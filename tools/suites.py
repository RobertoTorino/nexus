#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The suites of the repository: each a folder directly under the root with its portal's manifest,
<suite>/portal/apps.toml (bc250-bazzite/, the BC250 Bazzite Suite). The Nexus tools work on one suite at a time,
named with --suite; with one suite in the checkout it is the default.

    python3 tools/suites.py            # the suite folders, one per line (relative to the root)
    python3 tools/suites.py --default  # the one suite, or an error when there are several"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path("portal") / "apps.toml"


def suites(root: Path = ROOT) -> list[Path]:
    """Every suite folder under *root*, sorted by name. A *root* laid out as a suite itself (its own portal/, as
    the test repositories are) and holding none is the one suite."""
    found = sorted(p for p in root.iterdir() if p.is_dir() and (p / MANIFEST).is_file())
    return found or ([root] if (root / MANIFEST).is_file() else [])


def suite(name: str | None = None, root: Path = ROOT) -> Path:
    """The folder of the suite *name* names, or the one suite when *name* is None. Raises LookupError when there
    is no such suite, or no name was given and the checkout holds several."""
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
    raise LookupError(f"{root} holds several suites ({names}): say which with --suite")


def add_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--suite", metavar="NAME", help="the suite's folder, such as bc250-bazzite (default: the "
                                                        "one suite in the checkout)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--default", action="store_true", help="only the one suite (an error when there are several)")
    args = parser.parse_args(argv)
    try:
        folders = [suite()] if args.default else suites()
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    for folder in folders:
        print(folder.name if folder != ROOT else ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
