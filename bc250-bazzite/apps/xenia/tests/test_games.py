# SPDX-License-Identifier: GPL-3.0-or-later
"""The game scan (games.py): Xbox 360 disc images at each of the game partition's places, XEX files with their title
ID and an unpacked disc's default.xex, .zar archives, Games on Demand and Arcade packages with their name, the other
packages and files that are no game left out, a game found twice and depth."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest
from conftest import make_iso, make_package, make_xex, package_bytes, xex_bytes

from xenia_manager.games import GAME_PARTITIONS, Game, package, read_game, scan, xex_title_id
from xenia_manager import games


@pytest.mark.parametrize("partition", GAME_PARTITIONS)
def test_a_disc_image_at_each_place(tmp_path, partition):
    iso = make_iso(tmp_path / "Halo 3.iso", partition)
    assert read_game(iso) == Game(iso, "Halo 3", "", "iso") and read_game(iso).folder == tmp_path


def test_what_is_no_xbox_360_disc_is_not_a_game(tmp_path):
    other = tmp_path / "linux.iso"
    other.write_bytes(b"\0" * 0x20000)
    assert read_game(other) is None and read_game(tmp_path / "missing.iso") is None


def test_the_title_id_of_an_xex():
    assert xex_title_id(xex_bytes(0x4D5307E6)) == "4D5307E6"
    assert xex_title_id(xex_bytes()[:0x20]) == ""                                # the execution info cut off
    assert xex_title_id(b"MZ" + b"\0" * 0x100) is None


def test_an_unpacked_disc_is_its_default_xex(tmp_path):
    default = make_xex(tmp_path / "Gears of War" / "default.xex", 0x4D5307D5)
    make_xex(tmp_path / "Gears of War" / "module.xex")
    homebrew = make_xex(tmp_path / "homebrew" / "Snake.xex", 0x00000001)
    assert scan([tmp_path]) == [Game(default, "Gears of War", "4D5307D5", "xex"),
                                Game(homebrew, "Snake", "00000001", "xex")]


def test_a_zar_is_listed_under_its_name(tmp_path):
    (tmp_path / "Forza.zar").write_bytes(b"\0" * 64)
    assert scan([tmp_path]) == [Game(tmp_path / "Forza.zar", "Forza", "", "zar")]


def test_games_on_demand_and_arcade_packages(tmp_path):
    god = make_package(tmp_path / "Content", "Halo 3")
    xbla = make_package(tmp_path / "Content", "Braid", 0x000D0000, 0x58410954)
    assert scan([tmp_path]) == [Game(xbla, "Braid", "58410954", "xbla"), Game(god, "Halo 3", "4D5307E6", "god")]


def test_other_packages_are_no_games(tmp_path):
    assert package(package_bytes(content_type=0x00000002)) is None                 # downloadable content
    assert package(package_bytes(content_type=0x000B0000)) is None                 # a title update
    assert package(package_bytes(magic=b"NOPE")) is None
    assert package(package_bytes(magic=b"CON "))[0] == "god"
    dlc = make_package(tmp_path, "Map Pack", 0x00000002)
    loose = tmp_path / "00007000" / "notes"
    loose.parent.mkdir()
    loose.write_bytes(b"\0" * 0x2000)
    assert read_game(dlc) is None and scan([tmp_path]) == []


def test_a_package_without_a_name_is_named_after_its_file(tmp_path):
    god = make_package(tmp_path, "", file="F00D")
    assert read_game(god).title == "F00D"


def test_the_scan_sorts_finds_once_and_stops_at_a_depth(tmp_path):
    make_iso(tmp_path / "b" / "Zed.iso")
    make_iso(tmp_path / "a" / "apple.iso")
    deep = tmp_path
    for part in "1234567":
        deep = deep / part
    make_iso(deep / "Deep.iso")
    make_iso(tmp_path / ".hidden" / "Hidden.iso")
    games = scan([tmp_path, tmp_path / "a"])                                       # "a" is below the first folder too
    assert [g.title for g in games] == ["apple", "Zed"]
    assert scan([tmp_path / "missing"]) == []


def test_a_linked_game_is_counted_once(tmp_path):
    iso = make_iso(tmp_path / "one" / "Game.iso")
    (tmp_path / "two").mkdir()
    (tmp_path / "two" / "Game.iso").symlink_to(iso)
    assert len(scan([tmp_path])) == 1


# A failing or half-mounted SD card (29-10-2026, found on Windows with an empty card slot): asking about anything on it
# raises EIO, which Python's pathlib (3.12) passes on rather than answering no. The scan skips it and goes on.

class Unreadable:
    """A folder entry of a failing card: os.scandir lists it, asking what it is raises."""

    def __init__(self, path: Path):
        self.path, self.name = str(path), path.name

    def is_file(self, follow_symlinks: bool = True) -> bool:
        raise OSError(errno.EIO, "Input/output error", self.path)

    def is_dir(self, follow_symlinks: bool = True) -> bool:
        raise OSError(errno.EIO, "Input/output error", self.path)


def failing_card(monkeypatch, card: Path, root: Path | None = None) -> None:
    """Everything below *card* raises on is_file() and is_dir(); *root* lists an Unreadable entry beside its own."""
    real_file, real_dir, real_scandir = Path.is_file, Path.is_dir, os.scandir

    def broken(path) -> bool:
        return str(path).startswith(str(card))

    def is_file(self, *args, **kwargs):
        if broken(self):
            raise OSError(errno.EIO, "Input/output error", str(self))
        return real_file(self, *args, **kwargs)

    def is_dir(self, *args, **kwargs):
        if broken(self):
            raise OSError(errno.EIO, "Input/output error", str(self))
        return real_dir(self, *args, **kwargs)

    def scandir(path):
        entries = list(real_scandir(path))
        if broken(path):                                # the card lists its entries, none can be asked about
            return [Unreadable(Path(entry.path)) for entry in entries]
        return entries + [Unreadable(Path(path) / "card")] if root is not None and Path(path) == root else entries

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "is_dir", is_dir)
    if hasattr(games, "os"):                            # the scans list folders with os.scandir
        monkeypatch.setattr(games.os, "scandir", scandir)


def test_a_failing_card_ends_no_scan(tmp_path, monkeypatch):
    iso = make_iso(tmp_path / "Games" / "Halo 3.iso")
    failing_card(monkeypatch, tmp_path / "card", tmp_path / "Games")
    assert [game.file for game in scan([tmp_path / "Games", tmp_path / "card"])] == [iso]
