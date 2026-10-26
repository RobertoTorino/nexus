# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PCSX2's settings (pcsx2_settings.py): PCSX2's own defaults for a first start, the keys the
app owns and nothing else, player 1 left alone once a controller is mapped, the BIOS, each game's screen, the settings of
the Settings tab, player 2 and the memory card slots."""

from __future__ import annotations

from conftest import make_bios

from pcsx2_manager import pcsx2_settings
from pcsx2_manager.pcsx2_settings import IniFile, prepare, settings_path
from pcsx2_manager.userdata import bios_dir

EXISTING = """[UI]
SettingsVersion = 1
SetupWizardIncomplete = true
Theme = darkfusionblue


[Filenames]
BIOS = gone.bin


[Pad1]
Type = DualShock2
Cross = Keyboard/K
Start = Keyboard/Return


[GameList]
Paths = /games/one
Paths = /games/two
"""


def test_a_first_start_gets_pcsx2s_own_defaults(tmp_path):
    """No PCSX2.ini yet: PCSX2 2.8.2's defaults (its hotkeys too, which only its reset writes) with what the app
    owns; a second run changes nothing."""
    make_bios(bios_dir(tmp_path), "SCPH10000.BIN")
    done = prepare(tmp_path)
    assert done == ["PCSX2's settings made from its own defaults", "its own updates off",
                    "the mouse pointer hidden in a game", "the BIOS SCPH10000.BIN", "player 1 on the first controller",
                    "Select + Start quits a game"]
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("UI", "SettingsVersion") == "1" and ini.get("UI", "SetupWizardIncomplete") == "false"
    assert ini.get("Hotkeys", "ShutdownVM") == pcsx2_settings.QUIT_CHORD and ini.get("UI", "ConfirmShutdown") == "false"
    assert ini.get("Hotkeys", "OpenPauseMenu") == "Keyboard/Escape"
    assert ini.get("AutoUpdater", "CheckAtStartup") == "false" and ini.get("UI", "HideMouseCursor") == "true"
    assert ini.get("Filenames", "BIOS") == "SCPH10000.BIN"
    assert ini.keys("Pad1") == {"Type": "DualShock2", "InvertL": "0", "InvertR": "0", "Deadzone": "0",
                                "AxisScale": "1.33", "LargeMotorScale": "1", "SmallMotorScale": "1",
                                "ButtonDeadzone": "0", "PressureModifier": "0.5", **pcsx2_settings.PAD1}
    stamp = settings_path(tmp_path).stat().st_mtime_ns
    assert prepare(tmp_path) == [] and settings_path(tmp_path).stat().st_mtime_ns == stamp


def test_the_defaults_hold_nothing_personal():
    text = pcsx2_settings.DEFAULTS.read_text()
    for word in ("/home", "/var", "Geometry", "WindowState", "HeaderState", "[GameList]", "BIOS ="):
        assert word not in text, word


def test_an_existing_file_keeps_everything_else(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(EXISTING)
    make_bios(bios_dir(tmp_path), "SCPH-70004.BIN")
    assert prepare(tmp_path) == ["its setup wizard skipped", "its own updates off",
                                 "the mouse pointer hidden in a game", "the BIOS SCPH-70004.BIN",
                                 "player 1 on the first controller", "Select + Start quits a game"]
    text = path.read_text()
    assert "Theme = darkfusionblue" in text and "Paths = /games/one\nPaths = /games/two" in text
    assert "SetupWizardIncomplete = false" in text and "BIOS = SCPH-70004.BIN" in text
    assert "Cross = SDL-0/FaceSouth" in text and "Keyboard/" not in text
    assert text.index("[Pad1]") < text.index("Cross = SDL-0/FaceSouth") < text.index("[GameList]")
    assert text.endswith("[AutoUpdater]\nCheckAtStartup = false\n\n[Hotkeys]\nShutdownVM = SDL-0/Back & SDL-0/Start\n\n")
    assert "ConfirmShutdown = false" in text


def test_a_controller_mapped_in_pcsx2_stays(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(EXISTING.replace("Cross = Keyboard/K", "Cross = SDL-1/FaceEast"))
    prepare(tmp_path)
    ini = IniFile(path.read_text())
    assert ini.get("Pad1", "Cross") == "SDL-1/FaceEast" and ini.get("Pad1", "Start") == "Keyboard/Return"


def test_the_bios_is_left_when_it_is_there(tmp_path):
    folder = bios_dir(tmp_path)
    make_bios(folder, "A.bin")
    make_bios(folder, "B.bin")
    pcsx2_settings.choose_bios(tmp_path, "B.bin")
    prepare(tmp_path)
    assert pcsx2_settings.chosen_bios(tmp_path) == "B.bin"


def test_no_bios_no_bios_key(tmp_path):
    prepare(tmp_path)
    assert IniFile(settings_path(tmp_path).read_text()).get("Filenames", "BIOS") is None


def test_the_ini_is_changed_line_by_line():
    ini = IniFile("[A]\nx = 1\n\n\n[B]\n\n[C]\ny = 2\n")
    ini.set("A", "z", "3")
    ini.set("B", "w", "4")
    ini.set("C", "y", "5")
    ini.set("D", "v", "6")
    ini.remove("A", "x")
    assert ini.text() == "[A]\nz = 3\n\n\n[B]\nw = 4\n\n[C]\ny = 5\n\n[D]\nv = 6\n\n"
    assert ini.get("B", "w") == "4" and ini.get("B", "missing") is None and ini.get("E", "x") is None


def test_each_games_screen(tmp_path):
    path = pcsx2_settings.game_settings(tmp_path, "SLUS-21553", 0x93262D20)
    assert path == tmp_path / "gamesettings" / "SLUS-21553_93262D20.ini"
    assert pcsx2_settings.game_settings(tmp_path, "", 0xAB) == tmp_path / "gamesettings" / "000000AB.ini"
    assert pcsx2_settings.read_screen(path) == pcsx2_settings.ORIGINAL                  # no file yet
    pcsx2_settings.write_screen(path, pcsx2_settings.FILL)
    assert path.read_text() == "[EmuCore/GS]\nAspectRatio = Stretch\n\n"
    assert pcsx2_settings.read_screen(path) == pcsx2_settings.FILL
    pcsx2_settings.write_screen(path, pcsx2_settings.WIDESCREEN)
    assert "AspectRatio" not in path.read_text() and "EnableWideScreenPatches = true" in path.read_text()
    assert pcsx2_settings.read_screen(path) == pcsx2_settings.WIDESCREEN
    pcsx2_settings.write_screen(path, pcsx2_settings.ORIGINAL)
    assert not path.exists()                                                            # nothing left in it
    path.write_text("[EmuCore/GS]\nupscale_multiplier = 3\n")                           # set in PCSX2 for the game
    pcsx2_settings.write_screen(path, pcsx2_settings.FILL)
    pcsx2_settings.write_screen(path, pcsx2_settings.ORIGINAL)
    assert path.read_text() == "[EmuCore/GS]\nupscale_multiplier = 3\n"


def test_game_settings_follow_pcsx2s_folder(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[Folders]\nGameSettings = /elsewhere/settings\n")
    assert pcsx2_settings.game_settings(tmp_path, "SLUS-00001", 1).parent.as_posix() == "/elsewhere/settings"


def test_the_settings_of_the_tab(tmp_path):
    """Each setting read from PCSX2's defaults while there is no file, written one at a time into a file made from
    them; a switch on keys that are not true/false (the vibration motors' scale) reads and writes as a switch."""
    by_key = {s.key: s for s in pcsx2_settings.SETTINGS}
    values = pcsx2_settings.read_settings(tmp_path)
    assert values["renderer"] == "-1" and values["resolution"] == "1" and values["filter"] == "2"
    assert values["blending"] == "1" and values["fmv"] == "Off" and values["nointerlace"] == "false"
    assert values["fxaa"] == "false" and values["fastboot"] == "true" and values["volume"] == "100"
    assert values["vibration"] == "true" and not settings_path(tmp_path).exists()
    pcsx2_settings.write_setting(tmp_path, by_key["renderer"], "14")
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("EmuCore/GS", "Renderer") == "14" and ini.get("Hotkeys", "OpenPauseMenu") == "Keyboard/Escape"
    pcsx2_settings.write_setting(tmp_path, by_key["vibration"], "false")
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("Pad1", "LargeMotorScale") == "0" and ini.get("Pad1", "SmallMotorScale") == "0"
    assert pcsx2_settings.read_setting(tmp_path, by_key["vibration"]) == "false"
    pcsx2_settings.write_setting(tmp_path, by_key["vibration"], "true")
    assert IniFile(settings_path(tmp_path).read_text()).get("Pad1", "LargeMotorScale") == "1"
    for setting in pcsx2_settings.SETTINGS:                 # every choice names a value, and the default is one
        if setting.kind == pcsx2_settings.CHOICE:
            assert values[setting.key] in {v for v, _ in setting.choices}, setting.key
            assert setting.value_of(setting.choices[1][1]) == setting.choices[1][0]


def test_player_2_on_the_second_controller(tmp_path):
    assert not pcsx2_settings.player2(tmp_path)
    pcsx2_settings.set_player2(tmp_path, True)
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("Pad2", "Type") == "DualShock2" and ini.get("Pad2", "Cross") == "SDL-1/FaceSouth"
    assert ini.keys("Pad2") == {"Type": "DualShock2", **pcsx2_settings.PAD2} and pcsx2_settings.player2(tmp_path)
    assert ini.get("Pad1", "Cross") == "Keyboard/K"                                     # player 1 as it was
    pcsx2_settings.set_player2(tmp_path, False)
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.keys("Pad2") == {"Type": "None"} and not pcsx2_settings.player2(tmp_path)
    path = settings_path(tmp_path)
    path.write_text(EXISTING + "\n[Pad2]\nType = DualShock2\nCross = SDL-1/FaceEast\n")  # mapped in PCSX2
    assert pcsx2_settings.player2(tmp_path)


def test_quit_with_select_and_start(tmp_path):
    assert not pcsx2_settings.quit_chord(tmp_path)
    pcsx2_settings.set_quit_chord(tmp_path, True)
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("Hotkeys", "ShutdownVM") == pcsx2_settings.QUIT_CHORD == "SDL-0/Back & SDL-0/Start"
    assert ini.get("UI", "ConfirmShutdown") == "false" and ini.get("UI", "SettingsVersion") == "1"
    assert ini.get("Hotkeys", "Screenshot") == "Keyboard/F8" and pcsx2_settings.quit_chord(tmp_path)
    pcsx2_settings.set_quit_chord(tmp_path, False)
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("Hotkeys", "ShutdownVM") == "" and ini.get("Hotkeys", "Screenshot") == "Keyboard/F8"
    assert not pcsx2_settings.quit_chord(tmp_path)
    assert "Select + Start quits a game" not in prepare(tmp_path)                  # off stays off
    assert IniFile(settings_path(tmp_path).read_text()).get("Hotkeys", "ShutdownVM") == ""
    settings_path(tmp_path).write_text(EXISTING + "\n[Hotkeys]\nShutdownVM = Keyboard/End\n")   # a key of the user's
    assert not pcsx2_settings.quit_chord(tmp_path)
    assert "Select + Start quits a game" not in prepare(tmp_path)                  # the user's key stays
    settings_path(tmp_path).write_text(EXISTING)                                  # a PCSX2 from before the app
    assert "Select + Start quits a game" in prepare(tmp_path) and pcsx2_settings.quit_chord(tmp_path)


def test_the_memory_card_slots(tmp_path):
    from pcsx2_manager import memcards
    assert memcards.slot_cards(tmp_path) == {"Mcd001.ps2": 1, "Mcd002.ps2": 2}         # PCSX2's own names
    pcsx2_settings.set_slot(tmp_path, 1, "Rez.ps2")
    assert memcards.slot_cards(tmp_path) == {"Rez.ps2": 1, "Mcd002.ps2": 2}
    pcsx2_settings.set_slot(tmp_path, 2, "Rez.ps2")                                     # one slot at most
    assert memcards.slot_cards(tmp_path) == {"Rez.ps2": 2}
    ini = IniFile(settings_path(tmp_path).read_text())
    assert ini.get("MemoryCards", "Slot1_Enable") == "false" and ini.get("MemoryCards", "Slot2_Enable") == "true"
    pcsx2_settings.set_slot(tmp_path, 2, "")
    assert memcards.slot_cards(tmp_path) == {}
    assert IniFile(settings_path(tmp_path).read_text()).get("MemoryCards", "Slot2_Filename") == "Rez.ps2"
    pcsx2_settings.set_slot(tmp_path, 1, "Mcd001.ps2")
    assert memcards.slot_cards(tmp_path) == {"Mcd001.ps2": 1}
