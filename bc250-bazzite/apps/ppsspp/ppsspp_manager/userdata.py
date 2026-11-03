# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PPSSPP's settings: PSP/SYSTEM/ppsspp.ini on PPSSPP's memory stick (~/.config/ppsspp,
games.ppsspp_home). Never while PPSSPP runs: it keeps its settings in memory and writes the whole file back when it
closes.

PPSSPP writes "Key = Value" under [Section], keys matched whatever their case, booleans as True and False, with a
UTF-8 byte order mark first (its IniFile::Save); it reads a missing key as its default. The file is changed line by
line: every other line and its order stay as PPSSPP wrote it, and the mark too (read_lines, write_lines).

What the app owns, set when the window opens, after an install and before PPSSPP opens (prepare; owner, 03-11-2026,
from the Windows Portable Suite's PPSSPP Manager): PPSSPP's notice of a newer release off ([General]
CheckForNewVersion). A newer PPSSPP comes with the app, once it has been tried on the board; the notice is on
PPSSPP's main screen, which Game Mode never shows."""

from __future__ import annotations

import os
from pathlib import Path

# The settings the app owns: section, key, value, and what it did in the app's words.
OWNED = (("General", "CheckForNewVersion", "False", "its notice of a newer release off"),)


def settings_path(memstick: Path) -> Path:
    """ppsspp.ini on PPSSPP's memory stick."""
    return memstick / "PSP" / "SYSTEM" / "ppsspp.ini"


def _key_of(line: str) -> str:
    return line.split("=", 1)[0].strip().lower() if "=" in line and not line.lstrip().startswith("[") else ""


def ini_value(lines: list[str], section: str, key: str) -> str | None:
    """The value of *key* in *section*, as the file has it; None when the file does not name it."""
    inside = False
    for line in lines:
        text = line.strip()
        if text.startswith("[") and text.endswith("]"):
            inside = text[1:-1].strip().lower() == section.lower()
        elif inside and _key_of(line) == key.lower():
            return line.split("=", 1)[1].strip()
    return None


def ini_set(lines: list[str], section: str, key: str, value: str) -> None:
    """Sets *key* in *section* to *value* ("Key = Value", as PPSSPP writes it), in place when the file names it,
    else at the section's end; a section the file lacks is added at the end."""
    inside, last = False, -1
    for n, line in enumerate(lines):
        text = line.strip()
        if text.startswith("[") and text.endswith("]"):
            if inside:
                break
            inside = text[1:-1].strip().lower() == section.lower()
            if inside:
                last = n
        elif inside:
            if _key_of(line) == key.lower():
                lines[n] = f"{key} = {value}"
                return
            if text:
                last = n
    if last < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        last = len(lines) - 1
    lines.insert(last + 1, f"{key} = {value}")


BOM = "\ufeff"


def read_lines(path: Path) -> tuple[list[str], bool]:
    """The file's lines without its byte order mark, and whether it had one; ([], False) for no file."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    bom = text.startswith(BOM)
    text = text.removeprefix(BOM)
    return (text.rstrip("\n").split("\n") if text.strip() else []), bom


def write_lines(path: Path, lines: list[str], bom: bool = False) -> None:
    """The file written whole, with the byte order mark it had."""
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(f".{path.name}.{os.getpid()}")
    work.write_text((BOM if bom else "") + "\n".join(lines) + "\n", encoding="utf-8")
    work.replace(path)


def prepare(memstick: Path) -> list[str]:
    """Brings ppsspp.ini to what the app owns (OWNED); returns what changed, [] when nothing did. OSError is the
    caller's. The caller makes sure PPSSPP does not run."""
    path = settings_path(memstick)
    lines, bom = read_lines(path)
    done = []
    for section, key, value, said in OWNED:
        if (ini_value(lines, section, key) or "").lower() != value.lower():
            ini_set(lines, section, key, value)
            done.append(said)
    if done:
        write_lines(path, lines, bom)
    return done
