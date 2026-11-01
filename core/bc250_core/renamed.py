# SPDX-License-Identifier: GPL-3.0-or-later
"""A game renamed or moved after it was put in Steam (the Windows Portable Suite's game managers; owner, 01-11-2026:
renamed, its shortcut started Xenia with a file no longer there, and the game showed again without its mark). A game
manager knows a game by its file, as its Steam shortcut starts it, so it also remembers what each game in Steam is:
its code (a title ID, a serial, a disc ID) or, without one, its file's size (an .iso). A game found again under
another name or in another folder, not in Steam itself, takes the mark of the one in Steam that is no longer found,
when it is the only game that matches: Update Steam then takes the old shortcut out and puts the game in under its
new name.

What the app remembers is in its settings (KEY, JSON: the game's file, as its shortcut names it, and what it is), only
for the games in Steam; the standard library and QSettings."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

KEY = "games/in-steam"


def identity(code: str, file: Path) -> str:
    """What a game is, whatever its file is called: its code, else its file's size; "" when neither can be told."""
    if code:
        return f"code:{code.upper()}"
    try:
        return f"size:{file.stat().st_size}"
    except OSError:
        return ""


def load(settings) -> dict[str, str]:
    """What the app remembers of its games in Steam; {} when nothing (or nothing it can read) is kept."""
    try:
        known = json.loads(str(settings.value(KEY, "{}") or "{}"))
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in known.items()} if isinstance(known, dict) else {}


def remember(settings, known: Mapping[str, str], found: Mapping[str, str], in_steam: Iterable[str]) -> None:
    """Kept for next time: the games in Steam as found now (*found*: each game's file and identity()), and those in
    Steam that are not found now as they were (the ones follow() looks for); a game no longer in Steam is forgotten."""
    in_steam = set(in_steam)
    kept = {k: v for k, v in known.items() if k in in_steam}
    kept.update({k: v for k, v in found.items() if k in in_steam and v})
    settings.setValue(KEY, json.dumps(kept, sort_keys=True))


def follow(known: Mapping[str, str], found: Mapping[str, str], in_steam: Iterable[str]) -> dict[str, str]:
    """{the game's file now: its file in Steam} for each game in Steam no longer found that is found again under
    another name or in another folder: the only found game, not in Steam itself, that is what it was."""
    in_steam = set(in_steam)
    moved: dict[str, str] = {}
    for old in sorted(in_steam - set(found)):
        was = known.get(old)
        if not was:
            continue
        now = [k for k, v in found.items() if v == was and k not in in_steam and k not in moved]
        if len(now) == 1:
            moved[now[0]] = old
    return moved


def said(titles: Iterable[str]) -> str:
    """The status line's words for the games follow() found again."""
    return (f"Found again under a new name or in another folder, with its Steam mark: {', '.join(titles)}. The Y "
            "button updates Steam.")
