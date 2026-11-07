# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import dataclasses

from conftest import DEFAULT_PROFILE
from usb_hdcontrol import profiles
from usb_hdcontrol.editor import ProfileEditor


def _settings(**changes):
    return dataclasses.replace(profiles.settings_of(profiles.parse("Triangle", DEFAULT_PROFILE)), **changes)


def test_untouched_it_gives_back_what_it_was_opened_with(qapp):
    given = _settings(name="New profile", triggers=(3, 250, 0, 255))
    editor = ProfileEditor("Square", given, True, None)
    assert editor.settings() == given                   # the curve points kept, the triggers' exact bytes too
    assert editor.left.value.text() == "as it is" and editor.save_button.isEnabled()
    assert "Create the profile Fn + Square" in editor.windowTitle()


def test_changes_come_back_as_settings(qapp):
    editor = ProfileEditor("Cross", _settings(), False, None)
    editor.name.setText("  Racing  ")
    editor.left.curve.setCurrentIndex(editor.left.curve.findData(2))
    editor.right.level.setValue(8)
    editor.l2.end.setValue(50)
    editor.buttons[5].setCurrentIndex(editor.buttons[5].findData(0x04))        # Cross sends Circle
    editor.buttons[15].setCurrentIndex(editor.buttons[15].findData(0x11))      # the right back button: Touchpad
    result = editor.settings()
    assert result.name == "Racing"
    assert (result.left_curve, result.left_level) == (2, profiles.DEFAULT_LEVEL)
    assert (result.right_curve, result.right_level) == (0, 8)
    assert result.triggers == (0, 128, 0, 255)
    assert result.buttons[5] == 0x04 and result.buttons[15] == 0x11 and result.buttons[0] == 0
    assert editor.left.value.text() == f"level {profiles.DEFAULT_LEVEL}"


def test_a_level_it_knows_shows_and_the_back_buttons_are_no_targets(qapp):
    editor = ProfileEditor("Circle", _settings(left_curve=3, left_level=9), False, None)
    assert editor.left.level.value() == 9 and editor.left.value.text() == "level 9"
    targets = [editor.buttons[0].itemText(i) for i in range(editor.buttons[0].count())]
    assert targets[0] == "Its own" and "Up" not in targets and "Left back button" not in targets
    assert "Options" in targets and "Touchpad" in targets


def test_it_will_not_save_what_the_controller_cannot_hold(qapp):
    editor = ProfileEditor("Square", _settings(), True, None)
    editor.name.setText("   ")
    assert not editor.save_button.isEnabled() and "name" in editor.problem.text()
    editor.name.setText("Ok")
    editor.r2.start.setValue(60)
    editor.r2.end.setValue(40)
    assert not editor.save_button.isEnabled() and "R2" in editor.problem.text()
    editor.r2.end.setValue(100)
    assert editor.save_button.isEnabled() and editor.problem.text() == ""
