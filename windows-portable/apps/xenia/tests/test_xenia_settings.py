# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings pane's model (xenia_settings.py), as RPCS3 Manager's is tested: Xenia's defaults without a config file,
a value written into a file in the layout build e6cd2e4 writes (config.cc, SaveConfig: [Category], "name = value"
padded to column 50, then a tab and the description) with the padding, the description and every other line kept, a
key or a section the file lacks added, the resolution scale's two keys together, strings in single quotes, and the
tabs' rows that step round."""

from __future__ import annotations

from xenia_manager import xenia_settings
from xenia_manager.xenia_settings import SETTINGS, TABS, read_setting, read_settings, settings_path, write_setting

BY_KEY = {s.key: s for s in SETTINGS}


def line(name: str, value: str, description: str) -> str:
    """One line as Xenia writes it: the value padded to column 50, then a tab and the description."""
    text = f"{name} = {value}"
    return text + " " * max(0, 50 - len(text)) + f"\t# {description}"


XENIA_FILE = "\n".join([
    "[APU]", line("apu", "'any'", "Audio system. Use: [any, nop, sdl, xaudio2]"),
    line("mute", "false", "Mutes all audio output."), "",
    "[GPU]", line("draw_resolution_scale_x", "1", "Integer pixel width scale used for scaling the rendering"),
    " " * 50 + "\t# resolution opaquely to the game.",
    line("draw_resolution_scale_y", "1", "Integer pixel height scale."),
    line("gpu", "'any'", "Graphics system. Use: [any, d3d12, vulkan, null]"),
    line("vsync", "true", "Enable VSYNC."), "",
    "[HID]", line("guide_button", "true", "Forward guide button presses to guest."), ""])


def write_file(home):
    path = settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(XENIA_FILE, encoding="utf-8", newline="\n")
    return path


def test_the_defaults_without_a_file(tmp_path):
    values = read_settings(tmp_path)
    assert values["gpu"] == "any" and values["scale"] == "1" and values["antialiasing"] == ""
    assert values["letterbox"] == "true" and values["vsync"] == "true" and values["framelimit"] == "0"
    assert values["apu"] == "any" and values["mute"] == "false" and values["license"] == "0"
    assert not settings_path(tmp_path).exists()                                   # reading made no file
    assert settings_path(tmp_path) == tmp_path / "xenia-canary.config.toml"


def test_a_value_written_in_xenias_layout(tmp_path):
    path = write_file(tmp_path)
    assert read_setting(tmp_path, BY_KEY["gpu"]) == "any" and read_setting(tmp_path, BY_KEY["vsync"]) == "true"
    write_setting(tmp_path, BY_KEY["gpu"], "vulkan")
    write_setting(tmp_path, BY_KEY["scale"], "2")
    write_setting(tmp_path, BY_KEY["mute"], "true")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert line("gpu", "'vulkan'", "Graphics system. Use: [any, d3d12, vulkan, null]") in lines   # padding kept
    assert line("draw_resolution_scale_x", "2", "Integer pixel width scale used for scaling the rendering") in lines
    assert line("draw_resolution_scale_y", "2", "Integer pixel height scale.") in lines
    assert " " * 50 + "\t# resolution opaquely to the game." in lines                   # a description's next line
    assert line("mute", "true", "Mutes all audio output.") in lines
    assert len(lines) == len(XENIA_FILE.splitlines())
    values = read_settings(tmp_path)
    assert values["gpu"] == "vulkan" and values["scale"] == "2" and values["mute"] == "true"


def test_a_key_or_a_section_the_file_lacks(tmp_path):
    path = write_file(tmp_path)
    write_setting(tmp_path, BY_KEY["framelimit"], "30")                           # [GPU] has no framerate_limit
    write_setting(tmp_path, BY_KEY["antialiasing"], "fxaa")                      # there is no [Display]
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("framerate_limit = 30") - 1].startswith("vsync = true")   # at the end of [GPU]
    assert lines[-2:] == ["[Display]", "postprocess_antialiasing = 'fxaa'"]
    assert read_settings(tmp_path)["framelimit"] == "30" and read_settings(tmp_path)["antialiasing"] == "fxaa"
    write_setting(tmp_path, BY_KEY["license"], "1")                              # without any file: made
    assert read_setting(tmp_path, BY_KEY["license"]) == "1"


def test_every_setting_is_one_of_xenias():
    """The sections and defaults as build e6cd2e4 defines them; a CHOICE's default is one of its choices; a tab holds
    six rows at most (they fit the pane)."""
    assert len(BY_KEY) == len(SETTINGS)
    for setting in SETTINGS:
        if setting.kind == xenia_settings.SWITCH:
            assert setting.default in ("true", "false"), setting.key
        else:
            assert setting.default in {v for v, _ in setting.choices}, setting.key
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "console"]
    assert all(len(group) <= 6 for _, _, group in TABS)
    assert BY_KEY["scale"].names == ("draw_resolution_scale_x", "draw_resolution_scale_y")
    assert {(s.section, s.names[0]) for s in SETTINGS} >= {("GPU", "gpu"), ("APU", "apu"), ("Display",
                                                            "present_letterbox"), ("Content", "license_mask"),
                                                           ("UI", "show_achievement_notification"),
                                                           ("HID", "guide_button")}


def test_a_row_steps_through_its_values():
    gpu = BY_KEY["gpu"]
    assert gpu.shown("d3d12") == "Direct3D 12" and gpu.next_value("any") == "d3d12" and gpu.next_value("null") == "any"
    assert gpu.canonical("'vulkan'") == "vulkan" and gpu.canonical('"vulkan"') == "vulkan" and gpu.canonical(None) == "any"
    assert gpu.written("vulkan") == "'vulkan'" and BY_KEY["scale"].written("2") == "2"
    assert BY_KEY["antialiasing"].shown("") == "Off" and BY_KEY["antialiasing"].canonical("''") == ""
    vsync = BY_KEY["vsync"]
    assert vsync.shown("true") == "On" and vsync.next_value("true") == "false" and vsync.written("false") == "false"
