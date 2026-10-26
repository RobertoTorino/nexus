# SPDX-License-Identifier: AGPL-3.0-or-later
"""The environment Steam starts the app with (its Game Mode shortcut, or a non-Steam game on the desktop), put right
before Qt loads. Only the standard library here: this runs first.

Two things Steam adds break the app's OpenGL, and with it the stream's picture (on the owner's board, 13-10-2026:
"EGL not available", sound but no picture):
- its overlay, gameoverlayrenderer.so in LD_PRELOAD, which hooks a program's OpenGL to draw Steam's overlay; a
  non-Steam game gets it (reproduced with the shortcut's own environment: no OpenGL with it, OpenGL without it);
- its runtime in LD_LIBRARY_PATH, /usr/lib64 included, ahead of the app's libraries, so the app's Qt (PyQt6's own)
  mixes with the system's (with Steam's own environment, Qt does not even load).
So the app starts itself again without both (the rest of LD_PRELOAD, and a library path of the user's own, stay).
Steam's overlay is then not over the stream on the desktop; in Game Mode Steam draws its menu itself. In Game Mode
(gamescope) the app uses X11, which gamescope is built around."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

MARK = "BC250_LEFT_STEAM_LIBRARIES"


OVERLAY = "gameoverlayrenderer"


def steams_libraries(env: dict[str, str]) -> bool:
    path = env.get("LD_LIBRARY_PATH", "")
    return "steam-runtime" in path or "/Steam/ubuntu12_" in path


def steams_overlay(env: dict[str, str]) -> bool:
    return OVERLAY in env.get("LD_PRELOAD", "")


def clean(env: dict[str, str]) -> dict[str, str]:
    """The environment without Steam's library path and overlay, marked so the app does not start itself again
    and again."""
    cleaned = dict(env)
    if steams_libraries(env):
        cleaned.pop("LD_LIBRARY_PATH")
    preload = [p for p in env.get("LD_PRELOAD", "").split(":") if p and OVERLAY not in p]
    if preload:
        cleaned["LD_PRELOAD"] = ":".join(preload)
    else:
        cleaned.pop("LD_PRELOAD", None)
    cleaned[MARK] = "1"
    return cleaned


def platform(env: dict[str, str]) -> str | None:
    """X11 (xcb) in Game Mode, unless QT_QPA_PLATFORM is set already; None: Qt's own choice."""
    if env.get("QT_QPA_PLATFORM") or not env.get("DISPLAY"):
        return None
    return "xcb" if "gamescope" in env.get("XDG_CURRENT_DESKTOP", "").lower() else None


def settle(env=os.environ, execve: Callable = os.execve) -> None:
    """Starts the app again without Steam's libraries and overlay when it was started with them; else sets the Qt
    platform."""
    if (steams_libraries(env) or steams_overlay(env)) and not env.get(MARK):
        execve(sys.executable, sys.orig_argv, clean(dict(env)))
    chosen = platform(env)
    if chosen:
        env["QT_QPA_PLATFORM"] = chosen
