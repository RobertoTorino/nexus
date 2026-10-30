# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py): the plan Update Steam carries out (the marked games in, the others out, the shortcuts of
games no longer installed out too), whether it would change anything, and the suite's own folders for the key and the
pictures."""

from __future__ import annotations

from pathlib import Path

from vita3k_manager import library
from vita3k_manager.games import Game

ONE = Game(Path(r"C:\fs\ux0\app\PCSB00001"), "One", "PCSB00001")
TWO = Game(Path(r"C:\fs\ux0\app\PCSB00002"), "Two", "PCSB00002")


def test_the_plan():
    add, remove = library.plan([ONE, TWO], {"PCSB00001"}, {"PCSB00002": "[PS Vita] Two", "PCSB09999": "[PS Vita] Gone"})
    assert add == [ONE]
    assert [g.name for g in remove] == ["PCSB00002", "PCSB09999"] and remove[1].title == "[PS Vita] Gone"


def test_pending():
    assert not library.pending([ONE, TWO], set(), {})
    assert library.pending([ONE], {"PCSB00001"}, {})                                # in
    assert not library.pending([ONE], {"PCSB00001"}, {"PCSB00001": "[PS Vita] One"})
    assert library.pending([ONE], {"PCSB00001"}, {"PCSB00001": "[PS Vita] One"}, {"PCSB00001"})   # not the play mode
    assert library.pending([ONE], {"PCSB00001"}, {"PCSB00001": "[PS Vita] Old name"})   # renamed
    assert library.pending([ONE], set(), {"PCSB00001": "[PS Vita] One"})            # out


def test_the_suites_folders(tmp_path):
    assert library.key_file() == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    assert library.covers_home() == (tmp_path / "Local" / "windows-portable-suite" / "windows-portable-vita3k"
                                     / "covers")
