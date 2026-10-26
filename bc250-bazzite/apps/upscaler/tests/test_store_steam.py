# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

from upscaler import backend


def test_store_round_trip(tmp_path):
    path = tmp_path / "cfg" / "deployments.json"
    store = backend.DeploymentStore(path)
    assert store.items == []
    dep = store.record(tmp_path / "a.dll", backend.MODE_REPLACE, "Game A", "1.2.0")
    store.record(tmp_path / "folder", backend.MODE_FOLDER, "", "1.2.0")
    store.record(tmp_path / "a.dll", backend.MODE_REPLACE, "Game A", "1.3.0")   # same location: updated, not added
    assert len(store.items) == 2
    assert store.find(tmp_path / "a.dll").helixsr_version == "1.3.0"
    assert dep.location == tmp_path / "a.dll"

    again = backend.DeploymentStore(path)
    assert [d.location for d in again.items] == [d.location for d in store.items]
    again.forget(tmp_path / "a.dll")
    again.forget(tmp_path / "unknown")
    assert len(again.items) == 1
    assert len(backend.DeploymentStore(path).items) == 1


def test_store_tolerates_garbage(tmp_path):
    path = tmp_path / "deployments.json"
    path.write_text("{not json")
    assert backend.DeploymentStore(path).items == []
    path.write_text(json.dumps([{"foo": "bar"}, 42]))
    assert backend.DeploymentStore(path).items == []


def test_steam_libraries_and_games(tmp_path):
    home = tmp_path / "home"
    steam = home / ".local" / "share" / "Steam"
    (steam / "steamapps" / "common" / "Game One").mkdir(parents=True)
    extra = tmp_path / "ssd" / "SteamLibrary"
    (extra / "steamapps" / "common" / "Game Two").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n'
        % (steam, str(extra).replace("/", "\\/")), encoding="utf-8")
    libs = backend.steam_libraries(home)
    assert libs == [(steam / "steamapps").resolve(), (extra / "steamapps").resolve()]
    games = backend.steam_games(libs)
    assert [g.name for g in games] == ["Game One", "Game Two"]
    assert backend.game_name(games[1] / "x" / "y.dll", libs) == "Game Two"
    assert backend.steam_libraries(tmp_path / "nohome") == []
