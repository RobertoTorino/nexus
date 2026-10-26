# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing the pinned shadPS4 (emulator.py) from a zip made here instead of the download: checked against its
SHA-256 first, "current" switched, older versions removed, and nothing changed when a step fails."""

from __future__ import annotations

import hashlib
import io
import urllib.error
import zipfile
from pathlib import Path

import pytest

from shadps4_manager import emulator


def _zip(member: str = emulator.MEMBER, data: bytes = b"#!/bin/sh\necho shadPS4\n") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as packed:
        packed.writestr(member, data)
    return out.getvalue()


def _fetch(payload: bytes, calls: list | None = None):
    def fetch(url: str, dest: Path, progress=None) -> None:
        if calls is not None:
            calls.append(url)
        dest.write_bytes(payload)
    return fetch


@pytest.fixture
def pinned(monkeypatch):
    """The zip the tests use, pinned as the release."""
    payload = _zip()
    monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
    return payload


def test_the_pin_points_at_the_release():
    assert emulator.URL == ("https://github.com/shadps4-emu/shadPS4/releases/download/v.0.20.0/"
                            "shadps4-linux-sdl-0.20.0.zip")
    assert len(emulator.SHA256) == 64 and emulator.TAG.endswith(emulator.VERSION)


def test_install_and_remove(tmp_path, pinned):
    home = tmp_path / "emulator"
    assert emulator.installed_version(home) == ""
    calls = []
    assert emulator.install(home, _fetch(pinned, calls)) == f"shadPS4 {emulator.VERSION} is installed."
    assert calls == [emulator.URL]
    image = emulator.appimage(home)
    assert image.read_bytes().startswith(b"#!/bin/sh") and image.stat().st_mode & 0o777 == 0o755
    assert (home / "current").is_symlink() and emulator.installed_version(home) == emulator.VERSION
    assert sorted(p.name for p in home.iterdir()) == ["0.20.0", "current"]       # no download left behind
    emulator.remove(home)
    assert not home.exists() and emulator.installed_version(home) == ""


def test_an_older_version_is_replaced(tmp_path, pinned):
    home = tmp_path / "emulator"
    (home / "0.18.0").mkdir(parents=True)
    (home / "0.18.0" / emulator.MEMBER).write_text("old")
    (home / "current").symlink_to("0.18.0")
    assert emulator.installed_version(home) == "0.18.0"
    emulator.install(home, _fetch(pinned))
    assert emulator.installed_version(home) == emulator.VERSION and not (home / "0.18.0").exists()


@pytest.mark.parametrize("payload, message", [
    (b"something else", "SHA-256 differs"),
])
def test_a_different_file_is_refused(tmp_path, pinned, payload, message):
    home = tmp_path / "emulator"
    with pytest.raises(emulator.EmulatorError, match=message):
        emulator.install(home, _fetch(payload))
    assert emulator.installed_version(home) == "" and not list(home.iterdir())


def test_a_zip_without_the_appimage_or_damaged(tmp_path, monkeypatch):
    home = tmp_path / "emulator"
    for payload, message in ((_zip("other.AppImage"), "has no Shadps4-sdl.AppImage"), (b"PK\x03\x04broken", "damaged")):
        monkeypatch.setattr(emulator, "SHA256", hashlib.sha256(payload).hexdigest())
        with pytest.raises(emulator.EmulatorError, match=message):
            emulator.install(home, _fetch(payload))
        assert not list(home.iterdir())


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
    """GitHub's answer for /releases/latest (only stable releases)."""
    def fetch(url: str):
        assert url == "https://api.github.com/repos/shadps4-emu/shadPS4/releases/latest"
        return {"tag_name": tag, "html_url": f"https://github.com/shadps4-emu/shadPS4/releases/tag/{tag}",
                "published_at": "2026-11-20T10:00:00Z", "assets": []}
    return fetch


def test_a_newer_shadps4_release():
    newer = emulator.newer_release(_releases("v.0.21.0"))
    assert (newer.version, newer.published) == ("0.21.0", "2026-11-20") and newer.url.endswith("/v.0.21.0")
    assert emulator.newer_release(_releases(emulator.TAG)) is None                 # the one the app brings
    assert emulator.newer_release(_releases("v.0.19.0")) is None

    def offline(url: str):
        raise urllib.error.URLError("no network")
    assert emulator.newer_release(offline) is None                                 # nothing to say then
