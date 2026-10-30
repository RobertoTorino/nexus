# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py), as RPCS3 Manager's are tested: the app's own Games\\PS4 folders, Update Steam's plan, and
Steam's shortcuts written into a Steam folder of a test (never the real one), with Steam closed around it."""

from __future__ import annotations

from pathlib import Path

from bc250_core import steam
from conftest import make_game
from shadps4_manager import LOGO_PATH, library, shortcuts
from shadps4_manager.games import Game, scan

PROGRAM = Path(r"C:\emu\shadPS4.exe")


def test_the_apps_own_folders(tmp_path):
    r"""The app's own folders (owner, 30-10-2026: the games, packages and system modules are put there, no folder is
    chosen): Games\PS4 in the user's folder with its Modules folder, made when missing, then Games\PS4 on a removable
    drive that has one; an empty card slot is none."""
    home = tmp_path / "me"
    card, empty = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "PS4").mkdir(parents=True)
    empty.mkdir()

    class EmptySlot:                    # a card reader without a card: Windows raises when asked about it
        def __truediv__(self, other):
            return self

        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [EmptySlot(), card, empty]) == [home / "Games" / "PS4", card / "Games" / "PS4"]
    assert library.modules_home(home) == home / "Games" / "PS4" / "Modules" and library.modules_home(home).is_dir()


def test_the_plan(tmp_path):
    a, b = Game(tmp_path / "a" / "eboot.bin", "A"), Game(tmp_path / "b" / "eboot.bin", "B")
    gone = tmp_path / "gone" / "eboot.bin"
    in_steam = {str(b.eboot): "[PS4] B", str(gone): "[PS4] Gone"}
    add, remove = library.plan([a, b], {str(a.eboot)}, in_steam)
    assert add == [a] and [g.eboot for g in remove] == [b.eboot, gone]
    assert library.pending([a, b], {str(a.eboot)}, in_steam)
    assert not library.pending([b], {str(b.eboot)}, {str(b.eboot): "[PS4] B"})              # as it is in Steam


def test_update_steam_writes_the_shortcuts_with_steam_closed(qapp, tmp_path):
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    make_game(tmp_path / "games" / "CUSA00001", "Bloodborne", "CUSA00900", pictures=True)
    game = scan([tmp_path / "games"])[0]
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    ok, text, found = library.update_steam(steam_dir, [game], [], PROGRAM, LOGO_PATH, {}, with_steam_closed)
    assert ok and closed == [True] and "1 game(s) in Steam" in text
    assert found == shortcuts.in_steam(steam_dir) == {str(game.eboot): "[PS4] Bloodborne"}   # read back at once
    item = steam.shortcuts(steam_dir)[0]
    assert item["Exe"] == f'"{PROGRAM}"' and (config / "grid" / f"{item['appid'] & 0xFFFFFFFF}p.png").is_file()
    ok, text, found = library.update_steam(steam_dir, [], [game], PROGRAM, LOGO_PATH, shortcuts.in_steam(steam_dir),
                                           with_steam_closed)
    assert ok and found == shortcuts.in_steam(steam_dir) == {} and "1 taken out" in text


def test_a_steam_that_does_not_close_changes_nothing(qapp, tmp_path):
    (tmp_path / "Steam" / "userdata" / "1" / "config").mkdir(parents=True)

    def stuck(change):
        raise steam.SteamError("Steam did not close within 30 seconds; nothing was changed.")
    ok, text, found = library.update_steam(tmp_path / "Steam", [Game(tmp_path / "a" / "eboot.bin", "A")], [],
                                           PROGRAM, LOGO_PATH, {}, stuck)
    assert not ok and "did not close" in text and found is None and steam.shortcuts(tmp_path / "Steam") == []
