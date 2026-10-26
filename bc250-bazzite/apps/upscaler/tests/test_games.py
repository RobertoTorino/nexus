# SPDX-License-Identifier: GPL-3.0-or-later
"""The games list and keeping games current: the HelixSR version in a DLL, a game that put its own DLL back, Update
older games, what Run with HelixSR installs into, Steam's AppIDs and whether a game is running."""

from __future__ import annotations

from pathlib import Path

from upscaler import backend
from tests.conftest import FAKE_DLL, FAKE_GAME_DLL

NEWER_DLL = b"MZ-HelixSR 1.9.3-fake-dll"


def dll_of(game: Path) -> Path:
    return game / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64" / backend.UPSCALER_DLL


def newer_payload(payload: Path) -> None:
    (payload / backend.HELIXSR_DLL).write_bytes(NEWER_DLL)
    (payload / "README.md").write_text("**Version 1.9.3** - newer\n", encoding="utf-8")


def test_dll_version(tmp_path):
    dll = tmp_path / "a.dll"
    dll.write_bytes(b"MZ" + b"\0" * 100 + b"HelixSR 1.9.3\0more")
    assert backend.dll_version(dll) == "1.9.3"
    dll.write_bytes(FAKE_GAME_DLL)
    assert backend.dll_version(dll) == ""
    assert backend.dll_version(tmp_path / "missing.dll") == ""


def test_a_game_that_put_its_own_dll_back(game, payload):
    """A game update or Steam's file check puts the game's DLL back and leaves HelixSR's backup: Original restored,
    not an older build, and Update older games puts HelixSR back without touching the backup or helixsr.ini."""
    target = dll_of(game)
    backend.deploy(target, payload, "[Log]\r\nEnabled = true\r\n")
    dep = backend.Deployment(str(target), backend.MODE_REPLACE, "SomeGame", helixsr_version="1.2.0")
    assert backend.deployment_state(dep, payload) == ("ok", "In place") and not backend.needs_update(dep, payload)
    target.write_bytes(FAKE_GAME_DLL)
    info = backend.inspect_dll(target, payload)
    assert info.restored and info.deployed and info.state == "Game's own DLL again"
    assert backend.deployment_state(dep, payload) == ("bad", backend.RESTORED) and backend.needs_update(dep, payload)
    backend.update_deployment(dep, payload)
    assert target.read_bytes() == FAKE_DLL and backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    assert (target.parent / backend.INI).read_bytes() == b"[Log]\r\nEnabled = true\r\n"
    assert backend.deployment_state(dep, payload) == ("ok", "In place")


def test_update_older_builds(game, payload, tmp_path):
    target = dll_of(game)
    backend.deploy(target, payload)
    folder = tmp_path / "opti" / "HelixSR"
    fsr4 = tmp_path / "fsr4.dll"
    fsr4.write_bytes(b"MZ-amd-fsr4")
    backend.deploy_folder(folder, payload, None, fsr4)
    ini_before = (folder / backend.INI).read_bytes()
    deps = [backend.Deployment(str(target), backend.MODE_REPLACE, "g", helixsr_version="1.2.0"),
            backend.Deployment(str(folder), backend.MODE_FOLDER, "g", helixsr_version="1.2.0")]
    newer_payload(payload)
    assert [backend.deployment_state(d, payload) for d in deps] == [("warn", backend.OLDER)] * 2
    assert not backend.inspect_dll(target, payload).restored                # an older HelixSR, not the game's DLL
    for dep in deps:
        assert backend.needs_update(dep, payload)
        backend.update_deployment(dep, payload)
        assert backend.deployment_state(dep, payload) == ("ok", "In place")
    assert target.read_bytes() == NEWER_DLL and backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    assert (folder / backend.SECOND_UPSCALER_DLL).read_bytes() == b"MZ-amd-fsr4"
    assert (folder / backend.INI).read_bytes() == ini_before


def test_a_newer_build_is_left_alone(game, payload):
    """Deployments of a newer release than the payload (the fallback picked on the Setup page) are not updated."""
    target = dll_of(game)
    backend.deploy(target, payload)
    dep = backend.Deployment(str(target), backend.MODE_REPLACE, "g", helixsr_version="9.0.0")
    newer_payload(payload)
    assert backend.deployment_state(dep, payload) == ("warn", "Newer build") and not backend.needs_update(dep, payload)


def test_game_scan_states_and_targets(game, payload, tmp_path):
    empty = tmp_path / "NoFsr"
    empty.mkdir()
    assert backend.scan_game(empty, payload).state() == ("neutral", "No AMD FSR 3.1 DLL: HelixSR cannot be used")
    target = dll_of(game)
    generic = target.with_name(backend.HELIXSR_DLL)
    generic.write_bytes(FAKE_GAME_DLL)
    other = game / "Launcher" / backend.HELIXSR_DLL                          # only the generic DLL in this folder
    other.parent.mkdir()
    other.write_bytes(FAKE_GAME_DLL)
    scan = backend.scan_game(game, payload, "1234")
    assert scan.usable and scan.app_id == "1234" and scan.state() == ("info", "Not installed")
    assert sorted(d.path for d in scan.targets()) == sorted([target, other])   # the upscaler DLL where there are both
    backend.deploy(target, payload)
    scan = backend.scan_game(game, payload)
    assert [d.path for d in scan.targets()] == [target]                         # where HelixSR is
    assert scan.state() == ("ok", "HelixSR 1.2.0 installed")
    newer_payload(payload)
    assert backend.scan_game(game, payload).state() == ("warn", "HelixSR 1.2.0 installed; 1.9.3 is available")
    target.write_bytes(FAKE_GAME_DLL)
    assert backend.scan_game(game, payload).state() == ("bad", "The game put its own DLL back")


def test_steam_app_ids(tmp_path):
    library = tmp_path / "steamapps"
    (library / "common" / "Some Game").mkdir(parents=True)
    (library / "appmanifest_2420110.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"2420110"\n\t"name"\t\t"Some Game"\n\t"installdir"\t\t"Some Game"\n}\n',
        encoding="utf-8")
    (library / "appmanifest_1.acf").write_text("garbage", encoding="utf-8")
    assert backend.steam_app_ids([library, tmp_path / "gone"]) == {library / "common" / "Some Game": "2420110"}


def test_game_running(tmp_path):
    proc = tmp_path / "proc"
    for pid, cmdline in (("100", b"/usr/bin/bash\0"), ("200", b"/steam/reaper\0SteamLaunch\0AppId=2420110\0--\0x\0"),
                         ("self", b"AppId=99\0")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "cmdline").write_bytes(cmdline)
    assert backend.game_running("2420110", proc)
    assert not backend.game_running("242011", proc) and not backend.game_running("99", proc)
    assert not backend.game_running("1", tmp_path / "noproc")


def test_scan_can_be_cancelled(game, payload):
    assert backend.find_game_dlls(game, payload, cancelled=lambda: True) == []


def test_steam_tools_are_not_games():
    tools = ("Proton - Experimental", "Proton 9.0", "SteamLinuxRuntime_4", "SteamLinuxRuntime_sniper",
             "Steamworks Shared", "Steam Controller Configs")
    assert all(backend.is_steam_tool(Path("/lib/common") / name) for name in tools)
    assert not any(backend.is_steam_tool(Path("/lib/common") / name) for name in ("ProtonDB Game", "GodOfWar", "Steam"))
