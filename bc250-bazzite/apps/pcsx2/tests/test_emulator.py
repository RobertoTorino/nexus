# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing the pinned PCSX2 release (emulator.py) from a file made here instead of the download: checked against
its SHA-256 first, "current" switched, older versions removed, nothing changed when a step fails, and the newer
stable GitHub may list. (The nightly channel went, owner 24-10-2026: nothing of it is left to test.)"""

from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

from pcsx2_manager import emulator

APPIMAGE = b"#!/bin/sh\necho PCSX2\n"


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
    monkeypatch.setattr(emulator, "SIZE", len(APPIMAGE))
    return APPIMAGE


def test_the_pin_points_at_the_release():
    assert emulator.URL == ("https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/"
                            "pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage")
    assert emulator.VERSION == "2.8.2" and len(emulator.SHA256) == 64
    assert emulator.RELEASE_PAGE == "https://github.com/PCSX2/pcsx2/releases/tag/v2.8.2"
    assert emulator.SIZE_MB == 57


def test_install_and_remove(tmp_path, pinned):
    home = tmp_path / "emulator"
    assert emulator.installed_version(home) == ""
    calls = []
    assert emulator.install(home, _fetch(pinned, calls)) == f"PCSX2 {emulator.VERSION} is installed."
    assert calls == [emulator.URL]
    image = emulator.appimage(home)
    assert image.read_bytes() == APPIMAGE and image.stat().st_mode & 0o777 == 0o755
    assert image.name == "pcsx2.AppImage"                                        # the same name for every version
    assert (home / "current").is_symlink() and emulator.installed_version(home) == emulator.VERSION
    assert sorted(p.name for p in home.iterdir()) == ["2.8.2", "current"]        # no download left behind
    emulator.remove(home)
    assert not home.exists() and emulator.installed_version(home) == ""


def test_install_takes_pcsx2s_catalogue_out(tmp_path, pinned, monkeypatch):
    """PCSX2's titles and patches come out of the AppImage beside it; without them the install stands all the
    same."""
    from pcsx2_manager import catalogue
    taken = []

    def extract(image: Path) -> None:
        taken.append(image)
        for name in catalogue.FILES:
            (image.parent / name).write_text(name)
    monkeypatch.setattr(catalogue, "extract", extract)
    home = tmp_path / "emulator"
    emulator.install(home, _fetch(pinned))
    assert taken == [emulator.appimage(home)] and not catalogue.missing(emulator.appimage(home).parent)

    def fails(image: Path) -> None:
        raise OSError("no room")
    monkeypatch.setattr(catalogue, "extract", fails)
    other = tmp_path / "other"
    assert emulator.install(other, _fetch(pinned)) == f"PCSX2 {emulator.VERSION} is installed."
    assert not emulator.take_catalogue(other)


def test_an_older_version_is_replaced(tmp_path, pinned):
    home = tmp_path / "emulator"
    (home / "2.7.0").mkdir(parents=True)
    (home / "2.7.0" / emulator.MEMBER).write_text("old")
    (home / "current").symlink_to("2.7.0")
    assert emulator.installed_version(home) == "2.7.0"
    emulator.install(home, _fetch(pinned))
    assert emulator.installed_version(home) == emulator.VERSION and not (home / "2.7.0").exists()


def test_pcsx2_updated_itself(tmp_path, pinned):
    """PCSX2's own update writes another build over the AppImage it runs from, in the same folder."""
    home = tmp_path / "emulator"
    assert not emulator.replaced(home)                                            # nothing installed
    emulator.install(home, _fetch(pinned))
    assert not emulator.replaced(home)
    emulator.appimage(home).write_bytes(APPIMAGE + b"a newer build")
    assert emulator.replaced(home) and emulator.installed_version(home) == emulator.VERSION
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


def _releases(tag: str):
    """GitHub's answer for PCSX2's /releases/latest: the newest stable (the nightlies are pre-releases)."""
    def fetch(url: str):
        assert url == "https://api.github.com/repos/PCSX2/pcsx2/releases/latest"
        return {"tag_name": tag, "html_url": f"https://github.com/PCSX2/pcsx2/releases/tag/{tag}",
                "published_at": "2026-11-30T22:00:00Z", "assets": []}
    return fetch


def test_a_newer_pcsx2_stable():
    newer = emulator.newer_release(_releases("v2.9.0"))
    assert (newer.version, newer.published) == ("2.9.0", "2026-11-30") and newer.url.endswith("/v2.9.0")
    assert emulator.newer_release(_releases("v2.8.2")) is None                    # the one the app brings
    assert emulator.newer_release(_releases("v2.8.1")) is None

    def offline(url: str):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None                                # nothing to say then
