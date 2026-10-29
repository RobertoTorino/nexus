# SPDX-License-Identifier: GPL-3.0-or-later
"""Your games, as the BC250 suite's Vita3K Manager keeps them: the games Vita3K has installed (games.installed: no game
folders, Vita3K starts only what is in its storage), which have a Steam shortcut of this app, and the plan Update
Steam carries out: the marked games in Steam, the others out, and the shortcuts of games no longer installed out too
(the BC250 app's steam_plan). The suite's SteamGridDB key and the pictures found are in the suite's folders
(%APPDATA%\\windows-portable-suite\\steamgriddb-key, the app's covers\\)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bc250_core import covers, steam
from bc250_core.platform import suite_config, suite_data

from . import APP_ID, SUITE, shortcuts
from .games import Game


def key_file() -> Path:
    """The suite's SteamGridDB API key, the Windows Portable Suite's own (BC250's is in its ~/.config folder)."""
    return suite_config(SUITE) / "steamgriddb-key"


def covers_home() -> Path:
    return suite_data(SUITE) / APP_ID / "covers"


def plan(found: list[Game], marked: set[str], in_steam: dict[str, str]) -> tuple[list[Game], list[Game]]:
    """(games to add or bring up to date, games to take out): the marked ones in, the others out, and the shortcuts
    of games no longer installed out too."""
    add = [g for g in found if g.name in marked]
    names = {g.name for g in found}
    remove = [g for g in found if g.name in in_steam and g.name not in marked]
    remove += [Game(Path(name), title) for name, title in in_steam.items() if name not in names]
    return add, remove


def pending(found: list[Game], marked: set[str], in_steam: dict[str, str]) -> bool:
    """Whether Update Steam would change anything: a game in or out, or a name in Steam that differs."""
    add, remove = plan(found, marked, in_steam)
    named = shortcuts.names(add)
    return bool(remove) or any(in_steam.get(g.name) != named[g.name] for g in add)


def update_steam(steam_dir: Path, add: list[Game], remove: list[Game], program: Path, logo: Path,
                 existing: dict[str, str], closed: Callable[[Callable[[], None]], bool] = steam.with_steam_closed,
                 key: str = "", home: Path | None = None, get=None) -> tuple[bool, str, dict[str, str] | None]:
    """Steam's shortcuts made to match (off the window's thread): the pictures from SteamGridDB first when there is
    a key, then the shortcuts with Steam closed. (ok, what to tell, the app's games in Steam's file as read back
    right after the write, while Steam is still closed; None when nothing was written). Reading the file back then
    rather than once Steam starts again (29-10-2026: "it still says 0 games in Steam") tells whether the shortcuts
    were written as the app reads them, before Steam touches the file."""
    home = home or covers_home()
    notes = (covers.fetch([(shortcuts.cover_name(g), g.title) for g in add], shortcuts.COVERS, key, home,
                          *([get] if get else [])) if key else [])
    changes = shortcuts.changes(add, remove, program, logo, existing,
                                found=lambda g: covers.art(home, shortcuts.cover_name(g), shortcuts.COVERS))
    found: dict[str, str] = {}

    def change() -> None:
        steam.write_shortcuts(steam_dir, changes)
        found.update(shortcuts.in_steam(steam_dir))

    try:
        restarted = closed(change)
    except (steam.SteamError, steam.ShortcutError, OSError) as error:
        return False, "\n".join([*notes, f"Steam was not changed: {error}"]), None
    again = " Steam was closed for it and starts again in the background." if restarted else ""
    return True, "\n".join([*notes, f"{len(add)} game(s) in Steam, under Non-Steam in its library"
                                      f"{f'; {len(remove)} taken out' if remove else ''}.{again}"]), found
