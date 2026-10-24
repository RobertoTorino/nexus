#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The backlog: every item in MIGRATION.md that is on hold, as the body of the weekly review issue.

    python3 tools/backlog.py            # Markdown on stdout
    python3 tools/backlog.py --file X   # another file than MIGRATION.md

An item is the list entry (or paragraph) a line saying "on hold" belongs to: it starts at the line beginning with
"- " or "1. " above it, or after the blank line above it. Each item is listed once, under its section, with its title
(the bold text it starts with) or else its first words, and a link to its line on GitHub. The weekly workflow
.github/workflows/backlog.yml opens or updates the "Backlog review" issue with it; with no item on hold it prints
nothing. Nothing is changed here."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
SOURCE = SUITE / "MIGRATION.md"
BLOB_URL = "https://github.com/RobertoTorino/nexus/blob/main/MIGRATION.md#L{line}"
ON_HOLD = re.compile(r"\bon hold\b", re.IGNORECASE)
START = re.compile(r"^\s*(?:- |\d+\. )")
TITLE = re.compile(r"^\s*(?:- |\d+\. )?\*\*(.+?)\*\*")
WORDS = 12


@dataclass(frozen=True)
class Item:
    line: int           # 1-based, where the item starts
    section: str
    title: str


def _start(lines: list[str], index: int) -> int:
    """The line the item holding lines[index] starts on: its list marker, or the line after a blank one."""
    at = index
    while at > 0:
        if START.match(lines[at]):
            return at
        if not lines[at - 1].strip() or lines[at - 1].startswith("#"):
            return at
        at -= 1
    return at


def _title(lines: list[str], start: int) -> str:
    match = TITLE.match(lines[start])
    if match:
        return match.group(1).rstrip(".:")
    text = START.sub("", lines[start]).strip()
    words = text.split()
    return " ".join(words[:WORDS]) + (" …" if len(words) > WORDS else "")


def items(text: str) -> list[Item]:
    lines = text.splitlines()
    found: dict[int, Item] = {}
    section = ""
    sections: list[str] = []
    for line in lines:
        if line.startswith("## "):
            section = line[3:].strip()
        sections.append(section)
    for index, line in enumerate(lines):
        if ON_HOLD.search(line) and not line.startswith("#"):
            start = _start(lines, index)
            found.setdefault(start, Item(start + 1, sections[start], _title(lines, start)))
    return sorted(found.values(), key=lambda item: item.line)


def body(found: list[Item]) -> str:
    """The issue's text: the items by section, in the file's order."""
    if not found:
        return ""
    out = [f"{len(found)} item{'s' if len(found) != 1 else ''} on hold in MIGRATION.md. Go through them: pick one "
           "up, keep it on hold, or drop it (and say so in MIGRATION.md). Close this issue when done; it opens again "
           "next week.", ""]
    section = None
    for item in found:
        if item.section != section:
            section = item.section
            out += ["", f"### {section or 'MIGRATION.md'}", ""]
        out.append(f"- [{item.title}]({BLOB_URL.format(line=item.line)}) (line {item.line})")
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The items on hold in MIGRATION.md, as Markdown.")
    parser.add_argument("--file", type=Path, default=SOURCE)
    args = parser.parse_args(argv)
    sys.stdout.write(body(items(args.file.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
