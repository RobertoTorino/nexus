# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing the pinned Vita3K build (emulator.py) from a file made here instead of the download: checked against
its SHA-256 first, "current" switched, older builds removed, and nothing changed when a step fails; the newest build
on GitHub read from its tag, a number."""

from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

from vita3k_manager import emulator

APPIMAGE = b"#!/bin/sh\necho Vita3K\n"


def _fetch(payload: bytes, calls: list | None = None):
    def fetch(url: str, dest: Path, progress=None) -> None:
        if calls is not None:
            calls.append(url)
        dest.write_bytes(payload)
    return fetch


@pytest.fixture
def pinned(monkeypatch):
    """The file the tests use, pinned as the build."""
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(APPIMAGE).hexdigest())
    monkeypatch.setattr(emulator, "SIZE", len(APPIMAGE))
    return APPIMAGE


def test_the_pin_points_at_the_build():
    assert emulator.URL == "https://github.com/Vita3K/Vita3K-builds/releases/download/4186/Vita3K-x86_64.AppImage"
    assert emulator.VERSION == "4186" and len(emulator.SHA256) == 64 and emulator.COMMIT.startswith("f0273e4c")
    assert emulator.RELEASE_PAGE == "https://github.com/Vita3K/Vita3K-builds/releases/tag/4186"
    assert emulator.SIZE_MB == 75


def test_install_and_remove(tmp_path, pinned):
    home = tmp_path / "emulator"
    assert emulator.installed_version(home) == ""
    calls = []
    assert emulator.install(home, _fetch(pinned, calls)) == "Vita3K build 4186 is installed."
    assert calls == [emulator.URL]
    image = emulator.appimage(home)
    assert image.read_bytes() == APPIMAGE and image.stat().st_mode & 0o777 == 0o755
    assert image.name == "vita3k.AppImage"                                       # the same name for every build
    assert (home / "current").is_symlink() and emulator.installed_version(home) == "4186"
    assert sorted(p.name for p in home.iterdir()) == ["4186", "current"]          # no download left behind
    emulator.remove(home)
    assert not home.exists() and emulator.installed_version(home) == ""


def test_an_older_build_is_replaced(tmp_path, pinned):
    home = tmp_path / "emulator"
    (home / "4100").mkdir(parents=True)
    (home / "4100" / emulator.MEMBER).write_text("old")
    (home / "current").symlink_to("4100")
    assert emulator.installed_version(home) == "4100"
    emulator.install(home, _fetch(pinned))
    assert emulator.installed_version(home) == "4186" and not (home / "4100").exists()


def test_the_appimage_updated_itself(tmp_path, pinned):
    """Its self-updater writes another build over the AppImage it runs from, in the same folder."""
    home = tmp_path / "emulator"
    assert not emulator.replaced(home)                                            # nothing installed
    emulator.install(home, _fetch(pinned))
    assert not emulator.replaced(home)
    emulator.appimage(home).write_bytes(APPIMAGE + b"a newer build")
    assert emulator.replaced(home) and emulator.installed_version(home) == "4186"
    emulator.install(home, _fetch(pinned))
    assert not emulator.replaced(home)


def test_a_different_file_is_refused(tmp_path, pinned):
    home = tmp_path / "emulator"
    with pytest.raises(emulator.EmulatorError, match="SHA-256 differs"):
        emulator.install(home, _fetch(b"something else"))
    assert emulator.installed_version(home) == "" and not list(home.iterdir())


def test_a_failed_install_keeps_the_installed_one(tmp_path, pinned):
    home = tmp_path / "emulator"
    emulator.install(home, _fetch(pinned))
    with pytest.raises(emulator.EmulatorError):
        emulator.install(home, _fetch(b"broken"))
    assert emulator.installed_version(home) == "4186" and emulator.appimage(home).read_bytes() == APPIMAGE


def test_download_errors_say_what_happened(tmp_path):
    def http(url, dest, progress=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def offline(url, dest, progress=None):
        raise urllib.error.URLError("Name or service not known")
    with pytest.raises(emulator.EmulatorError, match="GitHub answered 404"):
        emulator.install(tmp_path, http)
    with pytest.raises(emulator.EmulatorError, match="download failed: Name or service not known"):
        emulator.install(tmp_path, offline)


def _builds(tag: str):
    """GitHub's answer for Vita3K-builds' /releases/latest: its tag is the build's number."""
    def fetch(url: str):
        assert url == "https://api.github.com/repos/Vita3K/Vita3K-builds/releases/latest"
        return {"tag_name": tag, "html_url": f"https://github.com/Vita3K/Vita3K-builds/releases/tag/{tag}",
                "published_at": "2026-11-30T22:00:00Z", "prerelease": False, "assets": []}
    return fetch


def test_a_newer_vita3k_build():
    newer = emulator.newer_release(_builds("4200"))
    assert (newer.version, newer.published) == ("4200", "2026-11-30") and newer.url.endswith("/tag/4200")
    assert emulator.newer_release(_builds("4186")) is None                         # the one the app brings
    assert emulator.newer_release(_builds("4185")) is None
    assert emulator.newer_release(_builds("continuous")) is None                   # not a build number

    def offline(url: str):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None                                 # nothing to say then
    assert emulator.newer_release(lambda url: ["not", "a", "release"]) is None
