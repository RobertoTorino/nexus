# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings window offers (owner, 03-11-2026, from the Windows Portable Suite's PPSSPP Manager):
PPSSPP's settings that matter for playing, each one key of ppsspp.ini on PPSSPP's memory stick (userdata), read from
the file (or PPSSPP's default while it names none) and written one at a time, every other line kept. Never while
PPSSPP runs: it writes the whole file back when it closes.

The keys, their sections and their defaults are PPSSPP 1.20.4's (Core/Config.cpp). PPSSPP writes booleans as True
and False, floats with six decimals (0.150000) and the renderer with its name (3 (VULKAN)); the app offers the
Linux build's renderers, Vulkan (PPSSPP's own choice where it is there) and OpenGL. The On screen switches are bits
of one key ([Graphics] iShowStatusFlags: 2 the FPS, 4 the speed). The window is core's settings_page, one box per
group (GROUPS below: the picture, the game, the sound, the controller, on screen), which takes a switch as "true"
or "false" and the volume as a number."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bc250_core.settings_page import CHOICE, PERCENT, SWITCH

from . import userdata

FLAG = "flag"                           # a bit of a number, offered as a switch
TRUE, FALSE = "True", "False"           # as PPSSPP writes them
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def _number(value: str) -> float | None:
    """The number a value starts with ("3 (VULKAN)": 3, "0.150000": 0.15); None for none."""
    match = _NUMBER.match(value or "")
    return float(match.group(1)) if match else None


@dataclass(frozen=True)
class Setting:
    """One setting: *ini_key* of *section* in ppsspp.ini. A CHOICE offers *choices* (the value as PPSSPP writes it,
    as shown); a SWITCH is True or False; a PERCENT a number; a FLAG the *bit* of a number, on or off. *default* is
    PPSSPP's own, in the form the window uses (a switch as "true" or "false")."""
    key: str                            # the app's own name for it
    group: str                          # the box it is shown in
    label: str
    section: str
    ini_key: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""
    default: str = ""
    bit: int = 0

    def canonical(self, raw: str | None) -> str:
        """What ppsspp.ini holds (None: nothing) in the window's form: the default for nothing, "true" or "false"
        for a switch or a flag, the offered choice with the same number for a choice ("3" and "3 (VULKAN)" are
        one), a number as it is."""
        if raw is None or raw.strip() == "":
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return "true" if raw.lower() in ("true", "1") else "false" if raw.lower() in ("false", "0") else raw
        if self.kind == FLAG:
            number = _number(raw)
            return raw if number is None else "true" if int(number) & self.bit else "false"
        if self.kind == PERCENT:
            number = _number(raw)
            return str(int(number)) if number is not None else raw
        number = _number(raw)
        return next((choice for choice, _ in self.choices if choice == raw
                     or (number is not None and _number(choice) == number)), raw)

    def written(self, value: str) -> str:
        """*value* (as the window gives it) as PPSSPP writes it: True or False for a switch."""
        if self.kind == SWITCH:
            return TRUE if value == "true" else FALSE
        return value


PICTURE, GAME, SOUND, CONTROLLER, ON_SCREEN = "Picture", "Game", "Sound", "Controller", "On screen"
# GraphicsBackend: the Linux build's renderers, as PPSSPP writes them (Vulkan its own choice where it is there)
RENDERERS = (("3 (VULKAN)", "Vulkan"), ("0 (OPENGL)", "OpenGL"))
# InternalResolution: the PSP's own picture (480 x 272) times this; Automatic follows the window's size
RESOLUTIONS = (("0", "Automatic (the screen's)"), ("1", "1x (480 × 272, the PSP's)"), ("2", "2x (960 × 544)"),
               ("3", "3x (1440 × 816, 1080p)"), ("4", "4x (1920 × 1088)"), ("5", "5x (2400 × 1360)"),
               ("6", "6x (2880 × 1632, 4K)"), ("8", "8x (3840 × 2176)"))
FILTERS = (("1", "Automatic"), ("2", "Nearest (sharp pixels)"), ("3", "Linear (smooth)"),
           ("4", "Automatic, best quality"))
ANISOTROPY = (("0", "Off"), ("1", "2x"), ("2", "4x"), ("3", "8x"), ("4", "16x"))
FRAMESKIPS = (("0", "Off"), ("1", "1 frame"), ("2", "2 frames"), ("3", "3 frames"))
DEADZONES = (("0.150000", "PPSSPP's (0.15)"), ("0.000000", "Off"), ("0.250000", "Medium (0.25)"),
             ("0.350000", "Large (0.35)"))
SENSITIVITIES = (("1.100000", "PPSSPP's (1.10)"), ("1.000000", "As the stick (1.00)"), ("1.300000", "Higher (1.30)"))

SETTINGS: tuple[Setting, ...] = (
    Setting("renderer", PICTURE, "Renderer", "Graphics", "GraphicsBackend", CHOICE, RENDERERS,
            "How PPSSPP draws: Vulkan is its own choice on the system; OpenGL when a game shows faults.",
            RENDERERS[0][0]),
    Setting("resolution", PICTURE, "Internal resolution", "Graphics", "InternalResolution", CHOICE, RESOLUTIONS,
            "The size PPSSPP draws the picture at: Automatic follows the screen; 3x fills a 1080p screen sharply, "
            "6x a 4K one. A higher one asks more of the GPU.", "0"),
    Setting("stretch", PICTURE, "Stretch to the screen", "DisplayLayout.Landscape", "DisplayStretch", SWITCH,
            tip="The picture fills the whole screen; off, it keeps the PSP's shape.", default="false"),
    Setting("integer", PICTURE, "Integer scaling", "DisplayLayout.Landscape", "DisplayIntegerScale", SWITCH,
            tip="Scales the picture by whole numbers only, so every pixel stays the same size; it may leave a "
                "border.", default="false"),
    Setting("filtering", PICTURE, "Texture filtering", "Graphics", "TextureFiltering", CHOICE, FILTERS,
            "How textures are smoothed: Nearest keeps pixel art sharp.", "1"),
    Setting("anisotropy", PICTURE, "Anisotropic filtering", "Graphics", "AnisotropyLevel", CHOICE, ANISOTROPY,
            "Sharper textures seen at an angle, such as a road ahead.", "4"),
    Setting("vsync", PICTURE, "VSync", "Graphics", "VerticalSync", SWITCH,
            tip="Waits for the screen's refresh before showing a frame: no tearing, a little more delay.",
            default="true"),
    Setting("frameskip", GAME, "Frame skipping", "Graphics", "FrameSkip", CHOICE, FRAMESKIPS,
            "Frames left out to keep a slow game at full speed.", "0"),
    Setting("cheats", GAME, "Cheats", "General", "EnableCheats", SWITCH,
            tip="The cheats in PPSSPP's cheats folder, for the games they are made for.", default="false"),
    Setting("volume", SOUND, "Volume", "Sound", "GameVolume", PERCENT, tip="The game's sound, in percent.",
            default="100"),
    Setting("deadzone", CONTROLLER, "Stick dead zone", "Control", "AnalogDeadzone", CHOICE, DEADZONES,
            "How far a stick moves before the game sees it: for a stick that drifts.", DEADZONES[0][0]),
    Setting("sensitivity", CONTROLLER, "Stick sensitivity", "Control", "AnalogSensitivity", CHOICE, SENSITIVITIES,
            "How far the PSP's stick goes for the stick's travel: PPSSPP's 1.10 reaches the edge a little sooner.",
            SENSITIVITIES[0][0]),
    Setting("fps", ON_SCREEN, "Show FPS", "Graphics", "iShowStatusFlags", FLAG,
            tip="The frames a second in a corner of the picture.", default="false", bit=2),
    Setting("speed", ON_SCREEN, "Show speed", "Graphics", "iShowStatusFlags", FLAG,
            tip="The game's speed in percent.", default="false", bit=4),
)
GROUPS = (PICTURE, GAME, SOUND, CONTROLLER, ON_SCREEN)


def read_setting(memstick: Path, setting: Setting) -> str:
    """The setting's value as ppsspp.ini holds it, in the window's form (Setting.canonical): PPSSPP's default when
    the file names none."""
    lines, _bom = userdata.read_lines(userdata.settings_path(memstick))
    return setting.canonical(userdata.ini_value(lines, setting.section, setting.ini_key))


def read_settings(memstick: Path) -> dict[str, str]:
    """Every setting's value, the app's key to the value."""
    lines, _bom = userdata.read_lines(userdata.settings_path(memstick))
    return {setting.key: setting.canonical(userdata.ini_value(lines, setting.section, setting.ini_key))
            for setting in SETTINGS}


def write_setting(memstick: Path, setting: Setting, value: str) -> None:
    """Sets the setting's key to *value* (as read_setting gives it; a FLAG sets or clears its bit of the number);
    everything else in the file stays. OSError is the caller's, who makes sure PPSSPP does not run."""
    path = userdata.settings_path(memstick)
    lines, bom = userdata.read_lines(path)
    if setting.kind == FLAG:
        number = _number(userdata.ini_value(lines, setting.section, setting.ini_key) or "")
        flags = int(number) if number is not None else 0
        value = str(flags | setting.bit if value == "true" else flags & ~setting.bit)
    userdata.ini_set(lines, setting.section, setting.ini_key, setting.written(value))
    userdata.write_lines(path, lines, bom)
