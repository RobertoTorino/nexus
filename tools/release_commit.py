#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether a commit is a release commit and nothing more, so the CI that passed on its parent (the work commit)
counts for it (owner, 30-10-2026: a release took about 18 minutes, 10 of them CI run twice on the same code). A
release commit, as the Nexus Release Tool writes it, has one parent and only modifies:

* VERSION files: one x.y.z line before and after;
* version copies (the lines tools/check_versions.py reads: ``__version__ = "x.y.z"``, ``VERSION="x.y.z"``,
  ``version = "x.y.z"`` in a .toml): each changed line is such a line before and after, the rest of the line equal;
* CHANGELOGs: entries put on top, each a ``Changelog:`` line, a blank line and one line ``Release x.y.z. ...`` or
  ``Version x.y.z. ...``, the old text unchanged under them;
* a portal's apps.toml: only ``tag = "..."`` and ``sha256 = "..."`` lines changed, each in place.

Anything else (an added, removed or renamed file, any other changed line, a merge) is not, and CI on the commit
itself decides as before. A Cargo.lock is never accepted (its crate version is no line of its own to check).

    python3 tools/release_commit.py <commit>

Prints the parent and exits 0 when the commit is only a release; prints why not and exits 1 otherwise."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = r"\d+\.\d+\.\d+"
ENTRY = re.compile(r"Changelog: \d\d-\d\d-\d{4} \d\d:\d\d:\d\d\n\n(?:Release|Version) " + SEMVER + r"\.[^\n]*\n\n")
PIN_LINE = re.compile(r'(tag|sha256) = "[^"\n]*"')
COPY_LINES = {                          # tools/check_versions.py's PATTERNS, one line each, the version as group 1
    ".py": re.compile(r'__version__ = "(' + SEMVER + r')"[ \t]*(?:#.*)?'),
    ".sh": re.compile(r'VERSION="(' + SEMVER + r')"[ \t]*(?:#.*)?'),
    ".toml": re.compile(r'version = "(' + SEMVER + r')".*'),
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


def parent(commit: str) -> str | None:
    """The one parent of *commit*; None for a merge, a root commit or one whose parent is not fetched."""
    try:
        shas = git("rev-list", "--parents", "-n", "1", commit).split()
        if len(shas) != 2:
            return None
        git("cat-file", "-e", shas[1] + "^{commit}")
    except subprocess.CalledProcessError:
        return None
    return shas[1]


def lines_changed_in_place(old: str, new: str) -> list[tuple[str, str]] | None:
    """The (old, new) pairs of the lines that differ, when both texts have the same number of lines; else None."""
    a, b = old.split("\n"), new.split("\n")
    if len(a) != len(b):
        return None
    return [(x, y) for x, y in zip(a, b) if x != y]


def why_not(path: str, old: str, new: str) -> str | None:
    """Why this change of *path* is more than a release's; None when it is a release's."""
    name = Path(path).name
    if name == "VERSION":
        ok = all(re.fullmatch(SEMVER + r"\n?", text) for text in (old, new))
        return None if ok else "a VERSION that is not one x.y.z line"
    if name == "CHANGELOG":
        if not new.endswith(old):
            return "a CHANGELOG changed below its new entries"
        added = new[:len(new) - len(old)]
        while added:
            entry = ENTRY.match(added)
            if entry is None:
                return "a CHANGELOG entry that is no Release x.y.z. or Version x.y.z. line"
            added = added[entry.end():]
        return None
    changed = lines_changed_in_place(old, new)
    if changed is None:
        return "lines added or removed"
    if name == "apps.toml":
        for a, b in changed:
            ma, mb = PIN_LINE.fullmatch(a), PIN_LINE.fullmatch(b)
            if not (ma and mb and ma.group(1) == mb.group(1)):
                return f"a line other than tag or sha256 changed: {b!r}"
        return None
    pattern = COPY_LINES.get(Path(path).suffix)
    if pattern is None or name == "Cargo.lock":
        return "not a VERSION, CHANGELOG, apps.toml or version copy"
    for a, b in changed:
        ma, mb = pattern.fullmatch(a), pattern.fullmatch(b)
        if not (ma and mb) or a[:ma.start(1)] + a[ma.end(1):] != b[:mb.start(1)] + b[mb.end(1):]:
            return f"a line other than a version copy changed: {b!r}"
    return None


def check(commit: str) -> tuple[str | None, list[str]]:
    """(the parent, []) when *commit* is only a release; (None, the reasons) when it is not."""
    first = parent(commit)
    if first is None:
        return None, [f"{commit[:7]} has not exactly one parent here (a merge, or the parent not fetched)"]
    reasons = []
    entries = git("diff", "--no-renames", "--name-status", "-z", first, commit).split("\0")
    for status, path in zip(entries[0::2], entries[1::2]):
        if status != "M":
            reasons.append(f"{path}: {'added' if status == 'A' else 'removed' if status == 'D' else status}")
            continue
        old, new = git("show", f"{first}:{path}"), git("show", f"{commit}:{path}")
        reason = why_not(path, old, new)
        if reason:
            reasons.append(f"{path}: {reason}")
    return (None, reasons) if reasons else (first, [])


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.split("\n\n")[-2], file=sys.stderr)
        return 2
    first, reasons = check(argv[0])
    if first is None:
        print(f"{argv[0][:7]} is more than a release commit:", file=sys.stderr)
        for reason in reasons:
            print(f"  {reason}", file=sys.stderr)
        return 1
    print(first)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
