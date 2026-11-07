# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

import pytest

from sftp_tools.profiles import ConnectionProfile, ConnectionProfileStore


def test_profile_store_persists_connection_details_without_credentials(
    tmp_path: Path,
) -> None:
    path = tmp_path / "profiles.json"
    store = ConnectionProfileStore(path)
    profile = ConnectionProfile(
        name="Bazzite",
        host="192.168.1.20",
        port=22,
        username="admin",
        key_filename="/home/admin/.ssh/id_ed25519",
    )

    store.save(profile)

    assert store.list_profiles() == [profile]
    stored_text = path.read_text(encoding="utf-8")
    assert "password" not in stored_text.lower()
    assert "passphrase" not in stored_text.lower()
    assert "secret" not in stored_text.lower()
    assert path.stat().st_mode & 0o777 == 0o600


def test_saving_a_profile_replaces_the_existing_profile(tmp_path: Path) -> None:
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    store.save(ConnectionProfile("Laptop", "192.168.1.2", 22, "user", ""))
    updated = ConnectionProfile("Laptop", "192.168.1.3", 2222, "admin", "")

    store.save(updated)

    assert store.list_profiles() == [updated]


def test_profile_store_deletes_selected_profile(tmp_path: Path) -> None:
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    store.save(ConnectionProfile("One", "host1", 22, "user", ""))
    store.save(ConnectionProfile("Two", "host2", 22, "user", ""))

    store.delete("One")

    assert [profile.name for profile in store.list_profiles()] == ["Two"]


def test_profile_store_reports_malformed_profile_file(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"profiles": [{"password": "secret"}]}))
    store = ConnectionProfileStore(path)

    with pytest.raises(ValueError, match="Profile is missing name"):
        store.list_profiles()
