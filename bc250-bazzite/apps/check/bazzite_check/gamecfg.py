# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-game in-game monitoring settings, shared by the wrapper (gamemon) and the GUI.

One INI file, one section per game. The key of a Steam game is "steam-<appid>", any other game uses a
slug of its executable name, so the wrapper and the GUI always agree. Plain configparser (no Qt): the
wrapper must work without the GUI's virtual environment.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "bc250-bazzite-test"
CONFIG_PATH = CONFIG_DIR / "games.ini"
LOG_DIR = Path.home() / ".local" / "share" / "bc250-bazzite-test" / "game-logs"

DEFAULT_INTERVAL_S = 2.0
MIN_INTERVAL_S = 1.0
MAX_INTERVAL_S = 60.0


def slug(text: str) -> str:
    """File- and section-safe name: lower case, runs of other characters become one dash."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "game"


def game_key(appid: str | None, name: str) -> str:
    return f"steam-{appid}" if appid else slug(name)


def shot_path(key: str) -> Path:
    """The game's one-time screenshot, taken by the wrapper during the first recorded session."""
    return LOG_DIR / f"bc250-game-{key}.png"


@dataclass
class GameConfig:
    key: str
    title: str = ""
    enabled: bool = True
    interval_s: float = DEFAULT_INTERVAL_S
    overlay: bool = False
    last_runtime_s: float = 0.0     # length of the most recent session, written by the wrapper
    total_runtime_s: float = 0.0    # all sessions together (also when recording is off)


def _clamp(v: float) -> float:
    return max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, v))


def _parser() -> configparser.ConfigParser:
    p = configparser.ConfigParser(interpolation=None)
    try:
        p.read(CONFIG_PATH, encoding="utf-8")
    except (OSError, configparser.Error):
        pass
    return p


def load(key: str) -> GameConfig:
    p = _parser()
    cfg = GameConfig(key)
    if p.has_section(key):
        s = p[key]
        cfg.title = s.get("title", "")
        cfg.enabled = s.getboolean("enabled", fallback=True)
        cfg.overlay = s.getboolean("overlay", fallback=False)
        try:
            cfg.interval_s = _clamp(s.getfloat("interval_s", fallback=DEFAULT_INTERVAL_S))
        except ValueError:
            pass
        try:
            cfg.last_runtime_s = max(0.0, s.getfloat("last_runtime_s", fallback=0.0))
            cfg.total_runtime_s = max(0.0, s.getfloat("total_runtime_s", fallback=0.0))
        except ValueError:
            pass
    return cfg


def load_all() -> list[GameConfig]:
    return [load(section) for section in _parser().sections()]


def save(cfg: GameConfig) -> None:
    p = _parser()
    if not p.has_section(cfg.key):
        p.add_section(cfg.key)
    p[cfg.key]["title"] = cfg.title
    p[cfg.key]["enabled"] = "true" if cfg.enabled else "false"
    p[cfg.key]["overlay"] = "true" if cfg.overlay else "false"
    p[cfg.key]["interval_s"] = f"{_clamp(cfg.interval_s):g}"
    p[cfg.key]["last_runtime_s"] = f"{max(0.0, cfg.last_runtime_s):.0f}"
    p[cfg.key]["total_runtime_s"] = f"{max(0.0, cfg.total_runtime_s):.0f}"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        p.write(fh)


def remember(key: str, title: str) -> GameConfig:
    """Load the game's config and make sure it has a section, so the GUI lists the game."""
    cfg = load(key)
    if title and cfg.title != title:
        cfg.title = title
    save(cfg)
    return cfg


def add_runtime(key: str, title: str, seconds: float) -> None:
    """Record a finished session's length: last session and the running total (wrapper, on game exit)."""
    cfg = load(key)
    if title and not cfg.title:
        cfg.title = title
    cfg.last_runtime_s = max(0.0, seconds)
    cfg.total_runtime_s += max(0.0, seconds)
    save(cfg)
