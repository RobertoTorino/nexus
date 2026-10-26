# SPDX-License-Identifier: GPL-3.0-or-later
"""A Steam shortcut per game, for Game Mode: a non-Steam game that runs the run wrapper with PPSSPP's launch line,
the game full screen with an Exit game entry in PPSSPP's pause menu
(bc250-ppsspp-run --fullscreen --pause-menu-exit "<game>").

The file and its format are core's (bc250_core.steam). The shortcut runs the wrapper, not the AppImage, so its
Steam number (from the program and the name) stays the same when the app brings another PPSSPP. The artwork comes
from inside the game's own image or PBP: ICON0.PNG (144 × 80) on the portrait and the wide picture and as the logo
on the banner (Steam's Properties > Customization > Logo), PIC1.PNG (480 × 272, its background) on the banner and
behind the wide one; without them (a CHD) the title is drawn on a dark background. A cover from SteamGridDB (core's
covers), when one is kept for the game, is the portrait instead: the game's own pictures fill the other three."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from bc250_core import covers, steam

from .games import Game

RUN = "~/.local/bin/bc250-ppsspp-run"
RUN_NAME = "bc250-ppsspp-run"
TAGS = ("PSP", "PPSSPP Manager")
PREFIX = f"[{TAGS[0]}] "    # before each name, so the same title on another system or on Steam itself is told apart
COVERS = covers.PORTRAIT    # from SteamGridDB: the portrait alone, the game's own pictures are the rest


def launch_options(game: Game) -> str:
    """Steam's usual form, the path in double quotes; a path with a character that is special inside them gets
    single quotes instead."""
    path = str(game.file)
    quoted = f'"{path}"' if not any(c in path for c in '"$`\\') else shlex.quote(path)
    return f"--fullscreen --pause-menu-exit {quoted}"


def _file(item: dict) -> str:
    """The game a shortcut of this app starts ("" for any other shortcut): the last word of its launch options,
    after --fullscreen."""
    if not str(item.get("Exe", "")).strip('"').endswith(RUN_NAME):
        return ""
    try:
        words = shlex.split(str(item.get("LaunchOptions", "")))
    except ValueError:
        return ""
    if "--fullscreen" not in words[:-1] or not words[-1] or words[-1].startswith("-"):
        return ""
    return words[-1]


def ours(item: dict) -> bool:
    """Any shortcut this app made."""
    return bool(_file(item))


def for_game(game: Game):
    """Recognizes the game's shortcut, whatever its name now."""
    return lambda item: _file(item) == str(game.file)


def names(games: Iterable[Game]) -> dict[Path, str]:
    """The name in Steam per game: the system and its title ("[PSP] Title"), with its ID when two games have
    the same title (Steam numbers a shortcut by its program and name, so two names must differ)."""
    games = list(games)
    titles = [g.title for g in games]
    return {g.file: PREFIX + (g.title if titles.count(g.title) == 1 or not g.disc_id
                              else f"{g.title} ({g.disc_id})")
            for g in games}


def entry(game: Game, name: str, run: Path, logo: Path) -> dict:
    return steam.shortcut_entry(f'"{run}"', name, f'"{run.parent}/"', str(steam.shortcut_icon(logo)),
                                launch_options(game), TAGS)


def in_steam(folder: Path) -> dict[str, str]:
    """The game files that have a shortcut of this app, for any Steam user, with the shortcut's name."""
    return {_file(item): str(item.get("AppName", "")) for item in steam.shortcuts(folder) if ours(item)}


def cover_name(game: Game) -> str:
    """The name the game's pictures from SteamGridDB are kept under."""
    return covers.name(game.title, game.disc_id)


def changes(add: Iterable[Game], remove: Iterable[Game], run: Path, logo: Path, existing: dict[str, str],
            art: bool = True, found: Callable[[Game], dict[str, bytes]] = lambda _game: {}) -> list[steam.Change]:
    """The changes for core's write_shortcuts: the games to add (or bring up to date) and to take out. The names
    are made unique over the games added; a shortcut taken out is named as in Steam (*existing*, from in_steam()),
    so its artwork, numbered by the name, goes too. *found*: a game's pictures from SteamGridDB, in place of the
    drawn ones."""
    add, remove = list(add), list(remove)
    named = names(add)
    result = [steam.Change(entry(g, named[g.file], run, logo), for_game(g),
                           {**draw_art(g, logo), **found(g)} if art else {})
              for g in add]
    result += [steam.Change(entry(g, existing.get(str(g.file), g.title), run, logo), for_game(g), remove=True)
               for g in remove]
    return result


# --- The artwork -----------------------------------------------------------------------------------------------

def draw_art(game: Game, logo: Path) -> dict[str, bytes]:
    """The portrait, the wide picture and the banner as PNG bytes, and the game's ICON0.PNG as the logo on the
    banner (without it no logo: Steam shows the name there)."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    own = game.picture("ICON0.PNG")
    icon = QImage.fromData(own or b"") if own else QImage(str(logo))
    background = QImage.fromData(game.picture("PIC1.PNG") or b"")
    images = {}
    for suffix in ("p", "", "_hero"):
        width, height = steam.ART[suffix]
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0, QColor("#0d2a4a"))
        gradient.setColorAt(1, QColor("#04080f"))
        painter.fillRect(0, 0, width, height, gradient)
        if suffix != "p" and not background.isNull():
            _cover(painter, background, width, height)
            if suffix == "":
                painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 110))
        if suffix != "_hero" and not icon.isNull():
            # ICON0.PNG is wide (144 × 80): as wide as fits, its shape kept.
            box_w, box_h = width * (0.86 if suffix == "p" else 0.7), height * (0.5 if suffix == "p" else 0.7)
            scale = min(box_w / icon.width(), box_h / icon.height())
            w, h = icon.width() * scale, icon.height() * scale
            top = height * 0.22 if suffix == "p" else (height - h) / 2
            painter.drawImage(QRectF((width - w) / 2, top, w, h), icon)
        if suffix == "p":
            font = QFont()
            font.setBold(True)
            font.setPixelSize(int(width * 0.07))
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(width * 0.05, height * 0.72, width * 0.9, height * 0.2),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, game.title)
        painter.end()
        images[suffix] = _png(image)
    if own and not icon.isNull():
        images["_logo"] = own                   # the picture as it is, as Steam copies a logo chosen in its settings
    return images


def _cover(painter, picture, width: int, height: int) -> None:
    """*picture* filling the whole area, cut to its shape from the middle."""
    from PyQt6.QtCore import QRectF
    scale = max(width / picture.width(), height / picture.height())
    w, h = width / scale, height / scale
    painter.drawImage(QRectF(0, 0, width, height), picture,
                      QRectF((picture.width() - w) / 2, (picture.height() - h) / 2, w, h))


def _png(image) -> bytes:
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)
