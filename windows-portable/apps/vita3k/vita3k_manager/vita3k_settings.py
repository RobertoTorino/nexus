# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings pane offers: Vita3K's settings that matter on the handheld, each one top-level key of
Vita3K's config.yml (in its portable folder), which Vita3K reads when it starts: the picture, the speed, the sound and
the PS Vita's system settings. The keys, values and defaults are build 4186's (config/config.h; the choices as its
settings window offers them, gui-qt/settings_dialog.cpp). The BC250 suite's Vita3K Manager opens Vita3K's own window
for these; on the handheld that window is never shown, so the app offers them as RPCS3 Manager does.

A setting is read from the file (Vita3K's default while the file, or the line, is not there) and written one line at
a time, every other line kept (userdata.set_values); Vita3K writes the whole file itself when it starts. Never while
Vita3K runs. A game's own settings in Vita3K come before these.

The pane shows them in tabs (TABS below: Picture, Speed, Sound, System), a row each with its value; A steps to the
next value (Setting.next_value), as RPCS3 Manager's pane does."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import userdata

CHOICE, SWITCH, NUMBER = "choice", "switch", "number"
TRUE, FALSE = "true", "false"


@dataclass(frozen=True)
class Setting:
    """One setting: *name* in config.yml. A CHOICE offers *choices* (the value as Vita3K writes it, as shown); a
    NUMBER the same, compared as numbers (yaml-cpp writes 1.5 or 2 for a float); a SWITCH is true or false. *default*
    is Vita3K's own."""
    key: str                            # the app's own name for it
    label: str
    name: str                           # the key in config.yml
    default: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def shown(self, value: str) -> str:
        """*value* as the pane shows it; a value Vita3K knows and the app does not is shown as it is."""
        if self.kind == SWITCH:
            return {TRUE: "On", FALSE: "Off"}.get(value, value or "Off")
        return next((text for choice, text in self.choices if choice == value), value)

    def next_value(self, value: str) -> str:
        """The value after *value*: A on the setting's row steps through them."""
        if self.kind == SWITCH:
            return FALSE if value == TRUE else TRUE
        values = [choice for choice, _ in self.choices]
        return values[(values.index(value) + 1) % len(values)] if value in values else values[0]

    def canonical(self, raw: str | None) -> str:
        """What config.yml holds (None: nothing) in the pane's form: the default for nothing, true or false for a
        switch, a number as the choices write it ("2.0" and "2" alike), the value as it is otherwise."""
        if raw is None or raw.strip() == "":
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return TRUE if raw.lower() == "true" else FALSE if raw.lower() == "false" else raw
        if self.kind == NUMBER:
            try:
                return f"{float(raw):g}"
            except ValueError:
                return raw
        return raw


RENDERERS = (("Vulkan", "Vulkan"), ("OpenGL", "OpenGL"))
SCALES = (("1", "Native (544p)"), ("1.5", "1.5x (816p)"), ("2", "2x (1088p)"), ("3", "3x (1632p)"))
FILTERS = (("Bilinear", "Bilinear"), ("Nearest", "Nearest"), ("Bicubic", "Bicubic"), ("FXAA", "FXAA"),
           ("FSR", "FidelityFX Super Resolution"))
ANISOTROPY = (("1", "Off"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x"))
VOLUMES = (("100", "100%"), ("75", "75%"), ("50", "50%"), ("25", "25%"), ("0", "Muted"))
AUDIO = (("SDL", "SDL"), ("Cubeb", "Cubeb"))
ENTER = (("1", "Cross (X)"), ("0", "Circle (O)"))           # SCE_SYSTEM_PARAM_ENTER_BUTTON_CIRCLE is 0, CROSS 1
LANGUAGES = (("1", "English (United States)"), ("18", "English (United Kingdom)"), ("0", "Japanese"),
             ("2", "French"), ("3", "Spanish"), ("4", "German"), ("5", "Italian"), ("6", "Dutch"),
             ("7", "Portuguese (Portugal)"), ("17", "Portuguese (Brazil)"), ("8", "Russian"), ("9", "Korean"),
             ("10", "Chinese (traditional)"), ("11", "Chinese (simplified)"), ("12", "Finnish"), ("13", "Swedish"),
             ("14", "Danish"), ("15", "Norwegian"), ("16", "Polish"), ("19", "Turkish"))   # SceSystemParamLang

# The Settings pane's tabs, as RPCS3 Manager's: the key, the tab's name and its settings, in the order the rows show
# them (six rows at most: they fit a page at 720 px high)
TABS: tuple[tuple[str, str, tuple[Setting, ...]], ...] = (
    ("picture", "Picture", (
        Setting("renderer", "Renderer", "backend-renderer", "Vulkan", CHOICE, RENDERERS,
                "how Vita3K draws: Vulkan on the handheld's graphics; OpenGL helps only a game that fails with "
                "Vulkan."),
        Setting("scale", "Resolution", "resolution-multiplier", "1", NUMBER, SCALES,
                "the size Vita3K draws the picture at, a multiple of the PS Vita's 960 × 544: 2x fills a 1080p "
                "screen sharply; higher asks more of the graphics chip and the battery."),
        Setting("filter", "Screen filter", "screen-filter", "Bilinear", CHOICE, FILTERS,
                "how the drawn picture is scaled to the screen: Bilinear smooth, Nearest sharp pixels, Bicubic "
                "sharper than Bilinear, FXAA smooths edges, FidelityFX Super Resolution AMD's upscaler (with Vulkan "
                "only)."),
        Setting("anisotropy", "Anisotropic filtering", "anisotropic-filtering", "1", CHOICE, ANISOTROPY,
                "sharper textures seen at an angle, such as a road ahead."),
        Setting("stretch", "Fill the screen", "stretch_the_display_area", FALSE, SWITCH,
                tip="the picture stretched to fill the whole screen; off, the PS Vita's shape is kept, with borders "
                    "where the screen is wider."),
        Setting("vsync", "VSync", "v-sync", TRUE, SWITCH,
                tip="waits for the screen's refresh before showing a frame: no tearing, a little more delay."),
    )),
    ("speed", "Speed", (
        Setting("accuracy", "High accuracy", "high-accuracy", FALSE, SWITCH,
                tip="draws more exactly, as the PS Vita does, for a game that shows errors; slower (Vulkan only)."),
        Setting("pipelines", "Compile shaders in the background", "async-pipeline-compilation", TRUE, SWITCH,
                tip="the game goes on while Vita3K compiles what it shows the first time, with a stutter less; "
                    "something may then show a moment late."),
        Setting("fps", "FPS hack", "fps-hack", FALSE, SWITCH,
                tip="may double a 30 FPS game to 60, but makes some games run twice as fast."),
        Setting("overlay", "Performance overlay", "performance-overlay", FALSE, SWITCH,
                tip="the frames per second shown over the game."),
        Setting("shaders", "Shader compilation message", "show-compile-shaders", TRUE, SWITCH,
                tip="a message in the game while Vita3K compiles shaders."),
    )),
    ("sound", "Sound", (
        Setting("volume", "Volume", "audio-volume", "100", CHOICE, VOLUMES, "the game's sound, in percent."),
        Setting("audio", "Sound output", "audio-backend", "SDL", CHOICE, AUDIO,
                "through which library Vita3K plays sound; SDL is its own choice, Cubeb an alternative when the "
                "sound crackles."),
        Setting("ngs", "NGS sound", "ngs-enable", TRUE, SWITCH,
                tip="the PS Vita's sound engine that many games play their music and effects with; off, those games "
                    "are silent, for one that hangs on it."),
    )),
    ("system", "System", (
        Setting("enter", "Confirm button", "sys-button", "1", CHOICE, ENTER,
                "which button confirms in the PS Vita's menus and many games: Cross as on a PS Vita sold outside "
                "Japan, Circle as in Japan."),
        Setting("language", "Language", "sys-lang", "1", CHOICE, LANGUAGES,
                "the PS Vita's language: a game with that language shows it."),
    )),
)
SETTINGS: tuple[Setting, ...] = tuple(setting for _key, _name, group in TABS for setting in group)


def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as config.yml holds it, in the pane's form (Setting.canonical): Vita3K's default when the
    file names none."""
    return setting.canonical(userdata.read_map(userdata.config_path(home)).get(setting.name))


def read_settings(home: Path) -> dict[str, str]:
    """Every setting's value, the app's key to the value."""
    values = userdata.read_map(userdata.config_path(home))
    return {setting.key: setting.canonical(values.get(setting.name)) for setting in SETTINGS}


def write_setting(home: Path, setting: Setting, value: str) -> None:
    """One line of config.yml set; the file made when there is none. OSError is the caller's; the caller makes sure
    Vita3K does not run."""
    userdata.set_values(userdata.config_path(home), {setting.name: value})
