# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PCSX2's settings, so PCSX2 opens ready to play with the handheld's controller: the BC250
suite's PCSX2 Manager's rules (pcsx2_settings.py there, found in its rounds on the board, 23 and 24-10-2026), carried
over to Windows. Never while PCSX2 runs: it keeps its settings in memory and writes them back when it closes.

PCSX2.ini (inis\\ in PCSX2's portable folder):

* Without one, the app starts from pcsx2_defaults.ini: the file PCSX2 2.8.2 wrote at its first start on the Ally
  (28-10-2026), its own defaults (the keyboard's keys, the hotkeys such as Esc for the pause menu). PCSX2 throws away
  a file without [UI] SettingsVersion and asks to reset, so a file made from nothing would not do.
* The app then sets what it owns: the setup wizard done ([UI] SetupWizardIncomplete; it would ask for what the app
  already did, with automatic updates ticked), PCSX2's own updates off ([AutoUpdater] CheckAtStartup: they would
  replace the build the app installed), the mouse pointer hidden over a full-screen game ([UI] HideMouseCursor), the
  BIOS ([Filenames] BIOS, when it names no dump in the bios folder), player 1 on the first controller ([Pad1], only
  while no controller is bound to it: a mapping made in PCSX2's window stays; PCSX2 itself maps only the keyboard,
  so the controller did nothing in a game), Select + Start on that controller to quit a game ([Hotkeys] ShutdownVM,
  with PCSX2's question before shutting down off) and PCSX2's Big Picture mode off ([UI] StartBigPictureMode:
  owner, 29-10-2026, it is PCSX2's own interface, and the app starts every game with PCSX2's window kept away). The
  first controller is SDL-0, whatever its kind: its buttons by position as PCSX2's Automatic Mapping binds them, so
  Cross is the bottom face button. The chord is set only while its line is missing: its switch in the Settings
  pane turns it off by leaving the line empty (which PCSX2 reads as no binding), so off stays off.
* The settings the Settings pane offers, in tabs (TABS below: Picture, Game, Controller, On screen): each one or
  more keys of PCSX2.ini, read from the file (or from the defaults while there is none) and written one at a time,
  as are player 2 on the second controller ([Pad2]) and the quit chord (OWN).

The file is changed line by line: every other line, comment and order stays as PCSX2 wrote it, with its CRLF line
ends (PCSX2 on Windows writes them)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import userdata

DEFAULTS = Path(__file__).resolve().parent / "pcsx2_defaults.ini"
NEWLINE = "\r\n"                        # as PCSX2 writes PCSX2.ini on Windows

# Player 1 on the first controller, as PCSX2's Automatic Mapping writes it for an SDL controller.
PAD1 = {
    "Up": "SDL-0/DPadUp", "Right": "SDL-0/DPadRight", "Down": "SDL-0/DPadDown", "Left": "SDL-0/DPadLeft",
    "Triangle": "SDL-0/FaceNorth", "Circle": "SDL-0/FaceEast", "Cross": "SDL-0/FaceSouth",
    "Square": "SDL-0/FaceWest", "Select": "SDL-0/Back", "Start": "SDL-0/Start",
    "L1": "SDL-0/LeftShoulder", "L2": "SDL-0/+LeftTrigger", "R1": "SDL-0/RightShoulder", "R2": "SDL-0/+RightTrigger",
    "L3": "SDL-0/LeftStick", "R3": "SDL-0/RightStick",
    "LUp": "SDL-0/-LeftY", "LRight": "SDL-0/+LeftX", "LDown": "SDL-0/+LeftY", "LLeft": "SDL-0/-LeftX",
    "RUp": "SDL-0/-RightY", "RRight": "SDL-0/+RightX", "RDown": "SDL-0/+RightY", "RLeft": "SDL-0/-RightX",
    "Analog": "SDL-0/Guide", "LargeMotor": "SDL-0/LargeMotor", "SmallMotor": "SDL-0/SmallMotor",
}
# Player 2 on the second controller: the same buttons on SDL-1.
PAD2 = {key: value.replace("SDL-0/", "SDL-1/") for key, value in PAD1.items()}

# Select (View on the handheld) and Start (Menu) together on the first controller: PCSX2 shuts the game down.
QUIT_CHORD = "SDL-0/Back & SDL-0/Start"

CHOICE, SWITCH = "choice", "switch"


@dataclass(frozen=True)
class Setting:
    """One setting of the Settings pane: *keys* of *section* in PCSX2.ini, all set to the same value. A CHOICE
    offers *choices* (value, as shown); a SWITCH is true or false."""
    key: str                            # the app's own name for it
    label: str
    section: str
    keys: tuple[str, ...]
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def shown(self, value: str) -> str:
        """*value* as the pane shows it; a value the app does not offer is shown as it is."""
        if self.kind == SWITCH:
            return {"true": "On", "false": "Off"}.get(value, value or "Off")
        return next((text for choice, text in self.choices if choice == value), value)

    def next_value(self, value: str) -> str:
        """The value after *value*: A on the setting's pill steps through them."""
        if self.kind == SWITCH:
            return "false" if value == "true" else "true"
        values = [choice for choice, _ in self.choices]
        return values[(values.index(value) + 1) % len(values)] if value in values else values[0]


# GSRendererType: the Windows build's renderers
RENDERERS = (("-1", "Automatic"), ("15", "Direct3D 12"), ("3", "Direct3D 11"), ("14", "Vulkan"), ("12", "OpenGL"),
             ("13", "Software"))
# upscale_multiplier: the PS2's own picture (about 640 x 448) times this; the screen sizes it comes to (owner,
# 29-10-2026: "screen sizes should be added in the first page")
RESOLUTIONS = (("1", "Native (the PS2's)"), ("2", "2x (720p)"), ("3", "3x (1080p)"), ("4", "4x (1440p)"),
               ("5", "5x (1800p)"), ("6", "6x (2160p, 4K)"), ("8", "8x (2880p)"))
ASPECTS = (("Auto 4:3/3:2", "Auto (the game's own)"), ("4:3", "4:3"), ("16:9", "16:9 (fills the screen)"),
           ("Stretch", "Stretch to the screen"))
FMV_ASPECTS = (("Off", "As the game"), ("Auto 4:3/3:2", "Auto"), ("4:3", "4:3"), ("16:9", "16:9"))
ANISOTROPY = (("0", "Off"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x"))
VOLUMES = (("100", "100%"), ("75", "75%"), ("50", "50%"), ("25", "25%"), ("0", "Muted"))
DEADZONES = (("0", "Off"), ("0.1", "Small"), ("0.2", "Medium"), ("0.3", "Large"))
STICK_RANGES = (("1.33", "PCSX2's (1.33)"), ("1", "As the stick (1.00)"), ("1.66", "Wider (1.66)"))
OSD_SIZES = (("100", "Normal"), ("150", "Larger"), ("200", "Largest"))

# The switches the app sets with a function of its own (player2(), quit_chord()): OWN below
PLAYER2 = Setting("player2", "Player 2", "Pad2", ("Type",), SWITCH,
                  tip="a second controller is player 2, with the same buttons as player 1.")
QUIT = Setting("quit", "Quit with View + Menu", "Hotkeys", ("ShutdownVM",), SWITCH,
               tip="View and Menu (☰) held together end the game; off, PCSX2's pause menu does.")

# The Settings pane's tabs (owner, 29-10-2026: "we have way too less settings, we can use tabs"): the key, the tab's
# name and its settings, each one or more keys of PCSX2.ini, in the order the rows show them
TABS: tuple[tuple[str, str, tuple[Setting, ...]], ...] = (
    ("picture", "Picture", (
        Setting("renderer", "Renderer", "EmuCore/GS", ("Renderer",), CHOICE, RENDERERS,
                "Automatic lets PCSX2 choose for the graphics chip; Software draws on the CPU, exact but slow."),
        Setting("resolution", "Resolution", "EmuCore/GS", ("upscale_multiplier",), CHOICE, RESOLUTIONS,
                "the picture's size: 3x fills a 1080p screen sharply, 6x a 4K TV; higher asks more of the graphics "
                "chip and the battery."),
        Setting("aspect", "Aspect ratio", "EmuCore/GS", ("AspectRatio",), CHOICE, ASPECTS,
                "how the picture fills the screen: Auto keeps the game's own shape with black at the sides, 16:9 "
                "fills a wide screen, Stretch fills it whatever the shape."),
        Setting("fmv_aspect", "Video aspect ratio", "EmuCore/GS", ("FMVAspectRatioSwitch",), CHOICE, FMV_ASPECTS,
                "the shape of a game's videos (its FMVs) when they are not the game's own."),
        Setting("widescreen", "Widescreen patches", "EmuCore", ("EnableWideScreenPatches",), SWITCH,
                tip="16:9 in the games PCSX2 has a widescreen patch for, with Aspect ratio on 16:9."),
        Setting("anisotropy", "Anisotropic filtering", "EmuCore/GS", ("MaxAnisotropy",), CHOICE, ANISOTROPY,
                "sharper textures seen at an angle, at little cost."),
        Setting("vsync", "VSync", "EmuCore/GS", ("VsyncEnable",), SWITCH,
                tip="no tearing, a little more delay."),
    )),
    ("game", "Game", (
        Setting("fastboot", "Fast boot", "EmuCore", ("EnableFastBoot",), SWITCH,
                tip="skips the PS2's start-up screen."),
        Setting("nointerlacing", "No-interlacing patches", "EmuCore", ("EnableNoInterlacingPatches",), SWITCH,
                tip="a steadier picture in the games PCSX2 has a no-interlacing patch for."),
        Setting("cheats", "Cheats", "EmuCore", ("EnableCheats",), SWITCH,
                tip="the cheats in PCSX2's cheats folder, for the games they are made for."),
        Setting("savestate", "Save state when quitting", "EmuCore", ("SaveStateOnShutdown",), SWITCH,
                tip="a save state when a game ends, to load from PCSX2's pause menu next time."),
        Setting("volume", "Volume", "SPU2/Output", ("StandardVolume",), CHOICE, VOLUMES,
                "PCSX2's own volume, before Windows'."),
    )),
    ("controller", "Controller", (
        Setting("vibration", "Vibration", "Pad1", ("LargeMotorScale", "SmallMotorScale"), SWITCH,
                tip="the controller's rumble in a game that uses it."),
        Setting("deadzone", "Stick dead zone", "Pad1", ("Deadzone",), CHOICE, DEADZONES,
                "how far a stick moves before the game sees it: for a stick that drifts."),
        Setting("stick_range", "Stick range", "Pad1", ("AxisScale",), CHOICE, STICK_RANGES,
                "how the stick's travel maps onto the PS2's: PCSX2's 1.33 reaches the edge sooner."),
        PLAYER2,
        QUIT,
    )),
    ("osd", "On screen", (
        Setting("fps", "Show FPS", "EmuCore/GS", ("OsdShowFPS",), SWITCH,
                tip="the frames a second in a corner of the picture."),
        Setting("speed", "Show speed", "EmuCore/GS", ("OsdShowSpeed",), SWITCH,
                tip="the game's speed in percent."),
        Setting("show_resolution", "Show resolution", "EmuCore/GS", ("OsdShowResolution",), SWITCH,
                tip="the picture's size in pixels."),
        Setting("load", "Show CPU and GPU use", "EmuCore/GS", ("OsdShowCPU", "OsdShowGPU"), SWITCH,
                tip="how busy the processor and the graphics chip are."),
        Setting("frametimes", "Show frame times", "EmuCore/GS", ("OsdShowFrameTimes",), SWITCH,
                tip="a graph of how long each frame took."),
        Setting("inputs", "Show inputs", "EmuCore/GS", ("OsdShowInputs",), SWITCH,
                tip="the controller's buttons as they are pressed."),
        Setting("osd_size", "Text size", "EmuCore/GS", ("OsdScale",), CHOICE, OSD_SIZES,
                "the size of PCSX2's text on the screen."),
    )),
)
SETTINGS: tuple[Setting, ...] = tuple(setting for _key, _name, group in TABS for setting in group)
SWITCH_VALUES = {"vibration": ("1", "0")}               # a SWITCH whose keys are not true/false: (on, off)


class IniFile:
    """An .ini as PCSX2 writes it ("Key = Value" under [Section]), changed line by line."""

    def __init__(self, text: str = ""):
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
                if at < 0 and "=" in s and s.split("=", 1)[0].strip() == key:
                    at = n
        if end < 0:
            end = next((n for n, line in enumerate(self.lines) if line.strip() == f"[{section}]"), -1)
        return end, at

    def get(self, section: str, key: str) -> str | None:
        _end, at = self._find(section, key)
        return self.lines[at].split("=", 1)[1].strip() if at >= 0 else None

    def keys(self, section: str) -> dict[str, str]:
        current, found = None, {}
        for line in self.lines:
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                current = s[1:-1]
            elif current == section and "=" in s:
                key, value = s.split("=", 1)
                found.setdefault(key.strip(), value.strip())
        return found

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
            self.lines += ([""] if self.lines else []) + [f"[{section}]", line, "", ""]

    def remove(self, section: str, key: str) -> None:
        _end, at = self._find(section, key)
        if at >= 0:
            del self.lines[at]

    def text(self) -> str:
        return NEWLINE.join(self.lines)


def settings_path(home: Path) -> Path:
    return home / "inis" / "PCSX2.ini"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(f".{path.name}.{os.getpid()}")
    work.write_bytes(text.encode("utf-8"))              # as given: CRLF, not Windows' text mode doubling it
    work.replace(path)


def _read(home: Path) -> IniFile:
    path = settings_path(home)
    return IniFile(path.read_text(encoding="utf-8") if path.is_file() else DEFAULTS.read_text(encoding="utf-8"))


def choose_bios(home: Path, name: str) -> None:
    """Makes the dump *name* in the bios folder the one PCSX2 uses ([Filenames] BIOS). OSError is the caller's."""
    ini = _read(home)
    ini.set("Filenames", "BIOS", name)
    _write(settings_path(home), ini.text())


def chosen_bios(home: Path) -> str:
    """The dump PCSX2.ini names ("" when none)."""
    return userdata.ini_value(home, "Filenames", "BIOS")


def _controller_bound(pad: dict[str, str]) -> bool:
    """Whether any of player 1's buttons is bound to something other than the keyboard."""
    return any(value and not value.startswith("Keyboard/") for key, value in pad.items() if key in PAD1)


def prepare(home: Path) -> list[str]:
    """Brings PCSX2.ini to what the app owns (see above); returns what changed, [] when nothing did. OSError is the
    caller's. The caller makes sure PCSX2 does not run."""
    path = settings_path(home)
    fresh = not path.is_file()
    ini = _read(home)
    before = ini.text()
    done = ["PCSX2's settings made from its own defaults"] if fresh else []
    if ini.get("UI", "SetupWizardIncomplete") != "false":
        ini.set("UI", "SetupWizardIncomplete", "false")
        done.append("its setup wizard skipped")
    if ini.get("AutoUpdater", "CheckAtStartup") != "false":
        ini.set("AutoUpdater", "CheckAtStartup", "false")
        done.append("its own updates off")
    if ini.get("UI", "HideMouseCursor") != "true":
        ini.set("UI", "HideMouseCursor", "true")
        done.append("the mouse pointer hidden in a game")
    dumps = userdata.bios_files(userdata.bios_dir(home))
    if dumps and ini.get("Filenames", "BIOS") not in {d.name for d in dumps}:
        ini.set("Filenames", "BIOS", dumps[0].name)
        done.append(f"the BIOS {dumps[0].name}")
    if not _controller_bound(ini.keys("Pad1")):
        if not ini.get("Pad1", "Type"):
            ini.set("Pad1", "Type", "DualShock2")
        for key, value in PAD1.items():
            ini.set("Pad1", key, value)
        done.append("player 1 on the first controller")
    if ini.get("Hotkeys", "ShutdownVM") is None:
        ini.set("Hotkeys", "ShutdownVM", QUIT_CHORD)
        ini.set("UI", "ConfirmShutdown", "false")
        done.append("Select + Start quits a game")
    if ini.get("UI", "StartBigPictureMode") != "false":
        ini.set("UI", "StartBigPictureMode", "false")
        done.append("PCSX2's Big Picture mode off")
    if fresh or ini.text() != before:
        _write(path, ini.text())
    return done


# --- The Settings pane ------------------------------------------------------------------------------------------

def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as PCSX2.ini holds it (the first of its keys), "" when it names none: for a SWITCH
    "true" or "false", for a CHOICE one of its values."""
    value = _read(home).get(setting.section, setting.keys[0]) or ""
    if setting.kind == SWITCH and setting.key in SWITCH_VALUES:
        on, off = SWITCH_VALUES[setting.key]
        return "true" if value == on else "false" if value == off else value
    return value


def write_setting(home: Path, setting: Setting, value: str) -> None:
    """Sets the setting's keys to *value* (as read_setting gives it); everything else in the file stays. OSError is
    the caller's, who makes sure PCSX2 does not run."""
    if setting.kind == SWITCH and setting.key in SWITCH_VALUES:
        on, off = SWITCH_VALUES[setting.key]
        value = on if value == "true" else off
    ini = _read(home)
    for key in setting.keys:
        ini.set(setting.section, key, value)
    _write(settings_path(home), ini.text())


def player2(home: Path) -> bool:
    """Whether player 2 is on the second controller (as the app sets it, or any controller bound in PCSX2)."""
    pad = _read(home).keys("Pad2")
    return pad.get("Type", "None") != "None" and _controller_bound(pad)


def set_player2(home: Path, on: bool) -> None:
    """Player 2 on the second controller (SDL-1, the same buttons as player 1), or no player 2 at all."""
    ini = _read(home)
    if on:
        ini.set("Pad2", "Type", "DualShock2")
        for key, value in PAD2.items():
            ini.set("Pad2", key, value)
    else:
        for key in PAD2:
            ini.remove("Pad2", key)
        ini.set("Pad2", "Type", "None")
    _write(settings_path(home), ini.text())


def quit_chord(home: Path) -> bool:
    """Whether Select + Start on the first controller shuts the game down (as the app sets it)."""
    return _read(home).get("Hotkeys", "ShutdownVM") == QUIT_CHORD


def set_quit_chord(home: Path, on: bool) -> None:
    """Select + Start on the first controller end the game, or not. On, PCSX2's question before shutting down goes
    too: it would open a dialog over the full-screen game. Off leaves the line empty (no binding for PCSX2), so
    prepare() does not set the chord again."""
    ini = _read(home)
    if on:
        ini.set("Hotkeys", "ShutdownVM", QUIT_CHORD)
        ini.set("UI", "ConfirmShutdown", "false")
    else:
        ini.set("Hotkeys", "ShutdownVM", "")
    _write(settings_path(home), ini.text())


# The switches set by a function of their own rather than by one key: (read, write)
OWN = {PLAYER2.key: (player2, set_player2), QUIT.key: (quit_chord, set_quit_chord)}
