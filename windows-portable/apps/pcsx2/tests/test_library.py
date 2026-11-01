# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games (library.py): the app's own folders, the BIOS taken from its folder, Remove game, Update Steam's plan,
and Steam's shortcuts written into a Steam folder of a test (never the real one), with Steam closed around it."""

from __future__ import annotations

from pathlib import Path

from bc250_core import play, steam
from conftest import make_disc
from pcsx2_manager import LOGO_PATH, ROOT, library, shortcuts, userdata
from pcsx2_manager.games import Game, scan

PROGRAM = Path(r"C:\emu\pcsx2-qt.exe")


def test_the_apps_own_folders(tmp_path):
    r"""Fixed folders (owner, 30-10-2026): Games\PS2 in the user's folder, made with its BIOS folder, then Games\PS2
    on each removable drive that has one; an empty card slot (Windows raises when asked about it) is no place."""
    home = tmp_path / "me"
    card, bare = tmp_path / "E", tmp_path / "F"
    (card / "Games" / "PS2").mkdir(parents=True)
    bare.mkdir()

    class EmptySlot:
        def __truediv__(self, other):
            return self

        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert library.fixed(home, lambda: [EmptySlot(), card, bare]) == [home / "Games" / "PS2", card / "Games" / "PS2"]
    assert library.bios_home(home) == home / "Games" / "PS2" / "BIOS" and library.bios_home(home).is_dir()


def test_the_bios_is_synced_new_or_changed_only(tmp_path):
    source, target = tmp_path / "Games" / "PS2" / "BIOS", tmp_path / "emulator" / "bios"
    assert userdata.sync_bios(source, target) == []                              # no folder: nothing
    source.mkdir(parents=True)
    (source / "SCPH-70012.bin").write_bytes(b"\0" * 64)
    (source / "SCPH-70012.nvm").write_bytes(b"\0" * 16)
    (source / "readme.txt").write_text("not a dump's")
    assert userdata.sync_bios(source, target) == ["SCPH-70012.bin", "SCPH-70012.nvm"]
    assert sorted(p.name for p in target.iterdir()) == ["SCPH-70012.bin", "SCPH-70012.nvm"]
    assert userdata.sync_bios(source, target) == []                              # unchanged: nothing copied
    (source / "SCPH-70012.nvm").write_bytes(b"\1" * 32)
    assert userdata.sync_bios(source, target) == ["SCPH-70012.nvm"]


def test_the_plan(tmp_path):
    a, b = Game(tmp_path / "a.iso", "A"), Game(tmp_path / "b.iso", "B")
    in_steam = {str(b.file): "[PS2] B", str(tmp_path / "gone.iso"): "[PS2] Gone"}
    add, remove = library.plan([a, b], {str(a.file)}, in_steam)
    assert add == [a] and [g.file for g in remove] == [b.file, tmp_path / "gone.iso"]
    assert library.pending([a, b], {str(a.file)}, in_steam)
    assert not library.pending([b], {str(b.file)}, {str(b.file): "[PS2] B"})              # as it is in Steam
    assert library.pending([b], {str(b.file)}, {str(b.file): "[PS2] B"}, {str(b.file)})  # not the play mode yet


def test_update_steam_writes_the_shortcuts_with_steam_closed(qapp, tmp_path):
    steam_dir = tmp_path / "Steam"
    config = steam_dir / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    game = scan([make_disc(tmp_path / "games" / "Lumines.iso", "SLUS_215.53").parent],
                {"SLUS-21553": "Lumines Plus"})[0]
    closed = []

    def with_steam_closed(change):
        closed.append(True)
        change()
        return False
    ok, text, found = library.update_steam(steam_dir, [game], [], PROGRAM, LOGO_PATH, {}, with_steam_closed)
    assert ok and closed == [True] and "1 game(s) in Steam" in text
    assert found == shortcuts.in_steam(steam_dir) == {str(game.file): "[PS2] Lumines Plus"}   # read back at once
    item = steam.shortcuts(steam_dir)[0]
    assert item["Exe"] == f'"{play.launcher(ROOT)[0]}"'                                       # the play mode's
    assert (config / "grid" / f"{item['appid'] & 0xFFFFFFFF}p.png").is_file()
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


def test_shortcuts_are_read_whatever_the_case_of_their_fields(tmp_path):
    """Steam has written appname and exe in lower case in some versions (29-10-2026): the app's shortcuts are found
    all the same, and so is the name a game has in Steam."""
    game = Game(tmp_path / "Lumines.iso", "Lumines Plus")
    item = shortcuts.entry(game, "[PS2] Lumines Plus", PROGRAM, LOGO_PATH)
    lower = {("appname" if key == "AppName" else "exe" if key == "Exe" else key): value for key, value in item.items()}
    assert shortcuts.ours(lower) and shortcuts.for_game(game)(lower)
    config = tmp_path / "Steam" / "userdata" / "1" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": lower}}))
    assert shortcuts.in_steam(tmp_path / "Steam") == {str(game.file): "[PS2] Lumines Plus"}
