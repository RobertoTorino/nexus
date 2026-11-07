# SPDX-License-Identifier: GPL-3.0-or-later
"""The static content: the region tables are square, and the pages render their HTML."""

from __future__ import annotations

from datstation import ROOT, history, regions
from datstation.history_page import page_html as history_html
from datstation.regions_page import page_html as regions_html, table_html


def test_the_history_html_and_links():
    html = history_html()
    assert html.count("<h3>") == 2 * len(history.CONSOLES)
    assert html.count("href='search:PlayStation 2 (2000)'") == 2           # the name in the totals and the legacy
    assert "<img" not in html and "image:" not in html                       # no pictures (their rights were not ours)
    assert history.search_url("Sony PSX (2003)") == "https://www.google.com/search?q=Sony%20PSX%20%282003%29&tbm=isch"


def test_no_console_pictures_ship():
    assert not (ROOT / "images" / "consoles").exists()


def test_the_region_tables_are_square():
    for section in regions.SECTIONS:
        if section.table is not None:
            assert all(len(row) == len(section.table.headers) for row in section.table.rows), section.console
    html = regions_html()
    assert html.count("<h3>") == 6 and "Coming soon" in html and "PPSA" in html and "2B: United Kingdom" in html
    table = table_html(regions.Table(("A", "B"), (("1", "<2>"),)))
    assert "<th>A</th>" in table and "<td>&lt;2&gt;</td>" in table
