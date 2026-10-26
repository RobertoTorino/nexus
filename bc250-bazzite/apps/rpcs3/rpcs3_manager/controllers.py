# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers connected, as the kernel lists them (/proc/bus/input/devices): a device with a joystick handler
(js0, js1…) that is not Steam's virtual controller (vendor 28DE), the same rule as the run wrapper's; a
controller's motion sensors, which the kernel lists as a joystick of their own over Bluetooth (the DualSense Edge
on the owner's board), are not a second controller. The window says when there is none (owner, 24-10-2026: a
controller switched off by its idle timer left a game without one), since a game started from Steam reads the
controller that is there when it starts.

The names RPCS3 knows the controllers by are SDL's (its SDL handler, the one the app sets for player 1), which
differ from the kernel's: SDL names a DualSense by its USB product string, the kernel puts the maker in front over
USB. So the app asks SDL itself, the system's SDL3 library (the same library RPCS3 builds in), in a process of its
own: SDL opens the controllers to read their names, which is nothing for the window's own process to do."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEVICES = Path("/proc/bus/input/devices")
STEAM_VENDOR = "28de"
NOT_A_CONTROLLER = (" Motion Sensors", " Touchpad")     # a controller's other input devices, by the kernel's names
_VENDOR = re.compile(r"\bVendor=([0-9a-fA-F]+)")
_NAME = re.compile(r'^N: Name="(.*)"')
_JS = re.compile(r"\bjs\d+\b")


def connected(path: Path = DEVICES) -> list[str]:
    """The names of the controllers connected, in the kernel's order; [] without one (or without the file)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for block in text.split("\n\n"):
        vendor = name = ""
        joystick = False
        for line in block.splitlines():
            if line.startswith("I:"):
                m = _VENDOR.search(line)
                vendor = m.group(1).lower() if m else ""
            elif m := _NAME.match(line):
                name = m.group(1)
            elif line.startswith("H:") and _JS.search(line):
                joystick = True
        if joystick and vendor != STEAM_VENDOR and not name.endswith(NOT_A_CONTROLLER):
            found.append(name or "a controller")
    return found


# Run with the app's own Python, apart from the window: SDL3's gamepads by name, Steam's virtual one left out.
SDL_PROBE = r"""
import ctypes, sys
try:
    sdl = ctypes.CDLL("libSDL3.so.0")
except OSError:
    sys.exit(3)
sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
sdl.SDL_Init.restype = ctypes.c_bool
if not sdl.SDL_Init(0x00002000 | 0x00000200):          # SDL_INIT_GAMEPAD | SDL_INIT_JOYSTICK
    sys.exit(4)
sdl.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
sdl.SDL_GetGamepadNameForID.restype = ctypes.c_char_p
sdl.SDL_GetGamepadVendorForID.restype = ctypes.c_uint16
count = ctypes.c_int()
ids = sdl.SDL_GetGamepads(ctypes.byref(count))
for i in range(count.value):
    name = sdl.SDL_GetGamepadNameForID(ids[i])
    if name and sdl.SDL_GetGamepadVendorForID(ids[i]) != 0x28DE:
        sys.stdout.write(name.decode("utf-8", "replace") + "\n")
sdl.SDL_free(ids)
sdl.SDL_Quit()
"""
PROBE_TIMEOUT = 15


def sdl_names(python: str = sys.executable, timeout: float = PROBE_TIMEOUT) -> list[str] | None:
    """The controllers connected as SDL names them, in SDL's order; None when SDL3 is not on the system or did
    not answer (the caller falls back on the kernel's names)."""
    try:
        done = subprocess.run([python, "-I", "-c", SDL_PROBE], capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.splitlines() if line.strip()]
