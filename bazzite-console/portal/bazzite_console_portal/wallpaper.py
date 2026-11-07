# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's wallpaper: a picture of the user's own behind the header, the tabs and the tiles (owner,
20-10-2026). It must be at least MIN_WIDTH x MIN_HEIGHT and 16:9 (within RATIO_TOLERANCE), as PNG, JPEG or WebP, so
it fills the window without blurring or stretching. The portal keeps a copy in its state folder (the original may be
moved or deleted later), which the portal's --purge removes.

The portal also remembers where the last SAVED_MAX wallpapers came from (owner, 20-10-2026), newest first, in
HISTORY in its state folder, so one used before can be chosen again from the Wallpaper pill. Only the paths are kept:
a picture moved or deleted since cannot be chosen again until it is back.

The portal ships an example wallpaper (EXAMPLE, owner, 20-10-2026), to show how a wallpaper looks before the user
adds their own. It is never set by itself: the user chooses it in the Wallpaper pill's menu, and USE_EXAMPLE in the
state folder records that choice."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PyQt6.QtGui import QImageReader

from . import ROOT, state_dir

MIN_WIDTH, MIN_HEIGHT = 1920, 1080
RATIO = 16 / 9
RATIO_TOLERANCE = 0.02                  # 1920 x 1080, 2560 x 1440, 3840 x 2160, and pictures a few pixels off
SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
NAME = "wallpaper"                      # wallpaper.<suffix> in the portal's state folder
HISTORY = "wallpapers.json"              # {"saved": [path, ...]}, newest first
SAVED_MAX = 10
EXAMPLE = ROOT / "images" / "wallpaper-example.webp"
USE_EXAMPLE = "wallpaper-example"       # in the portal's state folder: the example was chosen
RULES = (f"A wallpaper must be a PNG, JPEG or WebP picture of at least {MIN_WIDTH} x {MIN_HEIGHT} pixels, "
         "in 16:9 (as 1920 x 1080, 2560 x 1440 or 3840 x 2160).")


def problem(path: Path) -> str:
    """Why *path* cannot be the wallpaper, or "" when it can. Reads only the picture's header."""
    if path.suffix.lower() not in SUFFIXES:
        return f"{path.name} is not a PNG, JPEG or WebP picture."
    reader = QImageReader(str(path))
    size = reader.size()
    if not reader.canRead() or not size.isValid():
        return f"{path.name} could not be read as a picture."
    width, height = size.width(), size.height()
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return f"{path.name} is {width} x {height} pixels: smaller than {MIN_WIDTH} x {MIN_HEIGHT}."
    if abs(width / height - RATIO) > RATIO * RATIO_TOLERANCE:
        return f"{path.name} is {width} x {height} pixels: not 16:9."
    return ""


def current(folder: Path | None = None) -> Path | None:
    """The wallpaper chosen (the copy of the user's picture), or None."""
    folder = folder or state_dir()
    return next((p for p in sorted(folder.glob(f"{NAME}.*")) if p.suffix.lower() in SUFFIXES), None)


def is_example(folder: Path | None = None) -> bool:
    """Whether the example wallpaper was chosen."""
    return ((folder or state_dir()) / USE_EXAMPLE).is_file()


def shown(folder: Path | None = None, example: Path = EXAMPLE) -> Path | None:
    """The picture behind the portal: the user's own, else *example* when it was chosen; None for none."""
    folder = folder or state_dir()
    if (chosen := current(folder)) is not None:
        return chosen
    return example if is_example(folder) and example.is_file() else None


def _clear(folder: Path) -> None:
    for old in folder.glob(f"{NAME}.*"):
        old.unlink(missing_ok=True)
    (folder / USE_EXAMPLE).unlink(missing_ok=True)


def remove(folder: Path | None = None) -> None:
    """No wallpaper any more: neither the user's own nor the example."""
    _clear(folder or state_dir())


def use_example(folder: Path | None = None) -> None:
    """The example wallpaper, in place of the user's own."""
    folder = folder or state_dir()
    _clear(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / USE_EXAMPLE).touch()


def choose(path: Path, folder: Path | None = None) -> Path:
    """Make *path* the wallpaper: a copy in the state folder, in place of the one before. Raises ValueError with
    the reason when the picture does not meet the rules (OSError when it cannot be copied)."""
    reason = problem(path)
    if reason:
        raise ValueError(f"{reason}\n\n{RULES}")
    folder = folder or state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{NAME}{path.suffix.lower()}"
    staged = folder / f".{NAME}-new{path.suffix.lower()}"
    shutil.copyfile(path, staged)
    _clear(folder)
    staged.replace(target)
    remember(path, folder)
    return target


def saved(folder: Path | None = None) -> list[Path]:
    """Where the wallpapers chosen before came from, newest first (the first is the current one, if there is
    one); [] when none was chosen or the list cannot be read."""
    folder = folder or state_dir()
    try:
        paths = json.loads((folder / HISTORY).read_text(encoding="utf-8"))["saved"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [Path(p) for p in paths if isinstance(p, str)][:SAVED_MAX]


def remember(path: Path, folder: Path | None = None) -> None:
    """Put *path* first in the saved wallpapers, once, and keep the newest SAVED_MAX."""
    folder = folder or state_dir()
    path = path.absolute()
    paths = [path] + [p for p in saved(folder) if p != path]
    folder.mkdir(parents=True, exist_ok=True)
    staged = folder / f".{HISTORY}.new"
    staged.write_text(json.dumps({"saved": [str(p) for p in paths[:SAVED_MAX]]}, indent=1) + "\n", encoding="utf-8")
    staged.replace(folder / HISTORY)
