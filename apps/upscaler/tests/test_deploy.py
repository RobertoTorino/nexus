# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from upscaler import backend
from tests.conftest import FAKE_DLL, FAKE_GAME_DLL


def dll_of(game: Path) -> Path:
    return game / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64" / backend.UPSCALER_DLL


def test_find_game_dlls(game, payload):
    found = backend.find_game_dlls(game, payload)
    assert [g.path for g in found] == [dll_of(game)]
    assert found[0].state == "Game's own DLL" and not found[0].deployed
    assert backend.find_game_dlls(game, payload, max_depth=2) == []


def test_deploy_and_remove_round_trip(game, payload):
    target = dll_of(game)
    written = backend.deploy(target, payload, ini_text="[Log]\nEnabled = false\n")
    assert target in written
    assert target.read_bytes() == FAKE_DLL
    assert backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    folder = target.parent
    assert (folder / backend.WEIGHTS).is_file() and (folder / backend.KERNELS).is_file()
    assert (folder / backend.INI).read_text() == "[Log]\nEnabled = false\n"

    info = backend.find_game_dlls(game, payload)[0]
    assert info.deployed and info.state == "HelixSR deployed" and info.network_files and info.ini
    assert backend.deployment_state(backend.Deployment(str(target), backend.MODE_REPLACE, "g", "1.2.0"), payload)[0] == "ok"

    (folder / backend.LOG).write_text("log")
    backend.remove(target, payload)
    assert target.read_bytes() == FAKE_GAME_DLL
    assert not backup_exists(target)
    for name in (*backend.NETWORK_FILES, backend.INI, backend.LOG):
        assert not (folder / name).exists()


def backup_exists(target: Path) -> bool:
    return backend.original_path(target).exists()


def test_redeploy_keeps_real_original(game, payload):
    target = dll_of(game)
    backend.deploy(target, payload)
    (payload / backend.HELIXSR_DLL).write_bytes(b"MZ-newer-build")
    backend.deploy(target, payload)
    assert target.read_bytes() == b"MZ-newer-build"
    assert backend.original_path(target).read_bytes() == FAKE_GAME_DLL
    backend.remove(target, payload)
    assert target.read_bytes() == FAKE_GAME_DLL


def test_deploy_copies_payload_ini_when_none_given(game, payload):
    target = dll_of(game)
    backend.deploy(target, payload)
    assert (target.parent / backend.INI).read_text(encoding="utf-8") == backend.DEFAULT_INI_TEXT


def test_deploy_errors(game, payload, tmp_path):
    with pytest.raises(backend.HelixError):
        backend.deploy(game / "SomeGame.exe", payload)
    with pytest.raises(backend.HelixError):
        backend.deploy(game / "Win64" / backend.UPSCALER_DLL, payload)
    (payload / backend.WEIGHTS).unlink()
    with pytest.raises(backend.HelixError, match="incomplete"):
        backend.deploy(dll_of(game), payload)


def test_remove_refuses_foreign_dll(game, payload):
    target = dll_of(game)
    with pytest.raises(backend.HelixError):
        backend.remove(target, payload)
    assert target.read_bytes() == FAKE_GAME_DLL


def test_folder_mode(payload, tmp_path):
    folder = tmp_path / "HelixSR"
    written = backend.deploy_folder(folder, payload)
    names = {p.name for p in written}
    assert names == {*backend.GAME_DLLS, *backend.NETWORK_FILES, backend.INI}
    assert (folder / backend.UPSCALER_DLL).read_bytes() == FAKE_DLL
    dep = backend.Deployment(str(folder), backend.MODE_FOLDER, "", "1.2.0")
    assert dep.folder == folder and backend.deployment_state(dep, payload)[0] == "ok"

    snippet = backend.optiscaler_snippet(folder)
    assert "Dx12Upscaler=fsr31" in snippet
    assert f"FfxDx12Path=Z:{str(folder).replace('/', chr(92))}\\{backend.HELIXSR_DLL}" in snippet

    backend.remove_folder(folder, payload)
    assert not folder.exists()


def test_remove_folder_refuses_replaced_game_dll(game, payload):
    target = dll_of(game)
    backend.deploy(target, payload)
    with pytest.raises(backend.HelixError):
        backend.remove_folder(target.parent, payload)
    assert target.exists() and backend.original_path(target).exists()


def test_deployment_state_detects_problems(game, payload, tmp_path):
    target = dll_of(game)
    dep = backend.Deployment(str(target), backend.MODE_REPLACE, "g", "1.2.0")
    assert backend.deployment_state(dep, payload)[0] != "ok"      # not deployed yet
    backend.deploy(target, payload)
    (target.parent / backend.WEIGHTS).unlink()
    kind, text = backend.deployment_state(dep, payload)
    assert kind == "warn" and "Network" in text
    gone = backend.Deployment(str(tmp_path / "gone" / backend.UPSCALER_DLL), backend.MODE_REPLACE, "g", "1")
    assert backend.deployment_state(gone, payload)[0] != "ok"


def test_folder_mode_with_a_second_upscaler(payload, tmp_path):
    folder = tmp_path / "HelixSR"
    fsr4 = tmp_path / "downloads" / "amd_fidelityfx_upscaler_dx12.dll"
    fsr4.parent.mkdir()
    fsr4.write_bytes(b"MZ-amd-fsr4")
    written = backend.deploy_folder(folder, payload, second_upscaler=fsr4)
    assert folder / backend.SECOND_UPSCALER_DLL in written
    assert (folder / backend.SECOND_UPSCALER_DLL).read_bytes() == b"MZ-amd-fsr4"
    ini = (folder / backend.INI).read_text()
    assert backend.parse_ini(ini).upscaler_dll == backend.SECOND_UPSCALER_DLL
    assert "; Optional: another FidelityFX upscaler DLL" in ini or "[Forwarding]" in ini    # comments kept

    # Deploying again without it removes the DLL and clears the ini key that named it.
    backend.deploy_folder(folder, payload, ini_text=ini)
    assert not (folder / backend.SECOND_UPSCALER_DLL).exists()
    assert backend.parse_ini((folder / backend.INI).read_text()).upscaler_dll == ""

    backend.deploy_folder(folder, payload, second_upscaler=fsr4)
    backend.remove_folder(folder, payload)
    assert not folder.exists()


def test_second_upscaler_must_not_be_helixsr(payload, tmp_path):
    with pytest.raises(backend.HelixError):
        backend.deploy_folder(tmp_path / "HelixSR", payload, second_upscaler=payload / backend.HELIXSR_DLL)
    with pytest.raises(backend.HelixError):
        backend.deploy_folder(tmp_path / "HelixSR", payload, second_upscaler=tmp_path / "missing.dll")
    assert not (tmp_path / "HelixSR").exists()                    # refused before anything was written


def test_deployment_state_after_switching_versions(game, payload, tmp_path):
    """A payload replaced by another release: deployments of an older one are older, of a newer one newer."""
    target = dll_of(game)
    backend.deploy(target, payload)
    folder = tmp_path / "opti" / "HelixSR"
    backend.deploy_folder(folder, payload)
    replaced = backend.Deployment(str(target), backend.MODE_REPLACE, "g", helixsr_version="1.7.0")
    standalone = backend.Deployment(str(folder), backend.MODE_FOLDER, "g", helixsr_version="1.7.0")
    assert backend.deployment_state(replaced, payload) == ("ok", "In place")
    assert backend.deployment_state(standalone, payload) == ("ok", "In place")
    (payload / backend.HELIXSR_DLL).write_bytes(b"MZ-helixsr-1.4.3")
    (payload / "README.md").write_text("**Version 1.4.3** - fallback\n", encoding="utf-8")
    assert backend.deployment_state(replaced, payload) == ("warn", "Newer build")
    assert backend.deployment_state(standalone, payload) == ("warn", "Newer build")
    replaced.helixsr_version = standalone.helixsr_version = "1.2.0"
    assert backend.deployment_state(replaced, payload) == ("warn", "Older build")
    assert backend.deployment_state(standalone, payload) == ("warn", "Older build")


def test_one_file_dll(game, payload, tmp_path):
    """HelixSR 1.8+: the network is inside the DLL, so no network files go along, and stale ones are removed."""
    from tests.conftest import embedded_dll
    release = tmp_path / "HelixSR-1.8.0"
    release.mkdir()
    (release / backend.HELIXSR_DLL).write_bytes(embedded_dll())
    result = backend.import_payload(release, payload)
    status = backend.payload_status(payload)
    assert result.missing == [] and status.ready and status.embedded and status.missing() == []
    assert not (payload / backend.WEIGHTS).exists() and not (payload / backend.KERNELS).exists()   # 1.2.0's are gone
    target = dll_of(game)
    (target.parent / backend.WEIGHTS).write_bytes(b"old weights")
    written = backend.deploy(target, payload)
    assert backend.network_embedded(target) and not (target.parent / backend.WEIGHTS).exists()
    assert not any(p.name in backend.NETWORK_FILES for p in written)
    assert backend.inspect_dll(target, payload).network_files
    dep = backend.Deployment(str(target), backend.MODE_REPLACE, "g", helixsr_version="1.8.0")
    assert backend.deployment_state(dep, payload) == ("ok", "In place")
    folder = tmp_path / "opti" / "HelixSR"
    backend.deploy_folder(folder, payload)
    standalone = backend.Deployment(str(folder), backend.MODE_FOLDER, "g", helixsr_version="1.8.0")
    assert backend.deployment_state(standalone, payload) == ("ok", "In place")
    (payload / backend.HELIXSR_DLL).write_bytes(embedded_dll(b"MZ-helixsr-1.8.1"))  # the payload moved on
    backend.remove_folder(folder, payload)                                       # still recognized as HelixSR
    assert not folder.exists()
