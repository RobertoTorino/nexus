# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings window offers (owner, 03-11-2026, from the Windows Portable Suite's Xenia Manager):
Xenia's settings that matter for playing, each a key of Xenia's xenia-canary.config.toml in its own folder
(emulator.xenia_home, emulator.CONFIG), which Xenia reads when it starts: the picture, the speed, the sound and the
console. The keys, values and defaults are build e6cd2e4's (their DEFINE_ lines: gpu_flags.cc, texture_cache.cc,
emulator_window.cc, presenter.cc, xenia_main.cc, ...); the choices are the Linux build's (Vulkan, SDL). Xenia's own
window (Xenia settings) stays for everything else.

The file is TOML as Xenia writes it (config.cc, SaveConfig): a [Category] line, then "name = value" a line, padded,
with "\\t# description" after it; a string in single quotes ('any'), a number or true/false as it is. The app reads
and writes those lines only, so it needs no TOML library: a setting is read from the file (Xenia's default while the
file, or the line, is not there) and written one value at a time, its description kept (at column 50, as Xenia puts
it) and every other line too; a key the file does not name goes at the end of its [Category], or in a new one. Xenia
writes the whole file again when it starts, its values kept. Never while Xenia runs. A game's own config file comes
before these. The window is core's settings_page, one box per group (GROUPS below), which takes a switch as "true"
or "false"."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bc250_core.settings_page import CHOICE, SWITCH

from . import emulator

NUMBER = "number"                       # a choice written without quotes
TRUE, FALSE = "true", "false"


@dataclass(frozen=True)
class Setting:
    """One setting: *names* in [*section*] of the config file, all set to the same value (the resolution scale is
    two). A CHOICE offers *choices* (the string as Xenia writes it, unquoted, as shown); a NUMBER the same, written
    without quotes; a SWITCH is true or false. *default* is Xenia's own."""
    key: str                            # the app's own name for it
    group: str                          # the box it is shown in
    label: str
    section: str
    names: tuple[str, ...]
    default: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def canonical(self, raw: str | None) -> str:
        """What the file holds (None: nothing) in the window's form: the default for nothing, a string without its
        quotes, true or false for a switch."""
        if raw is None:
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return TRUE if raw.lower() == "true" else FALSE if raw.lower() == "false" else raw
        return _unquote(raw)

    def written(self, value: str) -> str:
        """*value* as Xenia writes it: a string in single quotes."""
        return f"'{value}'" if self.kind == CHOICE else value


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


PICTURE, SPEED, SOUND, CONSOLE = "Picture", "Speed", "Sound", "Console"
GRAPHICS = (("any", "Automatic (Vulkan)"), ("vulkan", "Vulkan"))
SCALES = (("1", "Native (720p)"), ("2", "2x (1440p)"), ("3", "3x (2160p)"))
ANTIALIASING = (("", "Off"), ("fxaa", "FXAA"), ("fxaa_extreme", "FXAA, extreme"))
SCALING = (("", "Bilinear"), ("cas", "Contrast Adaptive Sharpening"), ("fsr", "FidelityFX Super Resolution"))
FRAME_LIMITS = (("0", "As the game"), ("30", "30"), ("60", "60"))
READBACK = (("none", "Off"), ("fast", "Fast"), ("full", "Full"))
AUDIO = (("any", "Automatic (SDL)"), ("sdl", "SDL"))
LICENSES = (("0", "None"), ("1", "Full version"), ("-1", "All licenses"))

SETTINGS: tuple[Setting, ...] = (
    Setting("gpu", PICTURE, "Graphics", "GPU", ("gpu",), "any", CHOICE, GRAPHICS,
            "How Xenia draws: Vulkan is the Linux build's, and Automatic picks it."),
    Setting("scale", PICTURE, "Resolution scale", "GPU", ("draw_resolution_scale_x", "draw_resolution_scale_y"), "1",
            NUMBER, SCALES,
            "The size Xenia draws the picture at, a multiple of the game's own (mostly 1280 × 720); a higher one "
            "asks much more of the GPU, and breaks some games."),
    Setting("antialiasing", PICTURE, "Anti-aliasing", "Display", ("postprocess_antialiasing",), "", CHOICE,
            ANTIALIASING, "Smooths jagged edges after the game has drawn its picture; FXAA, extreme smooths more."),
    Setting("scaling", PICTURE, "Scaling and sharpening", "Display", ("postprocess_scaling_and_sharpening",), "",
            CHOICE, SCALING, "How the picture is scaled to the screen: Bilinear smooth, Contrast Adaptive "
                             "Sharpening sharper, FidelityFX Super Resolution AMD's upscaler."),
    Setting("letterbox", PICTURE, "Keep the picture's shape", "Display", ("present_letterbox",), TRUE, SWITCH,
            tip="Bars beside or above the picture where the screen's shape differs; off, the picture is stretched "
                "to fill the screen."),
    Setting("vsync", PICTURE, "VSync", "GPU", ("vsync",), TRUE, SWITCH,
            tip="Waits for the screen's refresh before showing a frame: no tearing, a little more delay."),
    Setting("framelimit", SPEED, "Frame limit", "GPU", ("framerate_limit",), "0", NUMBER, FRAME_LIMITS,
            "The most frames a second Xenia lets a game draw; As the game is 60 with VSync on."),
    Setting("readback", SPEED, "Readback resolve", "GPU", ("readback_resolve",), "none", CHOICE, READBACK,
            "For a game that shows wrong or missing effects: Fast reads them a frame late, Full exactly and "
            "slowly."),
    Setting("apu", SOUND, "Sound output", "APU", ("apu",), "any", CHOICE, AUDIO,
            "Through which library Xenia plays sound: SDL is the Linux build's, and Automatic picks it."),
    Setting("mute", SOUND, "Mute", "APU", ("mute",), FALSE, SWITCH, tip="The game without sound."),
    Setting("license", CONSOLE, "Arcade license", "Content", ("license_mask",), "0", NUMBER, LICENSES,
            "For an XBOX Live Arcade game: Full version unlocks the whole game where its package has the trial "
            "alone licensed; All licenses also its other content."),
    Setting("achievements", CONSOLE, "Achievement messages", "UI", ("show_achievement_notification",), FALSE,
            SWITCH, tip="A message in the game when an achievement is won."),
    Setting("guide", CONSOLE, "Guide button to the game", "HID", ("guide_button",), TRUE, SWITCH,
            tip="The controller's guide button reaches the game (the XBOX 360's guide); off, Steam keeps it."),
)
GROUPS = (PICTURE, SPEED, SOUND, CONSOLE)


def settings_path(home: Path) -> Path:
    return home / emulator.CONFIG


def _lines(home: Path) -> list[str]:
    try:
        return settings_path(home).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


ALIGN = 50                              # the column Xenia puts a description at (config.cc, value_alignment)


def _split(line: str) -> tuple[str, str, str]:
    """A "name = value<padding>\\t# description" line as (name, value, "\\t# description" or "")."""
    name, _sep, rest = line.partition("=")
    body, hash_, comment = rest.partition("\t#")
    return name.strip(), body.strip(), hash_ + comment


def _line(name: str, value: str, description: str) -> str:
    """The line as Xenia writes it: its description, when it has one, at column 50."""
    text = f"{name} = {value}"
    return text + " " * max(0, ALIGN - len(text)) + description if description else text


def _find(lines: list[str], section: str, name: str) -> tuple[int, int]:
    """(the line of *name* in [*section*] or -1, the line a new one goes before: the section's end, or -1 without the
    section)."""
    inside, end = False, -1
    for n, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if inside:
                return -1, end
            inside = stripped[1:-1].strip() == section
            if inside:
                end = n + 1
            continue
        if inside:
            if stripped and not stripped.startswith("#"):
                end = n + 1
            if "=" in line and not line[:1].isspace() and _split(line)[0] == name:
                return n, end
    return -1, end


def toml_value(lines: list[str], section: str, name: str) -> str | None:
    at, _end = _find(lines, section, name)
    return _split(lines[at])[1] if at >= 0 else None


def toml_set(lines: list[str], section: str, name: str, value: str) -> None:
    """*name* in [*section*] set to *value* (as written), in place: the line's description kept, at column 50."""
    at, end = _find(lines, section, name)
    if at >= 0:
        old_name, _old, description = _split(lines[at])
        lines[at] = _line(old_name, value, description)
    elif end >= 0:
        lines.insert(end, f"{name} = {value}")
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"[{section}]", f"{name} = {value}"]


def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as the file holds it, in the window's form (Setting.canonical): Xenia's default when the
    file names none (its first name tells: a resolution scale's two names are written together)."""
    return setting.canonical(toml_value(_lines(home), setting.section, setting.names[0]))


def read_settings(home: Path) -> dict[str, str]:
    """Every setting's value, the app's key to the value."""
    lines = _lines(home)
    return {setting.key: setting.canonical(toml_value(lines, setting.section, setting.names[0]))
            for setting in SETTINGS}


def write_setting(home: Path, setting: Setting, value: str) -> None:
    """The setting's lines set; the file made when there is none. OSError is the caller's; the caller makes sure
    Xenia does not run."""
    lines = _lines(home)
    for name in setting.names:
        toml_set(lines, setting.section, name, setting.written(value))
    path = settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
