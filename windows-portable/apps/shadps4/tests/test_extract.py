# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract PKG (extract.py), with the synthetic package of the BC250 app's tests (pkg_builder.py): a package's ID,
title and category read before it is unpacked; a game unpacked into its ID's folder byte for byte, the files counted;
a folder that is there never written into; an update beside its game, a second one only replacing the first when
asked and when every file was written, as the BC250 app's Extract PKG window does it."""

from __future__ import annotations

import shutil

import pytest

from pkg_builder import build_pkg, default_tree
from shadps4_manager import extract


def test_a_package_says_what_it_is(built_pkg, tmp_path):
    package = extract.read_package(built_pkg.path)
    assert (package.title_id, package.title, package.category, package.kind) == (
        built_pkg.title_id, "Synthetic Test Title", "gd", "game")
    other = tmp_path / "notes.pkg"
    other.write_bytes(b"not a package at all" * 10)
    with pytest.raises(extract.ExtractError, match="is not a PS4 package"):
        extract.read_package(other)


def test_a_game_is_unpacked_into_its_ids_folder(built_pkg, tmp_path):
    out = tmp_path / "games"
    out.mkdir()
    steps, lines = [], []
    folder, written, failed = extract.unpack(extract.read_package(built_pkg.path), out,
                                             progress=lambda done, total: steps.append((done, total)),
                                             log=lines.append)
    assert folder == out / built_pkg.title_id and failed == 0 and written == steps[-1][0] == steps[-1][1]
    assert [done for done, _ in steps] == list(range(1, written + 1))
    assert (folder / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]
    assert (folder / "data" / "big.bin").read_bytes() == built_pkg.expected_files["data/big.bin"]
    assert (folder / "sce_sys" / "param.sfo").read_bytes() == built_pkg.sce_sys_plain["param.sfo"]
    assert (folder / extract.FILE_LIST).is_file() and not (folder / extract.ERRORS).exists()
    assert any(f"{written} file(s) into" in line for line in lines)
    with pytest.raises(extract.ExtractError, match="never writes over a folder"):    # the same place again
        extract.unpack(extract.read_package(built_pkg.path), out)
    assert (folder / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]


def test_an_update_goes_beside_its_game_and_is_replaced_only_when_asked(built_pkg, tmp_path, monkeypatch):
    out = tmp_path / "games"
    out.mkdir()
    game, update = out / built_pkg.title_id, out / f"{built_pkg.title_id}-UPDATE"
    first = build_pkg(tmp_path / "update1.pkg", default_tree(), category="gp", app_ver="01.01")
    package = extract.read_package(first.path)
    assert package.kind == "update" and extract.target(out, package) == (game, False)
    extract.unpack(package, out)                    # without its game: into the ID's folder, as a patched game
    assert (game / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]
    shutil.rmtree(game)

    extract.unpack(extract.read_package(built_pkg.path), out)
    lines = []
    assert extract.target(out, package) == (update, True)
    assert extract.unpack(package, out, log=lines.append)[0] == update
    assert any("lays over the game" in line for line in lines)
    assert (game / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]
    assert (update / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]

    built = build_pkg(tmp_path / "update2.pkg", default_tree(), category="gp", app_ver="01.02")
    second = extract.read_package(built.path)
    with pytest.raises(extract.ExtractError):       # not asked to replace it
        extract.unpack(second, out)
    assert (update / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]
    extract.unpack(second, out, replace_update=True)
    assert sorted(p.name for p in out.iterdir()) == [game.name, update.name]
    assert (update / "eboot.bin").read_bytes() == built.expected_files["eboot.bin"]

    # One that fails to unpack leaves the update there as it was.
    third = extract.read_package(build_pkg(tmp_path / "update3.pkg", default_tree(), category="gp",
                                           app_ver="01.03").path)
    monkeypatch.setattr(extract.PKG, "extract_files", lambda self, index: (_ for _ in ()).throw(OSError("bad")))
    with pytest.raises(extract.ExtractError, match="stays as it was"):
        extract.unpack(third, out, replace_update=True)
    assert (update / "eboot.bin").read_bytes() == built.expected_files["eboot.bin"]
    assert sorted(p.name for p in out.iterdir()) == [game.name, update.name]


def test_files_that_fail_are_counted_and_named(built_pkg, tmp_path, monkeypatch):
    out = tmp_path / "games"
    out.mkdir()
    original = extract.PKG.extract_files

    def flaky(self, index):
        if index == 0:
            raise OSError("the card is full")
        original(self, index)
    monkeypatch.setattr(extract.PKG, "extract_files", flaky)
    folder, written, failed = extract.unpack(extract.read_package(built_pkg.path), out)
    assert failed == 1 and written > 0
    assert "File 1: the card is full" in (folder / extract.ERRORS).read_text(encoding="utf-8")
