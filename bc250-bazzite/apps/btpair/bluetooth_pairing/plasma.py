# SPDX-License-Identifier: GPL-3.0-or-later
"""Bluetooth at login: Plasma's Bluetooth (bluedevil) switches the adapter on or off when you log in. By default it
restores the state it saved when the last session ended ("Remember previous state" in System Settings, Bluetooth).
A reboot from a terminal, or one an update starts, stops bluetoothd before the desktop session, so Plasma saves it as
off: the keyboard and mouse that worked at the login screen then stop at the desktop (seen on the board,
11-11-2026). The app sets "When logging in: Enable Bluetooth" instead, your own setting in bluedevilglobalrc,
through KDE's kreadconfig6 and kwriteconfig6."""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable

FILE = "bluedevilglobalrc"
GROUP = "General"
KEY = "launchState"
ENABLE, REMEMBER, DISABLE = "enable", "remember", "disable"   # Plasma's choices; remember when the key is not set

Runner = Callable[[list[str]], tuple[int, str]]


def run(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return done.returncode, done.stdout


def available(which: Callable[[str], str | None] = shutil.which) -> bool:
    """Whether this is Plasma's desktop, with its tools to read and write the setting."""
    return bool(which("kreadconfig6") and which("kwriteconfig6"))


def launch_state(run: Runner = run) -> str:
    """What Plasma does with Bluetooth at login: ENABLE, REMEMBER (its default) or DISABLE."""
    code, out = run(["kreadconfig6", "--file", FILE, "--group", GROUP, "--key", KEY, "--default", REMEMBER])
    value = out.strip().lower()
    return value if code == 0 and value in (ENABLE, REMEMBER, DISABLE) else REMEMBER


def set_enable(on: bool, run: Runner = run) -> bool:
    """On: Bluetooth on at every login. Off: Plasma's default again (it remembers the last state)."""
    tail = [ENABLE] if on else ["--delete"]
    code, _out = run(["kwriteconfig6", "--file", FILE, "--group", GROUP, "--key", KEY, *tail])
    return code == 0
