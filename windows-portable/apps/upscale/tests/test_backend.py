# SPDX-License-Identifier: GPL-3.0-or-later
"""backend.py, as the BC250 app's tests take it: the payload imported from a folder or a zip, its version, a game's FSR
3.1 DLLs found, deploy and Go back (the game's own file always kept), the stand-alone folder with OptiScaler (native
Windows paths, no launch options), helixsr.ini kept with its comments, the deployments and their states, Steam's
libraries on Windows. Temp folders only."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from conftest import FAKE_DLL, FAKE_GAME_DLL, embedded_dll, make_game, make_payload, make_release, make_steam
from upscale_boost import backend
from upscale_boost.backend import Deployment, DeploymentStore, HelixError, HelixIni


def game_dll(game: Path) -> Path:
    return game / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64" / backend.UPSCALER_DLL


# The payload

def test_import_from_a_folder_takes_only_helixsrs_files(tmp_path, release):
    (release / "unrelated.txt").write_text("x")
    result = backend.import_payload(release, tmp_path / "payload")
    assert set(result.copied) == {backend.HELIXSR_DLL, backend.WEIGHTS, backend.KERNELS, backend.INI, "README.md"}
    assert result.missing == [] and not (tmp_path / "payload" / "unrelated.txt").exists()
    status = backend.payload_status(tmp_path / "payload")
    assert status.ready and status.version == "1.2.0" and not status.embedded


def test_import_from_the_zip_and_what_is_still_missing(tmp_path, release):
    archive = tmp_path / "HelixSR-1.2.0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(release / backend.HELIXSR_DLL, f"HelixSR-1.2.0/{backend.HELIXSR_DLL}")
    result = backend.import_payload(archive, tmp_path / "payload")
    assert result.copied == [backend.HELIXSR_DLL] and result.missing == [backend.WEIGHTS, backend.KERNELS]
    assert not backend.payload_status(tmp_path / "payload").ready


def test_import_refuses_a_folder_without_helixsr(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(HelixError, match="No amd_fidelityfx_dx12.dll"):
        backend.import_payload(tmp_path / "empty", tmp_path / "payload")


def test_a_one_file_dll_drops_network_files_of_an_older_build(tmp_path, payload):
    release = tmp_path / "HelixSR-2.0.0" / backend.FSRFG
    release.mkdir(parents=True)
    (release / backend.HELIXSR_DLL).write_bytes(embedded_dll())
    result = backend.import_payload(release.parent, payload)
    assert result.missing == [] and not (payload / backend.WEIGHTS).exists()
    assert backend.payload_status(payload).embedded


def test_the_version_from_each_readme_and_else_from_the_dll(tmp_path):
    folder = tmp_path / "p"
    folder.mkdir()
    (folder / "README.md").write_text("intro **Version 1.8.1.** more", encoding="utf-8")
    assert backend.payload_version(folder) == "1.8.1"
    (folder / "README.md").write_text("# HelixSR 2.0.0\n\nHelixSR runs ...", encoding="utf-8")
    assert backend.payload_version(folder) == "2.0.0"
    (folder / "README.md").unlink()
    (folder / backend.HELIXSR_DLL).write_bytes(b"MZ\0\0 built by HelixSR 1.9.3 for you")
    assert backend.payload_version(folder) == "1.9.3"


def test_payload_folder_is_helixsr_fsrfg_from_2_0(tmp_path):
    assert backend.payload_folder(tmp_path) == tmp_path
    (tmp_path / backend.FSRFG).mkdir()
    (tmp_path / backend.FSRFG / backend.HELIXSR_DLL).write_bytes(b"x")
    assert backend.payload_folder(tmp_path) == tmp_path / backend.FSRFG


# A game's DLLs, deploy and Go back

def test_the_games_dll_is_found_deep_and_the_helixsr_folder_is_not(tmp_path, game, payload):
    (game / backend.HELIXSR_FOLDER).mkdir()
    (game / backend.HELIXSR_FOLDER / backend.HELIXSR_DLL).write_bytes(FAKE_DLL)
    found = backend.find_game_dlls(game, payload)
    assert [d.path for d in found] == [game_dll(game)] and found[0].state == "Game's own DLL"


def test_deploy_keeps_the_original_and_go_back_restores_it(game, payload):
    target = game_dll(game)
    written = backend.deploy(target, payload, "[Log]\nEnabled = false\n")
    assert target.read_bytes() == FAKE_DLL and backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    assert target.parent / backend.INI in written and (target.parent / backend.WEIGHTS).is_file()
    info = backend.inspect_dll(target, payload)
    assert info.deployed and info.matches_payload and info.state == "HelixSR deployed"
    (target.parent / backend.LOG).write_text("log")
    backend.remove(target, payload)
    assert target.read_bytes() == FAKE_GAME_DLL and not backend.original_path(target).exists()
    assert not any((target.parent / n).exists() for n in (backend.WEIGHTS, backend.KERNELS, backend.INI, backend.LOG))


def test_a_newer_build_over_an_older_keeps_the_real_original(tmp_path, game, payload):
    target = game_dll(game)
    backend.deploy(target, payload)
    newer = make_payload(tmp_path / "newer")
    backend.deploy(target, newer)
    assert backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    assert not (target.parent / backend.WEIGHTS).exists()           # the one-file DLL carries the network


def test_go_back_refuses_a_dll_that_is_not_helixsr(game, payload):
    with pytest.raises(HelixError, match="is not HelixSR"):
        backend.remove(game_dll(game), payload)
    assert game_dll(game).read_bytes() == FAKE_GAME_DLL


def test_deploy_refuses_without_a_built_payload(tmp_path, game):
    make_release(tmp_path / "half", network=False)
    with pytest.raises(HelixError, match="not built yet"):
        backend.deploy(game_dll(game), tmp_path / "half")


def test_the_games_own_dll_back_after_an_update_shows(game, payload):
    target = game_dll(game)
    backend.deploy(target, payload)
    target.write_bytes(FAKE_GAME_DLL)                               # Steam's file check put the game's back
    info = backend.inspect_dll(target, payload)
    assert info.restored and info.state == "Game's own DLL again"
    scan = backend.scan_game(game, payload)
    assert scan.state() == ("bad", "The game put its own DLL back")


# The stand-alone folder and OptiScaler

def test_the_folder_with_a_second_upscaler_and_its_removal(tmp_path, game, payload):
    folder = game / backend.HELIXSR_FOLDER
    second = tmp_path / "amd_fidelityfx_upscaler_dx12.dll"
    second.write_bytes(b"MZ FSR 4")
    backend.deploy_folder(folder, payload, backend.DEFAULT_INI_TEXT, second)
    assert all((folder / n).read_bytes() == FAKE_DLL for n in backend.GAME_DLLS)
    assert (folder / backend.SECOND_UPSCALER_DLL).read_bytes() == b"MZ FSR 4"
    assert backend.parse_ini((folder / backend.INI).read_text()).upscaler_dll == backend.SECOND_UPSCALER_DLL
    backend.deploy_folder(folder, payload, (folder / backend.INI).read_text())    # again without: it goes
    assert not (folder / backend.SECOND_UPSCALER_DLL).exists()
    assert backend.parse_ini((folder / backend.INI).read_text()).upscaler_dll == ""
    backend.remove_folder(folder, payload)
    assert not folder.exists()


def test_the_snippet_names_the_folder_as_windows_writes_it(tmp_path):
    snippet = backend.optiscaler_snippet(tmp_path / "Game" / "HelixSR")
    path = str((tmp_path / "Game" / "HelixSR").resolve())
    assert "Dx12Upscaler=fsr31" in snippet and f"FfxDx12Path={path}\\{backend.HELIXSR_DLL}" in snippet
    assert "Z:" not in snippet


def test_optiscaler_beside_the_exe_and_back(tmp_path):
    payload = make_payload(tmp_path / "payload", "1.8.1", optiscaler=True)
    game = make_game(tmp_path / "common", "Shooter", fsr=False)
    exe_dir = backend.find_exe_folder(game)
    assert exe_dir == game / "Shooter" / "Binaries" / "Win64"
    (exe_dir / "dxgi.dll").write_bytes(b"MZ the game's own dxgi")
    folder = game / backend.HELIXSR_FOLDER
    backend.deploy_folder(folder, payload)
    backend.install_optiscaler(exe_dir, folder, payload)
    assert (exe_dir / "dxgi.dll").read_bytes() == b"MZ OptiScaler dll"
    assert (folder / backend.OPTISCALER_BACKUP / "dxgi.dll").read_bytes() == b"MZ the game's own dxgi"
    ini = (exe_dir / backend.OPTISCALER_INI).read_text()
    assert "Dx12Upscaler=fsr31" in ini and f"FfxDx12Path={folder.resolve()}\\{backend.HELIXSR_DLL}" in ini
    record = backend.optiscaler_record(folder)
    assert record["created"] == ["fakenvapi.dll", "fakenvapi.ini"] and "launch" not in record
    backend.remove_folder(folder, payload)
    assert (exe_dir / "dxgi.dll").read_bytes() == b"MZ the game's own dxgi"
    assert not (exe_dir / backend.OPTISCALER_INI).exists() and not (exe_dir / "fakenvapi.dll").exists()


def test_optiscaler_needs_a_payload_that_has_it(tmp_path):
    payload = make_payload(tmp_path / "payload")
    game = make_game(tmp_path / "common", "Shooter", fsr=False)
    with pytest.raises(HelixError, match="1.7.0 to 1.8.1"):
        backend.install_optiscaler(backend.find_exe_folder(game), game / backend.HELIXSR_FOLDER, payload)


def test_the_payload_takes_optiscaler_from_a_1_8_release(tmp_path, release):
    (release / backend.OPTISCALER_DIR).mkdir()
    for name in ("OptiScaler.dll", "OptiScaler.ini", "fakenvapi.dll"):
        (release / backend.OPTISCALER_DIR / name).write_bytes(b"x")
    result = backend.import_payload(release, tmp_path / "payload")
    assert "optiscaler/OptiScaler.dll" in result.copied and backend.payload_status(tmp_path / "payload").optiscaler


# helixsr.ini

def test_the_ini_round_trip_keeps_comments_and_unknown_keys():
    template = backend.DEFAULT_INI_TEXT.replace("[Log]", "[Log]\nCustom = 1")
    settings = backend.parse_ini(template)
    assert settings == HelixIni()
    settings.sharpness, settings.network = 0.5, "main"
    text = backend.render_ini(settings, template)
    assert "Sharpness = 0.5" in text and "Network = main" in text and "Custom = 1" in text
    assert "; helixsr.ini - optional" in text and backend.parse_ini(text) == settings


def test_keys_new_in_1_8_are_written_only_when_set():
    text = backend.render_ini(HelixIni(), backend.DEFAULT_INI_TEXT)
    assert "Sharpener" not in text and "UseGameSlider" not in text
    assert "Sharpener = rcas" in backend.render_ini(HelixIni(sharpener="rcas"), backend.DEFAULT_INI_TEXT)


def test_a_2_0_ini_keeps_its_own_sections():
    template = ("; helixsr.ini\n[Upscaling]\nInt8 = auto\n\n[Sharpening]\nSharpener = off\nSharpness = 0.5\n\n"
                "[Log]\nEnabled = true\n")
    text = backend.render_ini(HelixIni(sharpener="rcas", sharpness=0.5), template)
    assert "Int8 = auto" in text and "Sharpener = rcas" in text and text.startswith("; helixsr.ini")


def test_validation_and_the_fields_a_version_ignores():
    assert backend.validate_ini(HelixIni()) == []
    assert "Motion limit must be above the motion threshold." in backend.validate_ini(
        HelixIni(motion_threshold=16.0, motion_limit=8.0))
    assert backend.ini_ignored_fields("2.0.0") == {"sharpening_mode", "network"}
    assert "sharpener" in backend.ini_ignored_fields("1.4.3") and backend.ini_ignored_fields("") == set()


# Deployments

def test_the_store_and_the_states(tmp_path, game, payload):
    store = DeploymentStore(tmp_path / "deployments.json")
    target = game_dll(game)
    backend.deploy(target, payload)
    dep = store.record(target, backend.MODE_REPLACE, "SomeGame", "1.2.0")
    assert DeploymentStore(store.path).items == [dep]
    assert backend.deployment_state(dep, payload) == ("ok", "In place")
    newer = make_payload(tmp_path / "newer")
    assert backend.deployment_state(dep, newer) == ("warn", backend.OLDER) and backend.needs_update(dep, newer)
    (target.parent / backend.INI).write_text("; mine\n", encoding="utf-8")
    backend.update_deployment(dep, newer)
    assert backend.deployment_state(dep, newer) == ("ok", "In place")
    assert (target.parent / backend.INI).read_text() == "; mine\n"
    store.forget(target)
    assert DeploymentStore(store.path).items == []
    gone = Deployment(str(tmp_path / "nowhere" / backend.UPSCALER_DLL), backend.MODE_REPLACE, "Gone")
    assert backend.deployment_state(gone, payload) == ("bad", "Folder gone")


def test_the_store_survives_a_broken_file(tmp_path):
    (tmp_path / "deployments.json").write_text("{broken", encoding="utf-8")
    assert DeploymentStore(tmp_path / "deployments.json").items == []
    (tmp_path / "deployments.json").write_text(json.dumps({"deployments": [{"path": "x"}]}), encoding="utf-8")
    assert DeploymentStore(tmp_path / "deployments.json").items == []


# Steam on Windows

def test_steams_libraries_from_libraryfolders_vdf(tmp_path):
    steam = make_steam(tmp_path, {"Alpha": True, "Proton 9.0": False})
    other = tmp_path / "SD" / "SteamLibrary"
    make_game(other / "steamapps" / "common", "Beta")
    escaped = str(other).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{escaped}"\n\t}}\n}}\n', encoding="utf-8")
    libraries = backend.steam_libraries(steam)
    assert libraries == [(steam / "steamapps").resolve(), (other / "steamapps").resolve()]
    games = backend.steam_games(libraries)
    assert [g.name for g in games] == ["Alpha", "Beta", "Proton 9.0"]
    assert [g.name for g in games if not backend.is_steam_tool(g)] == ["Alpha", "Beta"]
    ids = backend.steam_app_ids(libraries)
    assert ids[(steam / "steamapps").resolve() / "common" / "Alpha"] == "1000"
    assert backend.steam_libraries(None) == []


def test_a_running_game_and_its_steam_address():
    assert backend.game_running("1000", lambda: "1000") and not backend.game_running("1000", lambda: "")
    assert not backend.game_running("", lambda: "")
    assert backend.play_url("1000") == "steam://rungameid/1000"


def test_the_game_name_inside_and_outside_a_library(tmp_path, game):
    library = tmp_path / "steamapps"
    assert backend.game_name(game_dll(game), [library]) == "SomeGame"
    assert backend.game_name(game_dll(game)) == "FSR3"


def test_targets_prefer_the_upscaler_dll_per_folder(tmp_path, payload):
    game = make_game(tmp_path / "common", "Twin")
    folder = game_dll(game).parent
    (folder / backend.HELIXSR_DLL).write_bytes(b"MZ amd ffx")
    scan = backend.scan_game(game, payload, "7")
    assert [d.path.name for d in scan.targets()] == [backend.UPSCALER_DLL]
    assert scan.state() == ("info", "Not installed")
    assert backend.scan_game(make_game(tmp_path / "common", "Plain", fsr=False), payload).state()[0] == "neutral"
