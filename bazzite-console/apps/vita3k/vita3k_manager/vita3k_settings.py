# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings window offers (owner, 03-11-2026, from the Windows Portable Suite's Vita3K Manager):
Vita3K's settings that matter for playing, each one top-level key of Vita3K's config.yml (userdata), which Vita3K
reads when it starts: the picture, the speed, the sound and the PS Vita's system settings. The keys, values and
defaults are build 4186's (config/config.h; the choices as its settings window offers them,
gui-qt/settings_dialog.cpp). Vita3K's own window (Vita3K settings) stays for everything else.

A setting is read from the file (Vita3K's default while the file, or the line, is not there) and written one line
at a time, every other line kept (userdata.set_values); Vita3K writes the whole file itself when it starts. Never
while Vita3K runs. A game's own settings in Vita3K come before these. The window is core's settings_page, one box
per group (GROUPS below), which takes a switch as "true" or "false" and the volume as a number."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bc250_core.settings_page import CHOICE, PERCENT, SWITCH

from . import userdata

NUMBER = "number"                       # a choice compared as a number (yaml-cpp writes 1.5 or 2 for a float)
TRUE, FALSE = "true", "false"


@dataclass(frozen=True)
class Setting:
    """One setting: *name* in config.yml. A CHOICE offers *choices* (the value as Vita3K writes it, as shown); a
    NUMBER the same, compared as numbers; a SWITCH is true or false; a PERCENT a number. *default* is Vita3K's
    own."""
    key: str                            # the app's own name for it
    group: str                          # the box it is shown in
    label: str
    name: str                           # the key in config.yml
    default: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def canonical(self, raw: str | None) -> str:
        """What config.yml holds (None: nothing) in the window's form: the default for nothing, true or false for a
        switch, a number as the choices write it ("2.0" and "2" alike), the value as it is otherwise."""
        if raw is None or raw.strip() == "":
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return TRUE if raw.lower() == "true" else FALSE if raw.lower() == "false" else raw
        if self.kind in (NUMBER, PERCENT):
            try:
                return f"{float(raw):g}"
            except ValueError:
                return raw
        return raw


PICTURE, SPEED, SOUND, SYSTEM = "Picture", "Speed", "Sound", "System"
RENDERERS = (("Vulkan", "Vulkan"), ("OpenGL", "OpenGL"))
SCALES = (("1", "Native (544p)"), ("1.5", "1.5x (816p)"), ("2", "2x (1088p)"), ("3", "3x (1632p)"))
FILTERS = (("Bilinear", "Bilinear"), ("Nearest", "Nearest"), ("Bicubic", "Bicubic"), ("FXAA", "FXAA"),
           ("FSR", "FidelityFX Super Resolution"))
ANISOTROPY = (("1", "Off"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x"))
AUDIO = (("SDL", "SDL"), ("Cubeb", "Cubeb"))
ENTER = (("1", "Cross (X)"), ("0", "Circle (O)"))           # SCE_SYSTEM_PARAM_ENTER_BUTTON_CIRCLE is 0, CROSS 1
LANGUAGES = (("1", "English (United States)"), ("18", "English (United Kingdom)"), ("0", "Japanese"),
             ("2", "French"), ("3", "Spanish"), ("4", "German"), ("5", "Italian"), ("6", "Dutch"),
             ("7", "Portuguese (Portugal)"), ("17", "Portuguese (Brazil)"), ("8", "Russian"), ("9", "Korean"),
             ("10", "Chinese (traditional)"), ("11", "Chinese (simplified)"), ("12", "Finnish"), ("13", "Swedish"),
             ("14", "Danish"), ("15", "Norwegian"), ("16", "Polish"), ("19", "Turkish"))   # SceSystemParamLang

SETTINGS: tuple[Setting, ...] = (
    Setting("renderer", PICTURE, "Renderer", "backend-renderer", "Vulkan", CHOICE, RENDERERS,
            "How Vita3K draws: Vulkan on the system; OpenGL helps only a game that fails with Vulkan."),
    Setting("scale", PICTURE, "Resolution", "resolution-multiplier", "1", NUMBER, SCALES,
            "The size Vita3K draws the picture at, a multiple of the PS Vita's 960 × 544: 2x fills a 1080p screen "
            "sharply. A higher one asks more of the GPU."),
    Setting("filter", PICTURE, "Screen filter", "screen-filter", "Bilinear", CHOICE, FILTERS,
            "How the drawn picture is scaled to the screen: Bilinear smooth, Nearest sharp pixels, Bicubic sharper "
            "than Bilinear, FXAA smooths edges, FidelityFX Super Resolution AMD's upscaler (with Vulkan only)."),
    Setting("anisotropy", PICTURE, "Anisotropic filtering", "anisotropic-filtering", "1", CHOICE, ANISOTROPY,
            "Sharper textures seen at an angle, such as a road ahead."),
    Setting("stretch", PICTURE, "Fill the screen", "stretch_the_display_area", FALSE, SWITCH,
            tip="The picture stretched to fill the whole screen; off, the PS Vita's shape is kept, with borders "
                "where the screen is wider."),
    Setting("vsync", PICTURE, "VSync", "v-sync", TRUE, SWITCH,
            tip="Waits for the screen's refresh before showing a frame: no tearing, a little more delay."),
    Setting("accuracy", SPEED, "High accuracy", "high-accuracy", FALSE, SWITCH,
            tip="Draws more exactly, as the PS Vita does, for a game that shows errors; slower (Vulkan only)."),
    Setting("pipelines", SPEED, "Compile shaders in the background", "async-pipeline-compilation", TRUE, SWITCH,
            tip="The game goes on while Vita3K compiles what it shows the first time, with a stutter less; "
                "something may then show a moment late."),
    Setting("fps", SPEED, "FPS hack", "fps-hack", FALSE, SWITCH,
            tip="May double a 30 FPS game to 60, but makes some games run twice as fast."),
    Setting("overlay", SPEED, "Performance overlay", "performance-overlay", FALSE, SWITCH,
            tip="The frames per second shown over the game."),
    Setting("shaders", SPEED, "Shader compilation message", "show-compile-shaders", TRUE, SWITCH,
            tip="A message in the game while Vita3K compiles shaders."),
    Setting("volume", SOUND, "Volume", "audio-volume", "100", PERCENT, tip="The game's sound, in percent."),
    Setting("audio", SOUND, "Sound output", "audio-backend", "SDL", CHOICE, AUDIO,
            "Through which library Vita3K plays sound; SDL is its own choice, Cubeb an alternative when the sound "
            "crackles."),
    Setting("ngs", SOUND, "NGS sound", "ngs-enable", TRUE, SWITCH,
            tip="The PS Vita's sound engine that many games play their music and effects with; off, those games "
                "are silent, for one that hangs on it."),
    Setting("enter", SYSTEM, "Confirm button", "sys-button", "1", CHOICE, ENTER,
            "Which button confirms in the PS Vita's menus and many games: Cross as on a PS Vita sold outside "
            "Japan, Circle as in Japan."),
    Setting("language", SYSTEM, "Language", "sys-lang", "1", CHOICE, LANGUAGES,
            "The PS Vita's language: a game with that language shows it."),
)
GROUPS = (PICTURE, SPEED, SOUND, SYSTEM)


def read_setting(config: Path, setting: Setting) -> str:
    """The setting's value as config.yml holds it, in the window's form (Setting.canonical): Vita3K's default when
    the file names none."""
    return setting.canonical(userdata.read_map(userdata.config_path(config)).get(setting.name))


def read_settings(config: Path) -> dict[str, str]:
    """Every setting's value, the app's key to the value."""
    values = userdata.read_map(userdata.config_path(config))
    return {setting.key: setting.canonical(values.get(setting.name)) for setting in SETTINGS}


def write_setting(config: Path, setting: Setting, value: str) -> None:
    """One line of config.yml set; the file made when there is none. OSError is the caller's; the caller makes sure
    Vita3K does not run."""
    userdata.set_values(userdata.config_path(config), {setting.name: value})
