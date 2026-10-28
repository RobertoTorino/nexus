# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcuts (shortcuts.py) on Windows: PCSX2's program with the game alone and full screen, paths in double
quotes as Steam writes them, "[PS2] <title>" names made unique, and the app's own shortcuts told from others."""

from __future__ import annotations

from pathlib import Path

from pcsx2_manager import shortcuts
from pcsx2_manager.games import Game

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\windows-portable-pcsx2\emulator\pcsx2-qt.exe")
LUMINES = Game(Path(r"D:\PS2 Games\Lumines Plus.iso"), "Lumines Plus", "SLUS-21553")


def test_a_shortcut_starts_pcsx2_with_the_game(tmp_path):
    item = shortcuts.entry(LUMINES, "[PS2] Lumines Plus", PROGRAM, tmp_path / "logo.png")
    assert item["Exe"] == f'"{PROGRAM}"' and item["StartDir"] == f'"{PROGRAM.parent}\\"'
    assert item["LaunchOptions"] == '-nogui -fullscreen -- "D:\\PS2 Games\\Lumines Plus.iso"'
    assert item["tags"] == {"0": "PS2", "1": "PCSX2 Manager"}
    assert shortcuts.ours(item) and shortcuts.for_game(LUMINES)(item)
    assert shortcuts.for_game(Game(Path(r"d:\ps2 games\LUMINES PLUS.iso"), "x"))(item)     # Windows ignores case


def test_other_shortcuts_are_not_ours():
    assert not shortcuts.ours({"Exe": '"C:\\Games\\other.exe"', "LaunchOptions": "-nogui -- x.iso"})
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": ""})              # PCSX2 alone, no game
    assert not shortcuts.ours({"Exe": f'"{PROGRAM}"', "LaunchOptions": '-fullscreen -- "a.iso"'})


def test_names_are_unique():
    other = Game(Path(r"D:\PS2\Lumines Plus (Europe).iso"), "Lumines Plus", "SLES-54317")
    named = shortcuts.names([LUMINES, other])
    assert named[LUMINES.file] == "[PS2] Lumines Plus (SLUS-21553)" and named[other.file] == "[PS2] Lumines Plus (SLES-54317)"
    assert shortcuts.names([LUMINES])[LUMINES.file] == "[PS2] Lumines Plus"
