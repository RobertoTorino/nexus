# SPDX-License-Identifier: GPL-3.0-or-later
"""The Steam shortcut on a Steam folder made in a temp folder: added with its artwork, recognized, brought up to
date, removed; the refusals without a launcher or without Steam."""

from __future__ import annotations

from pathlib import Path

import pytest

from bc250_core import steam

from datstation import APP_ID, APP_NAME, LOGO_PATH, steam_shortcut

OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "StartDir": '"/usr/bin/"',
         "LaunchOptions": "", "LastPlayTime": 1700000000, "tags": {"0": "Emulators"}}


def _steam(tmp_path: Path, users: int = 1) -> Path:
    for n in range(users):
        config = tmp_path / "Steam" / "userdata" / str(1000 + n) / "config"
        config.mkdir(parents=True)
        (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def _launcher(tmp_path: Path) -> Path:
    launcher = tmp_path / "bin" / APP_ID
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n")
    return launcher


def test_the_entry_and_recognising_it(tmp_path):
    launcher = _launcher(tmp_path)
    entry = steam_shortcut.entry(launcher, LOGO_PATH)
    assert entry["AppName"] == APP_NAME and entry["Exe"] == f'"{launcher}"' and entry["LaunchOptions"] == ""
    assert entry["StartDir"] == f'"{launcher.parent}/"'
    assert entry["icon"] == str(LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png"))   # the PNG beside the WebP icon
    assert list(entry["tags"].values()) == ["PlayStation", APP_NAME]
    assert steam_shortcut.ours(entry) and not steam_shortcut.ours(OTHER)
    assert steam_shortcut.ours({"Exe": f"/x/{APP_ID}"}) and not steam_shortcut.ours({"Exe": f"/x/{APP_ID}-other"})
    assert steam_shortcut.launcher_path() == tmp_path / "bin" / APP_ID          # XDG_BIN_HOME from conftest


def test_add_update_and_remove_for_every_user(tmp_path, qapp):
    folder = _steam(tmp_path, users=2)
    launcher = _launcher(tmp_path)
    closed = []

    def no_steam(change):
        closed.append(True)
        change()
        return False
    assert not steam_shortcut.in_steam(folder)
    assert steam_shortcut.add(LOGO_PATH, launcher, folder, closed=no_steam) is False
    assert closed == [True] and steam_shortcut.in_steam(folder)
    number = steam_shortcut.changes(launcher, LOGO_PATH)[0].number
    for config in steam.user_folders(folder):
        values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
        assert [item["AppName"] for item in values["shortcuts"].values()] == ["RetroArch", APP_NAME]
        assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(f"{number}{s}.png" for s in steam.ART)
    # Again: still one shortcut per user (brought up to date, not doubled).
    steam_shortcut.add(LOGO_PATH, launcher, folder, closed=no_steam, art=False)
    assert len([item for item in steam.shortcuts(folder) if steam_shortcut.ours(item)]) == 2
    assert steam_shortcut.remove(LOGO_PATH, launcher, folder, closed=no_steam) is False
    assert not steam_shortcut.in_steam(folder)
    for config in steam.user_folders(folder):
        assert [item["AppName"] for item in steam.shortcuts(folder)] == ["RetroArch", "RetroArch"]
        assert not list((config / "grid").iterdir())


def test_the_artwork_has_steams_sizes(qapp):
    from PyQt6.QtGui import QImage
    art = steam_shortcut.draw_art(LOGO_PATH)
    assert set(art) == {"p", "", "_hero", "_logo"}
    for suffix in ("p", "", "_hero"):
        image = QImage.fromData(art[suffix], "PNG")
        assert (image.width(), image.height()) == steam.ART[suffix], suffix
    assert QImage.fromData(art["_logo"], "PNG").size() == QImage(str(LOGO_PATH)).size()   # the icon, as PNG


def test_refusals(tmp_path):
    folder = _steam(tmp_path)
    with pytest.raises(steam_shortcut.NotInstalled, match="run install.sh first"):
        steam_shortcut.add(LOGO_PATH, tmp_path / "missing", folder, closed=lambda change: change())
    launcher = _launcher(tmp_path)
    with pytest.raises(steam.SteamError, match="not found"):
        steam_shortcut.add(LOGO_PATH, launcher, None, closed=lambda change: change())
    (tmp_path / "empty" / "userdata").mkdir(parents=True)
    with pytest.raises(steam.ShortcutError, match="no users"):
        steam_shortcut.add(LOGO_PATH, launcher, tmp_path / "empty", closed=lambda change: change(), art=False)
