# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py): the app's own folders, Update Steam's plan, what Remove game deletes, and Steam's
shortcuts written into a Steam folder of a test (never the real one), with Steam closed around it."""

from __future__ import annotations

from pathlib import Path

from bc250_core import play, steam
from conftest import make_disc
from ppsspp_manager import LOGO_PATH, ROOT, library, shortcuts
from ppsspp_manager.games import Game, scan

PROGRAM = Path(r"C:\emu\PPSSPPWindows64.exe")


def test_the_apps_own_folders(tmp_path):
    r"""The app's own folders (owner, 30-10-2026: the games are put there, no folder is chosen): Games\PSP in the
    user's folder, made when missing, then Games\PSP on a removable drive that has one; an empty card slot is none."""
    home = tmp_path / "me"
    card, empty = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "PSP").mkdir(parents=True)
    empty.mkdir()

    class EmptySlot:                    # a card reader without a card: Windows raises when asked about it
        def __truediv__(self, other):
            return self

        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [EmptySlot(), card, empty]) == [home / "Games" / "PSP", card / "Games" / "PSP"]
    assert (home / "Games" / "PSP").is_dir()


def test_what_remove_game_deletes(tmp_path):
    """A disc image is its file alone; a memory stick game its own folder; never a game folder of the list, a folder
    holding another game, or a drive."""
    games = tmp_path / "Games" / "PSP"
    disc = Game(games / "Sub" / "Daxter.iso", "Daxter", kind="iso")
    homebrew = Game(games / "Homebrew" / "EBOOT.PBP", "Homebrew", kind="pbp")
    loose = Game(games / "EBOOT.PBP", "Loose", kind="pbp")
    outer = Game(games / "Pack" / "EBOOT.PBP", "Outer", kind="pbp")
    inner = Game(games / "Pack" / "Inner" / "EBOOT.PBP", "Inner", kind="pbp")
    found = [disc, homebrew, loose, outer, inner]
    assert library.removal(disc, [games], found) == ([disc.file], "")
    assert library.removal(homebrew, [games], found) == ([games / "Homebrew"], "")
    assert library.removal(loose, [games], found)[1].startswith("Loose is in PSP, one of the app's game folders")
    assert library.removal(outer, [games], found)[1] == ("Pack holds another game too (Inner): delete Outer's files "
                                                         "by hand.")
    top = Game(Path(tmp_path.anchor) / "EBOOT.PBP", "Top", kind="pbp")
    assert library.removal(top, [], [top])[0] == []


def test_the_plan(tmp_path):
    a, b = Game(tmp_path / "a.iso", "A"), Game(tmp_path / "b.iso", "B")
    in_steam = {str(b.file): "[PSP] B", str(tmp_path / "gone.iso"): "[PSP] Gone"}
    add, remove = library.plan([a, b], {str(a.file)}, in_steam)
    assert add == [a] and [g.file for g in remove] == [b.file, tmp_path / "gone.iso"]
    assert library.pending([a, b], {str(a.file)}, in_steam)
    assert not library.pending([b], {str(b.file)}, {str(b.file): "[PSP] B"})              # as it is in Steam
    assert library.pending([b], {str(b.file)}, {str(b.file): "[PSP] B"}, {str(b.file)})   # not the play mode yet


def test_update_steam_writes_the_shortcuts_with_steam_closed(qapp, tmp_path):
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    game = scan([make_disc(tmp_path / "games" / "Daxter.iso", "Daxter", "ULUS10044", pictures=True).parent])[0]
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    ok, text, found = library.update_steam(steam_dir, [game], [], PROGRAM, LOGO_PATH, {}, with_steam_closed)
    assert ok and closed == [True] and "1 game(s) in Steam" in text
    assert found == shortcuts.in_steam(steam_dir) == {str(game.file): "[PSP] Daxter"}        # read back at once
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
    ok, text, found = library.update_steam(tmp_path / "Steam", [Game(tmp_path / "a.iso", "A")], [], PROGRAM,
                                           LOGO_PATH, {}, stuck)
    assert not ok and "did not close" in text and found is None and steam.shortcuts(tmp_path / "Steam") == []
