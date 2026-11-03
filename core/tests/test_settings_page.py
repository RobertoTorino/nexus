# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings page and its window (settings_page.py; owner, 03-11-2026): one box per group, the values as read,
a change written the moment it is made and said in the status, a value the app does not offer shown as it is, and
nothing written while the emulator runs."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QCheckBox, QComboBox, QGroupBox, QSpinBox

from bc250_core.settings_page import CHOICE, PERCENT, SWITCH, SettingsDialog, SettingsPage, running_text


@dataclass(frozen=True)
class Setting:
    key: str
    group: str
    label: str
    kind: str = CHOICE
    choices: tuple[tuple[str, str], ...] = ()
    tip: str = "a tip"
    top: int = 100


SETTINGS = (Setting("renderer", "Picture", "Renderer", CHOICE, (("vk", "Vulkan"), ("gl", "OpenGL"))),
            Setting("vsync", "Picture", "VSync", SWITCH),
            Setting("scale", "Picture", "Scale", "number", (("1", "1x"), ("2", "2x"))),    # an app's own kind
            Setting("volume", "Sound", "Volume", PERCENT, top=200),
            Setting("cheats", "Game", "Cheats", SWITCH),
            Setting("fps", "Game", "FPS", "flag"))


class Model:
    def __init__(self):
        self.values = {"renderer": "vk", "vsync": "true", "scale": "2", "volume": "80", "cheats": "false",
                       "fps": "false"}
        self.fail = False

    def read(self):
        return dict(self.values)

    def write(self, setting, value):
        if self.fail:
            raise OSError("read-only file system")
        self.values[setting.key] = value


def test_the_boxes_the_values_and_a_change(qapp):
    model = Model()
    page = SettingsPage("Emu", SETTINGS, model.read, model.write, lambda: False, lead="The lead.")
    assert [box.title() for box in page.findChildren(QGroupBox)] == ["Picture", "Sound", "Game"]
    widgets = page.widgets
    assert isinstance(widgets["renderer"], QComboBox) and widgets["renderer"].currentText() == "Vulkan"
    assert isinstance(widgets["vsync"], QCheckBox) and widgets["vsync"].isChecked()
    assert isinstance(widgets["volume"], QSpinBox) and widgets["volume"].value() == 80
    assert widgets["volume"].maximum() == 200 and not widgets["cheats"].isChecked()
    assert isinstance(widgets["scale"], QComboBox) and widgets["scale"].currentText() == "2x"
    assert isinstance(widgets["fps"], QCheckBox) and not widgets["fps"].isChecked()
    widgets["scale"].setCurrentIndex(0)
    assert model.values["scale"] == "1" and page.status.text() == "Scale: 1x."
    widgets["fps"].setChecked(True)
    assert model.values["fps"] == "true" and page.status.text() == "FPS: on."
    widgets["renderer"].setCurrentIndex(1)
    assert model.values["renderer"] == "gl" and page.status.text() == "Renderer: OpenGL."
    widgets["vsync"].setChecked(False)
    assert model.values["vsync"] == "false" and page.status.text() == "VSync: off."
    widgets["volume"].setValue(50)
    assert model.values["volume"] == "50" and page.status.text() == "Volume: 50 %."


def test_a_value_the_app_does_not_offer_is_shown_as_it_is(qapp):
    model = Model()
    model.values["renderer"] = "sw"
    model.values["volume"] = "loud"
    page = SettingsPage("Emu", SETTINGS, model.read, model.write, lambda: False)
    assert page.widgets["renderer"].currentText() == "sw" and page.widgets["renderer"].count() == 3
    assert page.widgets["volume"].value() == 200                                 # not a number: the top


def test_nothing_is_written_while_the_emulator_runs_or_the_file_refuses(qapp):
    model = Model()
    running = [True]
    page = SettingsPage("Emu", SETTINGS, model.read, model.write, lambda: running[0])
    page.widgets["cheats"].setChecked(True)
    assert model.values["cheats"] == "false" and page.status.text() == running_text("Emu")
    assert not page.widgets["cheats"].isChecked()                                # loaded again
    running[0] = False
    model.fail = True
    page.widgets["cheats"].setChecked(True)
    assert model.values["cheats"] == "false" and "Cheats was not changed: read-only" in page.status.text()
    assert not page.widgets["cheats"].isChecked()


def test_the_window_holds_the_page(qapp):
    model = Model()
    dialog = SettingsDialog("Emu settings", "Emu", SETTINGS, model.read, model.write, lambda: False)
    assert dialog.windowTitle() == "Emu settings" and dialog.page.widgets["renderer"].currentText() == "Vulkan"
    dialog.page.widgets["cheats"].setChecked(True)
    assert model.values["cheats"] == "true"
