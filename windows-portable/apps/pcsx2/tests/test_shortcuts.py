# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows: the app's play mode with the game alone and full screen (owner,
30-10-2026: View and Menu held quit it), one made before it that starts PCSX2 itself still the game's, paths in double
quotes as Steam writes them, "[PS2] <title>" names made unique, and the app's own shortcuts told from others."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bc250_core import play, steam
from pcsx2_manager import ROOT, shortcuts
from pcsx2_manager.games import Game

MANAGER = r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-pcsx2\app\PCSX2-Manager.exe"
PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-pcsx2\emulator\pcsx2-qt.exe")
LUMINES = Game(Path(r"D:\PS2 Games\Lumines Plus.iso"), "Lumines Plus", "SLUS-21553")


@pytest.fixture
def release(monkeypatch):
    """The app as a release runs it: PyInstaller's program."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", MANAGER)


def _steam(tmp_path: Path) -> Path:
    config = tmp_path / "Steam" / "userdata" / "1000" / "config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {}}))
    return tmp_path / "Steam"


def test_a_shortcut_starts_the_play_mode_with_the_game(tmp_path, release):
    item = shortcuts.entry(LUMINES, "[PS2] Lumines Plus", PROGRAM, tmp_path / "logo.png")
    assert item["Exe"] == f'"{MANAGER}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == '--play -nogui -fullscreen -batch -- "D:\\PS2 Games\\Lumines Plus.iso"'
    assert shortcuts.command(LUMINES) == [MANAGER, "--play", "-nogui", "-fullscreen", "-batch", "--",
                                          str(LUMINES.file)]
    assert item["tags"] == {"0": "PS2", "1": "PCSX2 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(LUMINES)(item)
    assert shortcuts.for_game(Game(Path(r"d:\ps2 games\LUMINES PLUS.iso"), "x"))(item)     # Windows ignores case


def test_a_shortcut_made_before_the_play_mode_is_the_games_and_outdated(tmp_path, release):
    """A shortcut that starts pcsx2-qt.exe itself (3.0.1 and before) is the game's, so Update Steam replaces it, and
    outdated() names it; one made from the checkout (PowerShell and run.ps1) is outdated in a release too."""
    folder = _steam(tmp_path)
    old = steam.shortcut_entry(f'"{PROGRAM}"', "[PS2] Lumines Plus", f'"{PROGRAM.parent}\\"', "",
                               '-nogui -fullscreen -batch -- "D:\\PS2 Games\\Lumines Plus.iso"', shortcuts.TAGS)
    assert shortcuts.ours(old) and shortcuts.for_game(LUMINES)(old)
    before = play.launcher(ROOT, frozen=False)[1]
    checkout = steam.shortcut_entry(f'"{play.POWERSHELL}"', "[PS2] Two", '"x\\"', "",
                                    play.launch_options(before, '-nogui -fullscreen -batch -- "D:\\Two.iso"'),
                                    shortcuts.TAGS)
    three = Game(Path(r"D:\Three.iso"), "Three", "SLUS-00003")
    config = steam.user_folders(folder)[0]
    values = {"shortcuts": {"0": old, "1": checkout,
                            "2": shortcuts.entry(three, "[PS2] Three", PROGRAM, tmp_path / "logo.png")}}
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    assert set(shortcuts.in_steam(folder)) == {str(LUMINES.file), r"D:\Two.iso", str(three.file)}
    assert shortcuts.outdated(folder) == {str(LUMINES.file), r"D:\Two.iso"}
    steam.write_shortcuts(folder, shortcuts.changes([LUMINES], [], PROGRAM, tmp_path / "logo.png", {}, art=False))
    assert shortcuts.outdated(folder) == {r"D:\Two.iso"} and len(steam.shortcuts(folder)) == 3


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": "-nogui -- x.iso"})
    assert not shortcuts.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": '-File x.ps1 -nogui -- "x.iso"'})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # PCSX2 alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '-fullscreen -- "a.iso"'})


def test_names_are_unique():
    other = Game(Path(r"D:\PS2\Lumines Plus (Europe).iso"), "Lumines Plus", "SLES-54317")
    named = shortcuts.names([LUMINES, other])
    assert named[LUMINES.file] == "[PS2] Lumines Plus (SLUS-21553)" and named[other.file] == "[PS2] Lumines Plus (SLES-54317)"
    assert shortcuts.names([LUMINES])[LUMINES.file] == "[PS2] Lumines Plus"
