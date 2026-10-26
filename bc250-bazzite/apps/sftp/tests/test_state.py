# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the app keeps things, the settings it runs with, the password rules and the completion sound."""

import pytest

from sftp_tools import APP_ID, common, settings, sound
from sftp_tools.connection import validate_password_requirements
from sftp_tools.settings_dialog import SettingsDialog


def test_files_live_in_folders_named_after_the_app(tmp_path):
    assert settings.config_dir() == tmp_path / "config" / APP_ID
    assert settings.data_dir() == tmp_path / "data" / APP_ID
    assert settings.log_file() == tmp_path / "data" / APP_ID / f"{APP_ID}.log"
    assert common.default_profile_store().path == settings.config_dir() / "profiles.json"
    assert common.default_profile_store(common.SERVER_PROFILES_FILE).path == settings.config_dir() / "server-profiles.json"


def test_settings_are_loaded_applied_and_kept(tmp_path):
    assert settings.load_settings() == settings.AppSettings()
    new = settings.AppSettings(connection_timeout=42)
    settings.apply_settings(new)
    assert settings.current_settings() is new
    assert (tmp_path / "config" / APP_ID / "settings.json").is_file()
    settings.load_settings()
    assert settings.current_settings().connection_timeout == 42


def test_invalid_settings_are_refused_and_not_applied():
    before = settings.current_settings()
    with pytest.raises(ValueError):
        settings.apply_settings(settings.AppSettings(connection_timeout=0))
    assert settings.current_settings() is before


def test_dialog_shows_a_settings_error_and_stays_open(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(common.PlainMessageBox, "critical", lambda parent, title, text: shown.append(title))
    dialog = SettingsDialog()
    dialog.local_folder.setText("/no/such/folder")
    dialog._save()
    assert shown == ["Could not save settings"]
    assert dialog.result() == 0


@pytest.mark.parametrize(("password", "valid"), [
    ("", True), ("Abcdef1!", True), ("abcdef1!", False), ("Abcdefg!", False), ("Abcdefg1", False), ("Ab1!", False)])
def test_password_requirements(password, valid):
    ok, message = validate_password_requirements(password)
    assert ok is valid
    assert (message == "") is valid


def test_beep_plays_the_desktop_sound_through_paplay():
    calls = []
    sound.play_beep(run=lambda *a, **k: calls.append(a[0]), which=lambda name: "/usr/bin/paplay")
    assert calls == [["/usr/bin/paplay", sound.COMPLETE_SOUND]]


def test_beep_falls_back_to_qt(qapp, monkeypatch):
    beeps = []
    monkeypatch.setattr(sound.QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    sound.play_beep(which=lambda name: None)

    def broken(*args, **kwargs):
        raise OSError("no paplay")

    sound.play_beep(run=broken, which=lambda name: "/usr/bin/paplay")
    assert beeps == [1, 1]
