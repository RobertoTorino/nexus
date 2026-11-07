# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from sftp_tools.settings import AppSettings, SizeFormat, SettingsStore


def test_round_trip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.save(AppSettings(str(tmp_path), 30, "DEBUG"))
    assert store.load() == AppSettings(str(tmp_path), 30, "DEBUG")


def test_missing_or_corrupt_gives_defaults(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    assert store.load() == AppSettings()
    (tmp_path / "s.json").write_text("{nope")
    assert store.load() == AppSettings()


def test_invalid_rejected(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    with pytest.raises(ValueError):
        store.save(AppSettings(connection_timeout=0))
    with pytest.raises(ValueError):
        store.save(AppSettings(default_local_folder=str(tmp_path / "missing")))


def test_new_settings_validated(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    with pytest.raises(ValueError):
        store.save(AppSettings(overwrite_mode="bogus"))
    with pytest.raises(ValueError):
        store.save(AppSettings(speed_limit_kbps=-1))
    store.save(AppSettings(overwrite_mode="skip", speed_limit_kbps=500))
    assert store.load().speed_limit_kbps == 500


def test_keepalive_interval(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.save(AppSettings(keepalive_interval=30))
    assert store.load().keepalive_interval == 30
    with pytest.raises(ValueError):
        store.save(AppSettings(keepalive_interval=0))
    with pytest.raises(ValueError):
        store.save(AppSettings(keepalive_interval=500))


def test_view_hidden_files(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.save(AppSettings(view_hidden_files=True))
    assert store.load().view_hidden_files is True
    store.save(AppSettings(view_hidden_files=False))
    assert store.load().view_hidden_files is False


def test_size_format(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    fmt = SizeFormat(format="binary", thousands_separator=False, decimal_places=2)
    store.save(AppSettings(size_format=fmt))
    loaded = store.load()
    assert loaded.size_format.format == "binary"
    assert loaded.size_format.thousands_separator is False
    assert loaded.size_format.decimal_places == 2
    with pytest.raises(ValueError):
        store.save(AppSettings(size_format=SizeFormat(format="bogus")))
    with pytest.raises(ValueError):
        store.save(AppSettings(size_format=SizeFormat(decimal_places=5)))


def test_sound_on_transfer_complete(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.save(AppSettings(sound_on_transfer_complete=True))
    assert store.load().sound_on_transfer_complete is True
    store.save(AppSettings(sound_on_transfer_complete=False))
    assert store.load().sound_on_transfer_complete is False

