# SPDX-License-Identifier: GPL-3.0-or-later
"""The RPCS3 the app installs (emulator.py): the pin (the BC250 suite's build, its Windows archive), the download
checked against the pin, the unpacking with Windows' tar (stood in for, and the real one where it is), the record,
Remove keeping what RPCS3 and the player made, the runtime check and the launch line Steam's shortcuts use. The real
download only with WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from rpcs3_manager import emulator

RELEASE = {emulator.EXE: b"rpcs3 program", "GuiConfigs/Envy.qss": b"qss", "config/games.yml": b"",
           "Qt6Core.dll": b"qt"}


def fake_extract(archive: Path, folder: Path) -> list[str]:
    """Stands in for Windows' tar: the archive here is a zip of RELEASE."""
    with zipfile.ZipFile(archive) as zf:
        names = [info.filename for info in zf.infolist() if not info.is_dir()]
        emulator._check_names(names)
        zf.extractall(folder)
    return names


def zip_bytes(files: dict[str, bytes]) -> bytes:
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def install(home: Path, data: bytes, **kwargs) -> str:
    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data)
        progress(len(data))
    kwargs.setdefault("extract", fake_extract)
    kwargs.setdefault("unpacks", lambda: "")
    return emulator.install(home, download=download, expected=hashlib.sha256(data).hexdigest(), **kwargs)


def test_the_pin():
    """The same build as the BC250 suite's RPCS3 Manager pins, its Windows archive on RPCS3's builds repository."""
    assert emulator.VERSION == f"{emulator.LANDMARK}-{emulator.BUILD}" == "0.0.43-20395"
    assert emulator.ASSET == f"rpcs3-v{emulator.VERSION}-{emulator.COMMIT[:8]}_win64_msvc.7z"
    assert emulator.URL == (f"https://github.com/RPCS3/rpcs3-binaries-win/releases/download/build-{emulator.COMMIT}/"
                            f"{emulator.ASSET}")
    assert emulator.TAG == "v0.0.43" and emulator.REPO == "RPCS3/rpcs3" and len(emulator.SHA256) == 64
    assert emulator.SIZE == 36_964_258 and emulator.EXE == "rpcs3.exe"
    assert emulator.GAME_ARGS == ("--no-gui", "--fullscreen")
    bc250 = Path(__file__).resolve().parents[4] / "bc250-bazzite" / "apps" / "rpcs3" / "rpcs3_manager" / "emulator.py"
    if bc250.is_file():                                             # the same commit as the BC250 suite's pin
        assert f'COMMIT = "{emulator.COMMIT}"' in bc250.read_text(encoding="utf-8")


def test_install_and_its_record(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert emulator.installed(home) == emulator.VERSION and (home / "GuiConfigs" / "Envy.qss").is_file()
    assert sorted(emulator.record(home)["files"]) == sorted(RELEASE)
    assert not list(tmp_path.glob("*.part"))


def test_nothing_is_downloaded_when_tar_cannot_unpack(tmp_path):
    downloads = []

    def download(url: str, dest: Path, progress) -> None:
        downloads.append(url)
    with pytest.raises(emulator.EmulatorError, match="cannot unpack"):
        emulator.install(tmp_path / "emulator", download=download,
                         unpacks=lambda: "The tar of this Windows cannot unpack RPCS3's archive")
    assert downloads == []


def test_a_download_that_is_not_the_pinned_build_is_refused(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"

    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data + b"changed")
    with pytest.raises(emulator.EmulatorError, match="SHA-256 differs"):
        emulator.install(home, download=download, expected=hashlib.sha256(data).hexdigest(), extract=fake_extract,
                         unpacks=lambda: "")
    assert emulator.installed(home) == "" and not list(tmp_path.glob("*.part"))


def test_a_failed_download_says_why(tmp_path):
    def offline(url: str, dest: Path, progress) -> None:
        raise OSError("getaddrinfo failed")
    with pytest.raises(emulator.EmulatorError, match="getaddrinfo failed"):
        emulator.install(tmp_path / "emulator", download=offline, unpacks=lambda: "")


def test_an_archive_that_leaves_its_folder_or_has_no_program_is_refused(tmp_path):
    with pytest.raises(emulator.EmulatorError, match="outside its folder"):
        install(tmp_path / "b", zip_bytes({**RELEASE, "../evil.txt": b"x"}))
    assert not (tmp_path / "evil.txt").exists() and emulator.installed(tmp_path / "b") == ""
    with pytest.raises(emulator.EmulatorError, match="has no rpcs3.exe"):
        install(tmp_path / "c", zip_bytes({"Qt6Core.dll": b"x"}))


def test_remove_keeps_rpcs3s_own_files(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    for made in ("dev_hdd0/home/00000001/savedata/BLUS30443-S01/PARAM.SFO", "dev_flash/vsh/etc/version.txt",
                 "config/config.yml", "GuiConfigs/CurrentSettings.ini", "log/RPCS3.log"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists()
    assert not (home / "Qt6Core.dll").exists() and not (home / "GuiConfigs" / "Envy.qss").exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "GuiConfigs/CurrentSettings.ini", "config/config.yml", "dev_flash/vsh/etc/version.txt",
        "dev_hdd0/home/00000001/savedata/BLUS30443-S01/PARAM.SFO", "log/RPCS3.log"]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


def test_a_newer_rpcs3_is_unpacked_over_the_older(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    (home / "dev_hdd0").mkdir()
    (home / "dev_hdd0" / "save").write_bytes(b"mine")
    install(home, zip_bytes({**RELEASE, emulator.EXE: b"a newer program"}))
    assert emulator.program(home).read_bytes() == b"a newer program"
    assert (home / "dev_hdd0" / "save").read_bytes() == b"mine"


def test_the_runtime_check(tmp_path):
    system32 = tmp_path / "System32"
    system32.mkdir()
    assert emulator.runtime_missing(system32) == list(emulator.RUNTIME_DLLS)
    for name in emulator.RUNTIME_DLLS:
        (system32 / name).write_bytes(b"")
    assert emulator.runtime_missing(system32) == []
    (system32 / "vcruntime140_1.dll").unlink()
    assert emulator.runtime_missing(system32) == ["vcruntime140_1.dll"]


def test_the_command_line(tmp_path):
    assert emulator.command(tmp_path, "--headless", "--installfw", "x.pup") == [str(tmp_path / "rpcs3.exe"),
                                                                                "--headless", "--installfw", "x.pup"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' tar")
def test_windows_tar_can_unpack_a_7z():
    """The tar of this Windows (System32\\tar.exe) was built with liblzma, so it unpacks RPCS3's archive; the message
    says so when it was not."""
    assert emulator.TAR.is_file()
    reason = emulator.tar_unpacks_7z()
    assert reason == "" or "cannot unpack" in reason


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 37 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_build(tmp_path):
    """The pinned archive from GitHub, checked and unpacked with Windows' tar: the program, its Qt and its folders."""
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).is_file() and (home / "GuiConfigs").is_dir() and (home / "Qt6Core.dll").is_file()
    files = emulator.record(home)["files"]
    assert emulator.EXE in files and len(files) > 200 and not any(name.endswith("/") for name in files)


def test_running_looks_for_this_folders_rpcs3(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no rpcs3.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
