# SPDX-License-Identifier: GPL-3.0-or-later
"""The eight naming templates, character cleaning, translated title and careful rename for disc images read by
games.py. A memory stick game is never renamed: its file must stay EBOOT.PBP."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from pathlib import Path

from .games import Game

RENAMABLE = ("iso", "cso")                          # what can carry the name (a CHD is not read, a PBP must not)


class NamingTemplate(Enum):
    """The order is the order of the Naming box in the window (and the number saved in the settings)."""
    ID_TITLE = "ID - Title"
    ID_TITLE_SPACE = "ID Title"
    ID_TITLE_VERSION = "ID - Title - Version"
    TITLE_ID = "Title - ID"
    TITLE_ID_SPACE = "Title Id"
    TITLE_ONLY = "Title only"
    TITLE_BRACKET_ID = "Title [ID]"
    TITLE_BRACKET_ID_VERSION = "Title [ID] [Version]"

    @classmethod
    def from_index(cls, index: int) -> "NamingTemplate":
        templates = list(cls)
        return templates[index] if 0 <= index < len(templates) else cls.ID_TITLE

    @property
    def index(self) -> int:
        return list(type(self)).index(self)


# Characters illegal in common filesystems, and the trademark symbol (U+2122).
INVALID_CHARS = "\\/:*?\"<>|™"


def renamable(games: Iterable[Game]) -> list[Game]:
    """The games whose file can carry the new name: the ISO and CSO images."""
    return [g for g in games if g.kind in RENAMABLE]


def effective_title(game: Game, translation: str = "") -> str:
    """The translation when one was typed, else the title from PARAM.SFO."""
    return translation.strip() or game.title


def formatted_name(game: Game, template: NamingTemplate = NamingTemplate.ID_TITLE, translation: str = "") -> str:
    """The target base filename (no extension): "ULJM05437 - Ever17", "ULJM05437 Ever17",
    "ULJM05437 - Ever17 - v1.01", "Ever17 - ULJM05437", "Ever17 ULJM05437", "Ever17", "Ever17 [ULJM05437]" or
    "Ever17 [ULJM05437] [v1.01]". Characters illegal in Windows/Linux filenames are removed."""
    title = effective_title(game, translation)
    version = game.version if game.version[:1].lower() == "v" else "v" + game.version

    if template is NamingTemplate.ID_TITLE:
        name = f"{game.disc_id} - {title}"
    elif template is NamingTemplate.ID_TITLE_SPACE:
        name = f"{game.disc_id} {title}"
    elif template is NamingTemplate.ID_TITLE_VERSION:
        name = f"{game.disc_id} - {title} - {version}"
    elif template is NamingTemplate.TITLE_ID:
        name = f"{title} - {game.disc_id}"
    elif template is NamingTemplate.TITLE_ID_SPACE:
        name = f"{title} {game.disc_id}"
    elif template is NamingTemplate.TITLE_ONLY:
        name = title
    elif template is NamingTemplate.TITLE_BRACKET_ID:
        name = f"{title} [{game.disc_id}]"
    else:
        name = f"{title} [{game.disc_id}] [{version}]"

    return "".join(c for c in name if c not in INVALID_CHARS)


def rename_file(path: Path, new_base: str) -> Path | None:
    """Rename *path* to *new_base* plus the file's own extension, in its folder. Returns the file's path after the
    rename; None when it failed. A file that already has that name is left alone and counts as renamed; another
    file with the target name is never overwritten."""
    target = path.with_name(new_base + path.suffix)
    if target == path:
        return path
    if target.exists():
        return None
    try:
        path.rename(target)
    except OSError:
        return None
    return target

