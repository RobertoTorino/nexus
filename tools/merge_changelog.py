#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""git's merge driver for the CHANGELOGs: two sides that each put a new entry on top merge without a conflict.

    tools/merge_changelog.py BASE OURS THEIRS        (git fills in %O %A %B; the result goes into OURS)

Every CHANGELOG grows at the top (newest first), so work on both machines ends in the same lines: the entry Claude
wrote here and the entry a release wrote on the other machine both sit above the same old entry, and git's line
merge stops with a conflict at every pull (owner, 01-11-2026: "I have this every time"). This driver merges by
entry instead of by line: an entry is a "Changelog: <time>" line with the text below it. The result is ours with
what theirs did since the base: its new entries put in above the entry they sat above there (and above our own new
entries that are older, so the new ones read newest first), an entry it changed taken as changed, an entry it
removed left out. Only when both sides changed the same entry, or the same text before the first entry, is it
handed to git's own line merge (git merge-file), which marks the conflict as always. Nothing is reordered that was
there before: the files are not strictly sorted, and an old entry keeps its place.

tools/git-setup.sh registers it (.gitattributes: CHANGELOG merge=changelog); git uses it in a pull --rebase, a
merge, a cherry-pick and when an autostash or stash pop comes back."""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

_HEADER = re.compile(r"^Changelog: (.*)$", re.M)
_TIME = "%d-%m-%Y %H:%M:%S"

Entries = dict[tuple[str, int], str]      # (header line, its ordinal among equal headers) -> the entry's text


def split(text: str) -> tuple[str, list[tuple[tuple[str, int], str]]]:
    """The text before the first entry, and the entries in order: each a key and its text from its "Changelog:"
    line up to the next one (blank lines included). A header that is in the file twice gets ordinals 0, 1, ..."""
    starts = [m.start() for m in _HEADER.finditer(text)]
    if not starts:
        return text, []
    seen: dict[str, int] = {}
    entries = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        header = chunk.split("\n", 1)[0].rstrip()
        key = (header, seen.get(header, 0))
        seen[header] = key[1] + 1
        entries.append((key, chunk))
    return text[:starts[0]], entries


def _when(key: tuple[str, int]) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(key[0][len("Changelog: "):].strip(), _TIME)
    except ValueError:
        return None


def _joined(preamble: str, entries: list[tuple[tuple[str, int], str]]) -> str:
    text = preamble + "".join(chunk for _, chunk in entries)
    return text if text.endswith("\n") or not text else text + "\n"


def merge(base: str, ours: str, theirs: str) -> str | None:
    """The merged CHANGELOG, or None when the sides changed the same entry (git's line merge then decides)."""
    base_pre, base_list = split(base)
    ours_pre, ours_list = split(ours)
    theirs_pre, theirs_list = split(theirs)
    base_map, ours_map, theirs_map = dict(base_list), dict(ours_list), dict(theirs_list)

    if theirs_pre != base_pre:
        if ours_pre not in (base_pre, theirs_pre):
            return None
        ours_pre = theirs_pre

    result = list(ours_list)
    # Entries theirs changed or removed since the base.
    for key, base_text in base_map.items():
        ours_text, theirs_text = ours_map.get(key), theirs_map.get(key)
        if theirs_text == base_text:
            continue                                            # theirs left it alone: ours decides
        if ours_text is not None and ours_text != base_text and ours_text != theirs_text:
            return None                                         # both changed it, differently
        if ours_text is None:
            continue                                            # ours removed it already
        index = next(i for i, (k, _) in enumerate(result) if k == key)
        if theirs_text is None:
            del result[index]
        else:
            result[index] = (key, theirs_text)
    # Entries theirs added since the base, in theirs' order: each goes in above the entry it sat above in theirs
    # (the first one below it that is in the result), and above our own new entries that are older than it.
    ours_new = {key for key, _ in ours_list if key not in base_map}
    for position, (key, text) in enumerate(theirs_list):
        if key in base_map:
            continue
        if key in ours_map:
            if ours_map[key] != text:
                return None                                     # the same entry written differently on both sides
            continue
        keys = [k for k, _ in result]
        anchor = next((k for k, _ in theirs_list[position + 1:] if k in keys), None)
        index = keys.index(anchor) if anchor is not None else len(result)
        when = _when(key)
        while index > 0 and keys[index - 1] in ours_new and when is not None:
            above = _when(keys[index - 1])
            if above is None or above >= when:
                break
            index -= 1
        result.insert(index, (key, text))
    return _joined(ours_pre, result)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    base, ours, theirs = (Path(p) for p in argv)
    texts = []
    for path in (base, ours, theirs):
        with path.open(encoding="utf-8", newline="") as f:      # as the bytes are: no line ending translated
            texts.append(f.read())
    merged = merge(*texts)
    if merged is None:
        # git's own line merge: the conflict is marked in OURS, and its exit code counts the conflicts.
        result = subprocess.run(["git", "merge-file", "-L", "ours", "-L", "base", "-L", "theirs",
                                 str(ours), str(base), str(theirs)])
        return 1 if result.returncode else 0
    with ours.open("w", encoding="utf-8", newline="") as f:
        f.write(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
