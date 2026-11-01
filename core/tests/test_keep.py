# SPDX-License-Identifier: GPL-3.0-or-later
"""keep: the rows of what would go, their marks and sizes, and the deleting."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from bc250_core import keep
from bc250_core.keep import Item


def test_every_row_starts_as_delete_and_a_turns_it_to_keep_and_back(tmp_path: Path) -> None:
    items = [Item("game", "BCES00569 (game)", (tmp_path,)), Item("steam", "Steam shortcut")]
    assert [i.key for i in keep.chosen(items)] == ["game", "steam"]
    assert keep.toggle(items, "game").delete is False
    assert [i.key for i in keep.chosen(items)] == ["steam"]
    keep.toggle(items, "game")
    assert items[0].delete is True
    assert keep.toggle(items, "nothing") is None


def test_rows_say_the_mark_what_it_is_and_the_size(tmp_path: Path) -> None:
    (tmp_path / "game").mkdir()
    (tmp_path / "game" / "eboot.bin").write_bytes(b"x" * 2048)
    (tmp_path / "game" / "sub").mkdir()
    (tmp_path / "game" / "sub" / "data").write_bytes(b"x" * 1024)
    items = [Item("game", "The game", (tmp_path / "game",)), Item("steam", "Steam shortcut")]
    keep.measure(items)
    assert items[0].size == 3072
    keep.toggle(items, "steam")
    assert keep.rows(items) == [("game", "Delete  ·  The game  ·  3.0 KB"), ("steam", "Keep  ·  Steam shortcut")]
    assert keep.total(items) == 3072


def test_sizes_read_as_a_person_reads_them() -> None:
    assert keep.human(512) == "512 B"
    assert keep.human(3 * 1024 * 1024 // 2) == "1.5 MB"
    assert keep.human(int(28.1 * 1024 ** 3)) == "28.1 GB"
    assert keep.human(3 * 1024 ** 4) == "3072.0 GB"


def test_a_missing_path_has_no_size(tmp_path: Path) -> None:
    assert keep.size_of(tmp_path / "gone") == 0


def test_delete_takes_files_and_folders_read_only_ones_too(tmp_path: Path) -> None:
    folder = tmp_path / "game"
    (folder / "sce_sys").mkdir(parents=True)
    locked = folder / "sce_sys" / "param.sfo"
    locked.write_bytes(b"sfo")
    os.chmod(locked, stat.S_IREAD)
    package = tmp_path / "game.pkg"
    package.write_bytes(b"pkg")
    os.chmod(package, stat.S_IREAD)
    assert keep.delete([folder, package, tmp_path / "gone"]) == []
    assert not folder.exists() and not package.exists()
