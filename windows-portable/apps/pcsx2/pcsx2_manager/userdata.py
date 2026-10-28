# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's own folder in portable mode: the emulator's folder itself (emulator.emulator_home()), where PCSX2 2.8.2
makes bios\\, memcards\\, sstates\\, inis\\ and the rest at its first start (seen on the Ally, 28-10-2026). The
settings are in inis\\PCSX2.ini (pcsx2_settings.py), the BIOS dumps in bios\\, as in the BC250 suite's PCSX2
Manager.

The PS2's BIOS is not ours to give: PCSX2 cannot start a game without it, and it comes from your own console. A dump
is a .bin or .rom file of 4 MB, often with files beside it (.erom, .nvm, ...) under the same name."""

from __future__ import annotations

from pathlib import Path

BIOS_SUFFIXES = (".bin", ".rom")


def bios_dir(home: Path) -> Path:
    return home / "bios"


def bios_files(folder: Path) -> list[Path]:
    """The BIOS dumps in PCSX2's bios folder (.bin and .rom files), sorted by name."""
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in BIOS_SUFFIXES)
    except OSError:
        return []
