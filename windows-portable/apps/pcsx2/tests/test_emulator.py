# SPDX-License-Identifier: GPL-3.0-or-later
"""The PCSX2 the app installs (emulator.py): the download checked against the pin, the unpacking with Windows'
tar.exe, portable mode, the record, a build PCSX2 put in place itself, and Remove keeping what the player made. The
real download only with WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from pcsx2_manager import emulator

TAR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"


def fake_release(tmp_path: Path) -> tuple[bytes, emulator.Extract]:
    """A stand-in archive (a zip: the unpacking is tested on its own below) and an extract that unpacks it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(emulator.EXE, b"pcsx2 program")
        zf.writestr("resources/fullscreenui/applications-system.svg", b"<svg/>")
        zf.writestr("Qt6Core.dll", b"qt")

    def extract(archive: Path, folder: Path) -> list[str]:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(folder)
            return zf.namelist()
    return buffer.getvalue(), extract


def install(home: Path, data: bytes, extract, **kwargs) -> str:
    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data)
        progress(len(data))
    return emulator.install(home, download=download, extract=extract, expected=hashlib.sha256(data).hexdigest(),
                            **kwargs)


def test_the_pin():
    assert emulator.URL == ("https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/"
                            "pcsx2-v2.8.2-windows-x64-Qt.7z")
    assert len(emulator.SHA256) == 64 and emulator.SIZE == 25_670_075


def test_install_in_portable_mode_and_its_record(tmp_path):
    data, extract = fake_release(tmp_path)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, extract, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert (home / emulator.MARKER).is_file() and emulator.installed(home) == emulator.VERSION
    record = emulator.record(home)
    assert record["exe_size"] == len(b"pcsx2 program") and emulator.EXE in record["files"]
    assert not list(tmp_path.glob("*.part")) and not emulator.replaced(home)


def test_a_download_that_is_not_the_pinned_release_is_refused(tmp_path):
    data, extract = fake_release(tmp_path)
    home = tmp_path / "emulator"

    def download(url: str, dest: Path, progress) -> None:
        dest.write_bytes(data + b"changed")
    with pytest.raises(emulator.EmulatorError, match="SHA-256 differs"):
        emulator.install(home, download=download, extract=extract, expected=hashlib.sha256(data).hexdigest())
    assert emulator.installed(home) == "" and not list(tmp_path.glob("*.part"))


def test_a_failed_download_says_why(tmp_path):
    def offline(url: str, dest: Path, progress) -> None:
        raise OSError("getaddrinfo failed")
    with pytest.raises(emulator.EmulatorError, match="getaddrinfo failed"):
        emulator.install(tmp_path / "emulator", download=offline)


def test_pcsx2_replacing_itself_and_reinstall_putting_the_pin_back(tmp_path):
    data, extract = fake_release(tmp_path)
    home = tmp_path / "emulator"
    install(home, data, extract)
    emulator.program(home).write_bytes(b"a newer build from PCSX2's own updater")
    assert emulator.replaced(home)
    install(home, data, extract)
    assert not emulator.replaced(home)


def test_remove_keeps_what_the_player_made(tmp_path):
    data, extract = fake_release(tmp_path)
    home = tmp_path / "emulator"
    install(home, data, extract)
    for made in ("bios/scph39001.bin", "memcards/Mcd001.ps2", "inis/PCSX2.ini"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists()
    assert not (home / "resources").exists() and not (home / emulator.MARKER).exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "bios/scph39001.bin", "inis/PCSX2.ini", "memcards/Mcd001.ps2"]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


@pytest.mark.skipif(sys.platform != "win32" or not TAR.is_file(), reason="Windows' tar.exe (bsdtar) unpacks the 7z")
def test_tar_unpacks_a_7z(tmp_path):
    src = tmp_path / "src"
    (src / "resources").mkdir(parents=True)
    (src / emulator.EXE).write_bytes(b"pcsx2")
    (src / "resources" / "a.svg").write_bytes(b"<svg/>")
    archive = tmp_path / "t.7z"
    subprocess.run([str(TAR), "--format", "7zip", "-cf", str(archive), emulator.EXE, "resources"], cwd=src, check=True)
    target = tmp_path / "out"
    target.mkdir()
    assert sorted(emulator.tar_extract(archive, target)) == [emulator.EXE, "resources/a.svg"]
    assert (target / "resources" / "a.svg").read_bytes() == b"<svg/>"


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 26 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_release(tmp_path):
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).is_file() and (home / emulator.MARKER).is_file()


def test_running_looks_for_this_folders_pcsx2(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no pcsx2-qt.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
