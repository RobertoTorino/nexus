# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xenia the app installs (emulator.py), as Vita3K Manager's is tested: the pin (the BC250 suite's build, its
Windows archive), the download checked against the pin, the unpacking with Windows' tar (stood in for, and the real
one where it is), the record, Remove keeping what Xenia and the player made, the runtime check, the newest build on
GitHub (by the time it was published: a tag is a commit) and the launch line Steam's shortcuts use. The real download
only with WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

from xenia_manager import emulator

RELEASE = {emulator.EXE: b"xenia program", "LICENSE": b"BSD"}


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
    """The same build as the BC250 suite's Xenia Manager pins, its Windows archive in the same release."""
    assert emulator.VERSION == emulator.TAG == "e6cd2e4" and emulator.COMMIT.startswith(emulator.VERSION)
    assert emulator.ASSET == "xenia_canary_windows.7z" and emulator.REPO == "xenia-canary/xenia-canary"
    assert emulator.URL == f"https://github.com/xenia-canary/xenia-canary/releases/download/e6cd2e4/{emulator.ASSET}"
    assert emulator.CADENCE == "daily" and len(emulator.SHA256) == 64 and emulator.SIZE == 3_677_214
    assert emulator.EXE == "xenia_canary.exe" and emulator.GAME_ARGS == ("--fullscreen=true",)
    bc250 = Path(__file__).resolve().parents[4] / "bc250-bazzite" / "apps" / "xenia" / "xenia_manager" / "emulator.py"
    if bc250.is_file():                                             # the same build as the BC250 suite's pin
        text = bc250.read_text(encoding="utf-8")
        assert f'COMMIT = "{emulator.COMMIT}"' in text and f'PUBLISHED = "{emulator.PUBLISHED}"' in text


def test_install_and_its_record(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert emulator.installed(home) == emulator.VERSION and (home / "LICENSE").is_file()
    assert sorted(emulator.record(home)["files"]) == sorted(RELEASE)
    assert not list(tmp_path.glob("*.part"))


def test_nothing_is_downloaded_when_tar_cannot_unpack(tmp_path):
    downloads = []

    def download(url: str, dest: Path, progress) -> None:
        downloads.append(url)
    with pytest.raises(emulator.EmulatorError, match="cannot unpack"):
        emulator.install(tmp_path / "emulator", download=download,
                         unpacks=lambda: "The tar of this Windows cannot unpack Xenia's archive")
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
    with pytest.raises(emulator.EmulatorError, match="has no xenia_canary.exe"):
        install(tmp_path / "c", zip_bytes({"LICENSE": b"x"}))


def test_remove_keeps_xenias_own_files(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    for made in (emulator.CONFIG, emulator.LOG, "content/0000000000000000/4D5307E6/00000001/save.bin",
                 "cache_host/shaders/x.bin"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists() and not (home / "LICENSE").exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "cache_host/shaders/x.bin", "content/0000000000000000/4D5307E6/00000001/save.bin", emulator.CONFIG,
        emulator.LOG]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


def test_a_newer_xenia_is_unpacked_over_the_older(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    (home / emulator.CONFIG).write_text("[GPU]\ngpu = 'vulkan'\n", encoding="utf-8")
    install(home, zip_bytes({**RELEASE, emulator.EXE: b"a newer program"}))
    assert emulator.program(home).read_bytes() == b"a newer program"
    assert "vulkan" in (home / emulator.CONFIG).read_text(encoding="utf-8")


def test_the_runtime_check(tmp_path):
    system32 = tmp_path / "System32"
    system32.mkdir()
    assert emulator.runtime_missing(system32) == list(emulator.RUNTIME_DLLS)
    for name in emulator.RUNTIME_DLLS:
        (system32 / name).write_bytes(b"")
    assert emulator.runtime_missing(system32) == []
    (system32 / "msvcp140_atomic_wait.dll").unlink()
    assert emulator.runtime_missing(system32) == ["msvcp140_atomic_wait.dll"]


def test_a_newer_build_on_github():
    """A tag is a commit: a release published after the pinned one is newer; the pinned one, an older one, or GitHub
    not answering is nothing to say."""
    def answer(tag, published):
        return lambda url: {"tag_name": tag, "html_url": f"https://github.com/x/{tag}", "published_at": published}
    newer = emulator.newer_release(answer("48b318a", "2026-10-27T18:08:48Z"))
    assert (newer.version, newer.url, newer.published) == ("48b318a", "https://github.com/x/48b318a", "2026-10-27")
    assert emulator.newer_release(answer("e6cd2e4", "2026-10-30T00:00:00Z")) is None
    assert emulator.newer_release(answer("f42147a", "2026-10-19T00:00:00Z")) is None

    def offline(url):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None
    assert emulator.newer_release(lambda url: []) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' tar")
def test_windows_tar_can_unpack_a_7z():
    assert emulator.TAR.is_file()
    reason = emulator.tar_unpacks_7z()
    assert reason == "" or "cannot unpack" in reason


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 4 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_build(tmp_path):
    """The pinned archive from GitHub, checked and unpacked with Windows' tar: the program and its license."""
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).is_file() and sorted(emulator.record(home)["files"]) == ["LICENSE", emulator.EXE]


def test_running_looks_for_this_folders_xenia(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no xenia_canary.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
