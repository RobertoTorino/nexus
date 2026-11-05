# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's Steam shortcut on a Steam folder made in a temp folder: the entry for a release and from the checkout,
recognized whatever its case, added with its artwork for every user, brought up to date, taken out; the refusal of a
Steam without users."""

from __future__ import annotations

import pytest

from bc250_core import play, steam
from conftest import make_steam
from dat_station import APP_NAME, LOGO_PATH, ROOT, steam_shortcut

PROGRAM = r"C:\Users\Someone\AppData\Local\windows-portable-suite\windows-portable-datstat\app\DatStation.exe"


def test_the_entry_of_a_release_and_of_the_checkout():
    entry = steam_shortcut.entry(LOGO_PATH, frozen=True, program=PROGRAM)
    assert entry["AppName"] == APP_NAME and entry["Exe"] == f'"{PROGRAM}"' and entry["LaunchOptions"] == ""
    assert entry["StartDir"] == '"C:\\Users\\Someone\\AppData\\Local\\windows-portable-suite\\windows-portable-datstat\\app\\"'
    assert entry["icon"] == str(LOGO_PATH.with_name(f"{LOGO_PATH.stem}-128.png"))   # the PNG beside the WebP icon
    assert list(entry["tags"].values()) == ["PlayStation", APP_NAME]
    checkout = steam_shortcut.entry(LOGO_PATH, frozen=False)
    assert checkout["Exe"] == f'"{play.POWERSHELL}"'
    assert checkout["LaunchOptions"].endswith(f"-File {ROOT / 'run.ps1'}") and "-WindowStyle Hidden" in \
        checkout["LaunchOptions"]
    assert steam_shortcut.ours(entry) and steam_shortcut.ours(checkout)


def test_recognizing_its_own():
    assert steam_shortcut.ours({"exe": '"D:\\Other\\datstation.EXE"'})          # any folder, any case
    assert not steam_shortcut.ours({"Exe": '"C:\\Games\\DatStation-Old.exe"'})
    assert not steam_shortcut.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": "-File C:\\x\\xenia\\run.ps1"})
    assert not steam_shortcut.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": '-File "unclosed'})
    assert not steam_shortcut.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": ""})
    assert steam_shortcut.ours({"Exe": f'"{play.POWERSHELL}"', "LaunchOptions": "-File C:\\nexus\\datstat\\run.ps1"})


def test_add_update_and_remove_for_every_user(tmp_path, qapp):
    folder = make_steam(tmp_path, users=2)
    closed = []

    def no_steam(change):
        closed.append(True)
        change()
        return False
    assert not steam_shortcut.in_steam(folder)
    assert steam_shortcut.apply(LOGO_PATH, folder, closed=no_steam) is False
    assert closed == [True] and steam_shortcut.in_steam(folder)
    number = steam_shortcut.changes(LOGO_PATH)[0].number
    for config in steam.user_folders(folder):
        values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
        assert [item["AppName"] for item in values["shortcuts"].values()] == ["RetroArch", APP_NAME]
        assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(f"{number}{s}.png" for s in steam.ART)
    # Again: still one shortcut per user (brought up to date, not doubled).
    steam_shortcut.apply(LOGO_PATH, folder, closed=no_steam, art=False)
    assert len([item for item in steam.shortcuts(folder) if steam_shortcut.ours(item)]) == 2
    assert steam_shortcut.apply(LOGO_PATH, folder, remove=True, closed=no_steam) is False
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


def test_a_steam_without_users_is_refused(tmp_path):
    (tmp_path / "empty" / "userdata").mkdir(parents=True)
    with pytest.raises(steam.ShortcutError, match="no users"):
        steam_shortcut.apply(LOGO_PATH, tmp_path / "empty", closed=lambda change: change(), art=False)
