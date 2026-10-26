# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing the pinned Xenia build (emulator.py) from a file made here instead of the download: checked against
its SHA-256 first, "current" switched, older builds removed, nothing changed when a step fails, and a newer build
found on GitHub by when it was published."""

from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

from xenia_manager import emulator

APPIMAGE = b"#!/bin/sh\necho Xenia\n"


def _fetch(payload: bytes, calls: list | None = None):
    def fetch(url: str, dest: Path, progress=None) -> None:
        if calls is not None:
            calls.append(url)
        dest.write_bytes(payload)
    return fetch


@pytest.fixture
def pinned(monkeypatch):
    """The file the tests use, pinned as the release."""
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(APPIMAGE).hexdigest())
    return APPIMAGE


def test_the_pin_points_at_the_release():
    assert emulator.URL == ("https://github.com/xenia-canary/xenia-canary/releases/download/e6cd2e4/"
                            "xenia_canary_linux.AppImage")
    assert emulator.VERSION == "e6cd2e4" and emulator.COMMIT.startswith("e6cd2e4") and len(emulator.SHA256) == 64
    assert emulator.RELEASE_PAGE == "https://github.com/xenia-canary/xenia-canary/releases/tag/e6cd2e4"
    assert emulator.SIZE_MB == 18


def test_install_and_remove(tmp_path, pinned):
    home = tmp_path / "emulator"
    assert emulator.installed_version(home) == ""
    calls = []
    assert emulator.install(home, _fetch(pinned, calls)) == f"Xenia {emulator.VERSION} is installed."
    assert calls == [emulator.URL]
    image = emulator.appimage(home)
    assert image.read_bytes() == APPIMAGE and image.stat().st_mode & 0o777 == 0o755
    assert image.name == "xenia.AppImage"                                        # the same name for every build
    assert (home / "current").is_symlink() and emulator.installed_version(home) == emulator.VERSION
    assert sorted(p.name for p in home.iterdir()) == ["current", "e6cd2e4"]       # no download left behind
    emulator.remove(home)
    assert not home.exists() and emulator.installed_version(home) == ""


def test_an_older_version_is_replaced(tmp_path, pinned):
    home = tmp_path / "emulator"
    (home / "f42147a").mkdir(parents=True)
    (home / "f42147a" / emulator.MEMBER).write_text("old")
    (home / "current").symlink_to("f42147a")
    assert emulator.installed_version(home) == "f42147a"
    emulator.install(home, _fetch(pinned))
    assert emulator.installed_version(home) == emulator.VERSION and not (home / "f42147a").exists()


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
    assert emulator.installed_version(home) == emulator.VERSION and emulator.appimage(home).read_bytes() == APPIMAGE


def test_download_errors_say_what_happened(tmp_path):
    def http(url, dest, progress=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def offline(url, dest, progress=None):
        raise urllib.error.URLError("Name or service not known")
    with pytest.raises(emulator.EmulatorError, match="GitHub answered 404"):
        emulator.install(tmp_path, http)
    with pytest.raises(emulator.EmulatorError, match="download failed: Name or service not known"):
        emulator.install(tmp_path, offline)


def _releases(tag: str, published: str = "2026-11-30T22:00:00Z"):
    """GitHub's answer for Xenia Canary's /releases/latest."""
    def fetch(url: str):
        assert url == "https://api.github.com/repos/xenia-canary/xenia-canary/releases/latest"
        return {"tag_name": tag, "html_url": f"https://github.com/xenia-canary/xenia-canary/releases/tag/{tag}",
                "published_at": published, "assets": []}
    return fetch


def test_a_newer_xenia():
    newer = emulator.newer_release(_releases("0a1b2c3"))
    assert (newer.version, newer.published) == ("0a1b2c3", "2026-11-30") and newer.url.endswith("/0a1b2c3")
    assert emulator.newer_release(_releases("e6cd2e4", emulator.PUBLISHED)) is None  # the one the app brings
    assert emulator.newer_release(_releases("f42147a", "2026-10-20T09:40:37Z")) is None   # an older build
    assert emulator.newer_release(lambda url: ["not a release"]) is None

    def offline(url: str):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None                                 # nothing to say then
