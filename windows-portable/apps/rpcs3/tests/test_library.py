# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py): the app's own Games\\PS3 folders and the firmware's, Update Steam's plan, Steam's
shortcuts written into a Steam folder of a test (never the real one), with Steam closed around it, and what Remove
game deletes."""

from __future__ import annotations

from pathlib import Path

from bc250_core import play, steam
from conftest import make_disc_game, make_hdd_game
from rpcs3_manager import LOGO_PATH, ROOT, library, shortcuts
from rpcs3_manager.games import Game, scan

PROGRAM = Path(r"C:\emu\rpcs3.exe")


def test_the_apps_own_folders(tmp_path):
    r"""Games\PS3 in the user's folder, made with its Firmware folder, then Games\PS3 on each removable drive that
    has one (owner, 30-10-2026: no folder chosen); an empty card slot, which raises when asked, is no place."""
    home = tmp_path / "me"
    card, bare = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "PS3").mkdir(parents=True)
    bare.mkdir()

    class EmptySlot(type(tmp_path)):    # a card reader without a card: Windows raises when asked about it
        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [card, bare, EmptySlot(tmp_path / "G")]) == [home / "Games" / "PS3",
                                                                                    card / "Games" / "PS3"]
    assert library.firmware_home(home) == home / "Games" / "PS3" / "Firmware" and library.firmware_home(home).is_dir()


def test_the_firmware_file(tmp_path):
    """PS3UPDAT.PUP first, else the first .PUP by name; its key changes with the file."""
    home = tmp_path / "me"
    assert library.firmware_file(home) is None                          # no folder yet
    folder = library.firmware_home(home)
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("")
    assert library.firmware_file(home) is None
    (folder / "b.pup").write_bytes(b"1")
    (folder / "a.PUP").write_bytes(b"1")
    assert library.firmware_file(home) == folder / "a.PUP"
    (folder / "PS3UPDAT.PUP").write_bytes(b"1")
    pup = library.firmware_file(home)
    assert pup == folder / "PS3UPDAT.PUP"
    key = library.file_key(pup)
    assert key.startswith("PS3UPDAT.PUP|1|") and library.file_key(pup) == key
    pup.write_bytes(b"22")
    assert library.file_key(pup) != key and library.file_key(folder / "missing.pup") == ""


def test_what_remove_game_deletes(tmp_path):
    """An installed game's folder in dev_hdd0\\game; a disc game's folder in the app's folders with its update in
    dev_hdd0; never a game folder of the list, a folder with another game, or a disc game outside the app's
    folders."""
    from rpcs3_manager.games import scan
    own = tmp_path / "me" / "Games" / "PS3"
    hdd0 = tmp_path / "emulator" / "dev_hdd0" / "game"
    make_disc_game(own / "DeS", "Demon's Souls", "BLUS30443")
    make_hdd_game(hdd0 / "BLUS30443", "Demon's Souls", "BLUS30443", "01.04", category="GD")     # its update
    make_disc_game(own / "Two" / "A", "A", "BLUS00001")
    make_disc_game(own / "Two" / "B", "B", "BLUS00002")
    card = tmp_path / "E" / "Games" / "PS3"
    make_disc_game(card, "Loose", "BLUS00003")                           # the game folder itself is a game
    make_hdd_game(hdd0 / "NPUB30001", "Flower", "NPUB30001")
    make_disc_game(tmp_path / "old" / "Other", "Other", "BLUS00004")
    chosen = [own, card]
    games = {g.title: g for g in scan([*chosen, tmp_path / "old"], hdd0)}
    found = list(games.values())
    assert library.removal(games["Demon's Souls"], chosen, found, hdd0) == ([own / "DeS", hdd0 / "BLUS30443"], "")
    assert library.removal(games["Flower"], chosen, found, hdd0) == ([hdd0 / "NPUB30001"], "")
    assert library.removal(games["A"], chosen, found, hdd0) == ([own / "Two" / "A"], "")
    folders, why = library.removal(games["Loose"], chosen, found, hdd0)
    assert folders == [] and "one of the app's game folders itself" in why
    folders, why = library.removal(games["Other"], chosen, found, hdd0)
    assert folders == [] and "outside the app's Games\\PS3 folders" in why
    folders, why = library.removal(games["Flower"], chosen, found, tmp_path / "elsewhere")
    assert folders == [] and "not in RPCS3's dev_hdd0" in why


def test_a_kept_package_is_known_by_its_place_size_and_time(tmp_path):
    package = tmp_path / "Game.pkg"
    package.write_bytes(b"pkg")
    key = library.kept_key(package)
    assert key.startswith(library.kept_path(package) + "|") and key == library.kept_key(package)
    package.write_bytes(b"pkg, another")                                # changed: waits again
    assert library.kept_key(package) != key and library.kept_key(tmp_path / "gone.pkg") == ""


def test_the_plan(tmp_path):
    a, b = Game(tmp_path / "a" / "EBOOT.BIN", "A"), Game(tmp_path / "b" / "EBOOT.BIN", "B")
    gone = tmp_path / "gone" / "EBOOT.BIN"
    in_steam = {str(b.eboot): "[PS3] B", str(gone): "[PS3] Gone"}
    add, remove = library.plan([a, b], {str(a.eboot)}, in_steam)
    assert add == [a] and [g.eboot for g in remove] == [b.eboot, gone]
    assert library.pending([a, b], {str(a.eboot)}, in_steam)
    assert not library.pending([b], {str(b.eboot)}, {str(b.eboot): "[PS3] B"})              # as it is in Steam
    assert library.pending([b], {str(b.eboot)}, {str(b.eboot): "[PS3] B"}, {str(b.eboot)})  # not the play mode yet


def test_update_steam_writes_the_shortcuts_with_steam_closed(qapp, tmp_path):
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    make_disc_game(tmp_path / "games" / "DeS", "Demon's Souls", "BLUS30443", pictures=True)
    game = scan([tmp_path / "games"])[0]
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    ok, text, found = library.update_steam(steam_dir, [game], [], PROGRAM, LOGO_PATH, {}, with_steam_closed)
    assert ok and closed == [True] and "1 game(s) in Steam" in text
    assert found == shortcuts.in_steam(steam_dir) == {str(game.eboot): "[PS3] Demon's Souls"}   # read back at once
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
    ok, text, found = library.update_steam(tmp_path / "Steam", [Game(tmp_path / "a" / "EBOOT.BIN", "A")], [],
                                           PROGRAM, LOGO_PATH, {}, stuck)
    assert not ok and "did not close" in text and found is None and steam.shortcuts(tmp_path / "Steam") == []
