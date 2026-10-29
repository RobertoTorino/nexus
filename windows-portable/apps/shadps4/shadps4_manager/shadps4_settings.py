# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings pane offers: the BC250 suite's shadPS4 Manager's (its shadps4_settings.py), each one key
of shadPS4's config.json, which shadPS4 reads when it starts: the picture (GPU), the sound (Audio, General), the
controller (Input) and what shadPS4 shows in a game (General). They are the settings shadPS4 0.20.0's own settings
window (Big Picture) offers for every game, with its values and defaults (emulator_settings.h,
big_picture/settings_dialog_imgui.h). A setting is read from the file (shadPS4's default while the file, or the key,
is not there) and written one key at a time, every other key kept (userdata.write_config); shadPS4 merges the file
with its defaults when it starts and writes the whole file back, also when it ends. Never while shadPS4 runs. A
game's own settings in shadPS4 (custom_configs\\<Id>.json) come before these.

The pane shows them in tabs (TABS below: Picture, Sound, Controller, In a game), a row each with its value; A steps to
the next value (Setting.next_value), as the suite's other managers do. The volume, which the BC250 app sets with a
slider, steps through a few values instead."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import userdata

CHOICE, SWITCH = "choice", "switch"


@dataclass(frozen=True)
class Setting:
    """One setting: *name* in the section *section* of config.json, a JSON value. A CHOICE offers *choices* (value,
    as shown); a SWITCH is true or false, shown the other way round when *inverted* (a key that turns something
    off)."""
    key: str                            # the app's own name for it
    label: str
    section: str
    name: str                           # the key in config.json
    default: object
    kind: str = CHOICE
    choices: tuple[tuple[object, str], ...] = ()
    tip: str = ""
    inverted: bool = False

    def shown(self, value: object) -> str:
        """*value* as the pane shows it; a value shadPS4 knows and the app does not is shown as it is."""
        if self.kind == SWITCH:
            return "On" if bool(value) != self.inverted else "Off"
        return next((text for choice, text in self.choices if choice == value and type(choice) is type(value)),
                    str(value))

    def next_value(self, value: object) -> object:
        """The value after *value*: A on the setting's row steps through them."""
        if self.kind == SWITCH:
            return not bool(value)
        values = [choice for choice, _ in self.choices]
        known = [n for n, choice in enumerate(values) if choice == value and type(choice) is type(value)]
        return values[(known[0] + 1) % len(values)] if known else values[0]


PRESENT = (("Mailbox", "Mailbox (no tearing)"), ("Fifo", "On"), ("Immediate", "Off"))
AUDIO = ((0, "SDL"), (1, "OpenAL"))
VOLUMES = ((100, "100%"), (75, "75%"), (50, "50%"), (25, "25%"), (0, "Muted"), (150, "150%"), (200, "200%"),
           (300, "300%"), (500, "500%"))
CURSOR = ((0, "Never"), (1, "After a few seconds"), (2, "Always"))
# shadPS4's languages by the number the PS4 knows them by, in the order of its own list (by name).
LANGUAGES = ((21, "Arabic"), (23, "Czech"), (14, "Danish"), (6, "Dutch"), (18, "English (United Kingdom)"),
             (1, "English (United States)"), (12, "Finnish"), (22, "French (Canada)"), (2, "French (France)"),
             (4, "German"), (25, "Greek"), (24, "Hungarian"), (29, "Indonesian"), (5, "Italian"), (0, "Japanese"),
             (9, "Korean"), (15, "Norwegian (Bokmål)"), (16, "Polish"), (17, "Portuguese (Brazil)"),
             (7, "Portuguese (Portugal)"), (26, "Romanian"), (8, "Russian"), (11, "Simplified Chinese"),
             (20, "Spanish (Latin America)"), (3, "Spanish (Spain)"), (13, "Swedish"), (27, "Thai"),
             (10, "Traditional Chinese"), (19, "Turkish"), (30, "Ukrainian"), (28, "Vietnamese"))

# The Settings pane's tabs: the key, the tab's name and its settings, in the order the rows show them (six rows at
# most: they fit a page at 720 px high)
TABS: tuple[tuple[str, str, tuple[Setting, ...]], ...] = (
    ("picture", "Picture", (
        Setting("present", "VSync", "GPU", "present_mode", "Mailbox", CHOICE, PRESENT,
                "how a frame goes to the screen. Mailbox, shadPS4's default: no tearing and little delay, the "
                "newest frame shown at each refresh. On: each frame waits for the refresh, a little more delay. "
                "Off: shown at once, it may tear."),
        Setting("fsr", "FidelityFX upscaling (FSR)", "GPU", "fsr_enabled", False, SWITCH,
                tip="AMD's upscaler scales the game's picture to the screen, sharper than plain scaling when the "
                    "game draws at a lower resolution than the screen's."),
        Setting("rcas", "Sharpening (RCAS)", "GPU", "rcas_enabled", True, SWITCH,
                tip="FSR's sharpening of the upscaled picture; it works only with FidelityFX upscaling on."),
        Setting("hdr", "HDR", "GPU", "hdr_allowed", False, SWITCH,
                tip="high dynamic range, for a game and a screen that support it."),
        Setting("fps", "Frame rate counter", "General", "show_fps_counter", False, SWITCH,
                tip="the frames a second in a corner of the picture while a game plays."),
    )),
    ("sound", "Sound", (
        Setting("audio", "Sound output", "Audio", "audio_backend", 0, CHOICE, AUDIO,
                "through which library shadPS4 plays sound; SDL is shadPS4's default."),
        Setting("volume", "Volume", "General", "volume_slider", 100, CHOICE, VOLUMES,
                "the game's sound, in percent; above 100 louder than the game."),
    )),
    ("controller", "Controller", (
        Setting("motion", "Motion controls", "Input", "motion_controls_enabled", True, SWITCH,
                tip="the controller's motion sensors, for a game that reads them (a DualShock 4 or DualSense; the "
                    "handheld's own controller has none)."),
        Setting("cursor", "Hide the mouse pointer", "Input", "cursor_state", 1, CHOICE, CURSOR,
                "over the game's picture: never, after it has not moved for a few seconds (shadPS4's default), or "
                "always."),
    )),
    ("game", "In a game", (
        Setting("language", "Language", "General", "console_language", 1, CHOICE, LANGUAGES,
                "the PS4's system language, in which a game that has it shows its text."),
        Setting("trophies", "Trophy messages", "General", "trophy_popup_disabled", False, SWITCH,
                tip="a message in the game when a trophy is won.", inverted=True),
        Setting("splash", "Splash screen", "General", "show_splash", False, SWITCH,
                tip="the game's own splash picture while it starts."),
    )),
)
SETTINGS: tuple[Setting, ...] = tuple(setting for _key, _name, group in TABS for setting in group)


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
    """One key of config.json set; the file made when there is none. UserDataError is the caller's; the caller makes
    sure shadPS4 does not run."""
    userdata.write_config(home, setting.section, setting.name, value)
