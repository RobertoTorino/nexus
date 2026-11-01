# SPDX-License-Identifier: GPL-3.0-or-later
r"""Your games (library.py): the app's own Games\Vita folders, the firmware files and the games waiting there, Remove
game's folders, the plan Update Steam carries out (the marked games in, the others out, the shortcuts of games no
longer installed out too), whether it would change anything, and the suite's own folders for the key and the
pictures."""

from __future__ import annotations

from pathlib import Path

from conftest import make_dump, make_game, make_pkg, make_vpk
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


def test_the_apps_own_folders(tmp_path):
    r"""The app's own folders (owner, 30-10-2026: the games and the firmware are put there, no folder is chosen):
    Games\Vita in the user's folder with its Firmware folder, made when missing, then Games\Vita on a removable drive
    that has one; an empty card slot is none."""
    home = tmp_path / "me"
    card, empty = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "Vita").mkdir(parents=True)
    empty.mkdir()

    class EmptySlot:                    # a card reader without a card: Windows raises when asked about it
        def __truediv__(self, other):
            return self

        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [EmptySlot(), card, empty]) == [home / "Games" / "Vita",
                                                                       card / "Games" / "Vita"]
    assert library.firmware_home(home) == home / "Games" / "Vita" / "Firmware" and library.firmware_home(home).is_dir()


def test_the_firmware_files(tmp_path):
    """The .PUP files in the Firmware folder and a folder right below it, the largest first; nothing else."""
    home = tmp_path / "me"
    assert library.firmware_files(home) == []                  # no folder yet
    folder = library.firmware_home(home)
    (folder / "Fonts" / "deeper").mkdir(parents=True)
    (folder / "PSP2UPDAT.PUP").write_bytes(b"s" * 200)
    (folder / "Fonts" / "PSP2UPDAT.PUP").write_bytes(b"f" * 100)
    (folder / "Fonts" / "deeper" / "PSP2UPDAT.PUP").write_bytes(b"d")
    (folder / "readme.txt").write_text("")
    assert library.firmware_files(home) == [folder / "PSP2UPDAT.PUP", folder / "Fonts" / "PSP2UPDAT.PUP"]
    assert library.stamp(folder / "PSP2UPDAT.PUP").startswith("200:") and library.stamp(folder / "gone.pup") == ""


def test_the_games_waiting_to_be_installed(tmp_path):
    """Each .vpk, .zip, .pkg and dumped folder in the game folders and below them, by title; a game installed already
    is left out (not an update, nor a .pkg), and so are the Firmware folder and what is inside a dumped folder."""
    own = tmp_path / "me" / "Games" / "Vita"
    persona = make_vpk(own / "Persona.vpk", "Persona 4 Golden", "PCSB00245")
    make_vpk(own / "old" / "Gravity.zip", "Gravity Rush", "PCSA00011")      # installed: left out
    update = make_vpk(own / "Gravity-update.vpk", "Gravity Rush", "PCSA00011", category="gp")
    dump = make_dump(own / "PCSE00001", "Uncharted", "PCSE00001")
    make_vpk(dump / "inside.vpk", "Inside", "PCSE00002")                    # inside a dump: not looked at
    pkg = make_pkg(own / "pkgs" / "Tearaway.pkg", "PCSA00099")
    (own / "pkgs" / "notes.pkg").write_bytes(b"not a package")
    (own / "Firmware").mkdir()
    make_vpk(own / "Firmware" / "Nope.vpk", "Nope", "PCSE00003")
    (own / "broken.vpk").write_bytes(b"PK")
    found = library.waiting([own, tmp_path / "missing"], {"PCSA00011"})
    assert [(w.path, w.kind, w.title, w.title_id) for w in found] == [
        (own / "broken.vpk", "VPK", "", ""),
        (update, "VPK", "Gravity Rush", "PCSA00011"),
        (own / "pkgs" / "notes.pkg", "PKG", "", ""),
        (persona, "VPK", "Persona 4 Golden", "PCSB00245"),
        (pkg, "PKG", "", "PCSA00099"),
        (dump, "Folder", "Uncharted", "PCSE00001")]
    assert found[4].package and not found[3].package and found[1].update
    assert library.package_id(pkg) == "PCSA00099" and library.package_id(persona) == ""


def test_remove_game_offers_the_game_its_update_and_its_shortcut(tmp_path):
    r"""Remove game's rows for the keep page: the game in ux0\app, its update and extra content when there, each a
    row marked Delete, then its Steam shortcut when it is in Steam; the saves are never offered; a game elsewhere has
    none."""
    fs = tmp_path / "fs"
    game = make_game(fs, "Persona 4 Golden", "PCSB00245")
    patch = make_game(fs, "Persona 4 Golden", "PCSB00245", kind="patch")
    saves = fs / "ux0" / "user" / "00" / "savedata" / "PCSB00245"
    saves.mkdir(parents=True)
    from vita3k_manager.games import read_game
    folders = library.removal(read_game(game), fs)
    assert folders == [game, patch]
    assert library.removal(Game(tmp_path / "elsewhere" / "PCSB00245", "X"), fs) == []
    items = library.removal_items(folders, in_steam=True)
    assert [(i.key, i.label, i.paths, i.delete) for i in items] == [
        (str(game), "The game, ux0\\app\\PCSB00245", (game,), True),
        (str(patch), "Its update, ux0\\patch\\PCSB00245", (patch,), True),
        (library.STEAM_ITEM, "Its shortcut in Steam", (), True)]
    assert [i.key for i in library.removal_items(folders, in_steam=False)] == [str(game), str(patch)]
