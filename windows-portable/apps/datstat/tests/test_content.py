# SPDX-License-Identifier: GPL-3.0-or-later
"""The static content: the history, the region tables and the system software files, and the plain text the pages
show of them; the tiles' symbols."""

from __future__ import annotations

import json

from dat_station import ROOT, history, regions
from dat_station.panes import (console_totals, entry_text, features, section_text, series_text, short_title,
                               symbol_pixmap, table_text)
from dat_station.quiz import DATA_CATEGORIES
from dat_station.versions import PAGES, Entry, Page, count, load_page, load_series


def test_the_history_and_its_picture_search():
    assert len(history.CONSOLES) == 9 and history.CONSOLES[0].name == "PlayStation (1994)"
    assert console_totals(history.CONSOLES[0]) == "102.4M sold • 3,168 titles"
    assert history.search_url("Sony PSX (2003)") == "https://www.google.com/search?q=Sony%20PSX%20%282003%29&tbm=isch"


def test_no_console_pictures_ship():
    assert not (ROOT / "images" / "consoles").exists()


def test_the_region_tables_are_square_and_their_text():
    for section in regions.SECTIONS:
        if section.table is not None:
            assert all(len(row) == len(section.table.headers) for row in section.table.rows), section.console
    assert [s.console for s in regions.SECTIONS][:2] == ["PlayStation 6", "PlayStation 5"]
    assert section_text(regions.SECTIONS[0]) == "PlayStation 6\n\nComing soon …"
    ps1 = section_text(regions.SECTIONS[-1])
    assert "Prefix\tRegion\tDescription\nSCPS\tJapan\tFirst-Party" in ps1 and "2B: United Kingdom" in ps1
    assert "PPSA\tUS / EU\tRetail + digital" in section_text(regions.SECTIONS[1])
    assert table_text(regions.Table(("A", "B"), (("1", "<2>"),))) == "A\tB\n1\t<2>"


def test_every_shipped_system_software_file_loads():
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
    assert [short_title(page) for page in PAGES][:3] == ["PlayStation 6", "PlayStation 5", "PlayStation Portal"]
    text = series_text(PAGES[-1], ps1)
    assert text.startswith("PlayStation 1 System Software\n46 versions\n\nDTLH1 SERIES\n\n")


def test_the_three_shapes_and_bad_files(tmp_path):
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps([{"version": "1.0", "release_date": "2020-01-01", "notes": "one note"}]))
    series = load_series(plain)
    assert len(series) == 1 and series[0].entries[0].notes == ("one note",)
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"series": [{"id": "a", "name": "A_Series", "entries": [{"version": "2"}]}]}))
    assert load_series(wrapped)[0].heading == "A Series" and load_series(wrapped)[0].entries[0].version == "2"
    bad = tmp_path / "bad.json"
    bad.write_text("nope")
    assert load_series(bad) == [] and load_series(tmp_path / "missing.json") == []


def test_the_text_of_an_entry():
    entry = Entry("System Software v1.0", "2020-01-01", size="1 GB", model="CUH-1000", region="Japan",
                  region_code="NTSC-J", color="Black & White", notes=("A <note>",), region_free="Yes")
    assert entry_text(entry) == ("System Software v1.0\nRelease Date: 2020-01-01\nRegion: Japan [NTSC-J] (CUH-1000)\n"
                                 "Color: Black & White\nSize: 1 GB\nRegion Free: Yes\n• A <note>")
    page = Page("Test System Software", "test.json")
    assert series_text(page, []) == "Test System Software\n0 versions\n\nNo system software data available."


def test_the_tiles(qapp):
    tiles = features(1436, len(DATA_CATEGORIES))
    assert [f.key for f in tiles] == ["quiz", "history", "versions", "regions", "guides", "news", "scores"]
    assert tiles[0].text.startswith("1,436 questions in 11 categories")
    assert all(len(f.tile) <= 19 for f in tiles)                   # one line on a tile
    for feature in tiles:
        image = symbol_pixmap(feature.shape, feature.color).toImage()
        assert image.pixelColor(64, 64).alpha() == 0 or feature.shape in ("star", "diamond_filled", "cross")
        drawn = sum(image.pixelColor(x, y).alpha() > 0 for x in range(0, 128, 4) for y in range(0, 128, 4))
        assert drawn > 20, feature.shape                            # the shape is there
