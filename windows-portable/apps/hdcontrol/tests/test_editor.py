# SPDX-License-Identifier: GPL-3.0-or-later
"""The profile editor's rows (the BC250 app's dialog, as rows a controller steps through): untouched it gives back
what it was opened with, every step comes back as settings, and it will not save what the controller cannot hold."""

from __future__ import annotations

import dataclasses

from conftest import DEFAULT_PROFILE
from hd_controller import profiles
from hd_controller.editor import Editor, targets


def _settings(**changes):
    return dataclasses.replace(profiles.settings_of(profiles.parse("Triangle", DEFAULT_PROFILE)), **changes)


def test_untouched_it_gives_back_what_it_was_opened_with():
    given = _settings(name="New profile", triggers=(3, 250, 0, 255))
    editor = Editor("Square", given, True)
    assert editor.settings() == given                   # the curve points kept, the triggers' exact bytes too
    rows = dict(editor.rows())
    assert rows["name"] == "Name: New profile" and rows["left_level"] == "Left stick sensitivity: as it is"
    assert rows["l2_start"] == "L2 starts counting at: 1 %" and rows["button_5"] == "Cross sends: its own"
    assert editor.title == "Create the profile Fn + Square" and editor.problem() == ""
    assert len(editor.rows()) == 1 + 4 + 4 + 16


def test_steps_come_back_as_settings():
    editor = Editor("Cross", _settings(), False)
    editor.set_name("  Racing  ")
    editor.step("left_curve", 1)
    editor.step("left_curve", 1)                        # Default, Quick, Precise
    editor.step("right_level", 1)
    editor.step("right_level", 1)
    editor.step("right_level", 1)                       # from the default level 5: 8
    for _ in range(10):
        editor.step("l2_end", -1)                       # 100 % down to 50 %
    editor.step("button_5", 1)                          # Cross: Up, the first other target
    editor.step("button_5", -1)
    editor.step("button_5", -1)                         # back past its own: the last, Touchpad
    editor.step("button_15", 1)
    result = editor.settings()
    assert result.name == "Racing"
    assert (result.left_curve, result.left_level) == (2, profiles.DEFAULT_LEVEL)
    assert (result.right_curve, result.right_level) == (0, 8)
    assert result.triggers == (0, 128, 0, 255)
    assert result.buttons[5] == 0x11 and result.buttons[15] == 0x00 and result.buttons[0] == 0
    assert dict(editor.rows())["left_level"] == f"Left stick sensitivity: level {profiles.DEFAULT_LEVEL}"


def test_values_go_round():
    editor = Editor("Circle", _settings(left_curve=3, left_level=9), False)
    assert dict(editor.rows())["left_level"] == "Left stick sensitivity: level 9"
    editor.step("left_level", 1)
    editor.step("left_level", 1)
    assert dict(editor.rows())["left_level"] == "Left stick sensitivity: level 0"
    editor.step("left_curve", -1)
    assert dict(editor.rows())["left_curve"] == "Left stick: Precise"
    editor.step("r2_start", -1)
    assert dict(editor.rows())["r2_start"] == "R2 starts counting at: 100 %"


def test_the_back_buttons_are_no_targets():
    choices = [profiles.OUTPUTS[value] for value in targets(0)]
    assert choices[0] == "Up" and choices.count("Up") == 1 and "Left back button" not in choices
    assert "Options" in choices and "Touchpad" in choices


def test_it_will_not_save_what_the_controller_cannot_hold():
    editor = Editor("Square", _settings(), True)
    editor.set_name("   ")
    assert "name" in editor.problem()
    editor.set_name("Ok")
    for _ in range(12):
        editor.step("r2_start", 1)                      # 0 % up to 60 %
    for _ in range(12):
        editor.step("r2_end", -1)                       # 100 % down to 40 %
    assert "R2" in editor.problem()
    for _ in range(12):
        editor.step("r2_start", -1)                     # back to 0 %
    assert editor.problem() == "" and editor.settings().triggers[2:] == (0, 102)
    editor.set_name("x" * 60)
    assert editor.name == "x" * 39 and editor.problem() == ""


def test_a_curve_the_list_does_not_know_shows_as_default():
    """As the dialog's list showed it: its first entry, which is what it then gave back."""
    editor = Editor("Square", _settings(left_curve=7), False)
    assert dict(editor.rows())["left_curve"] == "Left stick: Default" and editor.settings().left_curve == 0
