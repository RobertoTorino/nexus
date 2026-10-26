# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's own folder, ~/.config/PCSX2 (its BIOS, memory cards, saves and settings), as PCSX2 2.8 lays it out on
Linux: the BIOS in bios/, the settings in inis/PCSX2.ini. The few settings the app writes are in
pcsx2_settings.py.

The PS2's BIOS is not ours to give: PCSX2 cannot start a game without it, and it comes from your own console,
dumped with a homebrew tool (biosdrain). A dump is a .bin or .rom file of 4 MB, often with files beside it
(.erom, .nvm, ...) under the same name. The app copies the dump chosen in its window into PCSX2's bios folder, with
the files beside it, and tells PCSX2 to use it; Remove takes a dump out of that folder again, with those files.

PCSX2 also keeps a log of its last run (logs/emulog.txt, written over at every start): the game's serial and CRC,
the controllers it opened and, when it shut down by itself, the play time it counted. The app reads it for its own
log (owner, 24-10-2026: the log should say which game was played, how long and with which controller), since a
game started from Steam runs without the app. The play time PCSX2 counts per game is in inis/playtime.dat: one
line per serial, the serial, the seconds played and when it was last played (Unix time), each left-aligned in a
fixed width; the app shows the sum in its header (owner, 24-10-2026)."""

from __future__ import annotations

import configparser
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import config_home

BIOS_SUFFIXES = (".bin", ".rom")
BIOS_HELP_URL = "https://pcsx2.net/docs/setup/bios"


def pcsx2_home() -> Path:
    return config_home() / "PCSX2"


def bios_dir(home: Path) -> Path:
    return home / "bios"


def bios_files(folder: Path) -> list[Path]:
    """The BIOS dumps in PCSX2's bios folder (.bin and .rom files), sorted by name."""
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in BIOS_SUFFIXES)
    except OSError:
        return []


def copy_bios(dump: Path, folder: Path) -> Path:
    """Copies *dump* into *folder* with the files beside it under the same name (SCPH10000.BIN with SCPH10000.NVM
    and SCPH10000.MEC), unless it is in that folder already; returns the dump's place there. OSError is the
    caller's."""
    folder.mkdir(parents=True, exist_ok=True)
    if dump.parent.resolve() == folder.resolve():
        return dump
    stem = dump.stem.lower()
    for item in sorted(dump.parent.iterdir()):
        if item.is_file() and item.stem.lower() == stem:
            shutil.copy2(item, folder / item.name)
    return folder / dump.name


def remove_bios(dump: Path) -> list[str]:
    """Removes the dump from PCSX2's bios folder with the files beside it under the same name; the names removed.
    OSError is the caller's."""
    stem = dump.stem.lower()
    removed = []
    for item in sorted(dump.parent.iterdir()):
        if item.is_file() and item.stem.lower() == stem:
            item.unlink()
            removed.append(item.name)
    return removed


def play_times(home: Path) -> dict[str, tuple[int, int]]:
    """The play time PCSX2 counted per game, serial: (seconds, last played as Unix time); {} without the file."""
    try:
        text = (home / "inis" / "playtime.dat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    times: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and parts[0] not in times:
            times[parts[0]] = (int(parts[1]), int(parts[2]))
    return times


def ini_value(home: Path, section: str, key: str) -> str:
    """A value from PCSX2's settings (inis/PCSX2.ini), "" when it or the file is not there."""
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str                               # PCSX2's keys are case-sensitive: Slot1_Filename
    try:
        ini.read(home / "inis" / "PCSX2.ini", encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return ""
    return ini.get(section, key, fallback="").strip()


# --- PCSX2's last run -------------------------------------------------------------------------------------------

_VERSION = re.compile(r"^\[\s*[\d.]+\] PCSX2 v(\S+)")
_SERIAL = re.compile(r"^\[\s*[\d.]+\]\s+Serial: (\S+)")
_CRC = re.compile(r"^\[\s*[\d.]+\]\s+CRC: ([0-9A-Fa-f]+)")
_GAMEPAD = re.compile(r"^\[\s*[\d.]+\] SDLInputSource: Opened gamepad \d+ \(instance id \d+, player id \d+\): (.+)$")
_PLAY_TIME = re.compile(r"^\[\s*[\d.]+\] Add (\d+) seconds play time to (\S+)")
_STAMP = re.compile(r"^\[\s*([\d.]+)\]")


@dataclass(frozen=True)
class Session:
    """What PCSX2's log says about its last run."""
    ended: float                        # when the log was last written (the file's time)
    version: str = ""                   # PCSX2's
    serial: str = ""                    # the game's; "" when no game was started
    crc: str = ""
    seconds: int = 0                    # the play time PCSX2 counted, else the log's last time stamp
    counted: bool = False               # whether PCSX2 counted it (it shut down by itself)
    controllers: tuple[str, ...] = ()   # the controllers PCSX2 opened, by name


def log_file(home: Path) -> Path:
    """PCSX2's own log ([Folders] Logs, logs/ when not set)."""
    folder = Path(ini_value(home, "Folders", "Logs") or "logs").expanduser()
    return (folder if folder.is_absolute() else home / folder) / "emulog.txt"


def last_session(home: Path) -> Session | None:
    """PCSX2's last run as its log tells it; None without a log."""
    path = log_file(home)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        ended = path.stat().st_mtime
    except OSError:
        return None
    version = serial = crc = ""
    seconds, counted, last = 0, False, 0.0
    controllers: list[str] = []
    for line in text.splitlines():
        if m := _STAMP.match(line):
            last = float(m.group(1))
        if m := _VERSION.match(line):
            version = m.group(1)
        elif m := _SERIAL.match(line):
            serial = m.group(1)
        elif m := _CRC.match(line):
            crc = m.group(1).upper()
        elif m := _GAMEPAD.match(line):
            if m.group(1) not in controllers:
                controllers.append(m.group(1))
        elif m := _PLAY_TIME.match(line):
            seconds, counted = int(m.group(1)), True
    if not counted:
        seconds = int(last)
    return Session(ended, version, serial, crc, seconds, counted, tuple(controllers))


def played(seconds: int) -> str:
    """A play time in words: "3 h 5 min", "12 min", "40 s"."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min" + (f" {secs} s" if secs else "")
    return f"{secs} s"
