# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings tab (settings_page.py): every setting shown as PCSX2.ini holds it (PCSX2's defaults without a
file), a change written the moment it is made, player 2, a value the app does not know shown as it is, and nothing
written while PCSX2 runs."""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QSpinBox

from pcsx2_manager import pcsx2_settings
from pcsx2_manager.settings_page import OWN, PLAYER2, SOUND_DOWN, SOUND_MUTED, SettingsPage


def _ini(home):
    return pcsx2_settings.IniFile(pcsx2_settings.settings_path(home).read_text())


def test_the_defaults_and_a_change(qapp, tmp_path):
    page = SettingsPage(tmp_path, running=lambda: False)
    widgets = page.widgets
    assert set(widgets) == {s.key for s in pcsx2_settings.SETTINGS} | {"player2", "quit"}
    assert widgets["blending"].currentText() == "Basic" and widgets["fmv"].currentText() == "As the game"
    assert not widgets["nointerlace"].isChecked() and not widgets["quit"].isChecked()
    assert widgets["renderer"].currentText() == "Automatic (Vulkan)" and widgets["resolution"].currentData() == "1"
    assert widgets["filter"].currentText() == "Bilinear (as the PS2)" and widgets["anisotropy"].currentText() == "Off"
    assert not widgets["fxaa"].isChecked() and not widgets["vsync"].isChecked() and widgets["fastboot"].isChecked()
    assert widgets["volume"].value() == 100 and widgets["vibration"].isChecked()
    assert not widgets["player2"].isChecked()
    assert not pcsx2_settings.settings_path(tmp_path).exists()                   # reading made no file
    widgets["resolution"].setCurrentIndex(widgets["resolution"].findData("3"))
    assert page.status.text() == "Internal resolution: 3x (1080p)."
    ini = _ini(tmp_path)
    assert ini.get("EmuCore/GS", "upscale_multiplier") == "3" and ini.get("UI", "SettingsVersion") == "1"
    widgets["volume"].setValue(60)
    widgets["vibration"].setChecked(False)
    assert page.status.text() == "Vibration: off."
    ini = _ini(tmp_path)
    assert ini.get("SPU2/Output", "StandardVolume") == "60"
    assert ini.get("Pad1", "LargeMotorScale") == "0" and ini.get("Pad1", "SmallMotorScale") == "0"
    assert ini.get("Pad1", "Cross") == "Keyboard/K"                              # the rest of the file as it was


def test_player_2(qapp, tmp_path):
    page = SettingsPage(tmp_path, running=lambda: False)
    page.widgets["player2"].setChecked(True)
    assert page.status.text() == "Player 2 on the second controller: on."
    ini = _ini(tmp_path)
    assert ini.get("Pad2", "Type") == "DualShock2" and ini.get("Pad2", "Cross") == "SDL-1/FaceSouth"
    assert ini.get("Pad2", "LLeft") == "SDL-1/-LeftX" and pcsx2_settings.player2(tmp_path)
    page.load()
    assert page.widgets["player2"].isChecked()
    page.widgets["player2"].setChecked(False)
    ini = _ini(tmp_path)
    assert ini.get("Pad2", "Type") == "None" and ini.get("Pad2", "Cross") is None
    assert not pcsx2_settings.player2(tmp_path)


def test_quit_with_select_and_start(qapp, tmp_path):
    """The switch binds PCSX2's shutdown to Select + Start on the first controller and turns PCSX2's question
    before shutting down off; off again takes the binding out."""
    page = SettingsPage(tmp_path, running=lambda: False)
    page.widgets["quit"].setChecked(True)
    assert page.status.text() == "Quit a game with Select + Start: on."
    ini = _ini(tmp_path)
    assert ini.get("Hotkeys", "ShutdownVM") == "SDL-0/Back & SDL-0/Start"
    assert ini.get("UI", "ConfirmShutdown") == "false" and ini.get("Hotkeys", "OpenPauseMenu") == "Keyboard/Escape"
    page.load()
    assert page.widgets["quit"].isChecked()
    page.widgets["quit"].setChecked(False)
    assert _ini(tmp_path).get("Hotkeys", "ShutdownVM") == "" and not pcsx2_settings.quit_chord(tmp_path)


def test_a_value_the_app_does_not_know_is_shown_as_it_is(qapp, tmp_path):
    (tmp_path / "inis").mkdir()
    (tmp_path / "inis" / "PCSX2.ini").write_text("[UI]\nSettingsVersion = 1\n\n[EmuCore/GS]\nRenderer = 15\n"
                                                "upscale_multiplier = 7\nOsdShowFPS = true\n", encoding="utf-8")
    page = SettingsPage(tmp_path, running=lambda: False)
    assert page.widgets["renderer"].currentText() == "15" and page.widgets["resolution"].currentText() == "7"
    assert page.widgets["fps"].isChecked()
    assert page.widgets["volume"].value() == 100                                 # not in the file: PCSX2's default
    page.widgets["renderer"].setCurrentIndex(page.widgets["renderer"].findData("14"))
    assert _ini(tmp_path).get("EmuCore/GS", "Renderer") == "14" and _ini(tmp_path).get("UI", "SettingsVersion")


def test_nothing_written_while_pcsx2_runs(qapp, tmp_path):
    running = [True]
    page = SettingsPage(tmp_path, running=lambda: running[0])
    page.widgets["fxaa"].setChecked(True)
    assert page.status.text().startswith("PCSX2 is running") and "c62828" in page.status.styleSheet()
    assert not page.widgets["fxaa"].isChecked() and not pcsx2_settings.settings_path(tmp_path).exists()
    running[0] = False
    page.widgets["fxaa"].setChecked(True)
    assert page.status.text() == "FXAA: on." and _ini(tmp_path).get("EmuCore/GS", "fxaa") == "true"


def test_every_setting_has_a_widget_of_its_kind(qapp, tmp_path):
    page = SettingsPage(tmp_path, running=lambda: False)
    assert PLAYER2 in OWN
    # Each box is in its own place: the picture's on the left, the three others in the right column (a box over
    # another hid its rows; owner, 24-10-2026).
    from PyQt6.QtWidgets import QGroupBox
    boxes = {b.title(): b for b in page.findChildren(QGroupBox)}
    page.resize(900, 600)
    page.show()
    page.layout().activate()
    geometry = {name: box.geometry() for name, box in boxes.items()}
    assert geometry["Picture"].right() < geometry["Emulation"].left()
    assert geometry["Emulation"].bottom() < geometry["Sound"].top() < geometry["Controllers"].top()
    assert geometry["Sound"].left() == geometry["Emulation"].left()
    page.close()
    for setting in (*pcsx2_settings.SETTINGS, *OWN):
        widget = page.widgets[setting.key]
        kind = {pcsx2_settings.CHOICE: QComboBox, pcsx2_settings.SWITCH: QCheckBox,
                pcsx2_settings.PERCENT: QSpinBox}[setting.kind]
        assert isinstance(widget, kind), setting.key
        assert widget.toolTip() == setting.tip and setting.tip, setting.key
        if setting.kind == pcsx2_settings.CHOICE:
            assert [widget.itemData(i) for i in range(widget.count())] == [v for v, _ in setting.choices]


def test_bazzites_volume_for_pcsx2(qapp, tmp_path):
    """Beside PCSX2's volume: the volume Bazzite remembers for PCSX2, as the window passes it (core's sound); muted
    or turned down to nothing is a problem, said in words."""
    page = SettingsPage(tmp_path, running=lambda: False)
    assert page.system_sound.text() == "—"
    assert page.show_sound(None) == ("", False) and page.system_sound.text() == "— (PCSX2 has not played yet)"
    assert page.show_sound((0.7, False)) == ("", False) and page.system_sound.text() == "70 %"
    assert page.show_sound((1.0, True)) == (SOUND_MUTED, True) and page.system_sound.text() == "Muted"
    assert "c62828" in page.system_sound.styleSheet()
    assert page.show_sound((0.0, False)) == (SOUND_DOWN, True) and page.system_sound.text() == "0 %"
    assert page.show_sound((1.0, False)) == ("", False) and page.system_sound.styleSheet() == ""
