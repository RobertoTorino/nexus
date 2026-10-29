# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PPSSPP's settings, and the settings the Settings pane offers: memstick\\PSP\\SYSTEM\\ppsspp.ini
in the app's PPSSPP folder (portable mode, emulator.py). Never while PPSSPP runs: it keeps its settings in memory and
writes the whole file back when it closes (the BC250 suite's rule).

The keys, their sections and their defaults are PPSSPP 1.20.4's (Core\\Config.cpp). PPSSPP reads a missing key as its
default and writes every key at its next close, so a file the app starts holds only what the app set; a value the
app does not offer is shown as PPSSPP wrote it. PPSSPP writes "Key = Value" under [Section], keys matched whatever
their case, booleans as True and False, floats with six decimals (0.150000), the renderer with its name
(3 (VULKAN)), the file with a UTF-8 byte order mark first and CRLF line ends on Windows.

What the app owns, set after an install, when the window opens and before PPSSPP starts (prepare): PPSSPP's notice
of a newer release off ([General] CheckForNewVersion; a newer PPSSPP comes with the app, and the notice is on PPSSPP's
main screen, which the app never shows). The controller needs nothing: PPSSPP maps an Xbox controller (XInput), the
handheld's own, at its first start, with LT and the guide button for its pause menu (Core\\KeyMapDefaults.cpp).

The settings the Settings pane offers, in tabs (TABS below: Picture, Game, Controller, On screen): each one key of
ppsspp.ini, read from the file (or PPSSPP's default while it names none) and written one at a time. The On screen
switches are bits of one key ([Graphics] iShowStatusFlags: 2 the FPS, 4 the speed, 8 the battery). The file is
changed line by line: every other line and its order stay as PPSSPP wrote it."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import emulator

BOM = "﻿"
NEWLINE = "\r\n"                        # as PPSSPP writes ppsspp.ini on Windows
TRUE, FALSE = "True", "False"
CHOICE, SWITCH, FLAG = "choice", "switch", "flag"
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def _number(value: str) -> float | None:
    """The number a value starts with ("3 (VULKAN)": 3, "0.150000": 0.15); None for none."""
    match = _NUMBER.match(value or "")
    return float(match.group(1)) if match else None


@dataclass(frozen=True)
class Setting:
    """One setting of the Settings pane: *ini_key* of *section* in ppsspp.ini. A CHOICE offers *choices* (value as
    PPSSPP writes it, as shown); a SWITCH is True or False; a FLAG is the *bit* of a number, on or off. *default*
    is PPSSPP's own, in the form the pane uses."""
    key: str                            # the app's own name for it
    label: str
    section: str
    ini_key: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""
    default: str = ""
    bit: int = 0

    def shown(self, value: str) -> str:
        """*value* as the pane shows it; a value the app does not offer is shown as it is."""
        if self.kind in (SWITCH, FLAG):
            return {TRUE: "On", FALSE: "Off"}.get(value, value or "Off")
        return next((text for choice, text in self.choices if choice == value), value)

    def next_value(self, value: str) -> str:
        """The value after *value*: A on the setting's row steps through them."""
        if self.kind in (SWITCH, FLAG):
            return FALSE if value == TRUE else TRUE
        values = [choice for choice, _ in self.choices]
        return values[(values.index(value) + 1) % len(values)] if value in values else values[0]

    def canonical(self, raw: str | None) -> str:
        """What ppsspp.ini holds (None: nothing) in the form the pane uses: the default for nothing, True or False
        for a switch, the offered choice with the same number for a choice ("3" and "3 (VULKAN)" are one)."""
        if raw is None or raw.strip() == "":
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return TRUE if raw.lower() in ("true", "1") else FALSE if raw.lower() in ("false", "0") else raw
        if self.kind == FLAG:
            number = _number(raw)
            return raw if number is None else TRUE if int(number) & self.bit else FALSE
        number = _number(raw)
        return next((choice for choice, _ in self.choices if choice == raw
                     or (number is not None and _number(choice) == number)), raw)


# GraphicsBackend: the Windows build's renderers, as PPSSPP writes them (Vulkan its default on Windows 10 and later)
RENDERERS = (("3 (VULKAN)", "Vulkan"), ("2 (DIRECT3D11)", "Direct3D 11"), ("0 (OPENGL)", "OpenGL"))
# InternalResolution: the PSP's own picture (480 x 272) times this; Automatic follows the window's size
RESOLUTIONS = (("0", "Automatic (the screen's)"), ("1", "1x (480 × 272, the PSP's)"), ("2", "2x (960 × 544)"),
               ("3", "3x (1440 × 816, 1080p)"), ("4", "4x (1920 × 1088)"), ("5", "5x (2400 × 1360)"),
               ("6", "6x (2880 × 1632, 4K)"), ("8", "8x (3840 × 2176)"))
FILTERS = (("1", "Automatic"), ("2", "Nearest (sharp pixels)"), ("3", "Linear (smooth)"),
           ("4", "Automatic, best quality"))
ANISOTROPY = (("0", "Off"), ("1", "2x"), ("2", "4x"), ("3", "8x"), ("4", "16x"))
FRAMESKIPS = (("0", "Off"), ("1", "1 frame"), ("2", "2 frames"), ("3", "3 frames"))
VOLUMES = (("100", "100%"), ("75", "75%"), ("50", "50%"), ("25", "25%"), ("0", "Muted"))
DEADZONES = (("0.150000", "PPSSPP's (0.15)"), ("0.000000", "Off"), ("0.250000", "Medium (0.25)"),
             ("0.350000", "Large (0.35)"))
SENSITIVITIES = (("1.100000", "PPSSPP's (1.10)"), ("1.000000", "As the stick (1.00)"), ("1.300000", "Higher (1.30)"))

# The Settings pane's tabs, as PCSX2 Manager's: the key, the tab's name and its settings, in the order the rows show
# them
TABS: tuple[tuple[str, str, tuple[Setting, ...]], ...] = (
    ("picture", "Picture", (
        Setting("renderer", "Renderer", "Graphics", "GraphicsBackend", CHOICE, RENDERERS,
                "how PPSSPP draws: Vulkan is its choice on Windows; Direct3D 11 or OpenGL when a game shows faults.",
                RENDERERS[0][0]),
        Setting("resolution", "Resolution", "Graphics", "InternalResolution", CHOICE, RESOLUTIONS,
                "the picture's size: Automatic follows the screen; 3x fills a 1080p screen sharply, 6x a 4K TV; "
                "higher asks more of the graphics chip and the battery.", "0"),
        Setting("stretch", "Stretch to the screen", "DisplayLayout.Landscape", "DisplayStretch", SWITCH,
                tip="the picture fills the whole screen; off, it keeps the PSP's shape.", default=FALSE),
        Setting("integer", "Integer scaling", "DisplayLayout.Landscape", "DisplayIntegerScale", SWITCH,
                tip="the picture a whole multiple of the PSP's: sharp pixels, black edges.", default=FALSE),
        Setting("filtering", "Texture filtering", "Graphics", "TextureFiltering", CHOICE, FILTERS,
                "how textures are smoothed: Nearest keeps pixel art sharp.", "1"),
        Setting("anisotropy", "Anisotropic filtering", "Graphics", "AnisotropyLevel", CHOICE, ANISOTROPY,
                "sharper textures seen at an angle, at little cost.", "4"),
        Setting("vsync", "VSync", "Graphics", "VerticalSync", SWITCH,
                tip="no tearing, a little more delay.", default=TRUE),
    )),
    ("game", "Game", (
        Setting("frameskip", "Frame skipping", "Graphics", "FrameSkip", CHOICE, FRAMESKIPS,
                "frames left out to keep a slow game at full speed.", "0"),
        Setting("cheats", "Cheats", "General", "EnableCheats", SWITCH,
                tip="the cheats in PPSSPP's cheats folder, for the games they are made for.", default=FALSE),
        Setting("volume", "Volume", "Sound", "GameVolume", CHOICE, VOLUMES,
                "PPSSPP's own volume, before Windows'.", "100"),
    )),
    ("controller", "Controller", (
        Setting("deadzone", "Stick dead zone", "Control", "AnalogDeadzone", CHOICE, DEADZONES,
                "how far a stick moves before the game sees it: for a stick that drifts.", DEADZONES[0][0]),
        Setting("sensitivity", "Stick sensitivity", "Control", "AnalogSensitivity", CHOICE, SENSITIVITIES,
                "how far the PSP's stick goes for the stick's travel: PPSSPP's 1.10 reaches the edge a little "
                "sooner.", SENSITIVITIES[0][0]),
    )),
    ("osd", "On screen", (
        Setting("fps", "Show FPS", "Graphics", "iShowStatusFlags", FLAG,
                tip="the frames a second in a corner of the picture.", default=FALSE, bit=2),
        Setting("speed", "Show speed", "Graphics", "iShowStatusFlags", FLAG,
                tip="the game's speed in percent.", default=FALSE, bit=4),
        Setting("battery", "Show battery", "Graphics", "iShowStatusFlags", FLAG,
                tip="the device's battery in percent.", default=FALSE, bit=8),
    )),
)
SETTINGS: tuple[Setting, ...] = tuple(setting for _key, _name, group in TABS for setting in group)


class IniFile:
    """An .ini as PPSSPP writes it ("Key = Value" under [Section], keys whatever their case), changed line by line;
    its byte order mark and line ends kept."""

    def __init__(self, text: str = ""):
        self.bom = text.startswith(BOM) or not text
        text = text.removeprefix(BOM)
        self.newline = "\n" if text and "\r\n" not in text else NEWLINE
        self.lines = [line.rstrip("\r") for line in text.split("\n")] if text else []

    def _find(self, section: str, key: str) -> tuple[int, int]:
        """(the section's last line, the key's line), -1 for each that is not there."""
        current, end, at = None, -1, -1
        for n, line in enumerate(self.lines):
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                current = s[1:-1]
                continue
            if current == section:
                if s:
                    end = n
                if at < 0 and "=" in s and s.split("=", 1)[0].strip().lower() == key.lower():
                    at = n
        if end < 0:
            end = next((n for n, line in enumerate(self.lines) if line.strip() == f"[{section}]"), -1)
        return end, at

    def get(self, section: str, key: str) -> str | None:
        _end, at = self._find(section, key)
        return self.lines[at].split("=", 1)[1].strip() if at >= 0 else None

    def set(self, section: str, key: str, value: str) -> None:
        end, at = self._find(section, key)
        line = f"{key} = {value}"
        if at >= 0:
            self.lines[at] = line
        elif end >= 0:
            self.lines.insert(end + 1, line)
        else:
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            self.lines += [f"[{section}]", line, ""]

    def text(self) -> str:
        return (BOM if self.bom else "") + self.newline.join(self.lines)


def settings_path(home: Path) -> Path:
    """ppsspp.ini in the PPSSPP folder *home*."""
    return emulator.memstick(home) / "PSP" / "SYSTEM" / "ppsspp.ini"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(f".{path.name}.{os.getpid()}")
    work.write_bytes(text.encode("utf-8"))              # as given: CRLF, not Windows' text mode doubling it
    work.replace(path)


def _read(home: Path) -> IniFile:
    path = settings_path(home)
    return IniFile(path.read_bytes().decode("utf-8", "replace") if path.is_file() else "")


def prepare(home: Path) -> list[str]:
    """Brings ppsspp.ini to what the app owns (see above); returns what changed, [] when nothing did. OSError is the
    caller's. The caller makes sure PPSSPP does not run."""
    ini = _read(home)
    done = []
    if (ini.get("General", "CheckForNewVersion") or "").lower() != "false":
        ini.set("General", "CheckForNewVersion", FALSE)
        done.append("its notice of a newer release off")
    if done:
        _write(settings_path(home), ini.text())
    return done


# --- The Settings pane ------------------------------------------------------------------------------------------

def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as ppsspp.ini holds it, in the pane's form (Setting.canonical): PPSSPP's default when the
    file names none."""
    return setting.canonical(_read(home).get(setting.section, setting.ini_key))


def write_setting(home: Path, setting: Setting, value: str) -> None:
    """Sets the setting's key to *value* (as read_setting gives it; a FLAG sets or clears its bit of the number);
    everything else in the file stays. OSError is the caller's, who makes sure PPSSPP does not run."""
    ini = _read(home)
    if setting.kind == FLAG:
        number = _number(ini.get(setting.section, setting.ini_key) or "")
        flags = int(number) if number is not None else 0
        value = str(flags | setting.bit if value == TRUE else flags & ~setting.bit)
    ini.set(setting.section, setting.ini_key, value)
    _write(settings_path(home), ini.text())
