# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings pane's model (vita3k_settings.py), as RPCS3 Manager's is tested: Vita3K's defaults without a config.yml,
a line written into the file build 4186 wrote with the rest kept, the keys and defaults as that build spells them, a
float as yaml-cpp writes it, and the tabs' rows that step round."""

from __future__ import annotations

from conftest import CONFIG_4186, write_config

from vita3k_manager import userdata, vita3k_settings
from vita3k_manager.vita3k_settings import SETTINGS, TABS, read_setting, read_settings, write_setting

BY_KEY = {s.key: s for s in SETTINGS}


def test_the_defaults_without_a_file(tmp_path):
    values = read_settings(tmp_path)
    assert values["renderer"] == "Vulkan" and values["scale"] == "1" and values["filter"] == "Bilinear"
    assert values["vsync"] == "true" and values["stretch"] == "false" and values["volume"] == "100"
    assert values["enter"] == "1" and values["language"] == "1" and values["ngs"] == "true"
    assert not userdata.config_path(tmp_path).exists()                            # reading made no file


def test_every_default_is_what_build_4186_writes():
    """config-4186.yml is the file Vita3K wrote on its first start: each setting's default is the value there."""
    written = userdata.read_map(CONFIG_4186)
    for setting in SETTINGS:
        assert setting.name in written, setting.name
        assert setting.canonical(written[setting.name]) == setting.default, setting.key


def test_a_line_written_and_the_rest_kept(tmp_path):
    path = write_config(tmp_path)
    before = path.read_text(encoding="utf-8").splitlines()
    write_setting(tmp_path, BY_KEY["scale"], "2")
    write_setting(tmp_path, BY_KEY["stretch"], "true")
    write_setting(tmp_path, BY_KEY["language"], "6")
    after = path.read_text(encoding="utf-8").splitlines()
    assert [(old, new) for old, new in zip(before, after) if old != new] == [
        ("stretch_the_display_area: false", "stretch_the_display_area: true"),
        ("resolution-multiplier: 1", "resolution-multiplier: 2"), ("sys-lang: 1", "sys-lang: 6")]
    values = read_settings(tmp_path)
    assert values["scale"] == "2" and values["stretch"] == "true" and values["language"] == "6"
    assert read_setting(tmp_path, BY_KEY["renderer"]) == "Vulkan"


def test_every_setting_is_one_of_vita3ks():
    """A CHOICE's default is one of its choices; a tab holds six rows at most (they fit the pane); the keys are
    unique."""
    assert len({s.name for s in SETTINGS}) == len(SETTINGS) == len(BY_KEY)
    for setting in SETTINGS:
        if setting.kind == vita3k_settings.SWITCH:
            assert setting.default in ("true", "false"), setting.key
        else:
            assert setting.default in {v for v, _ in setting.choices}, setting.key
    assert [key for key, _, _ in TABS] == ["picture", "speed", "sound", "system"]
    assert all(len(group) <= 6 for _, _, group in TABS)
    assert [v for v, _ in BY_KEY["filter"].choices] == ["Bilinear", "Nearest", "Bicubic", "FXAA", "FSR"]
    assert [v for v, _ in BY_KEY["audio"].choices] == ["SDL", "Cubeb"]
    assert sorted(int(v) for v, _ in BY_KEY["language"].choices) == list(range(20))   # SceSystemParamLang


def test_a_row_steps_through_its_values():
    scale = BY_KEY["scale"]
    assert scale.canonical("2.0") == "2" and scale.canonical("1.5") == "1.5" and scale.canonical(None) == "1"
    assert scale.shown("2") == "2x (1088p)" and scale.next_value("1") == "1.5" and scale.next_value("3") == "1"
    assert scale.next_value("1.25") == "1" and scale.shown("1.25") == "1.25"      # a value the app does not offer
    stretch = BY_KEY["stretch"]
    assert stretch.shown("true") == "On" and stretch.shown("false") == "Off" and stretch.next_value("false") == "true"
    assert stretch.canonical("True") == "true" and stretch.canonical("") == "false"
    enter = BY_KEY["enter"]
    assert enter.shown("0") == "Circle (O)" and enter.next_value("0") == "1"
