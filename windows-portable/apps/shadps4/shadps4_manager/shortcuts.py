# SPDX-License-Identifier: GPL-3.0-or-later
"""A Steam shortcut per game, as the BC250 suite's shadPS4 Manager makes them (its shortcuts.py): a non-Steam game that
starts shadPS4 with the game full screen, shadPS4.exe -f true -g "<eboot.bin>", named "[PS4] <title>", in Steam's
library and its Big Picture mode.

On Windows the shortcut runs the app's own program in its play mode (core's play.py; owner, 30-10-2026: one way out
of every game, View, LB and RB held): shadPS4-Manager.exe --play -f true -g "<eboot.bin>" starts shadPS4 in the app's
emulator folder, watches the controller and ends with the game. The app's program stays where it is when the app is
updated, so the shortcut's Steam number, from the program and the name, stays the same. The shortcut starts in the
emulator folder, so shadPS4 finds its user\\ folder beside it (its portable mode). A shortcut made before, which runs
shadPS4.exe itself, is still the game's (outdated(): Update Steam brings it to the play mode). Windows paths are
quoted the way Steam writes them, in double quotes (a Windows path holds no double quote). The file and its format are
core's (bc250_core.steam).

The artwork comes from the game's sce_sys, as the BC250 app draws it: icon0.png (512 × 512) on the portrait and the
wide picture and as the logo on the banner (Steam's Properties > Customization > Logo), pic1.png (1920 × 1080, its
background) on the banner and behind the wide one; without them the title is drawn on a dark background. A cover from
SteamGridDB (core's covers), when one is kept for the game, is the portrait instead: the game's own pictures fill the
other three."""

from __future__ import annotations

import ntpath
import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from bc250_core import covers, play, steam

from . import EXE_NAME, ROOT, emulator
from .games import Game

TAGS = ("PS4", "shadPS4 Manager")
PREFIX = f"[{TAGS[0]}] "    # before each name, so the same title on another system or on Steam itself is told apart
COVERS = covers.PORTRAIT    # from SteamGridDB: the portrait alone, the game's own pictures are the rest


def launch_options(game: Game) -> str:
    """shadPS4's launch line after its program: the game's eboot.bin in double quotes, as Steam writes a path on
    Windows."""
    return f'{" ".join(emulator.GAME_ARGS)} "{game.eboot}"'


def command(game: Game) -> list[str]:
    """The game in the play mode, as its shortcut starts it: for a device without Steam (owner, 30-10-2026)."""
    program, before = play.launcher(ROOT)
    return [program, *before, *emulator.GAME_ARGS, str(game.eboot)]


def _file(item: dict) -> str:
    """The game a shortcut of this app starts ("" for any other shortcut): the word after -g in the launch options of
    a shortcut that runs the app's play mode, or shadPS4.exe itself (one made before it). The fields by name whatever
    their case (steam.field): Steam has written them in lower case in some versions."""
    program = ntpath.basename(str(steam.field(item, "Exe")).strip('"')).lower()
    if program != emulator.EXE.lower() and program not in play.programs(EXE_NAME):
        return ""
    try:
        words = shlex.split(str(steam.field(item, "LaunchOptions")).replace("\\", "/"))
    except ValueError:
        return ""
    if "-g" not in words[:-1] or (program != emulator.EXE.lower() and play.FLAG not in words):
        return ""
    found = words[words.index("-g") + 1]
    return "" if not found or found.startswith("-") else found.replace("/", "\\")


def ours(item: dict) -> bool:
    """Any shortcut this app made."""
    return bool(_file(item))


def _key(path: str) -> str:
    return ntpath.normcase(path.replace("/", "\\"))


def for_game(game: Game):
    """Recognizes the game's shortcut, whatever its name now."""
    return lambda item: bool(_file(item)) and _key(_file(item)) == _key(str(game.eboot))


def names(games: Iterable[Game]) -> dict[Path, str]:
    """The name in Steam per game: the system and its title ("[PS4] Title"), with its ID when two games have
    the same title (Steam numbers a shortcut by its program and name, so two names must differ)."""
    games = list(games)
    titles = [g.title for g in games]
    return {g.eboot: PREFIX + (g.title if titles.count(g.title) == 1 or not g.title_id
                               else f"{g.title} ({g.title_id})")
            for g in games}


def entry(game: Game, name: str, program: Path, logo: Path) -> dict:
    """The game's shortcut: the play mode (play.launcher), started in shadPS4's folder, *program*'s."""
    icon = game.picture("icon0.png") or steam.shortcut_icon(logo)
    launcher, before = play.launcher(ROOT)
    return steam.shortcut_entry(f'"{launcher}"', name, f'"{program.parent}\\"', str(icon),
                                play.launch_options(before, launch_options(game)), TAGS)


def in_steam(folder: Path) -> dict[str, str]:
    """The eboot.bin paths that have a shortcut of this app, for any Steam user, with the shortcut's name."""
    return {_file(item): str(steam.field(item, "AppName")) for item in steam.shortcuts(folder) if ours(item)}


def outdated(folder: Path) -> set[str]:
    """The eboot.bin paths whose shortcut does not start the play mode as it is now (one made before it, or one made
    from the checkout on a device with the release): Update Steam writes them again."""
    return {_file(item) for item in steam.shortcuts(folder) if ours(item)
            and not play.played(str(steam.field(item, "Exe")), str(steam.field(item, "LaunchOptions")), ROOT)}


def numbers(folder: Path) -> dict[str, int]:
    """The Steam number (appid, unsigned) of each shortcut of this app, by the game as in_steam() names it: what
    steam.play_url() starts (owner, 29-10-2026: a game started from the app, through Steam). A shortcut without an
    appid field is numbered as Steam numbers it, from its program and name."""
    found = {}
    for item in steam.shortcuts(folder):
        if ours(item):
            number = steam.field(item, "appid", None)
            found[_file(item)] = (number & 0xFFFFFFFF if isinstance(number, int) else
                                  steam.appid(str(steam.field(item, "Exe")), str(steam.field(item, "AppName"))))
    return found


def cover_name(game: Game) -> str:
    """The name the game's pictures from SteamGridDB are kept under."""
    return covers.name(game.title, game.title_id)


def changes(add: Iterable[Game], remove: Iterable[Game], program: Path, logo: Path, existing: dict[str, str],
            art: bool = True, found: Callable[[Game], dict[str, bytes]] = lambda _game: {}) -> list[steam.Change]:
    """The changes for core's write_shortcuts: the games to add (or bring up to date) and to take out. The names
    are made unique over the games added; a shortcut taken out is named as in Steam (*existing*, from in_steam()),
    so its artwork, numbered by the name, goes too. *found*: a game's pictures from SteamGridDB, in place of the
    drawn ones."""
    add, remove = list(add), list(remove)
    named = names(add)
    result = [steam.Change(entry(g, named[g.eboot], program, logo), for_game(g),
                           {**draw_art(g, logo), **found(g)} if art else {})
              for g in add]
    result += [steam.Change(entry(g, existing.get(str(g.eboot), g.title), program, logo), for_game(g), remove=True)
               for g in remove]
    return result


# --- The artwork (the BC250 app's) -------------------------------------------------------------------------------

def draw_art(game: Game, logo: Path) -> dict[str, bytes]:
    """The portrait, the wide picture and the banner as PNG bytes, and the game's icon0.png as the logo on the banner
    (without it no logo: Steam shows the name there)."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    icon = QImage(str(game.picture("icon0.png") or logo))
    background = QImage(str(game.picture("pic1.png") or ""))
    images = {}
    for suffix in ("p", "", "_hero"):
        width, height = steam.ART[suffix]
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0, QColor("#0b1d3a"))
        gradient.setColorAt(1, QColor("#030810"))
        painter.fillRect(0, 0, width, height, gradient)
        if suffix != "p" and not background.isNull():
            _cover(painter, background, width, height)
            if suffix == "":
                painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 110))
        if suffix != "_hero" and not icon.isNull():
            side = min(width, height) * (0.7 if suffix == "p" else 0.62)
            top = height * 0.12 if suffix == "p" else (height - side) / 2
            painter.drawImage(QRectF((width - side) / 2, top, side, side), icon)
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
    own = game.picture("icon0.png")
    if own is not None and not icon.isNull():
        images["_logo"] = own.read_bytes()      # the file as it is, as Steam copies a logo chosen in its settings
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
