# SPDX-License-Identifier: GPL-3.0-or-later
"""The Vita3K the app installs (emulator.py), as RPCS3 Manager's is tested: the pin (the BC250 suite's build, its
Windows archive), the download checked against the pin, the unpacking with Windows' tar (stood in for, and the real
one where it is), the portable folder and the record, Remove keeping what Vita3K and the player made, the runtime
check, the newest build on GitHub, Vita3K's installs (stood in for: the program is never started here) and the launch
line Steam's shortcuts use. The real download only with WPS_LIVE_DOWNLOAD=1."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

from vita3k_manager import emulator

RELEASE = {emulator.EXE: b"vita3k program", "data/fonts/a.otf": b"font", "shaders-builtin/x.spv": b"spv",
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
    """The same build as the BC250 suite's Vita3K Manager pins, its Windows archive on Vita3K's builds repository."""
    assert emulator.VERSION == emulator.TAG == "4186" and emulator.SEMVER == "0.2.1"
    assert emulator.ASSET == f"vita3k-{emulator.VERSION}-{emulator.COMMIT[:8]}-windows-x86_64.7z"
    assert emulator.URL == f"https://github.com/Vita3K/Vita3K-builds/releases/download/4186/{emulator.ASSET}"
    assert emulator.REPO == "Vita3K/Vita3K-builds" and emulator.CADENCE == "daily" and len(emulator.SHA256) == 64
    assert emulator.SIZE == 24_522_324 and emulator.EXE == "Vita3K.exe" and emulator.PORTABLE == "portable"
    assert emulator.GAME_ARGS == ("-r",)
    bc250 = Path(__file__).resolve().parents[4] / "bc250-bazzite" / "apps" / "vita3k" / "vita3k_manager" / "emulator.py"
    if bc250.is_file():                                             # the same build as the BC250 suite's pin
        text = bc250.read_text(encoding="utf-8")
        assert f'COMMIT = "{emulator.COMMIT}"' in text and f"BUILD = {emulator.VERSION}" in text


def test_install_makes_the_portable_folder_and_its_record(tmp_path):
    data = zip_bytes(RELEASE)
    home = tmp_path / "emulator"
    got, said = [], []
    assert install(home, data, progress=got.append, say=said.append) == emulator.VERSION
    assert got == [len(data)] and said == ["Checking the download…", "Unpacking…"]
    assert emulator.installed(home) == emulator.VERSION and (home / "data" / "fonts" / "a.otf").is_file()
    assert emulator.portable_folder(home).is_dir()                  # Vita3K keeps its files there, not in %APPDATA%
    assert sorted(emulator.record(home)["files"]) == sorted(RELEASE)
    assert not list(tmp_path.glob("*.part"))


def test_nothing_is_downloaded_when_tar_cannot_unpack(tmp_path):
    downloads = []

    def download(url: str, dest: Path, progress) -> None:
        downloads.append(url)
    with pytest.raises(emulator.EmulatorError, match="cannot unpack"):
        emulator.install(tmp_path / "emulator", download=download,
                         unpacks=lambda: "The tar of this Windows cannot unpack Vita3K's archive")
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
    with pytest.raises(emulator.EmulatorError, match="has no Vita3K.exe"):
        install(tmp_path / "c", zip_bytes({"Qt6Core.dll": b"x"}))


def test_remove_keeps_vita3ks_own_files(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    for made in ("portable/config.yml", "portable/vita3k.log", "portable/fs/vs0/vsh/shell/shell.self",
                 "portable/fs/ux0/app/PCSB00245/eboot.bin", "portable/fs/ux0/user/00/savedata/PCSB00245/sdslot.dat"):
        (home / made).parent.mkdir(parents=True, exist_ok=True)
        (home / made).write_bytes(b"x")
    emulator.remove(home)
    assert emulator.installed(home) == "" and not (home / emulator.EXE).exists()
    assert not (home / "Qt6Core.dll").exists() and not (home / "data").exists()
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == [
        "portable/config.yml", "portable/fs/ux0/app/PCSB00245/eboot.bin",
        "portable/fs/ux0/user/00/savedata/PCSB00245/sdslot.dat", "portable/fs/vs0/vsh/shell/shell.self",
        "portable/vita3k.log"]
    shutil.rmtree(home)
    emulator.remove(home)                                       # nothing there: nothing to do


def test_a_newer_vita3k_is_unpacked_over_the_older(tmp_path):
    home = tmp_path / "emulator"
    install(home, zip_bytes(RELEASE))
    (home / "portable" / "fs").mkdir()
    (home / "portable" / "fs" / "save").write_bytes(b"mine")
    install(home, zip_bytes({**RELEASE, emulator.EXE: b"a newer program"}))
    assert emulator.program(home).read_bytes() == b"a newer program"
    assert (home / "portable" / "fs" / "save").read_bytes() == b"mine"


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
    """The builds are tagged with their number alone; a newer one is reported, the pinned one or an older one not,
    and GitHub not answering is nothing to say."""
    def answer(tag):
        return lambda url: {"tag_name": tag, "html_url": f"https://github.com/x/{tag}",
                            "published_at": "2026-10-29T15:15:42Z"}
    newer = emulator.newer_release(answer("4242"))
    assert (newer.version, newer.url, newer.published) == ("4242", "https://github.com/x/4242", "2026-10-29")
    assert emulator.newer_release(answer("4186")) is None and emulator.newer_release(answer("4100")) is None
    assert emulator.newer_release(answer("continuous")) is None

    def offline(url):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None
    assert emulator.newer_release(lambda url: []) is None


def test_the_command_line(tmp_path):
    assert emulator.command(tmp_path, "--firmware", "x.PUP") == [str(tmp_path / "Vita3K.exe"), "--firmware", "x.PUP"]


class FakeProcess:
    """Stands in for Vita3K started with a game to install: it ends by itself after *ends* polls (None: never), and
    has a window from the *window*th look on (None: never)."""

    def __init__(self, ends=None):
        self.pid, self.polls, self.ends, self.killed, self.args = 4242, 0, ends, False, None

    def poll(self):
        self.polls += 1
        if self.killed:
            return 1
        return 0 if self.ends is not None and self.polls > self.ends else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 1


def test_a_game_install_is_closed_when_vita3ks_window_shows(tmp_path, monkeypatch):
    """Vita3K installs a .vpk and opens its window to start the game: the app closes it then (owner, 29-10-2026)."""
    monkeypatch.setattr(emulator, "WATCH_S", 0)
    process = FakeProcess()
    started = []

    def popen(command, **kwargs):
        started.append((command, kwargs["cwd"]))
        return process
    looks = []
    closed = emulator.install_content(tmp_path, Path("C:/games/Game.vpk"), popen=popen,
                                      has_window=lambda pid: looks.append(pid) or len(looks) >= 3)
    assert closed and process.killed and looks == [4242, 4242, 4242]
    assert started == [([str(tmp_path / "Vita3K.exe"), "--frontend", "sdl", str(Path("C:/games/Game.vpk"))],
                        tmp_path)]


def test_an_install_that_starts_no_game_ends_by_itself(tmp_path, monkeypatch):
    """An update or extra content starts no game: Vita3K's SDL frontend ends without a window."""
    monkeypatch.setattr(emulator, "WATCH_S", 0)
    process = FakeProcess(ends=2)
    assert emulator.install_content(tmp_path, Path("patch.vpk"), popen=lambda command, **k: process,
                                    has_window=lambda pid: False) is False
    assert not process.killed


def test_an_install_that_does_not_end_in_time(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, "WATCH_S", 0)
    process = FakeProcess()
    with pytest.raises(emulator.EmulatorError, match="did not finish installing Game.vpk"):
        emulator.install_content(tmp_path, Path("Game.vpk"), timeout=0, popen=lambda command, **k: process,
                                 has_window=lambda pid: False)
    assert process.killed


def test_no_window_of_a_process_that_is_not_there():
    assert emulator.window_shows(0) is False                    # pid 0 owns no window (off Windows: none at all)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' tar")
def test_windows_tar_can_unpack_a_7z():
    """The tar of this Windows (System32\\tar.exe) was built with liblzma, so it unpacks Vita3K's archive; the message
    says so when it was not."""
    assert emulator.TAR.is_file()
    reason = emulator.tar_unpacks_7z()
    assert reason == "" or "cannot unpack" in reason


@pytest.mark.skipif(os.environ.get("WPS_LIVE_DOWNLOAD") != "1", reason="the real 25 MB download: WPS_LIVE_DOWNLOAD=1")
def test_the_real_build(tmp_path):
    """The pinned archive from GitHub, checked and unpacked with Windows' tar: the program, its Qt and its data."""
    home = tmp_path / "emulator"
    assert emulator.install(home) == emulator.VERSION
    assert emulator.program(home).is_file() and (home / "Qt6Core.dll").is_file()
    assert (home / "shaders-builtin").is_dir() and emulator.portable_folder(home).is_dir()
    files = emulator.record(home)["files"]
    assert emulator.EXE in files and len(files) > 100 and not any(name.endswith("/") for name in files)


def test_running_looks_for_this_folders_vita3k(tmp_path, monkeypatch):
    assert emulator.running(tmp_path) is False                  # no Vita3K.exe from this folder runs
    monkeypatch.setattr(emulator.sys, "platform", "linux")
    assert emulator.running(tmp_path) is False
