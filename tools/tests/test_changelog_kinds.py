# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic versioning (owner, 15-10-2026): every entry in a versioned CHANGELOG (an app's, core's, the portal's)
starts with the kind of change it is, Breaking., Added. or Fixed., so the release tool can offer the version it asks
for. The release tools' own entries (Release x.y.z., Version x.y.z., a withdrawal) need none. Entries from before the
rule stay as they were. The root CHANGELOG is Nexus's, versioned since 28-10-2026 (the root VERSION): its entries
from then on too."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
SINCE = datetime.datetime(2026, 10, 15, 23, 30)        # the rule's start, Amsterdam time like the entries
NEXUS_SINCE = datetime.datetime(2026, 10, 28, 13, 15, 16)   # the root CHANGELOG's: Nexus's VERSION came
WORDS = ("Breaking.", "Added.", "Fixed.")
TOOL_ENTRIES = ("Release ", "Version ", "Withdrawn: ", "Withdrawal of ")
HEADER = re.compile(r"^Changelog: (\d\d-\d\d-\d{4} \d\d:\d\d:\d\d)$", re.M)


def versioned_changelogs() -> list[Path]:
    return sorted(path.parent / "CHANGELOG" for path in SUITE.glob("**/VERSION")
                  if (path.parent / "CHANGELOG").is_file() and ".venv" not in str(path) and "/tests/" not in str(path))


def new_entries(text: str, since: datetime.datetime = SINCE) -> list[tuple[str, str]]:
    """(stamp, body) of each entry dated from *since* on."""
    heads = list(HEADER.finditer(text))
    out = []
    for head, nxt in zip(heads, heads[1:] + [None]):
        stamp = datetime.datetime.strptime(head.group(1), "%d-%m-%Y %H:%M:%S")
        if stamp >= since:
            out.append((head.group(1), text[head.end():nxt.start() if nxt else len(text)].strip()))
    return out


def unmarked(text: str, since: datetime.datetime = SINCE) -> list[str]:
    return [f"{stamp}: {body[:60]}" for stamp, body in new_entries(text, since)
            if not body.startswith(WORDS + TOOL_ENTRIES)]


def since(path: Path) -> datetime.datetime:
    return NEXUS_SINCE if path == SUITE / "CHANGELOG" else SINCE


def test_the_rule_reads_entries_as_written():
    text = ("Changelog: 16-10-2026 10:00:00\n\nA change without its kind.\n\n"
            "Changelog: 16-10-2026 09:00:00\n\nAdded. A button.\n\n"
            "Changelog: 16-10-2026 08:00:00\n\nRelease 0.2.0.\n\n"
            "Changelog: 01-10-2026 08:00:00\n\nFrom before the rule.\n")
    assert unmarked(text) == ["16-10-2026 10:00:00: A change without its kind."]


def test_new_entries_say_what_kind_of_change_they_are():
    changelogs = versioned_changelogs()
    assert SUITE / "bc250-bazzite" / "portal" / "CHANGELOG" in changelogs and SUITE / "core" / "CHANGELOG" in changelogs
    assert SUITE / "CHANGELOG" in changelogs                                  # Nexus's own, with the root VERSION
    problems = [f"{path.relative_to(SUITE)} {line}" for path in changelogs
                for line in unmarked(path.read_text(encoding="utf-8"), since(path))]
    assert not problems, "start these CHANGELOG entries with Breaking., Added. or Fixed.:\n" + "\n".join(problems)
