# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings the Settings pane offers: RPCS3's settings that matter on the handheld (the BC250 suite's RPCS3
Manager's choice, owner 24-10-2026: the picture settings PCSX2 Manager has, and what goes with them), each one key of
RPCS3's config\\config.yml, which RPCS3 reads when a game starts: the picture (Video), the speed (Video and Core), the
sound (Audio) and the messages RPCS3 shows in a game (Miscellaneous). The values and defaults are RPCS3 0.0.43's
(system_config.h, system_config_types.cpp); Vulkan is its renderer where it has Vulkan, Cubeb its sound on Windows.

A setting is read from the file (RPCS3's default while the file, or the line, is not there) and written one line at a
time, every other line kept (userdata.yaml_set); RPCS3 writes the whole file itself when its own settings are saved.
Never while RPCS3 runs. Screen sets two lines, Aspect ratio and Stretch To Display Area (userdata.read_screen and
write_screen, the values a game's own settings took when X on a game set them: owner, 29-10-2026, X plays a game
now). A game's own settings in RPCS3 (a config_<ID>.yml made before) come before these.

The pane shows them in tabs (TABS below: Picture, Speed, Sound, Messages), a row each with its value; A steps to the
next value (Setting.next_value), as PPSSPP Manager's pane does."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import userdata

CONFIG = "config.yml"
CHOICE, SWITCH = "choice", "switch"
SCREEN = "screen"                       # the setting of two lines: userdata.read_screen and write_screen
TRUE, FALSE = "true", "false"


@dataclass(frozen=True)
class Setting:
    """One setting: *name* of the top-level map *section* in config.yml. A CHOICE offers *choices* (the value as
    RPCS3 writes it, as shown); a SWITCH is true or false. *default* is RPCS3's own."""
    key: str                            # the app's own name for it
    label: str
    section: str
    name: str                           # the key in config.yml
    default: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = ""

    def shown(self, value: str) -> str:
        """*value* as the pane shows it; a value RPCS3 knows and the app does not is shown as it is."""
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
        switch, the value as it is otherwise."""
        if raw is None or raw.strip() == "":
            return self.default
        raw = raw.strip()
        if self.kind == SWITCH:
            return TRUE if raw.lower() == "true" else FALSE if raw.lower() == "false" else raw
        return raw


RENDERERS = (("Vulkan", "Vulkan"), ("OpenGL", "OpenGL"))
SCALES = (("100", "Native (720p)"), ("150", "150% (1080p)"), ("200", "200% (1440p)"), ("300", "300% (2160p)"))
ANISOTROPY = (("0", "As the game"), ("2", "2x"), ("4", "4x"), ("8", "8x"), ("16", "16x"))
MSAA = (("Auto", "As the game"), ("Disabled", "Off"))
VSYNC = (("Disabled", "Off"), ("Full", "On"), ("Adaptive", "Adaptive"))
FRAME_LIMITS = (("Auto", "Automatic"), ("Off", "Off"), ("30", "30"), ("50", "50"), ("60", "60"), ("120", "120"),
                ("Display", "The screen's rate"), ("PS3 Native", "As the PS3"), ("Infinite", "No limit"))
SCALING = (("Bilinear", "Bilinear"), ("Nearest", "Nearest"), ("FidelityFX Super Resolution", "FidelityFX Super "
                                                                                              "Resolution"))
PPU = (("Recompiler (LLVM)", "Recompiler (LLVM)"), ("Interpreter (static)", "Interpreter"))
SPU = (("Recompiler (LLVM)", "Recompiler (LLVM)"), ("Recompiler (ASMJIT)", "Recompiler (ASMJIT)"),
       ("Interpreter (dynamic)", "Interpreter (dynamic)"), ("Interpreter (static)", "Interpreter (static)"))
AUDIO = (("Cubeb", "Cubeb"), ("XAudio2", "XAudio2"), ("FAudio", "FAudio"), ("Null", "No sound"))
VOLUMES = (("100", "100%"), ("75", "75%"), ("50", "50%"), ("25", "25%"), ("0", "Muted"), ("150", "150%"),
           ("200", "200%"))

# The Settings pane's tabs, as PPSSPP Manager's: the key, the tab's name and its settings, in the order the rows show
# them (six rows at most: they fit a page at 720 px high)
TABS: tuple[tuple[str, str, tuple[Setting, ...]], ...] = (
    ("picture", "Picture", (
        Setting("renderer", "Renderer", "Video", "Renderer", "Vulkan", CHOICE, RENDERERS,
                "how RPCS3 draws: Vulkan on the handheld's graphics; OpenGL is slower and helps only when Vulkan "
                "fails."),
        Setting("scale", "Resolution scale", "Video", "Resolution Scale", "100", CHOICE, SCALES,
                "the size RPCS3 draws the picture at, in percent of the PS3's 1280 × 720: 150% fills a 1080p screen "
                "sharply, 300% a 4K TV; higher asks more of the graphics chip and the battery, and breaks some "
                "games."),
        Setting("anisotropy", "Anisotropic filtering", "Video", "Anisotropic Filter Override", "0", CHOICE,
                ANISOTROPY, "sharper textures seen at an angle, such as a road ahead; As the game leaves it to the "
                            "game."),
        Setting("msaa", "Anti-aliasing (MSAA)", "Video", "MSAA", "Auto", CHOICE, MSAA,
                "smooths jagged edges as the game asks for it; Off draws without, faster."),
        Setting("scaling", "Output scaling", "Video", "Output Scaling Mode", "Bilinear", CHOICE, SCALING,
                "how the drawn picture is scaled to the screen: Bilinear smooth, Nearest sharp pixels, FidelityFX "
                "Super Resolution AMD's upscaler, sharper from a lower resolution scale."),
        Setting(SCREEN, "Screen", "Video", "Aspect ratio", userdata.WIDE, CHOICE,
                tuple(userdata.SCREENS.items()),
                "how the games fill the screen: 16:9, the PS3's picture for a wide screen; 4:3, with borders on a "
                "wide one; or Fill screen, stretched to fill it."),
    )),
    ("speed", "Speed", (
        Setting("vsync", "VSync", "Video", "VSync Mode", "Disabled", CHOICE, VSYNC,
                "waits for the screen's refresh before showing a frame: no tearing, a little more delay; Adaptive "
                "waits only while the game keeps up."),
        Setting("framelimit", "Frame limit", "Video", "Frame limit", "Auto", CHOICE, FRAME_LIMITS,
                "how many frames a second RPCS3 lets a game draw: Automatic follows the game, As the PS3 its own "
                "pace."),
        Setting("ppu", "PPU decoder", "Core", "PPU Decoder", "Recompiler (LLVM)", CHOICE, PPU,
                "how the PS3's main processor is run: the recompiler is fast, the interpreter exact and slow."),
        Setting("spu", "SPU decoder", "Core", "SPU Decoder", "Recompiler (LLVM)", CHOICE, SPU,
                "how the PS3's SPU cores are run: the LLVM recompiler is fastest once a game's code is compiled, "
                "ASMJIT compiles quicker, an interpreter is slow."),
    )),
    ("sound", "Sound", (
        Setting("audio", "Sound output", "Audio", "Renderer", "Cubeb", CHOICE, AUDIO,
                "through which library RPCS3 plays sound; Cubeb is RPCS3's own choice on Windows, XAudio2 "
                "Windows' own."),
        Setting("volume", "Volume", "Audio", "Master Volume", "100", CHOICE, VOLUMES,
                "the game's sound, in percent; above 100 louder than the game."),
        Setting("buffering", "Buffering", "Audio", "Enable Buffering", TRUE, SWITCH,
                tip="sound kept a little ahead so it does not crackle; off, less delay."),
    )),
    ("messages", "Messages", (
        Setting("trophies", "Trophy messages", "Miscellaneous", "Show trophy popups", TRUE, SWITCH,
                tip="a message in the game when a trophy is won."),
        Setting("shaders", "Shader compilation message", "Miscellaneous", "Show shader compilation hint", FALSE,
                SWITCH, tip="a message in the game while RPCS3 compiles shaders, which it does the first time a game "
                            "shows something new."),
    )),
)
SETTINGS: tuple[Setting, ...] = tuple(setting for _key, _name, group in TABS for setting in group)


def settings_path(home: Path) -> Path:
    return userdata.config_dir(home) / CONFIG


def _lines(home: Path) -> list[str]:
    path = settings_path(home)
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def read_setting(home: Path, setting: Setting) -> str:
    """The setting's value as config.yml holds it, in the pane's form (Setting.canonical): RPCS3's default when the
    file names none."""
    if setting.key == SCREEN:
        return userdata.read_screen(settings_path(home))
    return setting.canonical(userdata.yaml_value(_lines(home), setting.section, setting.name))


def read_settings(home: Path) -> dict[str, str]:
    """Every setting's value, the app's key to the value."""
    lines = _lines(home)
    return {setting.key: (userdata.read_screen(settings_path(home)) if setting.key == SCREEN else
                          setting.canonical(userdata.yaml_value(lines, setting.section, setting.name)))
            for setting in SETTINGS}


def write_setting(home: Path, setting: Setting, value: str) -> None:
    """One line of config.yml set; the file made when there is none. OSError is the caller's; the caller makes sure
    RPCS3 does not run."""
    if setting.key == SCREEN:
        userdata.write_screen(settings_path(home), value)
        return
    lines = _lines(home)
    userdata.yaml_set(lines, setting.section, setting.name, value)
    userdata.write_lines(settings_path(home), lines)
