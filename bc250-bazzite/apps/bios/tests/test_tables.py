# SPDX-License-Identifier: GPL-3.0-or-later
"""The built-in tables, and (optionally) a real dump: BC250_BIOS_DUMP=/path/to/dump.bin runs the last test."""

import os
from pathlib import Path

import pytest

from bios_reader import bios, table


def test_every_stock_release_has_a_table_with_its_fingerprints():
    for version, stock in bios.STOCK.items():
        found_version, date, formsets, defaults = table.load_table(table.table_path(version))
        assert (found_version, date) == (version, stock["date"])
        assert {fs.guid: fs.sha256 for fs in formsets} == stock["formsets"]
        assert defaults


def test_p500_table_screens():
    _, _, formsets, _ = table.load_table(table.table_path("P5.00"))
    titles = {fs.title for fs in formsets}
    assert {"Setup", "AMD CBS"} <= titles
    cbs = next(fs for fs in formsets if fs.title == "AMD CBS")
    assert cbs.varstores[0x5000].size == bios.STOCK["P5.00"]["amdsetup_size"]


@pytest.mark.skipif(not os.environ.get("BC250_BIOS_DUMP"), reason="set BC250_BIOS_DUMP to a dump to run this")
def test_real_dump():
    b = bios.load_dump(Path(os.environ["BC250_BIOS_DUMP"]))
    v = bios.verdict(b)
    assert b.version and v.kind in ("stock", "modded", "unknown")
    if b.version in bios.STOCK and v.kind == "stock":
        assert v.certain
