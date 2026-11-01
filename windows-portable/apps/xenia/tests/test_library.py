# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py), as shadPS4 Manager's are tested: the app's own Games\\Xbox360 folders (an empty card slot
left out), what Remove game deletes, Update Steam's plan, and Steam's shortcuts written into a Steam folder of a test
(never the real one), with Steam closed around it."""

from __future__ import annotations

from pathlib import Path

from bc250_core import keep, play, steam
from conftest import make_iso, make_package, make_xex, package_bytes
from xenia_manager import LOGO_PATH, ROOT, library, shortcuts
from xenia_manager.games import Game, scan

PROGRAM = Path(r"C:\emu\xenia_canary.exe")


def test_the_apps_own_folders(tmp_path):
    r"""The app's own folders (owner, 30-10-2026: fixed folders, no folder selecting): Games\Xbox360 in the user's
    folder, made when missing, then Games\Xbox360 on a removable drive that has one; an empty card slot is none."""
    home = tmp_path / "me"
    card, empty = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "Xbox360").mkdir(parents=True)
    empty.mkdir()

    class EmptySlot:                    # a card reader without a card: Windows raises when asked about it
        def __truediv__(self, other):
            return self

        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [EmptySlot(), card, empty]) == [home / "Games" / "Xbox360",
                                                                        card / "Games" / "Xbox360"]
    assert (home / "Games" / "Xbox360").is_dir()


def test_what_remove_game_offers_to_delete(tmp_path):
    r"""Remove game (owner, 30-10-2026; owner, 01-11-2026: the user decides what to keep): an .iso is its file, an
    unpacked disc its folder, a console package's title ID folder a row per part (the game, its title updates, its
    add-ons), so the add-ons can be kept; a package elsewhere is the file with its .data folder. A game folder of the
    list, or a folder holding another game, is never offered."""
    own = tmp_path / "Games" / "Xbox360"
    make_iso(own / "Halo 3.iso")
    make_xex(own / "Gears" / "default.xex", 0x4D5307D5)
    make_xex(own / "Gears" / "media.xex", 0x4D5307D5)
    make_package(own, "Fable II", title_id=0x4D5307E6)
    (own / "4D5307E6" / "000B0000").mkdir()                     # its title update
    (own / "4D5307E6" / "00000002").mkdir()                     # its add-ons
    loose = own / "Lone" / "00007000" / "123456"                # its folder renamed: not the title ID's
    loose.parent.mkdir(parents=True)
    loose.write_bytes(package_bytes("Lone", title_id=0x584108A9))
    (loose.parent / "123456.data").mkdir()
    found = scan([own])
    games = {g.title: g for g in found}
    def offered(title):
        items, why = library.removal(games[title], [own], found)
        assert why == "" and all(item.delete for item in items)          # every row marked Delete at first
        return [(item.label, list(item.paths)) for item in items]
    assert offered("Halo 3") == [("Halo 3.iso (the game)", [own / "Halo 3.iso"])]
    assert offered("Gears") == [("Gears (the game's folder)", [own / "Gears"])]
    title = own / "4D5307E6"
    assert offered("Fable II") == [("the game (00007000)", [title / "00007000"]),
                                   ("Add-ons (00000002)", [title / "00000002"]),
                                   ("Title updates (000B0000)", [title / "000B0000"])]
    assert offered("Lone") == [("123456 (the game)", [loose, loose.parent / "123456.data"])]
    alone = Game(own / "default.xex", "Xbox360", "41560817", "xex")    # an unpacked disc that is the game folder
    items, why = library.removal(alone, [own], [alone])
    assert items == [] and "one of the app's game folders itself" in why
    inner = Game(own / "Gears" / "Extra" / "default.xex", "Extra", "", "xex")
    items, why = library.removal(games["Gears"], [own], [games["Gears"], inner])
    assert items == [] and "holds another game too (Extra)" in why


def test_the_title_folder_goes_once_it_is_empty(tmp_path):
    """tidy: the console's title ID folder is taken away when Remove game left nothing in it, kept with a part."""
    own = tmp_path / "Games" / "Xbox360"
    make_package(own, "Fable II", title_id=0x4D5307E6)
    (own / "4D5307E6" / "00000002").mkdir()
    game = scan([own])[0]
    keep.delete([game.folder])
    library.tidy(game)
    assert (own / "4D5307E6" / "00000002").is_dir()
    keep.delete([own / "4D5307E6" / "00000002"])
    library.tidy(game)
    assert not (own / "4D5307E6").exists() and own.is_dir()


def test_the_plan(tmp_path):
    a, b = Game(tmp_path / "A.iso", "A"), Game(tmp_path / "B.iso", "B")
    gone = tmp_path / "Gone.iso"
    in_steam = {str(b.file): "[X360] B", str(gone): "[X360] Gone"}
    add, remove = library.plan([a, b], {str(a.file)}, in_steam)
    assert add == [a] and [g.file for g in remove] == [b.file, gone]
    assert library.pending([a, b], {str(a.file)}, in_steam)
    assert not library.pending([b], {str(b.file)}, {str(b.file): "[X360] B"})              # as it is in Steam
    assert library.pending([b], {str(b.file)}, {str(b.file): "[X360] B"}, {str(b.file)})  # not the play mode yet


def test_update_steam_writes_the_shortcuts_with_steam_closed(qapp, tmp_path):
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    make_iso(tmp_path / "games" / "Halo 3.iso")
    game = scan([tmp_path / "games"])[0]
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    ok, text, found = library.update_steam(steam_dir, [game], [], PROGRAM, LOGO_PATH, {}, with_steam_closed)
    assert ok and closed == [True] and "1 game(s) in Steam" in text
    assert found == shortcuts.in_steam(steam_dir) == {str(game.file): "[X360] Halo 3"}   # read back at once
    item = steam.shortcuts(steam_dir)[0]
    assert item["Exe"] == f'"{play.launcher(ROOT)[0]}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert (config / "grid" / f"{item['appid'] & 0xFFFFFFFF}p.png").is_file()                # the play mode's
    ok, text, found = library.update_steam(steam_dir, [], [game], PROGRAM, LOGO_PATH, shortcuts.in_steam(steam_dir),
                                           with_steam_closed)
    assert ok and found == shortcuts.in_steam(steam_dir) == {} and "1 taken out" in text


def test_a_steam_that_does_not_close_changes_nothing(qapp, tmp_path):
    (tmp_path / "Steam" / "userdata" / "1" / "config").mkdir(parents=True)

    def stuck(change):
        raise steam.SteamError("Steam did not close within 30 seconds; nothing was changed.")
    ok, text, found = library.update_steam(tmp_path / "Steam", [Game(tmp_path / "A.iso", "A")], [],
                                           PROGRAM, LOGO_PATH, {}, stuck)
    assert not ok and "did not close" in text and found is None and steam.shortcuts(tmp_path / "Steam") == []


def test_the_suites_folders(tmp_path):
    assert library.key_file() == tmp_path / "Roaming" / "windows-portable-suite" / "steamgriddb-key"
    assert library.covers_home() == tmp_path / "Local" / "windows-portable-suite" / "windows-portable-xenia" / "covers"
