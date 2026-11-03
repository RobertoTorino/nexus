# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings window's model (ppsspp_settings.py; owner, 03-11-2026): the values read in PPSSPP's own forms (True
and False, six decimals, the renderer with its name) and its defaults while the file names none, a setting written
one key at a time with the rest of the file and its byte order mark kept, and the On screen switches as bits of one
number."""

from __future__ import annotations

from ppsspp_manager import ppsspp_settings as ps
from ppsspp_manager import userdata

SETTINGS = {s.key: s for s in ps.SETTINGS}
# As PPSSPP 1.20.4 writes it: a byte order mark, and keys of its own the app leaves alone
WRITTEN = ("﻿[General]\nFirstRun = False\nCheckForNewVersion = True\n[Graphics]\n"
           "iShowStatusFlags = 6\nGraphicsBackend = 0 (OPENGL)\nInternalResolution = 3\n"
           "VerticalSync = False\n[Control]\nAnalogDeadzone = 0.250000\n[Sound]\nGameVolume = 70\n")


def write(memstick, text: str = WRITTEN):
    path = userdata.settings_path(memstick)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_values_as_ppsspp_writes_them(tmp_path):
    write(tmp_path)
    read = ps.read_settings(tmp_path)
    assert read["renderer"] == "0 (OPENGL)" and read["resolution"] == "3" and read["vsync"] == "false"
    assert read["deadzone"] == "0.250000" and read["volume"] == "70"
    assert (read["fps"], read["speed"]) == ("true", "true")
    # PPSSPP's defaults where the file names nothing
    assert read["anisotropy"] == "4" and read["stretch"] == "false" and read["sensitivity"] == "1.100000"
    assert ps.read_setting(tmp_path, SETTINGS["frameskip"]) == "0"


def test_the_defaults_without_a_file(tmp_path):
    read = ps.read_settings(tmp_path)
    assert read["renderer"] == "3 (VULKAN)" and read["resolution"] == "0" and read["vsync"] == "true"
    assert read["volume"] == "100" and read["fps"] == "false" and read["cheats"] == "false"
    assert not userdata.settings_path(tmp_path).exists()                            # reading made no file


def test_other_forms_of_a_value():
    renderer, deadzone, vsync, volume = (SETTINGS[k] for k in ("renderer", "deadzone", "vsync", "volume"))
    assert renderer.canonical("3") == "3 (VULKAN)" and renderer.canonical("0 (OPENGL)") == "0 (OPENGL)"
    assert deadzone.canonical("0.25") == "0.250000" and vsync.canonical("true") == "true"
    assert deadzone.canonical("0.42") == "0.42"                                     # not offered: as it is
    assert renderer.canonical(None) == renderer.canonical("") == "3 (VULKAN)"
    assert volume.canonical("55.0") == "55" and vsync.written("true") == "True" and vsync.written("false") == "False"


def test_a_setting_is_written_with_the_rest_of_the_file(tmp_path):
    path = write(tmp_path)
    ps.write_setting(tmp_path, SETTINGS["renderer"], "3 (VULKAN)")
    assert ps.read_setting(tmp_path, SETTINGS["renderer"]) == "3 (VULKAN)"
    ps.write_setting(tmp_path, SETTINGS["stretch"], "true")                       # a section the file lacks
    ps.write_setting(tmp_path, SETTINGS["volume"], "40")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("﻿[General]\nFirstRun = False\n")                  # the mark and the rest kept
    assert "GraphicsBackend = 3 (VULKAN)\n" in text and "AnalogDeadzone = 0.250000" in text
    assert "[DisplayLayout.Landscape]\nDisplayStretch = True\n" in text and "GameVolume = 40\n" in text


def test_the_on_screen_switches_are_bits_of_one_number(tmp_path):
    write(tmp_path)
    fps, speed = SETTINGS["fps"], SETTINGS["speed"]
    ps.write_setting(tmp_path, fps, "false")
    assert "iShowStatusFlags = 4" in userdata.settings_path(tmp_path).read_text(encoding="utf-8")
    assert ps.read_setting(tmp_path, fps) == "false" and ps.read_setting(tmp_path, speed) == "true"
    ps.write_setting(tmp_path, speed, "false")
    ps.write_setting(tmp_path, fps, "true")
    assert "iShowStatusFlags = 2" in userdata.settings_path(tmp_path).read_text(encoding="utf-8")


def test_the_groups_and_the_defaults():
    assert list(dict.fromkeys(s.group for s in ps.SETTINGS)) == list(ps.GROUPS)
    assert len({s.key for s in ps.SETTINGS}) == len(ps.SETTINGS)
    for setting in ps.SETTINGS:
        assert setting.tip and setting.default, setting.key
        if setting.kind == ps.CHOICE:
            assert setting.default in [value for value, _ in setting.choices], setting.key
        elif setting.kind in (ps.SWITCH, ps.FLAG):
            assert setting.default in ("true", "false"), setting.key
