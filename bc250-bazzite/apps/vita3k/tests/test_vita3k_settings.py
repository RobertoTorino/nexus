# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings window's model (vita3k_settings.py; owner, 03-11-2026): Vita3K's defaults without a config.yml, a
line written into the file build 4186 wrote with the rest kept, the keys and defaults as that build spells them, and
a float as yaml-cpp writes it."""

from __future__ import annotations

from conftest import CONFIG_4186, write_vita3k_files

from vita3k_manager import userdata, vita3k_settings
from vita3k_manager.vita3k_settings import SETTINGS, read_setting, read_settings, write_setting

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
    path = write_vita3k_files(tmp_path) / "config.yml"
    before = path.read_text(encoding="utf-8").splitlines()
    write_setting(tmp_path, BY_KEY["scale"], "2")
    write_setting(tmp_path, BY_KEY["stretch"], "true")
    write_setting(tmp_path, BY_KEY["language"], "6")
    write_setting(tmp_path, BY_KEY["volume"], "40")
    after = path.read_text(encoding="utf-8").splitlines()
    assert [(old, new) for old, new in zip(before, after) if old != new] == [
        ("stretch_the_display_area: false", "stretch_the_display_area: true"),
        ("resolution-multiplier: 1", "resolution-multiplier: 2"), ("audio-volume: 100", "audio-volume: 40"),
        ("sys-lang: 1", "sys-lang: 6")]
    values = read_settings(tmp_path)
    assert values["scale"] == "2" and values["stretch"] == "true" and values["language"] == "6"
    assert values["volume"] == "40" and read_setting(tmp_path, BY_KEY["renderer"]) == "Vulkan"


def test_every_setting_is_one_of_vita3ks():
    """A CHOICE's default is one of its choices; the keys are unique; the boxes in order."""
    assert len({s.name for s in SETTINGS}) == len(SETTINGS) == len(BY_KEY)
    for setting in SETTINGS:
        assert setting.tip, setting.key
        if setting.kind == vita3k_settings.SWITCH:
            assert setting.default in ("true", "false"), setting.key
        elif setting.kind != vita3k_settings.PERCENT:
            assert setting.default in {v for v, _ in setting.choices}, setting.key
    assert list(dict.fromkeys(s.group for s in SETTINGS)) == list(vita3k_settings.GROUPS)
    assert [v for v, _ in BY_KEY["filter"].choices] == ["Bilinear", "Nearest", "Bicubic", "FXAA", "FSR"]
    assert sorted(int(v) for v, _ in BY_KEY["language"].choices) == list(range(20))   # SceSystemParamLang


def test_the_forms_of_a_value():
    scale = BY_KEY["scale"]
    assert scale.canonical("2.0") == "2" and scale.canonical("1.5") == "1.5" and scale.canonical(None) == "1"
    assert scale.canonical("x") == "x"
    stretch = BY_KEY["stretch"]
    assert stretch.canonical("True") == "true" and stretch.canonical("") == "false"
    assert BY_KEY["volume"].canonical("70.0") == "70"
