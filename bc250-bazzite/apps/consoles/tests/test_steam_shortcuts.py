# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Steam shortcut for Game Mode (steam_shortcuts.py, jobs.steam_shortcut) on Steam folders made in a temp folder:
the binary file, the shortcut beside others, updating and removing it, the artwork, and Steam closed for it."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from consoles_link import LOGO_PATH, jobs, steam_shortcuts as ss
from consoles_link.consoles import RegisteredConsole
from consoles_link.target import Target

PS4 = RegisteredConsole(host_id="001122334455", nickname="PS4-728", address="192.168.1.21", target=Target.PS4_10,
                        regist_key=bytes(16), rp_key=bytes(16), mac=bytes(6))
OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "StartDir": '"/usr/bin/"',
         "LaunchOptions": "", "LastPlayTime": 1700000000, "tags": {"0": "Emulators"}}


def test_the_binary_format_by_hand():
    data = (b"\x00shortcuts\x00" + b"\x000\x00" + b"\x02appid\x00" + struct.pack("<i", -5) +
            b"\x01AppName\x00Game\x00" + b"\x00tags\x00\x01" + b"0\x00x\x00\x08" + b"\x08" + b"\x08" + b"\x08")
    values = ss.read_vdf(data)
    assert values == {"shortcuts": {"0": {"appid": -5, "AppName": "Game", "tags": {"0": "x"}}}}
    assert ss.write_vdf(values) == data
    assert ss.read_vdf(b"") == {}
    with pytest.raises(ss.ShortcutError):
        ss.read_vdf(b"\x00shortcuts\x00\x05x\x00")


def test_appid_is_steams_crc():
    exe, name = '"/home/u/.local/bin/bc250-console-link"', "PS4-728 (Console Link)"
    number = ss.appid(exe, name)
    assert number == zlib.crc32((exe + name).encode()) | 0x80000000 and number >= 1 << 31
    assert ss.as_int32(number) == number - (1 << 32) and ss.as_int32(5) == 5


def _steam(tmp_path: Path, with_other: bool = True) -> Path:
    config = tmp_path / "Steam" / "userdata" / "170579662" / "config"
    config.mkdir(parents=True)
    if with_other:
        (config / "shortcuts.vdf").write_bytes(ss.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def test_add_update_and_remove(tmp_path):
    steam = _steam(tmp_path)
    launcher = tmp_path / "bin" / "bc250-console-link"
    art = {"p": b"P", "": b"W", "_hero": b"H", "_logo": b"L"}
    number = ss.write_shortcut(steam, PS4, launcher, Path("/icon.png"), art)
    config = steam / "userdata" / "170579662" / "config"
    values = ss.read_vdf((config / "shortcuts.vdf").read_bytes())
    assert list(values["shortcuts"]) == ["0", "1"] and values["shortcuts"]["0"] == OTHER     # the other one stays
    ours = values["shortcuts"]["1"]
    assert ours["AppName"] == "PS4-728 (Console Link)" and ours["Exe"] == f'"{launcher}"'
    assert ours["LaunchOptions"] == "--stream 001122334455" and ours["StartDir"] == f'"{launcher.parent}/"'
    assert ours["appid"] & 0xFFFFFFFF == number == ss.appid(f'"{launcher}"', "PS4-728 (Console Link)")
    assert {p.name: p.read_bytes() for p in (config / "grid").iterdir()} == {
        f"{number}p.png": b"P", f"{number}.png": b"W", f"{number}_hero.png": b"H", f"{number}_logo.png": b"L"}
    assert ss.has_shortcut(steam, PS4)
    # Again after the console got another name: the same shortcut, renamed, its play time kept.
    values["shortcuts"]["1"]["LastPlayTime"] = 1750000000
    (config / "shortcuts.vdf").write_bytes(ss.write_vdf(values))
    renamed = RegisteredConsole(**{**PS4.__dict__, "nickname": "Living room"})
    ss.write_shortcut(steam, renamed, launcher, Path("/icon.png"), art)
    values = ss.read_vdf((config / "shortcuts.vdf").read_bytes())
    assert len(values["shortcuts"]) == 2 and values["shortcuts"]["1"]["AppName"] == "Living room (Console Link)"
    assert values["shortcuts"]["1"]["LastPlayTime"] == 1750000000
    # Removed: the shortcut and its artwork go, the other one stays.
    number = ss.write_shortcut(steam, renamed, launcher, Path("/icon.png"), {}, remove=True)
    values = ss.read_vdf((config / "shortcuts.vdf").read_bytes())
    assert values == {"shortcuts": {"0": OTHER}} and not list((config / "grid").glob(f"{number}*"))
    assert not ss.has_shortcut(steam, PS4)


def test_a_first_shortcut_and_no_users(tmp_path):
    steam = _steam(tmp_path, with_other=False)
    ss.write_shortcut(steam, PS4, Path("/l/bc250-console-link"), Path("/i.png"), {})
    assert ss.has_shortcut(steam, PS4)
    with pytest.raises(ss.ShortcutError, match="no users"):
        ss.write_shortcut(tmp_path / "nowhere", PS4, Path("/l/x"), Path("/i.png"), {})


def test_artwork(qapp):
    from PyQt6.QtGui import QImage
    art = ss.draw_art(PS4, LOGO_PATH)
    # the icon, as PNG, over the banner
    assert QImage.fromData(art["_logo"], "PNG").size() == QImage(str(LOGO_PATH)).size()
    for suffix, (width, height) in ss.ART.items():
        if suffix != "_logo":
            image = QImage.fromData(art[suffix], "PNG")
            assert (image.width(), image.height()) == (width, height), suffix


def test_artwork_without_the_icon(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    art = ss.draw_art(PS4, tmp_path / "none.png")
    logo = QImage.fromData(art["_logo"], "PNG")                               # the console's name instead
    assert (logo.width(), logo.height()) == ss.ART["_logo"] and logo.pixelColor(0, 0).alpha() == 0
    assert QImage.fromData(art["p"], "PNG").width() == ss.ART["p"][0]


def test_the_job_closes_steam_for_it(qapp, tmp_path):
    steam = _steam(tmp_path)
    launcher = tmp_path / "bin" / "bc250-console-link"
    missing = jobs.steam_shortcut(PS4, steam, launcher=launcher, running=lambda: False)
    assert not missing.ok and "install Console Link through the portal first" in missing.message
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n")
    commands, state = [], {"running": True}

    def run(command):
        commands.append(command)
        if command == ["steam", "-shutdown"]:
            state["running"] = False
    added = jobs.steam_shortcut(PS4, steam, launcher=launcher, run=run, running=lambda: state["running"],
                                sleep=lambda s: None)
    assert added.ok and added.message.startswith('"PS4-728 (Console Link)" is in Steam')
    assert "starts again" in added.message
    assert commands[0] == ["steam", "-shutdown"] and commands[1][1] == "-silent" and ss.has_shortcut(steam, PS4)
    removed = jobs.steam_shortcut(PS4, steam, remove=True, launcher=launcher, running=lambda: False)
    assert removed.ok and "no longer in Steam" in removed.message and not ss.has_shortcut(steam, PS4)
