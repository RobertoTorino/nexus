# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PCSX2's settings (pcsx2_settings.py), as the BC250 suite's PCSX2 Manager does: PCSX2's own
defaults for a first start, the keys the app owns and nothing else, player 1 left alone once a controller is mapped,
the BIOS, the quit chord and Big Picture left off once turned off, the Settings pane's settings and player 2; the
file keeps PCSX2's CRLF line ends."""

from __future__ import annotations

from pcsx2_manager import pcsx2_settings
from pcsx2_manager.pcsx2_settings import IniFile, prepare, settings_path
from pcsx2_manager.userdata import bios_dir

EXISTING = """[UI]\r
SettingsVersion = 1\r
SetupWizardIncomplete = true\r
Theme = darkfusionblue\r
\r
\r
[Pad1]\r
Type = DualShock2\r
Cross = Keyboard/K\r
Start = Keyboard/Return\r
\r
\r
[GameList]\r
Paths = D:\\Games\\PS2\r
"""


def make_bios(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"\0" * 16)


def read(home) -> IniFile:
    return IniFile(settings_path(home).read_bytes().decode("utf-8"))


def test_a_first_start_gets_pcsx2s_own_defaults(tmp_path):
    """No PCSX2.ini yet: PCSX2 2.8.2's defaults as it wrote them on the Ally (its hotkeys too) with what the app
    owns; a second run changes nothing."""
    make_bios(bios_dir(tmp_path), "SCPH10000.BIN")
    assert prepare(tmp_path) == [
        "PCSX2's settings made from its own defaults", "its setup wizard skipped", "its own updates off",
        "the mouse pointer hidden in a game", "the BIOS SCPH10000.BIN", "player 1 on the first controller",
        "Select + Start quits a game", "PCSX2's Big Picture mode off"]
    ini = read(tmp_path)
    assert ini.get("UI", "SettingsVersion") == "1" and ini.get("UI", "SetupWizardIncomplete") == "false"
    assert ini.get("Hotkeys", "ShutdownVM") == pcsx2_settings.QUIT_CHORD and ini.get("UI", "ConfirmShutdown") == "false"
    assert ini.get("Hotkeys", "OpenPauseMenu") == "Keyboard/Escape"
    assert ini.get("AutoUpdater", "CheckAtStartup") == "false" and ini.get("UI", "HideMouseCursor") == "true"
    assert ini.get("UI", "StartBigPictureMode") == "false" and ini.get("UI", "StartFullscreen") == "false"
    assert ini.get("Filenames", "BIOS") == "SCPH10000.BIN" and ini.get("InputSources", "SDL") == "true"
    assert ini.keys("Pad1") == {"Type": "DualShock2", "InvertL": "0", "InvertR": "0", "Deadzone": "0",
                                "AxisScale": "1.33", "LargeMotorScale": "1", "SmallMotorScale": "1",
                                "ButtonDeadzone": "0", "PressureModifier": "0.5", **pcsx2_settings.PAD1}
    raw = settings_path(tmp_path).read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") > 600                     # CRLF, as PCSX2 writes it on Windows
    stamp = settings_path(tmp_path).stat().st_mtime_ns
    assert prepare(tmp_path) == [] and settings_path(tmp_path).stat().st_mtime_ns == stamp


def test_the_defaults_hold_nothing_personal():
    text = pcsx2_settings.DEFAULTS.read_text(encoding="utf-8")
    for word in (":\\", "Users", "Geometry", "WindowState", "HeaderState", "[GameList]", "BIOS ="):
        assert word not in text, word
    assert "\r" not in text                                                  # LF in git, as every text file


def test_an_existing_file_keeps_everything_else(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(EXISTING.encode("utf-8"))
    make_bios(bios_dir(tmp_path), "SCPH-70004.BIN")
    assert prepare(tmp_path) == ["its setup wizard skipped", "its own updates off",
                                 "the mouse pointer hidden in a game", "the BIOS SCPH-70004.BIN",
                                 "player 1 on the first controller", "Select + Start quits a game",
                                 "PCSX2's Big Picture mode off"]
    text = path.read_bytes().decode("utf-8")
    assert "Theme = darkfusionblue\r\n" in text and "Paths = D:\\Games\\PS2" in text
    assert "SetupWizardIncomplete = false" in text and "BIOS = SCPH-70004.BIN" in text
    assert "Cross = SDL-0/FaceSouth" in text and "Keyboard/" not in text
    assert text.index("[Pad1]") < text.index("Cross = SDL-0/FaceSouth") < text.index("[GameList]")
    assert "\n" not in text.replace("\r\n", "")


def test_a_controller_mapped_in_pcsx2_stays(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(EXISTING.replace("Cross = Keyboard/K", "Cross = SDL-1/FaceEast").encode("utf-8"))
    prepare(tmp_path)
    ini = read(tmp_path)
    assert ini.get("Pad1", "Cross") == "SDL-1/FaceEast" and ini.get("Pad1", "Start") == "Keyboard/Return"


def test_no_bios_no_bios_key(tmp_path):
    prepare(tmp_path)
    assert read(tmp_path).get("Filenames", "BIOS") is None


def test_the_ini_is_changed_line_by_line():
    ini = IniFile("[A]\r\nx = 1\r\n\r\n\r\n[B]\r\n\r\n[C]\r\ny = 2\r\n")
    ini.set("A", "z", "3")
    ini.set("B", "w", "4")
    ini.set("C", "y", "5")
    ini.set("D", "v", "6")
    ini.remove("A", "x")
    assert ini.text() == "[A]\r\nz = 3\r\n\r\n\r\n[B]\r\nw = 4\r\n\r\n[C]\r\ny = 5\r\n\r\n[D]\r\nv = 6\r\n\r\n"
    assert ini.get("B", "w") == "4" and ini.get("B", "missing") is None and ini.get("E", "x") is None


def test_the_settings_are_read_and_written(tmp_path):
    prepare(tmp_path)
    by_key = {s.key: s for s in pcsx2_settings.SETTINGS}
    renderer, vibration = by_key["renderer"], by_key["vibration"]
    assert pcsx2_settings.read_setting(tmp_path, renderer) == "-1" and renderer.shown("-1") == "Automatic"
    assert renderer.next_value("-1") == "15" and renderer.next_value("13") == "-1"
    assert renderer.shown("99") == "99" and renderer.next_value("99") == "-1"   # a value PCSX2 has, not offered
    pcsx2_settings.write_setting(tmp_path, renderer, "15")
    assert read(tmp_path).get("EmuCore/GS", "Renderer") == "15"
    assert pcsx2_settings.read_setting(tmp_path, vibration) == "true"
    pcsx2_settings.write_setting(tmp_path, vibration, "false")
    ini = read(tmp_path)
    assert ini.get("Pad1", "LargeMotorScale") == ini.get("Pad1", "SmallMotorScale") == "0"
    assert vibration.shown("false") == "Off" and vibration.next_value("false") == "true"


def test_player2_the_quit_chord_and_big_picture_off(tmp_path):
    prepare(tmp_path)
    assert not pcsx2_settings.player2(tmp_path)
    pcsx2_settings.set_player2(tmp_path, True)
    assert pcsx2_settings.player2(tmp_path) and read(tmp_path).get("Pad2", "Cross") == "SDL-1/FaceSouth"
    pcsx2_settings.set_player2(tmp_path, False)
    assert not pcsx2_settings.player2(tmp_path) and read(tmp_path).get("Pad2", "Cross") is None
    assert pcsx2_settings.quit_chord(tmp_path)
    pcsx2_settings.set_quit_chord(tmp_path, False)
    assert prepare(tmp_path) == []                                               # off stays off
    assert not pcsx2_settings.quit_chord(tmp_path) and read(tmp_path).get("Hotkeys", "ShutdownVM") == ""
    # Big Picture is PCSX2's own interface (owner, 29-10-2026: PCSX2 is never seen): owned, and kept off
    assert read(tmp_path).get("UI", "StartBigPictureMode") == "false"
    path = settings_path(tmp_path)
    path.write_bytes(path.read_bytes().replace(b"StartBigPictureMode = false", b"StartBigPictureMode = true"))
    assert prepare(tmp_path) == ["PCSX2's Big Picture mode off"]


def test_the_bios_pcsx2_uses(tmp_path):
    assert pcsx2_settings.chosen_bios(tmp_path) == ""
    prepare(tmp_path)
    pcsx2_settings.choose_bios(tmp_path, "SCPH-70012.bin")
    assert pcsx2_settings.chosen_bios(tmp_path) == "SCPH-70012.bin"
    assert read(tmp_path).get("Filenames", "BIOS") == "SCPH-70012.bin"
