# SPDX-License-Identifier: GPL-3.0-or-later
"""The TV remote's buttons as key presses: the mappings of Valve's CEC daemon (cecd), which turns the CEC UI
commands the TV relays into Linux key events.

cecd's `mappings` table maps a UI command name to a Linux key code (a number). Setting it replaces cecd's whole
default table, so the app writes the defaults with the user's changes on top. The defaults below are the ones in
linux-cec's README (/usr/share/doc/linux-cec/README.md), by key name; libevdev turns the names into the codes."""

from __future__ import annotations

import ctypes
import ctypes.util
from functools import lru_cache

EV_KEY = 1

# cecd's default mapping: UI command name -> Linux key name (linux-cec 0.2.1).
DEFAULTS = {
    "select": "KEY_ENTER", "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
    "right-up": "KEY_RIGHT_UP", "right-down": "KEY_RIGHT_DOWN", "left-up": "KEY_LEFT_UP",
    "left-down": "KEY_LEFT_DOWN", "device-root-menu": "KEY_ROOT_MENU", "device-setup-menu": "KEY_SETUP",
    "contents-menu": "KEY_MENU", "favorite-menu": "KEY_FAVORITES", "back": "KEY_ESC",
    "media-top-menu": "KEY_MEDIA_TOP_MENU", "media-context-sensitive-menu": "KEY_CONTEXT_MENU",
    "number-entry-mode": "KEY_DIGITS", "11": "KEY_NUMERIC_11", "12": "KEY_NUMERIC_12", "0": "KEY_NUMERIC_0",
    "1": "KEY_NUMERIC_1", "2": "KEY_NUMERIC_2", "3": "KEY_NUMERIC_3", "4": "KEY_NUMERIC_4", "5": "KEY_NUMERIC_5",
    "6": "KEY_NUMERIC_6", "7": "KEY_NUMERIC_7", "8": "KEY_NUMERIC_8", "9": "KEY_NUMERIC_9", "dot": "KEY_DOT",
    "enter": "KEY_ENTER", "clear": "KEY_CLEAR", "next-favorite": "KEY_NEXT_FAVORITE", "channel-up": "KEY_CHANNELUP",
    "channel-down": "KEY_CHANNELDOWN", "previous-channel": "KEY_PREVIOUS", "sound-select": "KEY_SOUND",
    "display-information": "KEY_INFO", "help": "KEY_HELP", "page-up": "KEY_PAGEUP", "page-down": "KEY_PAGEDOWN",
    "power": "KEY_POWER", "volume-up": "KEY_VOLUMEUP", "volume-down": "KEY_VOLUMEDOWN", "mute": "KEY_MUTE",
    "play": "KEY_PLAYCD", "stop": "KEY_STOPCD", "pause": "KEY_PAUSECD", "record": "KEY_RECORD",
    "rewind": "KEY_REWIND", "fast-forward": "KEY_FASTFORWARD", "eject": "KEY_EJECTCD",
    "skip-forward": "KEY_NEXTSONG", "skip-backward": "KEY_PREVIOUSSONG", "stop-record": "KEY_STOP_RECORD",
    "pause-record": "KEY_PAUSE_RECORD", "angle": "KEY_ANGLE", "video-on-demand": "KEY_VOD",
    "electronic-program-guide": "KEY_EPG", "timer-programming": "KEY_TIME", "initial-configuration": "KEY_CONFIG",
    "audio-description": "KEY_AUDIO_DESC", "internet": "KEY_WWW", "3d-mode": "KEY_3D_MODE",
    "restore-volume-function": "KEY_UNMUTE", "power-toggle-function": "KEY_POWER",
    "power-off-function": "KEY_SLEEP", "power-on-function": "KEY_WAKEUP", "f1": "KEY_BLUE", "f2": "KEY_RED",
    "f3": "KEY_GREEN", "f4": "KEY_YELLOW", "f5": "KEY_F5", "data": "KEY_DATA",
}

# The buttons most TVs relay from their remote, first in the list. (cecd name, label)
COMMON = (
    ("select", "OK"), ("up", "Up"), ("down", "Down"), ("left", "Left"), ("right", "Right"), ("back", "Back"),
    ("play", "Play"), ("pause", "Pause"), ("stop", "Stop"), ("rewind", "Rewind"), ("fast-forward", "Fast forward"),
    ("skip-backward", "Previous"), ("skip-forward", "Next"), ("f2", "Red"), ("f3", "Green"), ("f4", "Yellow"),
    ("f1", "Blue"), ("display-information", "Info"), ("channel-up", "Channel up"),
    ("channel-down", "Channel down"),
)


def _button_label(name: str) -> str:
    """ "device-root-menu" -> "Device root menu", "7" -> "Number 7", "f5" -> "F5" """
    if name.isdigit():
        return f"Number {name}"
    if name[0] == "f" and name[1:].isdigit():
        return name.upper()
    return name.replace("-", " ").capitalize()


# Every button cecd maps: the common ones, then the rest in cecd's order. TVs differ in what they relay (a CEC 2.0
# TV may pass on more of its remote), so all of them can be changed.
BUTTONS = COMMON + tuple((name, _button_label(name)) for name in DEFAULTS if name not in dict(COMMON))

# What a button can do: (key name, label). "" is cecd's default for that button, None is nothing.
KEYS = (
    ("", "Default"), (None, "Nothing"),
    ("KEY_ENTER", "Enter"), ("KEY_ESC", "Escape"), ("KEY_SPACE", "Space"), ("KEY_TAB", "Tab"),
    ("KEY_BACKSPACE", "Backspace"), ("KEY_UP", "Arrow up"), ("KEY_DOWN", "Arrow down"),
    ("KEY_LEFT", "Arrow left"), ("KEY_RIGHT", "Arrow right"), ("KEY_HOME", "Home"), ("KEY_END", "End"),
    ("KEY_PAGEUP", "Page up"), ("KEY_PAGEDOWN", "Page down"), ("KEY_PLAYPAUSE", "Play/pause"),
    ("KEY_PLAYCD", "Play"), ("KEY_PAUSECD", "Pause"), ("KEY_STOPCD", "Stop"), ("KEY_NEXTSONG", "Next track"),
    ("KEY_PREVIOUSSONG", "Previous track"), ("KEY_REWIND", "Rewind"), ("KEY_FASTFORWARD", "Fast forward"),
    ("KEY_VOLUMEUP", "Volume up"), ("KEY_VOLUMEDOWN", "Volume down"), ("KEY_MUTE", "Mute"),
    ("KEY_F11", "F11 (full screen)"), ("KEY_F12", "F12 (Steam screenshot)"), ("KEY_SYSRQ", "Print (screenshot)"),
    ("KEY_LEFTMETA", "Super (app launcher)"), ("KEY_MENU", "Menu"), ("KEY_INFO", "Info"),
    ("KEY_RED", "Red"), ("KEY_GREEN", "Green"), ("KEY_YELLOW", "Yellow"), ("KEY_BLUE", "Blue"),
)
_LABELS = {name: label for name, label in KEYS if name}


@lru_cache(maxsize=None)
def _libevdev():
    path = ctypes.util.find_library("evdev") or "libevdev.so.2"
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        return None
    lib.libevdev_event_code_from_name.restype = ctypes.c_int
    lib.libevdev_event_code_from_name.argtypes = [ctypes.c_uint, ctypes.c_char_p]
    lib.libevdev_event_code_get_name.restype = ctypes.c_char_p
    lib.libevdev_event_code_get_name.argtypes = [ctypes.c_uint, ctypes.c_uint]
    return lib


def available() -> bool:
    return _libevdev() is not None


def code(name: str) -> int:
    """KEY_ENTER -> 28; -1 for a name this system does not know."""
    lib = _libevdev()
    return lib.libevdev_event_code_from_name(EV_KEY, name.encode()) if lib else -1


def name_of(number: int) -> str:
    lib = _libevdev()
    found = lib.libevdev_event_code_get_name(EV_KEY, number) if lib else None
    return found.decode() if found else f"key code {number}"


def label(name: str | None) -> str:
    return "Nothing" if name is None else _LABELS.get(name, name)


def choices_from(mappings: dict[str, int] | None) -> dict[str, str | None]:
    """The app's choice for each button from a written `mappings` table: "" where it is the default."""
    if not mappings:
        return {button: "" for button, _label in BUTTONS}
    out = {}
    for button, _label in BUTTONS:
        number = mappings.get(button)
        if number is None:
            out[button] = None
        else:
            name = name_of(number)
            out[button] = "" if name == DEFAULTS[button] else name
    return out


def mappings_for(choices: dict[str, str | None]) -> dict[str, int] | None:
    """The full table to write: cecd's defaults with the choices on top; None when every choice is the default
    (then the app writes no table and cecd keeps its own)."""
    if all(choices.get(button, "") == "" for button, _label in BUTTONS):
        return None
    table = {button: code(key) for button, key in DEFAULTS.items()}
    for button, key in choices.items():
        if key is None:
            table.pop(button, None)
        elif key:
            table[button] = code(key)
    return {button: number for button, number in table.items() if number >= 0}
