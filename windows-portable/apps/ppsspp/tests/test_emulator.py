# SPDX-License-Identifier: GPL-3.0-or-later
"""The PPSSPP the app installs (emulator.py): the download checked against the pin, the unpacking of the zip,
portable mode (no installed.txt, the memory stick in its folder), the record, Remove keeping what the player made,
and the launch line Steam's shortcuts use. The real download only with WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from ppsspp_manager import emulator


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


RELEASE = {emulator.EXE: b"ppsspp program", "assets/ppge_atlas.zim": b"zim", "assets/lang/en_US.ini": b"[x]",
           "InfoLog.bat": b"@echo off"}


def install(home: Path, data: bytes, **kwargs) -> str:
    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data)
        progress(len(data))
    return emulator.install(home, download=download, expected=hashlib.sha256(data).hexdigest(), **kwargs)


def test_the_pin():
    assert emulator.URL == ("https://github.com/hrydgard/ppsspp/releases/download/v1.20.4/"
                            "PPSSPP-v1.20.4-Windows-x64.zip")
    assert len(emulator.SHA256) == 64 and emulator.SIZE == 20_390_334 and emulator.EXE == "PPSSPPWindows64.exe"


def test_install_in_portable_mode_and_its_record(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert emulator.installed(home) == emulator.VERSION and (home / "assets" / "lang" / "en_US.ini").is_file()
    assert emulator.memstick(home).is_dir() and not (home / emulator.PORTABLE_OFF).exists()
    assert sorted(emulator.record(home)["files"]) == sorted(RELEASE)
    assert not list(tmp_path.glob("*.part"))


def test_an_installed_txt_would_move_the_memory_stick_and_goes(tmp_path):
    home = tmp_path / "emulator"
    home.mkdir()
    (home / emulator.PORTABLE_OFF).write_text("")
    install(home, zip_bytes({**RELEASE, emulator.PORTABLE_OFF: b""}))
    assert not (home / emulator.PORTABLE_OFF).exists()


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
    with pytest.raises(emulator.EmulatorError, match="has no PPSSPPWindows64.exe"):
        install(tmp_path / "c", zip_bytes({"assets/x": b"x"}))


def test_remove_keeps_the_memory_stick(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    for made in ("memstick/PSP/SAVEDATA/ULUS10041/DATA.BIN", "memstick/PSP/SYSTEM/ppsspp.ini"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists() and not (home / "assets").exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "memstick/PSP/SAVEDATA/ULUS10041/DATA.BIN", "memstick/PSP/SYSTEM/ppsspp.ini"]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


def test_a_newer_ppsspp_is_unpacked_over_the_older(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    (home / "memstick" / "PSP").mkdir(parents=True)
    (home / "memstick" / "PSP" / "save").write_bytes(b"mine")
    install(home, zip_bytes({**RELEASE, emulator.EXE: b"a newer program"}))
    assert emulator.program(home).read_bytes() == b"a newer program"
    assert (home / "memstick" / "PSP" / "save").read_bytes() == b"mine"


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 20 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_release(tmp_path):
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).is_file() and (home / "assets").is_dir() and emulator.memstick(home).is_dir()


def test_running_looks_for_this_folders_ppsspp(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no PPSSPPWindows64.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
