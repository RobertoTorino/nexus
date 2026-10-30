# SPDX-License-Identifier: GPL-3.0-or-later
"""Steam's files (bc250_core.steam) on Steam folders made in a temp folder: the binary format, the appid, shortcuts
added, updated and removed beside others, several in one write, closing Steam for a change, and finding Steam."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250_core import steam

OTHER = {"appid": -1234, "AppName": "RetroArch", "Exe": '"/usr/bin/retroarch"', "StartDir": '"/usr/bin/"',
         "LaunchOptions": "", "LastPlayTime": 1700000000, "tags": {"0": "Emulators"}}


def _steam(tmp_path: Path, users: int = 1, with_other: bool = True) -> Path:
    for n in range(users):
        config = tmp_path / "Steam" / "userdata" / str(1000 + n) / "config"
        config.mkdir(parents=True)
        if with_other:
            (config / "shortcuts.vdf").write_bytes(steam.write_vdf({"shortcuts": {"0": OTHER}}))
    return tmp_path / "Steam"


def _game(name: str, options: str) -> steam.Change:
    entry = steam.shortcut_entry('"/bin/run"', name, '"/bin/"', "/icon.png", options, ["PS4", "BC250"])
    return steam.Change(entry, lambda item, options=options: item.get("LaunchOptions") == options)


def test_the_binary_format_by_hand():
    data = (b"\x00shortcuts\x00" + b"\x000\x00" + b"\x02appid\x00" + struct.pack("<i", -5) +
            b"\x01AppName\x00Game\x00" + b"\x00tags\x00\x01" + b"0\x00x\x00\x08" + b"\x08" + b"\x08" + b"\x08")
    values = steam.read_vdf(data)
    assert values == {"shortcuts": {"0": {"appid": -5, "AppName": "Game", "tags": {"0": "x"}}}}
    assert steam.write_vdf(values) == data
    assert steam.read_vdf(b"") == {}
    with pytest.raises(steam.ShortcutError):
        steam.read_vdf(b"\x00shortcuts\x00\x05x\x00")
    with pytest.raises(steam.ShortcutError, match="damaged"):
        steam.read_vdf(b"\x00shortcuts\x00\x01AppName")


def test_the_entry_and_its_appid():
    entry = steam.shortcut_entry('"/bin/run"', "Game", '"/bin/"', "/i.png", "-g x", ["A", "B"])
    number = steam.appid('"/bin/run"', "Game")
    assert number == zlib.crc32(b'"/bin/run"Game') | 0x80000000 and number >= 1 << 31
    assert entry["appid"] == steam.as_int32(number) == number - (1 << 32) and steam.as_int32(5) == 5
    assert list(entry)[:7] == ["appid", "AppName", "Exe", "StartDir", "icon", "ShortcutPath", "LaunchOptions"]
    assert entry["tags"] == {"0": "A", "1": "B"} and entry["LastPlayTime"] == 0


def test_the_shortcut_icon_is_the_png_beside_a_webp_icon(tmp_path):
    logo, png = tmp_path / "app.webp", tmp_path / "app-128.png"
    logo.write_bytes(b"W")
    assert steam.shortcut_icon(logo) == logo                                  # no PNG beside it: the logo itself
    png.write_bytes(b"P")
    assert steam.shortcut_icon(logo) == png
    assert steam.shortcut_icon(tmp_path / "icon0.png") == tmp_path / "icon0.png"     # a PNG as it is


def test_several_shortcuts_in_one_write(tmp_path):
    folder = _steam(tmp_path, users=2)
    first, second = _game("Game one", "-g /a"), _game("Game two", "-g /b")
    art = {"p": b"P", "": b"W", "_hero": b"H", "_logo": b"L"}
    first = steam.Change(first.entry, first.ours, art)
    numbers = steam.write_shortcuts(folder, [first, second])
    assert numbers == [first.number, second.number]
    for config in steam.user_folders(folder):                             # every Steam user gets them
        values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
        assert [item["AppName"] for item in values["shortcuts"].values()] == ["RetroArch", "Game one", "Game two"]
        assert values["shortcuts"]["0"] == OTHER                          # the other one stays as it was
        assert sorted(p.name for p in (config / "grid").iterdir()) == sorted(
            f"{first.number}{suffix}.png" for suffix in steam.ART)        # artwork only where given
        assert not list(config.glob("*.bc250-tmp"))
    assert len(steam.shortcuts(folder)) == 6 and steam.has_shortcut(folder, second.ours)


def test_update_keeps_the_play_time_and_remove_takes_the_artwork(tmp_path):
    folder = _steam(tmp_path)
    game = _game("Game", "-g /a")
    steam.write_shortcuts(folder, [steam.Change(game.entry, game.ours, {"p": b"P"})])
    config = steam.user_folders(folder)[0]
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    values["shortcuts"]["1"]["LastPlayTime"] = 1750000000
    (config / "shortcuts.vdf").write_bytes(steam.write_vdf(values))
    renamed = _game("Game, renamed", "-g /a")
    steam.write_shortcuts(folder, [steam.Change(renamed.entry, renamed.ours, {"p": b"R"})])
    values = steam.read_vdf((config / "shortcuts.vdf").read_bytes())
    assert len(values["shortcuts"]) == 2 and values["shortcuts"]["1"]["AppName"] == "Game, renamed"
    assert values["shortcuts"]["1"]["LastPlayTime"] == 1750000000
    assert [p.name for p in (config / "grid").iterdir()] == [f"{renamed.number}p.png"]   # the old number's went
    steam.write_shortcuts(folder, [steam.Change(renamed.entry, renamed.ours, remove=True)])
    assert steam.read_vdf((config / "shortcuts.vdf").read_bytes()) == {"shortcuts": {"0": OTHER}}
    assert not list((config / "grid").iterdir())


def test_a_shortcut_of_another_program_taken_out_takes_its_artwork(tmp_path):
    """A shortcut made before a game manager's play mode starts the emulator itself, so its number is another's than
    the change that takes it out (30-10-2026): the artwork under the number it has goes."""
    folder = _steam(tmp_path)
    old = _game("Game", "-g /a")
    steam.write_shortcuts(folder, [steam.Change(old.entry, old.ours, {"p": b"P", "_hero": b"H"})])
    entry = steam.shortcut_entry('"/bin/manager"', "Game", '"/bin/"', "/icon.png", "-g /a", ["PS4", "BC250"])
    assert steam.Change(entry, old.ours).number != old.number
    steam.write_shortcuts(folder, [steam.Change(entry, old.ours, remove=True)])
    config = steam.user_folders(folder)[0]
    assert steam.read_vdf((config / "shortcuts.vdf").read_bytes()) == {"shortcuts": {"0": OTHER}}
    assert not list((config / "grid").iterdir())


def test_a_rename_keeps_artwork_whose_number_is_taken_again(tmp_path):
    """Two shortcuts that swap names: each number is in use after the change, so no artwork goes."""
    folder = _steam(tmp_path)
    a, b = _game("A", "-g /a"), _game("B", "-g /b")
    steam.write_shortcuts(folder, [steam.Change(a.entry, a.ours, {"p": b"A"}),
                                   steam.Change(b.entry, b.ours, {"p": b"B"})])
    swapped = [_game("B", "-g /a"), _game("A", "-g /b")]
    steam.write_shortcuts(folder, swapped)
    grid = steam.user_folders(folder)[0] / "grid"
    assert sorted(p.name for p in grid.iterdir()) == sorted([f"{a.number}p.png", f"{b.number}p.png"])


def test_no_users_and_a_damaged_file(tmp_path):
    with pytest.raises(steam.ShortcutError, match="no users"):
        steam.write_shortcuts(tmp_path / "nowhere", [_game("Game", "-g /a")])
    folder = _steam(tmp_path, with_other=False)
    (steam.user_folders(folder)[0] / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00\x05")
    assert steam.shortcuts(folder) == []                                   # left out, not an error


def test_find_steam(tmp_path):
    assert steam.find_steam(tmp_path) is None
    flatpak = tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata"
    flatpak.mkdir(parents=True)
    assert steam.find_steam(tmp_path) == flatpak.parent
    native = tmp_path / ".local/share/Steam/userdata"
    native.mkdir(parents=True)
    assert steam.find_steam(tmp_path) == native.parent                    # the native one first


def test_closed_for_a_change_and_started_again():
    commands, state, changed = [], {"running": True, "polls": 0}, []

    def run(command):
        commands.append(command)

    def running():
        if commands:
            state["polls"] += 1
            state["running"] = state["polls"] <= 2                        # closes after a moment
        return state["running"]
    assert steam.with_steam_closed(lambda: changed.append(state["running"]), run, running, sleep=lambda s: None)
    assert changed == [False] and commands == [steam.shutdown_command(), steam.start_command()]
    assert steam.with_steam_closed(lambda: None, run, lambda: False) is False and len(commands) == 2


def test_steam_that_does_not_close_changes_nothing():
    commands, changed = [], []
    with pytest.raises(steam.SteamError, match="did not close"):
        steam.with_steam_closed(lambda: changed.append(1), commands.append, lambda: True, timeout=1.0,
                                sleep=lambda s: None)
    assert commands == [steam.shutdown_command()] and changed == []


def test_steam_running_reads_process_names(tmp_path, monkeypatch):
    monkeypatch.setattr(steam, "WINDOWS", False)    # Linux's /proc, read on any system
    def process(pid, name, state="S"):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "comm").write_text(name + "\n")
        (tmp_path / str(pid) / "stat").write_text(f"{pid} ({name}) {state} 1 {pid} {pid} 0 -1\n")
    process(10, "bash")
    process(11, "steamwebhelper")
    process(12, "steam", "Z")               # a finished steam -shutdown not collected yet (the owner's board, 13-10-2026)
    assert not steam.steam_running(tmp_path)
    process(13, "steam")
    assert steam.steam_running(tmp_path)


def test_game_mode(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "gamescope")
    assert steam.game_mode()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert not steam.game_mode()


def test_linux_closes_steam_with_its_own_command(monkeypatch):
    monkeypatch.setattr(steam, "WINDOWS", False)
    assert steam.shutdown_command() == ["steam", "-shutdown"]          # as before Windows (29-10-2026)


def test_steam_on_windows(tmp_path, monkeypatch):
    """Windows (the Windows Portable Suite's PCSX2 Manager, 29-10-2026): Steam's folder from its registry key, its own
    steam.exe to close and start it, steam.exe in the process list."""
    monkeypatch.setattr(steam, "WINDOWS", True)
    folder = tmp_path / "Steam"
    monkeypatch.setattr(steam, "windows_steam", lambda: folder)
    assert steam.find_steam() is None                                   # never started: no userdata
    (folder / "userdata" / "123" / "config").mkdir(parents=True)
    assert steam.find_steam() == folder.resolve() and steam.user_folders(folder)
    assert steam.find_steam(tmp_path / "home") is None                  # a home given: the Linux folders below it
    assert steam.shutdown_command() == [str(folder / "steam.exe"), "-shutdown"]
    assert steam.start_command() == [str(folder / "steam.exe")]        # -silent never signed in on Windows
    names = []
    monkeypatch.setattr(steam, "_windows_running", lambda name: names.append(name) or True)
    assert steam.steam_running() and names == ["steam.exe"]


def test_installed_is_steams_program(tmp_path, monkeypatch):
    """The portal's RT Steam shows only where Steam's program is (owner, 30-10-2026)."""
    monkeypatch.setattr(steam, "WINDOWS", True)
    monkeypatch.setattr(steam, "windows_steam", lambda: tmp_path / "Steam")
    assert not steam.installed()
    (tmp_path / "Steam").mkdir()
    (tmp_path / "Steam" / "steam.exe").write_bytes(b"")
    assert steam.installed()                            # never signed in yet (no userdata): there, to be opened
    monkeypatch.setattr(steam, "WINDOWS", False)
    monkeypatch.setattr(steam.shutil, "which", lambda name: None)
    assert not steam.installed()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' file names")
def test_steams_folder_has_its_name_as_on_the_disk(tmp_path, monkeypatch):
    """The registry names Steam's folder in lower case, and a steam.exe started by that name never signed in (the
    owner's Ally, 30-10-2026): the folder as it is on the disk, also where the key is missing."""
    folder = tmp_path / "Program Files (x86)" / "Steam"
    folder.mkdir(parents=True)

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    lower = str(folder).lower().replace("\\", "/")
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=0, OpenKey=lambda *a: Key(), QueryValueEx=lambda key, name: (lower, 1)))
    monkeypatch.setattr(steam, "WINDOWS", True)
    assert str(steam.windows_steam()) == str(folder)
    assert steam.start_command() == [str(folder / "steam.exe")]

    def missing(*a):
        raise OSError("no key")
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(HKEY_CURRENT_USER=0, OpenKey=missing))
    monkeypatch.setattr(steam, "WINDOWS_STEAM", lower)
    assert str(steam.windows_steam()) == str(folder)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' process list")
def test_windows_process_list_finds_this_python():
    assert steam._windows_running(Path(sys.executable).name.lower())
    assert not steam._windows_running("no-such-program.exe")


def test_a_shortcut_is_started_by_its_game_id(monkeypatch):
    """A game started from its manager goes through Steam (owner, 29-10-2026): steam://rungameid/ with the shortcut's
    appid in the high half."""
    assert steam.play_url(0x9ABCDEF0) == f"steam://rungameid/{(0x9ABCDEF0 << 32) | 0x02000000}"
    assert steam.play_url(steam.as_int32(0x9ABCDEF0)) == steam.play_url(0x9ABCDEF0)   # signed as in the file
    ran = []
    monkeypatch.setattr(steam, "WINDOWS", False)
    monkeypatch.setattr(steam, "_run", ran.append)
    steam.open_url(steam.OPEN_URL)
    assert ran == [["xdg-open", "steam://open/bigpicture"]]


def test_on_windows_a_steam_not_running_is_started_plainly_first(monkeypatch, tmp_path):
    """A steam:// address as Steam's first command never signed in (the owner's Ally, 30-10-2026): a Steam that does
    not run is started as a plain steam.exe, and the address follows once it is signed in; a running one gets it at
    once."""
    monkeypatch.setattr(steam, "WINDOWS", True)
    monkeypatch.setattr(steam, "windows_steam", lambda: tmp_path / "Steam")
    given, ran, later = [], [], []
    monkeypatch.setattr(steam, "_startfile", given.append)
    steam.open_url(steam.OPEN_URL, run=ran.append, running=lambda: True, later=later.append)
    assert given == [steam.OPEN_URL] and ran == [] and later == []
    steam.open_url(steam.OPEN_URL, run=ran.append, running=lambda: False, later=later.append)
    assert ran == [[str(tmp_path / "Steam" / "steam.exe")]] and later == [steam.OPEN_URL] and len(given) == 1
    answers, slept = iter([False, False, True]), []
    assert steam.hand_over("steam://x", signed=lambda: next(answers), give=given.append, sleep=slept.append)
    assert given[-1] == "steam://x" and slept == [0.5, 0.5]
    assert not steam.hand_over("steam://y", signed=lambda: False, give=given.append, timeout=1.0, sleep=lambda s: None)
    assert given[-1] == "steam://x"                            # never signed in: nothing given


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' registry")
def test_signed_in_reads_the_registry_without_failing():
    assert steam.signed_in() in (True, False)
