# SPDX-License-Identifier: GPL-3.0-or-later
"""The firmware store and the pinned download, with a fake network and a stand-in file (the real one is Sony's and
is not in the repository)."""

from __future__ import annotations

import hashlib
import urllib.error

import pytest
from conftest import FIRMWARE

from usb_hdcam import firmware


@pytest.fixture
def pinned(monkeypatch):
    """The PS5 HD Camera's pin, pointed at the stand-in file."""
    real = firmware.PINNED["cfi-zey1"]
    pin = firmware.Pinned(url=real.url, sha256=hashlib.sha256(FIRMWARE).hexdigest(), size=len(FIRMWARE),
                          source=real.source)
    monkeypatch.setitem(firmware.PINNED, "cfi-zey1", pin)
    return pin


def test_each_pin_is_a_commit_and_a_known_file_of_its_model():
    ps5, ps4 = firmware.PINNED["cfi-zey1"], firmware.PINNED["ps4-camera"]
    assert "/8773610978d5a4d91a6a6d8063d48a4f3afcfe5b/" in ps5.url and ps5.size == 68948
    assert "/f90eeade2256d6617753e71832c729bec86c5479/" in ps4.url and ps4.size == 66608
    assert set(firmware.PINNED) == {"cfi-zey1", "ps4-camera"}
    for model, pin in firmware.PINNED.items():                  # each download is a known file of its model
        assert firmware.KNOWN[pin.sha256].model == model
    assert firmware.KNOWN[ps5.sha256].sha1 == "0fa4da31a12b662a9a80abc8b84932770df8f7e1"
    # PS Move API's tested file for the CUH-ZEY2, which the pinned PS4 download is
    assert firmware.KNOWN[ps4.sha256].sha1 == "fe86162309518a0ffe267075a2fcf728c5856b3e"


def test_known_files_are_keyed_by_sha256():
    assert all(len(key) == 64 and len(entry.sha1) == 40 for key, entry in firmware.KNOWN.items())
    assert len({entry.sha1 for entry in firmware.KNOWN.values()}) == len(firmware.KNOWN)


def test_folder_follows_xdg(tmp_path):
    assert firmware.path("cfi-zey1") == tmp_path / "data/bc250-usb-hdcam/firmware/cfi-zey1.bin"


def test_store_and_read(tmp_path):
    assert firmware.read("cfi-zey1") is None
    path = firmware.store("cfi-zey1", FIRMWARE)
    assert firmware.read("cfi-zey1") == FIRMWARE and path.name == "cfi-zey1.bin"
    assert firmware.read("ps4-camera") is None
    assert firmware.describe(FIRMWARE).startswith("Unknown file (SHA-256 ") and firmware.short(FIRMWARE) == "Own file"
    assert firmware.known(FIRMWARE) is None


def test_check_refuses_what_cannot_be_firmware(monkeypatch):
    with pytest.raises(firmware.FirmwareError, match="empty"):
        firmware.check("cfi-zey1", b"")
    with pytest.raises(firmware.FirmwareError, match="too large"):
        firmware.check("cfi-zey1", bytes(firmware.MAX_SIZE + 1))
    monkeypatch.setitem(firmware.KNOWN, firmware.sha256(FIRMWARE),
                        firmware.Known("ps4-camera", "PS4 system software 1.50 to 3.15", "x", "0" * 40))
    with pytest.raises(firmware.FirmwareError, match="another camera"):
        firmware.store("cfi-zey1", FIRMWARE)
    assert firmware.store("ps4-camera", FIRMWARE).name == "ps4-camera.bin"
    assert firmware.describe(FIRMWARE) == "PS4 system software 1.50 to 3.15"


def test_download(pinned):
    urls = []
    path = firmware.download("cfi-zey1", get=lambda url: urls.append(url) or FIRMWARE)
    assert urls == [pinned.url] and path.read_bytes() == FIRMWARE


def test_download_refuses_another_file(pinned):
    with pytest.raises(firmware.FirmwareError, match="not the expected one"):
        firmware.download("cfi-zey1", get=lambda url: FIRMWARE[:-1] + b"\xff")
    assert firmware.read("cfi-zey1") is None


def test_download_failure(pinned):
    def offline(url):
        raise urllib.error.URLError("Name or service not known")
    with pytest.raises(firmware.FirmwareError, match="failed: Name or service not known"):
        firmware.download("cfi-zey1", get=offline)


def test_the_ps4_cameras_download_goes_in_its_own_file(monkeypatch):
    real = firmware.PINNED["ps4-camera"]
    monkeypatch.setitem(firmware.PINNED, "ps4-camera", firmware.Pinned(
        real.url, hashlib.sha256(FIRMWARE).hexdigest(), len(FIRMWARE), real.source))
    path = firmware.download("ps4-camera", get=lambda url: FIRMWARE)
    assert path.name == "ps4-camera.bin" and firmware.read("cfi-zey1") is None
