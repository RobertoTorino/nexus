# SPDX-License-Identifier: GPL-3.0-or-later
"""The firmware file (firmware.py): the pinned download checked by size and SHA-256, a file of the user's, and what
is refused."""

from __future__ import annotations

import hashlib

import pytest

from usb_hd_cam import firmware


def test_the_pinned_file_is_a_known_one():
    known = firmware.KNOWN[firmware.PINNED.sha256]
    assert known.model == firmware.MODEL and firmware.PINNED.url.startswith("https://")


def test_download_stores_the_checked_file(tmp_path, monkeypatch):
    data = b"x" * firmware.PINNED.size
    monkeypatch.setitem(firmware.KNOWN, hashlib.sha256(data).hexdigest(), firmware.KNOWN[firmware.PINNED.sha256])
    monkeypatch.setattr(firmware, "PINNED", firmware.Pinned(firmware.PINNED.url, hashlib.sha256(data).hexdigest(),
                                                            len(data), "test"))
    path = firmware.download(tmp_path, get=lambda url: data)
    assert path == tmp_path / "cfi-zey1.bin" and firmware.read(tmp_path) == data
    assert firmware.short(data) == "21.01"


def test_download_refuses_another_file(tmp_path):
    with pytest.raises(firmware.FirmwareError, match="not the expected one"):
        firmware.download(tmp_path, get=lambda url: b"other")
    assert firmware.read(tmp_path) is None


def test_download_says_why_it_failed(tmp_path):
    def offline(url):
        raise OSError("no network")
    with pytest.raises(firmware.FirmwareError, match="no network"):
        firmware.download(tmp_path, get=offline)


def test_an_own_file_is_taken(tmp_path):
    source = tmp_path / "mine.bin"
    source.write_bytes(b"\x01\x02")
    firmware.take(source, tmp_path / "kept")
    assert firmware.read(tmp_path / "kept") == b"\x01\x02"
    assert firmware.short(b"\x01\x02") == "Own file" and firmware.describe(b"\x01\x02").startswith("Unknown file")


def test_what_cannot_be_the_firmware_is_refused(tmp_path):
    for data, reason in ((b"", "empty"), (b"x" * (firmware.MAX_SIZE + 1), "too large")):
        source = tmp_path / "f.bin"
        source.write_bytes(data)
        with pytest.raises(firmware.FirmwareError, match=reason):
            firmware.take(source, tmp_path / "kept")


def test_a_ps4_cameras_firmware_is_refused(monkeypatch):
    monkeypatch.setitem(firmware.KNOWN, hashlib.sha256(b"ps4").hexdigest(),
                        firmware.Known("ps4-camera", "PS4 system software", "PS4", ""))
    with pytest.raises(firmware.FirmwareError, match="another camera"):
        firmware.check(b"ps4")


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(firmware.FirmwareError, match="could not be read"):
        firmware.take(tmp_path / "gone.bin", tmp_path)


def test_the_folder_is_the_suites(tmp_path):
    assert firmware.path().parts[-3:] == ("windows-portable-hdcam", "firmware", "cfi-zey1.bin")
