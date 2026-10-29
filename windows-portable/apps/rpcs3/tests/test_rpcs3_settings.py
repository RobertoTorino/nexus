# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings pane's model (rpcs3_settings.py): RPCS3's defaults without a config.yml, a line written into a file
RPCS3 wrote with the rest kept, the values and defaults as RPCS3 0.0.43 spells them, and the tabs' rows that step
round."""

from __future__ import annotations

from rpcs3_manager import rpcs3_settings
from rpcs3_manager.rpcs3_settings import SETTINGS, TABS, read_setting, read_settings, settings_path, write_setting

BY_KEY = {s.key: s for s in SETTINGS}


def test_the_defaults_without_a_file(tmp_path):
    values = read_settings(tmp_path)
    assert values["renderer"] == "Vulkan" and values["scale"] == "100" and values["vsync"] == "Disabled"
    assert values["framelimit"] == "Auto" and values["stretch"] == "false" and values["volume"] == "100"
    assert values["ppu"] == "Recompiler (LLVM)" and values["audio"] == "Cubeb" and values["trophies"] == "true"
    assert not settings_path(tmp_path).exists()                                 # reading made no file
    assert settings_path(tmp_path) == tmp_path / "config" / "config.yml"


def test_a_line_written_and_the_rest_kept(tmp_path):
    write_setting(tmp_path, BY_KEY["scale"], "150")
    assert settings_path(tmp_path).read_text() == "Video:\n  Resolution Scale: 150\n"
    settings_path(tmp_path).write_text("Audio:\n  Master Volume: 100\n  Renderer: Cubeb\nVideo:\n"
                                       "  Renderer: Vulkan\n  Resolution Scale: 100\n  Vulkan:\n    Adapter: AMD\n")
    write_setting(tmp_path, BY_KEY["scale"], "200")
    write_setting(tmp_path, BY_KEY["volume"], "75")
    write_setting(tmp_path, BY_KEY["trophies"], "false")
    assert settings_path(tmp_path).read_text() == (
        "Audio:\n  Master Volume: 75\n  Renderer: Cubeb\nVideo:\n  Renderer: Vulkan\n  Resolution Scale: 200\n"
        "  Vulkan:\n    Adapter: AMD\nMiscellaneous:\n  Show trophy popups: false\n")
    values = read_settings(tmp_path)
    assert values["scale"] == "200" and values["volume"] == "75" and values["trophies"] == "false"
    assert values["renderer"] == "Vulkan" and values["msaa"] == "Auto"
    assert read_setting(tmp_path, BY_KEY["scale"]) == "200"


def test_every_setting_is_one_of_rpcs3s():
    """The keys, sections and defaults as RPCS3 0.0.43 writes them (system_config.h); a CHOICE's default is one
    of its choices; a tab holds six rows at most (they fit the pane)."""
    names = {(s.section, s.name) for s in SETTINGS}
    assert ("Video", "Stretch To Display Area") in names and ("Core", "SPU Decoder") in names
    assert ("Audio", "Master Volume") in names and ("Miscellaneous", "Show shader compilation hint") in names
    assert len(names) == len(SETTINGS)
    for setting in SETTINGS:
        if setting.kind == rpcs3_settings.CHOICE:
            assert setting.default in {v for v, _ in setting.choices}, setting.key
        else:
            assert setting.default in ("true", "false"), setting.key
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "messages"]
    assert all(len(group) <= 6 for _, _, group in TABS)
    assert [v for v, _ in BY_KEY["vsync"].choices] == ["Disabled", "Full", "Adaptive"]
    assert [v for v, _ in BY_KEY["framelimit"].choices] == ["Auto", "Off", "30", "50", "60", "120", "Display",
                                                            "PS3 Native", "Infinite"]
    assert [v for v, _ in BY_KEY["audio"].choices] == ["Cubeb", "XAudio2", "FAudio", "Null"]


def test_a_row_steps_through_its_values():
    scale = BY_KEY["scale"]
    assert scale.shown("150") == "150% (1080p)" and scale.next_value("100") == "150"
    assert scale.next_value("300") == "100" and scale.next_value("175") == "100"   # a value the app does not offer
    assert scale.shown("175") == "175" and scale.canonical(None) == "100" and scale.canonical(" 200 ") == "200"
    stretch = BY_KEY["stretch"]
    assert stretch.shown("true") == "On" and stretch.shown("false") == "Off" and stretch.next_value("false") == "true"
    assert stretch.canonical("True") == "true" and stretch.canonical("") == "false"
