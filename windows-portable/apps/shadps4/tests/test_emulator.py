# SPDX-License-Identifier: GPL-3.0-or-later
"""The shadPS4 the app installs (emulator.py), as PPSSPP Manager's is tested: the download checked against the pin,
the unpacking of the zip, shadPS4's portable folder (user\\ beside its program), the record, Remove keeping what the
player made, the Visual C++ runtime, and the launch line Steam's shortcuts use. The real download only with
WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from shadps4_manager import emulator


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


RELEASE = {emulator.EXE: b"shadps4 program"}            # the release's zip holds shadPS4.exe alone


def install(home: Path, data: bytes, **kwargs) -> str:
    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data)
        progress(len(data))
    return emulator.install(home, download=download, expected=hashlib.sha256(data).hexdigest(), **kwargs)


def test_the_pin():
    """shadPS4's newest stable release (0.21.0), its Windows build; GitHub's digest of the file."""
    assert emulator.URL == ("https://github.com/shadps4-emu/shadPS4/releases/download/v.0.21.0/"
                            "shadps4-win64-sdl-0.21.0.zip")
    assert emulator.SHA256 == "95295b8f109663f70c2dac685e6232aa97be1353f6ed0a5d5e0c5dd24a797d88"
    assert emulator.SIZE == 31_725_856 and emulator.EXE == "shadPS4.exe"


def test_install_with_its_portable_folder_and_its_record(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert emulator.installed(home) == emulator.VERSION and emulator.user_folder(home) == home / "user"
    assert emulator.user_folder(home).is_dir()          # shadPS4 keeps its files there, not in %APPDATA%\shadPS4
    assert emulator.record(home)["files"] == [emulator.EXE] and not list(tmp_path.glob("*.part"))


def test_a_download_that_is_not_the_pinned_release_is_refused(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"

    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data + b"changed")
    with pytest.raises(emulator.EmulatorError, match="SHA-256 differs"):
        emulator.install(home, download=download, expected=hashlib.sha256(data).hexdigest())
    assert emulator.installed(home) == "" and not list(tmp_path.glob("*.part"))


def test_a_failed_download_says_why(tmp_path):
    def offline(url: str, dest: Path, progress) -> None:
        raise OSError("getaddrinfo failed")
    with pytest.raises(emulator.EmulatorError, match="getaddrinfo failed"):
        emulator.install(tmp_path / "emulator", download=offline)


def test_an_archive_that_is_no_zip_or_leaves_its_folder_is_refused(tmp_path):
    with pytest.raises(emulator.EmulatorError, match="could not be read"):
        install(tmp_path / "a", b"not a zip at all")
    with pytest.raises(emulator.EmulatorError, match="outside its folder"):
        install(tmp_path / "b", zip_bytes({**RELEASE, "../evil.txt": b"x"}))
    assert not (tmp_path / "evil.txt").exists() and emulator.installed(tmp_path / "b") == ""
    with pytest.raises(emulator.EmulatorError, match="has no shadPS4.exe"):
        install(tmp_path / "c", zip_bytes({"readme.txt": b"x"}))


def test_remove_keeps_shadps4s_folder(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    for made in ("user/config.json", "user/home/1000/savedata/CUSA00001/SAVEDATA00/sce_sys/param.sfo",
                 "user/sys_modules/libSceUlt.sprx"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists() and not (home / emulator.RECORD).exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "user/config.json", "user/home/1000/savedata/CUSA00001/SAVEDATA00/sce_sys/param.sfo",
        "user/sys_modules/libSceUlt.sprx"]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


def test_a_newer_shadps4_replaces_the_program_only(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    (home / "user" / "config.json").write_bytes(b"mine")
    install(home, zip_bytes({emulator.EXE: b"a newer program"}))
    assert emulator.program(home).read_bytes() == b"a newer program"
    assert (home / "user" / "config.json").read_bytes() == b"mine"


def test_the_visual_c_runtime(tmp_path, monkeypatch):
    """shadPS4.exe imports vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll and msvcp140_atomic_wait.dll."""
    system32 = tmp_path / "System32"
    system32.mkdir()
    assert emulator.runtime_missing(system32) == list(emulator.RUNTIME_DLLS)
    for name in emulator.RUNTIME_DLLS[:3]:
        (system32 / name).write_bytes(b"")
    assert emulator.runtime_missing(system32) == ["msvcp140_atomic_wait.dll"]
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.runtime_missing() == []


def test_the_launch_line_is_the_bc250_apps():
    assert emulator.GAME_ARGS == ("-f", "true", "-g")


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 32 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_release(tmp_path):
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).stat().st_size > 10_000_000 and emulator.user_folder(home).is_dir()


def test_running_looks_for_this_folders_shadps4(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no shadPS4.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
