# SPDX-License-Identifier: GPL-3.0-or-later
"""Steam launch options that start the game monitor (gamemon) from a place that is no longer there.

The In-Game page hands out a launch line that names a python, the app's folder (PYTHONPATH) and the package. When
any of them goes (a checkout moved, the package renamed from bc250_gui to bazzite_check), Steam's start of the game
fails at once and the game never starts, with nothing pointing to the cause. Steam keeps the launch options per
user in userdata/<user>/config/localconfig.vdf, under apps/<appid>/LaunchOptions, in the text key-value format;
this module only reads it. The game's name comes from the appmanifest_<appid>.acf in one of Steam's libraries."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "bazzite_check"
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')
# A launch line's gamemon part: an optional PYTHONPATH=..., the python and -m <package>.gamemon. A word is
# unquoted or in the quotes shlex.quote() puts around a path with spaces.
_WORD = r"""(?:'[^']*'|"[^"]*"|[^\s'"])+"""
_GAMEMON = re.compile(rf"(?:PYTHONPATH={_WORD}\s+)?{_WORD}\s+-m\s+[A-Za-z_][\w.]*\.gamemon(?=\s|$)")
_NAME = re.compile(r'^\s*"name"\s+"((?:[^"\\]|\\.)*)"', re.MULTILINE)
_PATH = re.compile(r'^\s*"path"\s+"((?:[^"\\]|\\.)*)"', re.MULTILINE)


@dataclass(frozen=True)
class StaleLine:
    appid: str
    name: str
    line: str           # the launch options as Steam has them
    reason: str         # what is missing, for the page
    fixed: str          # the same options with the current gamemon part


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), text)


def launch_options(text: str) -> dict[str, str]:
    """appid -> LaunchOptions from a localconfig.vdf, for every app that has them (an empty value is left out)."""
    found: dict[str, str] = {}
    path: list[str] = []
    key: str | None = None
    for match in _TOKEN.finditer(text):
        string, brace = match.groups()
        if brace == "{":
            path.append(key or "")
            key = None
        elif brace == "}":
            if path:
                path.pop()
            key = None
        elif key is None:
            key = _unescape(string)
        else:
            value = _unescape(string)
            if (key.lower() == "launchoptions" and value.strip() and len(path) >= 2
                    and path[-2].lower() == "apps" and path[-1].isdigit()):
                found[path[-1]] = value
            key = None
    return found


def gamemon_problem(line: str) -> str | None:
    """Why the gamemon part of a launch line cannot start, or None when it can or the line has no gamemon."""
    match = _GAMEMON.search(line)
    if not match:
        return None
    try:
        words = shlex.split(match[0])
    except ValueError:
        return "the launch line cannot be read"
    pythonpath = next((w.split("=", 1)[1] for w in words if w.startswith("PYTHONPATH=")), None)
    python, module = words[-3], words[-1]
    package = module.rsplit(".", 1)[0]
    if not (os.path.isfile(python) and os.access(python, os.X_OK)):
        return f"its python is gone ({python})"
    if pythonpath and not Path(pythonpath).is_dir():
        return f"its app folder is gone ({pythonpath})"
    if package != PACKAGE:
        return f"it names the package {package}, now {PACKAGE}"
    if pythonpath and not (Path(pythonpath) / PACKAGE / "gamemon.py").is_file():
        return f"its app folder has no {PACKAGE} ({pythonpath})"
    return None


def fixed_line(line: str, prefix: str) -> str:
    """The launch options with their gamemon part replaced by `prefix` (the current one); the rest stays."""
    return _GAMEMON.sub(lambda _m: prefix, line, count=1)


def _libraries(steam: Path) -> list[Path]:
    folders = [steam / "steamapps"]
    try:
        text = (steam / "steamapps" / "libraryfolders.vdf").read_text(errors="replace")
    except OSError:
        return folders
    for raw in _PATH.findall(text):
        folder = Path(_unescape(raw)) / "steamapps"
        if folder not in folders:
            folders.append(folder)
    return folders


def game_name(steam: Path, appid: str) -> str:
    for library in _libraries(steam):
        try:
            text = (library / f"appmanifest_{appid}.acf").read_text(errors="replace")
        except OSError:
            continue
        if match := _NAME.search(text):
            return _unescape(match[1])
    return f"AppID {appid}"


def stale_lines(steam: Path | None, prefix: str) -> list[StaleLine]:
    """Every Steam user's launch options whose gamemon cannot start, each with the current line in its place."""
    if steam is None:
        return []
    found: dict[str, StaleLine] = {}
    for config in sorted((steam / "userdata").glob("*/config/localconfig.vdf")):
        try:
            text = config.read_text(errors="replace")
        except OSError:
            continue
        for appid, line in launch_options(text).items():
            reason = gamemon_problem(line)
            if reason and appid not in found:
                found[appid] = StaleLine(appid, game_name(steam, appid), line, reason, fixed_line(line, prefix))
    return sorted(found.values(), key=lambda s: s.name.lower())


def from_checkout(root: Path) -> bool:
    """Whether the app runs from a git checkout rather than its installed folder: a launch line copied then names
    the checkout, and stops working when it moves or its python goes."""
    return any((folder / ".git").exists() for folder in (root, *root.parents))
