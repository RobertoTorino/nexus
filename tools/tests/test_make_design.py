# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/make_design.py: DESIGN.md and its samples are what the script writes, each sample on a backdrop its color
reads on, a translucent color over a checkerboard; and the wikis' stylesheets have exactly the colors their
listings name, so a color added to a wiki is added to DESIGN.md too."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_design  # noqa: E402


def test_design_is_up_to_date():
    changed, stale = make_design.differences(make_design.build())
    assert not changed and not stale, f"run python3 tools/make_design.py: {changed + stale}"


def test_a_text_sample_sits_on_the_backdrop_it_reads_on():
    make_design.FILES.clear()
    light_text = make_design.FILES[make_design.text_svg("#ffffff")]
    dark_text = make_design.FILES[make_design.text_svg("#1e2226")]
    assert f'fill="{make_design.DARK}"' in light_text and f'fill="{make_design.LIGHT}"' in dark_text


def test_a_translucent_colour_shows_over_a_checkerboard():
    make_design.FILES.clear()
    tint = make_design.FILES[make_design.block_svg("#0a55b01a")]
    solid = make_design.FILES[make_design.block_svg("#0a55b0")]
    assert "<pattern" in tint and 'fill="#0a55b0" fill-opacity="0.102"' in tint
    assert "<pattern" not in solid and "fill-opacity" not in solid.split("stroke")[0]


def test_every_colour_of_the_wikis_is_listed():
    assert make_design.unlisted() == [], "change the listing in tools/make_design.py and run it"


def test_unlisted_reports_both_directions(tmp_path):
    sheet = tmp_path / make_design.SUITE_DIR / "docs" / "stylesheets" / "suite.css"
    sheet.parent.mkdir(parents=True)
    listed = {hex_ for hex_, _ in make_design.WIKI_TEXT + make_design.WIKI_BLOCKS}
    sheet.write_text("/* #abcdef in a comment is not a color */\n:root { --a: #123; --b: #5835CE; }\n",
                     encoding="utf-8")
    report = make_design.unlisted(tmp_path)
    assert f"{make_design.SUITE_DIR}/docs/stylesheets/suite.css has #112233, which the listing lacks" in report
    assert "#abcdef" not in "\n".join(report) and "#5835ce" not in "\n".join(report)
    assert sum("no longer has" in line for line in report) == len(listed) - 1
    assert make_design.unlisted(tmp_path / "nowhere") == [f"{p} is missing" for p in make_design.STYLESHEETS]


def test_check_lists_changed_and_unused_samples(tmp_path):
    folder = tmp_path / make_design.COLORS
    folder.mkdir(parents=True)
    (folder / "block-123456.svg").write_text("old", encoding="utf-8")
    (tmp_path / "DESIGN.md").write_text("# Design\n", encoding="utf-8")
    changed, stale = make_design.differences({"DESIGN.md": "# Design, new\n"}, tmp_path)
    assert changed == ["DESIGN.md"] and stale == [f"{make_design.COLORS}/block-123456.svg"]
