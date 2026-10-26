# SPDX-License-Identifier: GPL-3.0-or-later
"""The Settings tab (settings_page.py): every setting shown as config.yml holds it (RPCS3's defaults without a
file), a change written the moment it is made, a value the app does not know shown as it is, and nothing written
while RPCS3 runs."""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QSpinBox

from rpcs3_manager import rpcs3_settings
from rpcs3_manager.settings_page import RUNNING, SOUND_DOWN, SOUND_MUTED, SettingsPage


def test_the_defaults_and_a_change(qapp, tmp_path):
    page = SettingsPage(tmp_path, running=lambda: False)
    widgets = page.widgets
    assert set(widgets) == {s.key for s in rpcs3_settings.SETTINGS}
    assert widgets["renderer"].currentText() == "Vulkan" and widgets["scale"].currentText() == "Native (720p)"
    assert widgets["anisotropy"].currentText() == "As the game" and widgets["vsync"].currentText() == "Off"
    assert widgets["framelimit"].currentText() == "Automatic" and widgets["scaling"].currentText() == "Bilinear"
    assert not widgets["stretch"].isChecked() and widgets["buffering"].isChecked()
    assert widgets["volume"].value() == 100 and widgets["volume"].maximum() == 200
    assert widgets["trophies"].isChecked() and not widgets["shaders"].isChecked()
    assert not rpcs3_settings.settings_path(tmp_path).exists()                   # reading made no file
    widgets["scale"].setCurrentIndex(widgets["scale"].findData("150"))
    assert page.status.text() == "Resolution scale: 150 % (1080p)."
    widgets["stretch"].setChecked(True)
    widgets["volume"].setValue(120)
    assert page.status.text() == "Volume: 120 %."
    assert rpcs3_settings.settings_path(tmp_path).read_text() == (
        "Video:\n  Stretch To Display Area: true\n  Resolution Scale: 150\nAudio:\n  Master Volume: 120\n")
    page.load()
    assert widgets["scale"].currentData() == "150" and widgets["stretch"].isChecked()


def test_a_value_the_app_does_not_know_is_shown_as_it_is(qapp, tmp_path):
    rpcs3_settings.settings_path(tmp_path).write_text("Video:\n  Renderer: \"Null\"\n  Frame limit: 59.94\n")
    page = SettingsPage(tmp_path, running=lambda: False)
    assert page.widgets["framelimit"].currentText() == "59.94" and page.widgets["framelimit"].currentData() == "59.94"
    assert page.widgets["renderer"].currentText() == "Null"


def test_nothing_written_while_rpcs3_runs(qapp, tmp_path):
    running = [True]
    page = SettingsPage(tmp_path, running=lambda: running[0])
    page.widgets["vsync"].setCurrentIndex(page.widgets["vsync"].findData("Full"))
    assert page.status.text() == RUNNING and not rpcs3_settings.settings_path(tmp_path).exists()
    assert page.widgets["vsync"].currentData() == "Disabled"                      # shown as the file has it
    running[0] = False
    page.widgets["vsync"].setCurrentIndex(page.widgets["vsync"].findData("Full"))
    assert "VSync Mode: Full" in rpcs3_settings.settings_path(tmp_path).read_text()


def test_bazzites_volume_for_rpcs3(qapp, tmp_path):
    """The Sound box's last row: the volume Bazzite remembers for RPCS3, as the window passes it; muted or turned
    down to nothing is a problem, said in words."""
    page = SettingsPage(tmp_path, running=lambda: False)
    assert page.system_sound.text() == "—"
    assert page.show_sound(None) == ("", False) and page.system_sound.text() == "— (RPCS3 has not played yet)"
    assert page.show_sound((0.7, False)) == ("", False) and page.system_sound.text() == "70 %"
    assert page.show_sound((1.0, True)) == (SOUND_MUTED, True) and page.system_sound.text() == "Muted"
    assert "c62828" in page.system_sound.styleSheet()
    assert page.show_sound((0.0, False)) == (SOUND_DOWN, True) and page.system_sound.text() == "0 %"
    assert page.show_sound((1.0, False)) == ("", False) and page.system_sound.styleSheet() == ""


def test_every_setting_has_a_widget_of_its_kind(qapp, tmp_path):
    page = SettingsPage(tmp_path, running=lambda: False)
    for setting in rpcs3_settings.SETTINGS:
        widget = page.widgets[setting.key]
        expected = {rpcs3_settings.CHOICE: QComboBox, rpcs3_settings.SWITCH: QCheckBox,
                    rpcs3_settings.PERCENT: QSpinBox}[setting.kind]
        assert isinstance(widget, expected), setting.key
        assert widget.toolTip() == setting.tip and setting.tip, setting.key
