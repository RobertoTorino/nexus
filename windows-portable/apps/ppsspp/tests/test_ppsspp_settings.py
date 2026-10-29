# SPDX-License-Identifier: GPL-3.0-or-later
"""PPSSPP's settings (ppsspp_settings.py): what the app owns set in ppsspp.ini, the Settings pane's values read in
PPSSPP's own forms (True and False, six decimals, the renderer with its name) and its defaults while the file names
none, written one key at a time with the rest of the file, its byte order mark and its CRLF line ends kept, and the On
screen switches as bits of one number."""

from __future__ import annotations

from ppsspp_manager import ppsspp_settings as ps

BOM = "﻿".encode()
SETTINGS = {s.key: s for s in ps.SETTINGS}
# As PPSSPP 1.20.4 writes it on Windows: a byte order mark, CRLF, and keys of its own the app leaves alone
WRITTEN = ("﻿[General]\r\nFirstRun = False\r\nCheckForNewVersion = True\r\n[Graphics]\r\n"
           "iShowStatusFlags = 8\r\nGraphicsBackend = 2 (DIRECT3D11)\r\nInternalResolution = 3\r\n"
           "VerticalSync = False\r\n[Control]\r\nAnalogDeadzone = 0.250000\r\n")


def write(home, text: str = WRITTEN):
    path = ps.settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def test_the_settings_file_is_on_the_memory_stick(tmp_path):
    assert ps.settings_path(tmp_path) == tmp_path / "memstick" / "PSP" / "SYSTEM" / "ppsspp.ini"


def test_prepare_starts_a_file_with_what_the_app_owns(tmp_path):
    assert ps.prepare(tmp_path) == ["its notice of a newer release off"]
    data = ps.settings_path(tmp_path).read_bytes()
    assert data.startswith(BOM) and data[3:] == b"[General]\r\nCheckForNewVersion = False\r\n"
    assert ps.prepare(tmp_path) == []                                       # nothing to change the second time


def test_prepare_changes_only_its_own_line(tmp_path):
    path = write(tmp_path)
    assert ps.prepare(tmp_path) == ["its notice of a newer release off"]
    assert path.read_bytes().decode("utf-8") == WRITTEN.replace("CheckForNewVersion = True", "CheckForNewVersion = False")


def test_the_values_as_ppsspp_writes_them(tmp_path):
    write(tmp_path)
    read = {key: ps.read_setting(tmp_path, setting) for key, setting in SETTINGS.items()}
    assert read["renderer"] == "2 (DIRECT3D11)" and SETTINGS["renderer"].shown(read["renderer"]) == "Direct3D 11"
    assert read["resolution"] == "3" and read["vsync"] == "False" and read["deadzone"] == "0.250000"
    assert (read["fps"], read["speed"], read["battery"]) == ("False", "False", "True")
    # PPSSPP's defaults where the file names nothing
    assert read["anisotropy"] == "4" and read["volume"] == "100" and read["stretch"] == "False"
    assert read["sensitivity"] == "1.100000" and SETTINGS["sensitivity"].shown(read["sensitivity"]) == "PPSSPP's (1.10)"


def test_other_forms_of_a_value(tmp_path):
    renderer, deadzone, vsync = SETTINGS["renderer"], SETTINGS["deadzone"], SETTINGS["vsync"]
    assert renderer.canonical("3") == "3 (VULKAN)" and renderer.canonical("0 (OPENGL)") == "0 (OPENGL)"
    assert deadzone.canonical("0.25") == "0.250000" and vsync.canonical("true") == "True"
    assert deadzone.canonical("0.42") == "0.42" and deadzone.shown("0.42") == "0.42"      # not offered: as it is
    assert deadzone.next_value("0.42") == "0.150000"                                       # A starts the list again
    assert renderer.canonical(None) == renderer.canonical("") == "3 (VULKAN)"


def test_a_setting_is_written_with_the_rest_of_the_file(tmp_path):
    path = write(tmp_path)
    renderer = SETTINGS["renderer"]
    ps.write_setting(tmp_path, renderer, renderer.next_value(ps.read_setting(tmp_path, renderer)))
    assert ps.read_setting(tmp_path, renderer) == "0 (OPENGL)"
    ps.write_setting(tmp_path, SETTINGS["stretch"], "True")                 # a section the file does not have yet
    text = path.read_bytes().decode("utf-8")
    assert text.startswith("﻿[General]\r\nFirstRun = False\r\n") and "\n" not in text.replace("\r\n", "")
    assert "GraphicsBackend = 0 (OPENGL)\r\n" in text and "AnalogDeadzone = 0.250000" in text
    assert "[DisplayLayout.Landscape]\r\nDisplayStretch = True\r\n" in text


def test_the_on_screen_switches_are_bits_of_one_number(tmp_path):
    write(tmp_path)
    fps, battery = SETTINGS["fps"], SETTINGS["battery"]
    ps.write_setting(tmp_path, fps, "True")
    assert ps.prepare(tmp_path) and "iShowStatusFlags = 10" in ps.settings_path(tmp_path).read_text(encoding="utf-8")
    assert ps.read_setting(tmp_path, fps) == ps.read_setting(tmp_path, battery) == "True"
    ps.write_setting(tmp_path, battery, "False")
    assert ps.read_setting(tmp_path, battery) == "False" and ps.read_setting(tmp_path, fps) == "True"
    assert "iShowStatusFlags = 2" in ps.settings_path(tmp_path).read_text(encoding="utf-8")


def test_keys_are_found_whatever_their_case(tmp_path):
    write(tmp_path, "[Graphics]\ninternalresolution = 2\n")
    assert ps.read_setting(tmp_path, SETTINGS["resolution"]) == "2"
    ps.write_setting(tmp_path, SETTINGS["resolution"], "4")
    text = ps.settings_path(tmp_path).read_text(encoding="utf-8")
    assert text == "[Graphics]\nInternalResolution = 4\n"                   # LF and no mark, as the file had


def test_the_tabs():
    assert [key for key, _name, _group in ps.TABS] == ["picture", "game", "controller", "osd"]
    assert all(len(group) <= 7 for _key, _name, group in ps.TABS)
    assert len({s.key for s in ps.SETTINGS}) == len(ps.SETTINGS)
    for setting in ps.SETTINGS:
        assert setting.tip and setting.default, setting.key
        if setting.kind == ps.CHOICE:
            assert setting.default in [value for value, _ in setting.choices], setting.key
