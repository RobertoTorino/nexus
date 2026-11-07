# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers connected, as the kernel lists them (/proc/bus/input/devices): a device with a joystick handler
(js0, js1…) that is not Steam's virtual controller (vendor 28DE), the same rule as the run wrapper's; a
controller's motion sensors, which the kernel lists as a joystick of their own over Bluetooth (the DualSense Edge
on the owner's board), are not a second controller. The window says when there is none (owner, 24-10-2026: a
controller switched off by its idle timer left a game without one), since a game started from Steam reads the
controller that is there when it starts."""

from __future__ import annotations

import re
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
