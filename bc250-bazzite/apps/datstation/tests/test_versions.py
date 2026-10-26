# SPDX-License-Identifier: GPL-3.0-or-later
"""The system software files: every shipped file loads, in the three shapes the loader knows, and the page's
HTML carries what an entry has."""

from __future__ import annotations

import json

from datstation.versions import PAGES, Entry, count, load_page, load_series
from datstation.versions_page import entry_html, series_html


def test_every_shipped_file_loads():
    totals = {page.file: count(load_page(page)) for page in PAGES}
    assert totals == {"ps6_systemsoftware.json": 1, "ps5_systemsoftware.json": 71,
                      "psportal_systemsoftware.json": 16, "ps4_systemsoftware.json": 97,
                      "ps3_systemsoftware.json": 81, "psvita_systemsoftware.json": 54,
                      "psp_systemsoftware.json": 61, "ps2_systemsoftware.json": 208, "ps1_systemsoftware.json": 46}
    ps1 = load_page(PAGES[-1])
    assert ps1[0].id == "DTL1000" and ps1[0].heading == "DTLH1 Series"
    first = ps1[0].entries[0]
    assert first.model == "DTL-H1000" and first.region_code == "NTSC-J" and first.release_date == "1994-09-22"
    assert [name for name, _ in first.specs] == ["Region Free", "CD-R Copies", "A/V Direct Out", "Parallel Port",
                                                 "Serial Port"]
    ps5 = load_page(PAGES[1])
    assert len(ps5) == 1 and ps5[0].name == "" and ps5[0].entries[0].release_date.startswith("October")


def test_the_three_shapes_and_bad_files(tmp_path):
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps([{"version": "1.0", "release_date": "2020-01-01", "notes": "one note"}]))
    series = load_series(plain)
    assert len(series) == 1 and series[0].entries[0].notes == ("one note",) and series[0].entries[0].release_date \
        == "2020-01-01"
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"series": [{"id": "a", "name": "A_Series", "entries": [{"version": "2"}]}]}))
    assert load_series(wrapped)[0].heading == "A Series" and load_series(wrapped)[0].entries[0].version == "2"
    bad = tmp_path / "bad.json"
    bad.write_text("nope")
    assert load_series(bad) == [] and load_series(tmp_path / "missing.json") == []
    number = tmp_path / "number.json"
    number.write_text("5")
    assert load_series(number) == []


def test_the_html_of_an_entry():
    entry = Entry("System Software v1.0", "2020-01-01", size="1 GB", model="CUH-1000", region="Japan",
                  region_code="NTSC-J", color="Black & White", notes=("A <note>",), region_free="Yes")
    html = entry_html(entry)
    for text in ("System Software v1.0", "Release Date: 2020-01-01", "Region: Japan [NTSC-J] (CUH-1000)",
                 "Color: Black &amp; White", "Size: 1 GB", "Region Free: Yes", "• A &lt;note&gt;"):
        assert text in html
    assert "No system software data" in series_html([])
