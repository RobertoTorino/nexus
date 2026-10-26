# SPDX-License-Identifier: AGPL-3.0-or-later
"""Started by Steam: its library path left, X11 in Game Mode (steam_env.py)."""

from __future__ import annotations

import sys

from consoles_link import steam_env

STEAM_PATH = ("/home/u/.local/share/Steam/ubuntu12_32:/home/u/.local/share/Steam/ubuntu12_32/steam-runtime/"
              "pinned_libs_64:/usr/lib64")


def test_started_by_steam_the_app_starts_again_without_its_libraries(monkeypatch):
    calls = []
    env = {"LD_LIBRARY_PATH": STEAM_PATH, "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "KDE", "HOME": "/home/u"}
    steam_env.settle(env, lambda *args: calls.append(args))
    path, argv, cleaned = calls[0]
    assert path == sys.executable and argv == sys.orig_argv
    assert "LD_LIBRARY_PATH" not in cleaned and cleaned[steam_env.MARK] == "1" and cleaned["HOME"] == "/home/u"


def test_steams_overlay_is_left_and_the_rest_kept():
    calls = []
    preload = ("/usr/lib/extest/libextest.so:/home/u/.local/share/Steam/ubuntu12_32/gameoverlayrenderer.so:"
               "/home/u/.local/share/Steam/ubuntu12_64/gameoverlayrenderer.so")
    env = {"LD_PRELOAD": preload, "LD_LIBRARY_PATH": "/opt/mine/lib"}       # the shortcut's (owner's board)
    steam_env.settle(env, lambda *args: calls.append(args))
    cleaned = calls[0][2]
    assert cleaned["LD_PRELOAD"] == "/usr/lib/extest/libextest.so" and cleaned["LD_LIBRARY_PATH"] == "/opt/mine/lib"
    calls.clear()
    steam_env.settle({"LD_PRELOAD": "/x/gameoverlayrenderer.so"}, lambda *args: calls.append(args))
    assert "LD_PRELOAD" not in calls[0][2]


def test_once_only_and_not_without_steam():
    calls = []
    steam_env.settle({"LD_LIBRARY_PATH": STEAM_PATH, steam_env.MARK: "1"}, lambda *args: calls.append(args))
    steam_env.settle({"LD_LIBRARY_PATH": "/opt/mine/lib", "LD_PRELOAD": "/usr/lib/extest/libextest.so"},
                     lambda *args: calls.append(args))
    steam_env.settle({}, lambda *args: calls.append(args))
    assert calls == []


def test_x11_in_game_mode():
    env = {"DISPLAY": ":1", "XDG_CURRENT_DESKTOP": "gamescope"}
    steam_env.settle(env, lambda *args: None)
    assert env["QT_QPA_PLATFORM"] == "xcb"
    own = {"DISPLAY": ":1", "XDG_CURRENT_DESKTOP": "gamescope", "QT_QPA_PLATFORM": "wayland"}
    steam_env.settle(own, lambda *args: None)
    assert own["QT_QPA_PLATFORM"] == "wayland"                     # the user's choice stays
    desktop = {"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "KDE"}
    steam_env.settle(desktop, lambda *args: None)
    assert "QT_QPA_PLATFORM" not in desktop
