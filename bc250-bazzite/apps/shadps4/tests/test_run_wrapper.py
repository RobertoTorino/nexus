# SPDX-License-Identifier: GPL-3.0-or-later
"""The run wrapper (bc250-shadps4-run) with a fake shadPS4 that prints its arguments and SDL's controller lists: Steam's
list of controllers to ignore replaced while a real controller is there, left alone otherwise; a game Steam starts on
a Wayland desktop opened through XWayland, so Steam's overlay works over it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "bc250-shadps4-run"

# /proc/bus/input/devices on the owner's board with Steam running (14-10-2026): a DualShock 4 on USB, its motion
# sensors and touchpad, and Steam's virtual controller.
DS4_AND_STEAM = """\
I: Bus=0003 Vendor=054c Product=09cc Version=8111
N: Name="Sony Interactive Entertainment Wireless Controller"
H: Handlers=event3 js0

I: Bus=0003 Vendor=054c Product=09cc Version=8111
N: Name="Sony Interactive Entertainment Wireless Controller Motion Sensors"
H: Handlers=event4

I: Bus=0003 Vendor=054c Product=09cc Version=8111
N: Name="Sony Interactive Entertainment Wireless Controller Touchpad"
H: Handlers=mouse0 event5

I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 0"
H: Handlers=event14 js1
"""
STEAM_ONLY = DS4_AND_STEAM.split("\n\n")[-1]
STEAM_LIST = "0x054C/0x09CC"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a bash script for Linux")


@pytest.fixture
def run(tmp_path):
    shad = tmp_path / "data" / "bc250-shadps4-manager" / "emulator" / "current" / "Shadps4-sdl.AppImage"
    shad.parent.mkdir(parents=True)
    shad.write_text('#!/bin/sh\necho "args=$*"\necho "ignore=${SDL_GAMECONTROLLER_IGNORE_DEVICES-unset}"\n'
                    'echo "except=${SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT-unset}"\n'
                    'echo "video=${SDL_VIDEO_DRIVER-unset}"\n')
    shad.chmod(0o755)
    devices = tmp_path / "devices"

    def go(inputs: str, *args: str, **env: str) -> dict[str, str]:
        devices.write_text(inputs)
        environ = {k: v for k, v in os.environ.items()
                   if not k.startswith("SDL_") and k not in ("SteamGameId", "WAYLAND_DISPLAY", "DISPLAY")}
        environ.update(XDG_DATA_HOME=str(tmp_path / "data"), BC250_INPUT_DEVICES=str(devices), **env)
        done = subprocess.run(["/bin/bash", str(WRAPPER), *args], capture_output=True, text=True, env=environ,
                              check=True)
        return dict(line.split("=", 1) for line in done.stdout.splitlines())
    return go


def test_started_by_steam_with_a_real_controller(run):
    out = run(DS4_AND_STEAM, "-f", "true", "-g", "/games/a b/eboot.bin", SDL_GAMECONTROLLER_IGNORE_DEVICES=STEAM_LIST,
              SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT="0x28DE/0x1205")
    assert out == {"args": "-f true -g /games/a b/eboot.bin", "ignore": "0x28DE/0x11FF", "except": "unset",
                   "video": "unset"}


def test_started_by_steam_with_only_steams_controller(run):
    out = run(STEAM_ONLY, "-g", "x", SDL_GAMECONTROLLER_IGNORE_DEVICES=STEAM_LIST)
    assert out["ignore"] == STEAM_LIST                                  # Steam's choice stands


def test_started_outside_steam(run):
    out = run(DS4_AND_STEAM, "-b")
    assert out == {"args": "-b", "ignore": "unset", "except": "unset",  # SDL leaves Steam's controller out itself
                   "video": "unset"}


def test_started_by_steam_on_a_wayland_desktop(run):
    desktop = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    assert run(DS4_AND_STEAM, "-g", "x", SteamGameId="3710761059", **desktop)["video"] == "x11"
    assert run(DS4_AND_STEAM, "-g", "x", **desktop)["video"] == "unset"                     # Play, outside Steam
    assert run(DS4_AND_STEAM, "-g", "x", SteamGameId="1", DISPLAY=":0")["video"] == "unset"  # X11 only
    assert run(DS4_AND_STEAM, "-g", "x", SteamGameId="1", SDL_VIDEO_DRIVER="wayland",
               **desktop)["video"] == "wayland"                                             # a choice of the user's


def test_the_game_started_goes_to_the_apps_log(run, tmp_path):
    """One line in the app's log file, in its form, with the game's folder name (its ID as Extract PKG names it;
    not its path) and from where; a start without a game (shadPS4's own window) says nothing. Only the tools the
    wrapper needs on the PATH, so no real desktop notification is sent."""
    import re
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("awk", "dirname", "grep", "ldconfig"):
        found = subprocess.run(["bash", "-c", f"command -v {name}"], capture_output=True, text=True)
        if found.stdout.strip():
            (tools / name).symlink_to(found.stdout.strip())
    path = str(tools)
    log = tmp_path / "data" / "bc250-shadps4-manager" / "bc250-shadps4-manager.log"
    run(DS4_AND_STEAM, "-b", PATH=path)
    assert not log.exists()
    run(DS4_AND_STEAM, "-f", "true", "-g", "/games/a b/CUSA11624/eboot.bin", SteamGameId="3710761059", PATH=path)
    run(DS4_AND_STEAM, "--game", "/games/CUSA00001/eboot.bin", PATH=path)
    run(STEAM_ONLY, "-g", "/games/CUSA00002/eboot.bin", SteamGameId="3710761059", PATH=path)   # no real controller
    lines = log.read_text().splitlines()
    assert [line[20:] for line in lines] == ["INFO Started CUSA11624 from Steam, with a controller.",
                                             "INFO Started CUSA00001 from a terminal, with a controller.",
                                             "INFO Started CUSA00002 from Steam, without a controller."]
    assert all(re.fullmatch(r"\d\d-\d\d-\d{4} \d\d:\d\d:\d\d", line[:19]) for line in lines)
    assert "/games/" not in log.read_text() and "eboot" not in log.read_text()
