# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import dataclasses
import json

import pytest

from conftest import DEFAULT_PROFILE, FakeDevice, empty_slot, profile_reports
from usb_hdcontrol import profiles


def test_the_owners_default_profile():
    profile = profiles.parse("Triangle", DEFAULT_PROFILE)
    assert not profile.empty and profile.crc_ok
    assert profile.label == "Fn + Triangle" and profile.name == "Default Profile"
    assert (profile.left_curve, profile.right_curve) == ("Default", "Default")
    assert profile.triggers == (0, 255, 0, 255) and profile.remapped == ()


def test_an_empty_slot():
    assert profiles.parse("Square", empty_slot(0x73)).empty


def test_a_profile_with_curves_triggers_and_remapped_buttons():
    third = bytearray(DEFAULT_PROFILE[2][2:56])
    third[2:6] = bytes([26, 230, 0, 128])           # L2 10 to 90 %, R2 0 to 50 %
    third[8 + 5] = 0x04                             # Cross sends Circle
    third[8 + 14] = 0x10                            # the left back button sends Options
    third[28], third[30] = 2, 5                     # Precise, Dynamic
    profile = profiles.parse("Cross", profile_reports(0x76, "FPS with a long name, forty characters!", bytes(third)))
    assert profile.name == "FPS with a long name, forty characters!"
    assert (profile.left_curve, profile.right_curve) == ("Precise", "Dynamic")
    assert profiles.trigger_text(*profile.triggers[:2]) == "10 to 90 %"
    assert profiles.trigger_text(*profile.triggers[2:]) == "0 to 50 %"
    assert profile.remapped == (("Cross", "Circle"), ("Left back button", "Options"))
    assert profile.crc_ok


def test_a_changed_byte_fails_the_checksum():
    reports = list(DEFAULT_PROFILE)
    reports[1] = reports[1][:10] + b"\x01" + reports[1][11:]
    assert not profiles.parse("Triangle", tuple(reports)).crc_ok


def test_read_asks_for_the_twelve_reports_in_order():
    asked = []

    class Recording(FakeDevice):
        def get_feature(self, report_id):
            asked.append(report_id)
            return super().get_feature(report_id)
    read = profiles.read(Recording())
    assert asked == list(range(0x70, 0x7C))
    assert [p.slot for p in read] == ["Triangle", "Square", "Cross", "Circle"]
    assert [p.empty for p in read] == [False, True, True, True]


def test_backup_keeps_the_reports(tmp_path):
    read = profiles.read(FakeDevice())
    target = profiles.backup(read, tmp_path / "b" / "profiles.json", "DualSense Edge", "0x0200")
    data = json.loads(target.read_text())
    assert data["controller"] == "DualSense Edge" and data["firmware"] == "0x0200"
    first = data["profiles"][0]
    assert first["slot"] == "Fn + Triangle" and first["name"] == "Default Profile"
    assert first["reports"]["0x72"] == DEFAULT_PROFILE[2].hex()
    assert data["profiles"][3]["empty"] is True


def test_backup_path(tmp_path):
    path = profiles.backup_path(tmp_path, 0)
    assert path.parent == tmp_path / "profiles" and path.name.startswith("profiles-19")


def test_changed_parts():
    assert profiles.changed_parts(profiles.parse("Triangle", DEFAULT_PROFILE)) == set()
    assert profiles.changed_parts(profiles.parse("Square", empty_slot(0x73))) == set()
    third = bytearray(DEFAULT_PROFILE[2][2:56])
    third[2] = 40                                   # L2 starts later
    third[8 + 0] = 0x07                             # Up sends Triangle
    third[8 + 15] = 0x05                            # the right back button sends Cross
    third[30] = 1                                   # right stick Quick
    profile = profiles.parse("Circle", profile_reports(0x79, "Racing", bytes(third)))
    assert profiles.changed_parts(profile) == {"triggers", "dpad", "back", "sticks"}


def _settings(**changes):
    return dataclasses.replace(profiles.settings_of(profiles.parse("Triangle", DEFAULT_PROFILE)), **changes)


def test_settings_of_the_default_profile_keep_its_curve_points():
    settings = _settings()
    assert settings.name == "Default Profile" and (settings.left_curve, settings.right_curve) == (0, 0)
    assert settings.left_level is None and settings.right_level is None     # its points are zeros: kept as they are
    assert settings.buttons == tuple(range(16))


def test_the_owners_write_test_as_built_by_the_app():
    """The reports the owner's Edge took on 23-10-2026: the default profile renamed "Write test" in Fn + Square,
    with the per-report CRCs the test script printed."""
    reports = profiles.framed("Square", profiles.build(_settings(name="Write test"), DEFAULT_PROFILE))
    assert [r[0] for r in reports] == [0x60] * 3 and [r[1] for r in reports] == [0, 1, 2]
    assert [r[60:64].hex() for r in reports] == ["2511dc23", "bc4ba189", "a4eeddbd"]


def test_build_puts_every_setting_in_and_keeps_the_rest():
    buttons = list(range(16))
    buttons[5], buttons[14] = 0x04, 0x10            # Cross sends Circle, the left back button Options
    parts = profiles.build(_settings(name="Racing ✓", left_curve=1, left_level=7, right_curve=5, right_level=0,
                                     triggers=(26, 230, 0, 128), buttons=tuple(buttons)),
                           DEFAULT_PROFILE, new_id=bytes(range(16)))
    profile = profiles.parse("Cross", parts)
    assert profile.name == "Racing ✓" and profile.crc_ok
    assert (profile.left_curve, profile.right_curve) == ("Quick", "Dynamic")
    assert profile.triggers == (26, 230, 0, 128)
    assert profile.remapped == (("Cross", "Circle"), ("Left back button", "Options"))
    assert parts[1][28:44] == bytes(range(16))
    assert parts[1][47:53] == profiles.curve_points(1, 7) and parts[1][44] == 0x03
    assert parts[1][56:60] + parts[2][2:4] == profiles.curve_points(5, 0) and parts[1][53] == 0x03
    assert parts[2][28] == 0xC0                      # a byte the app does not know, as the controller made it
    settings = profiles.settings_of(profile)
    assert (settings.left_level, settings.right_level) == (7, 0)


def test_curve_points_follow_the_tables():
    assert list(profiles.curve_points(0, 3)) == [128, 128, 196, 196, 225, 225]
    assert list(profiles.curve_points(1, 5)) == [38, 38, 107, 167, 255, 255]
    assert list(profiles.curve_points(2, 2)) == [76, 50, 140, 102, 200, 162]
    assert profiles.curve_level(3, profiles.curve_points(3, 9)) == 9 and profiles.curve_level(3, bytes(6)) is None


def test_build_refuses_what_the_controller_cannot_hold():
    for changes, words in (({"name": " "}, "name"), ({"name": "x" * 40}, "name"),
                           ({"triggers": (100, 100, 0, 255)}, "range"), ({"buttons": (0,) * 15}, "button map")):
        with pytest.raises(profiles.ProfileError, match=words):
            profiles.build(_settings(**changes), DEFAULT_PROFILE)
    assert profiles.name_fits("x" * 39) and not profiles.name_fits("😀" * 20)


def test_write_reads_back_and_clear_empties():
    device = FakeDevice()
    parts = profiles.build(_settings(name="Write test"), DEFAULT_PROFILE)
    written = profiles.write(device, "Circle", parts, wait=0)
    assert written.name == "Write test" and [r[0] for r in device.sent] == [0x62] * 3
    profiles.clear(device, "Circle", wait=0)
    assert device.sent[-1][:2] == bytes([0x68, 4])
    after = profiles.read(device)
    assert after[3].empty and after[0].reports == DEFAULT_PROFILE


def test_the_default_profile_is_never_written_or_cleared():
    device = FakeDevice()
    for change in (lambda: profiles.write(device, "Triangle", DEFAULT_PROFILE, wait=0),
                   lambda: profiles.clear(device, "Triangle", wait=0)):
        with pytest.raises(profiles.ProfileError, match="default profile"):
            change()
    assert device.sent == []


def test_a_write_the_controller_does_not_keep_is_an_error():
    class Deaf(FakeDevice):
        def set_feature(self, data):
            self.sent.append(bytes(data))
    with pytest.raises(profiles.ProfileError, match="did not keep"):
        profiles.write(Deaf(), "Square", profiles.build(_settings(), DEFAULT_PROFILE), wait=0)
    with pytest.raises(profiles.ProfileError, match="still holds"):
        profiles.clear(Deaf({0x73: DEFAULT_PROFILE[0]}), "Square", wait=0)
