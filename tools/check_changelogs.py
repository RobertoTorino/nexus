#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI check that no CHANGELOG loses history:

    python3 tools/check_changelogs.py [--base REF]

Every entry a CHANGELOG had at REF (the last push, or the PR base) must still be in it: its "Changelog: <time>"
line, as often as it was there. The text of an old entry may be corrected; an entry that went, or a file cut down to
its newest entries, fails. A CHANGELOG may only go together with its folder (an app removed). A CHANGELOG that moved
since REF (git's rename detection: bc250-bazzite/apps/suite/CHANGELOG to dev/releases/CHANGELOG, staged or committed)
or into a suite's folder (apps/x/CHANGELOG to bc250-bazzite/apps/x/CHANGELOG) is compared with its new place.
Without --base there is nothing to compare with, and the check passes."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
_HEADER = re.compile(r"^Changelog: .*$", re.M)


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def headers(text: str) -> Counter:
    return Counter(m.group(0).rstrip() for m in _HEADER.finditer(text))


def changelogs(root: Path, base: str) -> list[str]:
    """The CHANGELOG files git had at *base*."""
    listing = git(root, "ls-tree", "-r", "--name-only", base) or ""
    return [path for path in listing.splitlines() if path == "CHANGELOG" or path.endswith("/CHANGELOG")]


def moved(root: Path, path: str) -> Path | None:
    """Where *path* is now when it moved into a suite's folder (a folder under *root* with portal/apps.toml)."""
    for suite in sorted(p for p in root.iterdir() if p.is_dir() and (p / "portal" / "apps.toml").is_file()):
        if (suite / path).is_file():
            return suite / path
    return None


def renamed(root: Path, base: str) -> dict[str, str]:
    """The CHANGELOGs git sees moved since *base* (a git mv, committed or still staged), old path to new. Git
    finds a move by the file's content, so the committed moves are read against HEAD (where the file still is what
    it was), the staged ones against the working tree."""
    found = {}
    for target in (["HEAD"], []):
        out = git(root, "diff", "-M", "--name-status", "--diff-filter=R", base, *target, "--", "*CHANGELOG") or ""
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                found.setdefault(parts[1], parts[2])
    return found


def check(root: Path, base: str) -> list[str]:
    """What each CHANGELOG lost since *base*, one line per file; empty when nothing went."""
    problems = []
    moves = renamed(root, base)
    for path in changelogs(root, base):
        file = root / moves.get(path, path)
        if not file.is_file():
            file = moved(root, path) or file
        if not file.is_file():
            if file.parent.is_dir():
                problems.append(f"{path}: removed, while its folder is still there")
            continue
        old = headers(git(root, "show", f"{base}:{path}") or "")
        lost = old - headers(file.read_text(encoding="utf-8"))
        if lost:
            total = sum(old.values())
            newest = next(h for h in old if h in lost)          # old lists them newest first
            problems.append(f"{path}: {sum(lost.values())} of the {total} entries it had at {base} are gone "
                            f"(the newest: {newest!r})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="the commit to compare with (the last push, or the PR base)")
    args = parser.parse_args(argv)
    if not args.base:
        print("OK: no --base, nothing to compare with")
        return 0
    if git(SUITE, "rev-parse", "--verify", "-q", f"{args.base}^{{commit}}") is None:
        print(f"ERROR: {args.base} is not a commit here", file=sys.stderr)
        return 1
    problems = check(SUITE, args.base)
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        print("A CHANGELOG is history: put the lost entries back below the new ones "
              f"(git show {args.base}:<path> has them).", file=sys.stderr)
        return 1
    print(f"OK: {len(changelogs(SUITE, args.base))} CHANGELOGs keep every entry they had at {args.base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
