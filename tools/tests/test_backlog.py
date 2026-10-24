# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/backlog.py: the items on hold in MIGRATION.md, each once, with its section, title and line."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backlog  # noqa: E402

SUITE = Path(__file__).resolve().parents[2]

SAMPLE = """# Plan

## Open

1. A step that is not held.
2. **Board test**: waits for the second PS4 (on hold
   until it arrives); more text, and on hold again in the same item.

A paragraph that is on hold, without a list marker and with many more words than the title shows here.

## Candidates

- **Windows portal (on hold, owner 15-10-2026).** Long text.
- **Something else.** Not held.
"""


def test_items_on_hold_once_each_with_section_title_and_line():
    found = backlog.items(SAMPLE)
    assert [(i.line, i.section, i.title) for i in found] == [
        (6, "Open", "Board test"),
        (9, "Open", "A paragraph that is on hold, without a list marker and with …"),
        (13, "Candidates", "Windows portal (on hold, owner 15-10-2026)"),
    ]


def test_body_groups_by_section_and_links_the_lines():
    text = backlog.body(backlog.items(SAMPLE))
    assert text.startswith("3 items on hold in MIGRATION.md.")
    assert "### Open" in text and "### Candidates" in text
    assert "- [Board test](https://github.com/RobertoTorino/nexus/blob/main/MIGRATION.md#L6) (line 6)" \
        in text
    assert "\n\n\n" not in text


def test_nothing_on_hold_prints_nothing(tmp_path, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text("## Open\n\n- **Done thing.**\n", encoding="utf-8")
    assert backlog.main(["--file", str(plan)]) == 0
    assert capsys.readouterr().out == ""


def test_the_real_backlog_reads():
    """MIGRATION.md itself: whatever is on hold there, each item has a title and a section."""
    found = backlog.items((SUITE / "MIGRATION.md").read_text(encoding="utf-8"))
    assert all(item.title and item.section for item in found)
