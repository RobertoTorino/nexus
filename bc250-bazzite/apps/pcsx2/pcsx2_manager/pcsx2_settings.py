# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PCSX2's settings, so a game started from Steam goes straight into the game (owner,
23-10-2026: the emulator only runs the game, the manager does the rest). Never while PCSX2 runs: it keeps its
settings in memory and writes them back when it closes.

PCSX2.ini (inis/ in PCSX2's folder):

* Without one, the app starts from pcsx2_defaults.ini: the file PCSX2 2.8.2 writes at its first start, its own
  defaults (the keyboard's keys, the hotkeys such as Esc for the pause menu), with the window's places, the BIOS and
  the game folders left out. PCSX2 throws away a file without [UI] SettingsVersion and asks to reset, so a file made
  from nothing would not do.
* The app then sets what it owns: the setup wizard done ([UI] SetupWizardIncomplete), PCSX2's own updates off
  ([AutoUpdater] CheckAtStartup: they would replace the build the app installed), the mouse pointer hidden over a
  full-screen game ([UI] HideMouseCursor; owner, 24-10-2026), the BIOS ([Filenames] BIOS, when it names no dump in
  the bios folder), player 1 on the first controller ([Pad1], only while no controller is bound to it: a mapping
  made in PCSX2's window stays) and Select + Start on that controller to quit a game ([Hotkeys] ShutdownVM, with
  PCSX2's question before shutting down off; owner, 24-10-2026: on by default, tried on the board). The first
  controller is SDL-0, whatever its kind; its buttons by position as PCSX2's Automatic Mapping binds them, so Cross
  is the bottom face button. The chord is set only while PCSX2.ini has no ShutdownVM line at all: the Settings tab's
  switch turns it off by leaving the line empty, which PCSX2 reads as no binding, so it stays off.
* The settings the app's Settings tab offers (SETTINGS below; owner, 24-10-2026: every setting through the app,
  PCSX2's own window is not opened): the picture, the emulation, the sound and the controllers, each one key of
  PCSX2.ini, read from the file (or from the defaults while there is none) and written one at a time. The memory
  card in each slot ([MemoryCards]), player 2 on the second controller ([Pad2]) and the quit chord above are
  written the same way.

A game's own settings (gamesettings/<serial>_<CRC>.ini, as PCSX2 names them) hold how it fills the screen, chosen
per game in the app: the PS2's picture as it is, PCSX2's widescreen patch for the game ([EmuCore]
EnableWideScreenPatches; the patch sets 16:9 itself), or stretched to fill the screen ([EmuCore/GS] AspectRatio =
Stretch).

The files are changed line by line: every other line, comment and order stays as PCSX2 wrote it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import userdata

DEFAULTS = Path(__file__).resolve().parent / "pcsx2_defaults.ini"

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

# Select (Share, Create or View) and Start (Options or Menu) together on the first controller: PCSX2 shuts down.
QUIT_CHORD = "SDL-0/Back & SDL-0/Start"

ORIGINAL, WIDESCREEN, FILL = "original", "widescreen", "fill"
SCREENS = {ORIGINAL: "Original", WIDESCREEN: "Widescreen", FILL: "Fill screen"}

CHOICE, SWITCH, PERCENT = "choice", "switch", "percent"


@dataclass(frozen=True)
class Setting:
    """One setting of the Settings tab: *keys* of *section* in PCSX2.ini, all set to the same value. A CHOICE
    offers *choices* (value, as shown); a SWITCH is true or false; a PERCENT 0 to 100."""
    key: str                            # the app's own name for it
    group: str                          # the box it is shown in
    label: str
    section: str
    keys: tuple[str, ...]
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def value_of(self, shown: str) -> str:
        return next((value for value, text in self.choices if text == shown), shown)


PICTURE, EMULATION, SOUND, CONTROLLERS = "Picture", "Emulation", "Sound", "Controllers"
RENDERERS = (("-1", "Automatic (Vulkan)"), ("14", "Vulkan"), ("12", "OpenGL"), ("13", "Software"))
RESOLUTIONS = (("1", "Native (the PS2's)"), ("2", "2x (720p)"), ("3", "3x (1080p)"), ("4", "4x (1440p)"),
               ("5", "5x (1800p)"), ("6", "6x (2160p)"), ("8", "8x (2880p)"))
FILTERS = (("0", "Nearest"), ("1", "Bilinear (forced)"), ("2", "Bilinear (as the PS2)"),
           ("3", "Bilinear (forced, sprites left out)"))
ANISOTROPY = (("0", "Off"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x"))
BLENDING = (("0", "Minimum"), ("1", "Basic"), ("2", "Medium"), ("3", "High"), ("4", "Full"), ("5", "Maximum"))
FMV_SCREENS = (("Off", "As the game"), ("4:3", "4:3"), ("16:9", "16:9"))
SETTINGS: tuple[Setting, ...] = (
    Setting("renderer", PICTURE, "Renderer", "EmuCore/GS", ("Renderer",), CHOICE, RENDERERS,
            "How PCSX2 draws: Automatic picks Vulkan on the BC-250. Software draws on the CPU, exact but slow."),
    Setting("resolution", PICTURE, "Internal resolution", "EmuCore/GS", ("upscale_multiplier",), CHOICE,
            RESOLUTIONS, "The size PCSX2 draws the picture at: 3x fills a 1080p screen sharply, 6x a 4K one. A "
                         "higher one asks more of the GPU."),
    Setting("filter", PICTURE, "Texture filtering", "EmuCore/GS", ("filter",), CHOICE, FILTERS,
            "How textures are smoothed. As the PS2: only where the game asked for it."),
    Setting("anisotropy", PICTURE, "Anisotropic filtering", "EmuCore/GS", ("MaxAnisotropy",), CHOICE, ANISOTROPY,
            "Sharper textures seen at an angle, such as a road ahead."),
    Setting("fxaa", PICTURE, "FXAA", "EmuCore/GS", ("fxaa",), SWITCH,
            tip="Smooths jagged edges in the finished picture; it also softens it a little."),
    Setting("integer", PICTURE, "Integer scaling", "EmuCore/GS", ("IntegerScaling",), SWITCH,
            tip="Scales the picture by whole numbers only, so every pixel stays the same size; it may leave a "
                "border."),
    Setting("vsync", PICTURE, "VSync", "EmuCore/GS", ("VsyncEnable",), SWITCH,
            tip="Waits for the screen's refresh before showing a frame: no tearing, a little more delay."),
    Setting("blending", PICTURE, "Blending accuracy", "EmuCore/GS", ("accurate_blending_unit",), CHOICE, BLENDING,
            "How exactly the PS2's blending of transparent layers is copied: Basic is right for most games, a "
            "higher level fixes glitches in some at a cost to the GPU."),
    Setting("fmv", PICTURE, "Video (FMV) shape", "EmuCore/GS", ("FMVAspectRatioSwitch",), CHOICE, FMV_SCREENS,
            "The shape of a game's videos: as the game's screen setting, or 4:3 so a video is not stretched by Fill "
            "screen."),
    Setting("fps", PICTURE, "Show FPS", "EmuCore/GS", ("OsdShowFPS",), SWITCH,
            tip="The frames a second in the corner of the picture."),
    Setting("nointerlace", EMULATION, "No-interlacing patches", "EmuCore", ("EnableNoInterlacingPatches",), SWITCH,
            tip="PCSX2's patch that makes a game draw a progressive picture instead of an interlaced one: sharper "
                "and without shimmer, for the games PCSX2 has one for."),
    Setting("fastboot", EMULATION, "Fast boot", "EmuCore", ("EnableFastBoot",), SWITCH,
            tip="Skips the PS2's start-up screen and goes into the game."),
    Setting("cheats", EMULATION, "Cheats", "EmuCore", ("EnableCheats",), SWITCH,
            tip="PCSX2's cheat files (.pnach) for a game, from its cheats folder."),
    Setting("volume", SOUND, "Volume", "SPU2/Output", ("StandardVolume",), PERCENT,
            tip="The game's sound, in percent."),
    Setting("vibration", CONTROLLERS, "Vibration", "Pad1", ("LargeMotorScale", "SmallMotorScale"), SWITCH,
            tip="The controller's rumble motors in a game that uses them."),
)
SWITCH_VALUES = {"vibration": ("1", "0")}               # a SWITCH whose keys are not true/false: (on, off)


class IniFile:
    """An .ini as PCSX2 writes it ("Key = Value" under [Section]), changed line by line."""

    def __init__(self, text: str = ""):
        self.lines = text.split("\n") if text else []

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
        return "\n".join(self.lines)


def settings_path(home: Path) -> Path:
    return home / "inis" / "PCSX2.ini"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(f".{path.name}.{os.getpid()}")
    work.write_text(text, encoding="utf-8")
    work.replace(path)


def _controller_bound(pad: dict[str, str]) -> bool:
    """Whether any of player 1's buttons is bound to something other than the keyboard."""
    return any(value and not value.startswith("Keyboard/") for key, value in pad.items() if key in PAD1)


def prepare(home: Path) -> list[str]:
    """Brings PCSX2.ini to what the app owns (see above); returns what changed, [] when nothing did. OSError is the
    caller's. The caller makes sure PCSX2 does not run."""
    path = settings_path(home)
    fresh = not path.is_file()
    before = DEFAULTS.read_text(encoding="utf-8") if fresh else path.read_text(encoding="utf-8")
    ini = IniFile(before)
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
    if ini.text() != before:
        _write(path, ini.text())
    return done


def choose_bios(home: Path, name: str) -> None:
    """Makes the dump *name* in the bios folder the one PCSX2 uses."""
    path = settings_path(home)
    ini = IniFile(path.read_text(encoding="utf-8") if path.is_file() else DEFAULTS.read_text(encoding="utf-8"))
    ini.set("Filenames", "BIOS", name)
    _write(path, ini.text())


def chosen_bios(home: Path) -> str:
    return userdata.ini_value(home, "Filenames", "BIOS")


# --- The Settings tab -------------------------------------------------------------------------------------------

def _read(home: Path) -> IniFile:
    path = settings_path(home)
    return IniFile(path.read_text(encoding="utf-8") if path.is_file() else DEFAULTS.read_text(encoding="utf-8"))


def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as PCSX2.ini holds it (the first of its keys), "" when it names none: for a SWITCH
    "true" or "false", for a PERCENT the number, for a CHOICE one of its values."""
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


def read_settings(home: Path) -> dict[str, str]:
    return {setting.key: read_setting(home, setting) for setting in SETTINGS}


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
    """Whether Select + Start on the first controller shuts PCSX2 down (as the app sets it)."""
    return _read(home).get("Hotkeys", "ShutdownVM") == QUIT_CHORD


def set_quit_chord(home: Path, on: bool) -> None:
    """Select + Start on the first controller end the game and close PCSX2 (-nogui exits with the game), or not.
    On, PCSX2's question before shutting down goes too: it would open a dialog over the full-screen game. Off
    leaves the line empty (no binding for PCSX2), so prepare() does not set the chord again."""
    ini = _read(home)
    if on:
        ini.set("Hotkeys", "ShutdownVM", QUIT_CHORD)
        ini.set("UI", "ConfirmShutdown", "false")
    else:
        ini.set("Hotkeys", "ShutdownVM", "")
    _write(settings_path(home), ini.text())


# --- The memory card slots --------------------------------------------------------------------------------------

def set_slot(home: Path, slot: int, name: str) -> None:
    """The card file *name* in PCSX2's slot 1 or 2; "" leaves the slot empty (PCSX2 then has no card there). A card
    moved into a slot leaves the other one, as a card can be in one slot only."""
    ini = _read(home)
    for other in (1, 2):
        if other != slot and name and ini.get("MemoryCards", f"Slot{other}_Filename") == name:
            ini.set("MemoryCards", f"Slot{other}_Enable", "false")
    ini.set("MemoryCards", f"Slot{slot}_Enable", "true" if name else "false")
    if name:
        ini.set("MemoryCards", f"Slot{slot}_Filename", name)
    _write(settings_path(home), ini.text())


# --- A game's screen --------------------------------------------------------------------------------------------

def game_settings(home: Path, serial: str, crc: int) -> Path:
    """The game's own settings file, as PCSX2 names it ([Folders] GameSettings, gamesettings when not set)."""
    folder = userdata.ini_value(home, "Folders", "GameSettings") or "gamesettings"
    path = Path(os.path.expanduser(folder))
    name = f"{serial}_{crc:08X}.ini" if serial else f"{crc:08X}.ini"
    return (path if path.is_absolute() else home / path) / name


def read_screen(path: Path) -> str:
    try:
        ini = IniFile(path.read_text(encoding="utf-8"))
    except OSError:
        return ORIGINAL
    if ini.get("EmuCore/GS", "AspectRatio") == "Stretch":
        return FILL
    if ini.get("EmuCore", "EnableWideScreenPatches") == "true":
        return WIDESCREEN
    return ORIGINAL


def write_screen(path: Path, screen: str) -> None:
    """Sets how the game fills the screen; the game's other settings stay. A file left with no setting goes."""
    ini = IniFile(path.read_text(encoding="utf-8") if path.is_file() else "")
    ini.remove("EmuCore/GS", "AspectRatio")
    ini.remove("EmuCore", "EnableWideScreenPatches")
    if screen == FILL:
        ini.set("EmuCore/GS", "AspectRatio", "Stretch")
    elif screen == WIDESCREEN:
        ini.set("EmuCore", "EnableWideScreenPatches", "true")
    if any("=" in line for line in ini.lines):
        _write(path, ini.text())
    else:
        path.unlink(missing_ok=True)
