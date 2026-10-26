# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings of the Settings tab (owner, 24-10-2026: every manager takes the Settings tab when it is rebuilt on
PCSX2 Manager's), each one key of shadPS4's config.json, which shadPS4 reads when it starts: the picture (GPU), the
sound (Audio, General), the controller (Input) and what shadPS4 shows in a game (General). They are the settings
shadPS4 0.20.0's own settings window (Big Picture) offers for every game, with its values and defaults
(emulator_settings.h, big_picture/settings_dialog_imgui.h); what shadPS4 keeps there for experiments (per game only)
and its window's size stay out. A setting is read from the file (shadPS4's default while the file, or the key, is
not there) and written one key at a time, every other key kept (userdata.write_config); shadPS4 merges the file
with its defaults when it starts and writes the whole file back, also when it ends. Never while shadPS4 runs. A
game's own settings in shadPS4 (custom_configs/<Id>.json, made in its Big Picture window) come before these."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import userdata

CHOICE, SWITCH, PERCENT = "choice", "switch", "percent"


@dataclass(frozen=True)
class Setting:
    """One setting: *name* in the section *section* of config.json, a JSON value. A CHOICE offers *choices* (value,
    as shown); a SWITCH is true or false, shown the other way round when *inverted* (a key that turns something
    off); a PERCENT 0 to *top*."""
    key: str                            # the app's own name for it
    group: str                          # the box it is shown in
    label: str
    section: str
    name: str                           # the key in config.json
    default: object
    kind: str = CHOICE
    choices: tuple[tuple[object, str], ...] = ()
    tip: str = ""
    top: int = 100
    inverted: bool = False


PICTURE, SOUND, CONTROLLER, IN_GAME = "Picture", "Sound", "Controller and mouse", "In a game"
PRESENT = (("Mailbox", "Mailbox (no tearing)"), ("Fifo", "On"), ("Immediate", "Off"))
AUDIO = ((0, "SDL"), (1, "OpenAL"))
CURSOR = ((0, "Never"), (1, "After a few seconds"), (2, "Always"))
# shadPS4's languages by the number the PS4 knows them by, in the order of its own list (by name).
LANGUAGES = ((21, "Arabic"), (23, "Czech"), (14, "Danish"), (6, "Dutch"), (18, "English (United Kingdom)"),
             (1, "English (United States)"), (12, "Finnish"), (22, "French (Canada)"), (2, "French (France)"),
             (4, "German"), (25, "Greek"), (24, "Hungarian"), (29, "Indonesian"), (5, "Italian"), (0, "Japanese"),
             (9, "Korean"), (15, "Norwegian (Bokmål)"), (16, "Polish"), (17, "Portuguese (Brazil)"),
             (7, "Portuguese (Portugal)"), (26, "Romanian"), (8, "Russian"), (11, "Simplified Chinese"),
             (20, "Spanish (Latin America)"), (3, "Spanish (Spain)"), (13, "Swedish"), (27, "Thai"),
             (10, "Traditional Chinese"), (19, "Turkish"), (30, "Ukrainian"), (28, "Vietnamese"))
SETTINGS: tuple[Setting, ...] = (
    Setting("present", PICTURE, "VSync", "GPU", "present_mode", "Mailbox", CHOICE, PRESENT,
            "How a frame goes to the screen. Mailbox, shadPS4's default: no tearing and little delay, the newest "
            "frame shown at each refresh. On: each frame waits for the refresh, a little more delay. Off: shown at "
            "once, it may tear."),
    Setting("fsr", PICTURE, "FidelityFX upscaling (FSR)", "GPU", "fsr_enabled", False, SWITCH,
            tip="AMD's upscaler scales the game's picture to the screen, sharper than plain scaling when the game "
                "draws at a lower resolution than the screen's."),
    Setting("rcas", PICTURE, "Sharpening (RCAS)", "GPU", "rcas_enabled", True, SWITCH,
            tip="FSR's sharpening of the upscaled picture; it works only with FidelityFX upscaling on."),
    Setting("hdr", PICTURE, "HDR", "GPU", "hdr_allowed", False, SWITCH,
            tip="High dynamic range, for a game and a screen that support it."),
    Setting("fps", PICTURE, "Frame rate counter", "General", "show_fps_counter", False, SWITCH,
            tip="The frames a second in a corner of the picture while a game plays."),
    Setting("audio", SOUND, "Sound output", "Audio", "audio_backend", 0, CHOICE, AUDIO,
            "Through which library shadPS4 plays sound; SDL is shadPS4's default."),
    Setting("volume", SOUND, "Volume", "General", "volume_slider", 100, PERCENT, top=500,
            tip="The game's sound, in percent; above 100 louder than the game."),
    Setting("motion", CONTROLLER, "Motion controls", "Input", "motion_controls_enabled", True, SWITCH,
            tip="The controller's motion sensors, for a game that reads them (a DualShock 4 or DualSense)."),
    Setting("cursor", CONTROLLER, "Hide the mouse pointer", "Input", "cursor_state", 1, CHOICE, CURSOR,
            "Over the game's window: never, after it has not moved for a few seconds (shadPS4's default), or "
            "always."),
    Setting("language", IN_GAME, "Language", "General", "console_language", 1, CHOICE, LANGUAGES,
            "The PS4's system language, in which a game that has it shows its text."),
    Setting("trophies", IN_GAME, "Trophy messages", "General", "trophy_popup_disabled", False, SWITCH,
            tip="A message in the game when a trophy is won.", inverted=True),
    Setting("splash", IN_GAME, "Splash screen", "General", "show_splash", False, SWITCH,
            tip="The game's own splash picture while it starts."),
)


def read_settings(home: Path) -> dict[str, object]:
    """Every setting's value, the app's key to config.json's value (shadPS4's default while it is not there)."""
    config = userdata.read_config(home)
    values = {}
    for setting in SETTINGS:
        section = config.get(setting.section)
        found = section.get(setting.name) if isinstance(section, dict) else None
        values[setting.key] = setting.default if found is None else found
    return values


def write_setting(home: Path, setting: Setting, value: object) -> None:
    """One key of config.json set; the file made when there is none. OSError and UserDataError are the caller's;
    the caller makes sure shadPS4 does not run."""
    userdata.write_config(home, setting.section, setting.name, value)
