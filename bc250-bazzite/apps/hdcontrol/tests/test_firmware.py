# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json

import pytest

from conftest import FIRMWARE_REPORT, plug
from usb_hdcontrol import controller, firmware

INFO = controller.parse_info(FIRMWARE_REPORT)


def image(product: int = 0x0DF2, target: int = 0x0044, update: int = 0x0217, size: int = 4096) -> bytes:
    """An image with the header of Sony's DualSense Edge 0x0217 (19-09-2025), not its body."""
    head = bytearray(256)
    head[:54] = b"Copyright (C) 2022 Sony Interactive Entertainment Inc.".ljust(54, b"\0")
    head[0x40:0x4B] = b"Sep 19 2025"
    head[0x50:0x58] = b"10:14:30"
    head[0x60:0x62] = (2).to_bytes(2, "little")
    head[0x62:0x64] = product.to_bytes(2, "little")
    head[0x70:0x74] = (0x0100008B).to_bytes(4, "little")
    head[0x74:0x76] = target.to_bytes(2, "little")
    head[0x78:0x7A] = update.to_bytes(2, "little")
    return bytes(head) + bytes(size - 256)


@pytest.fixture
def edge(tmp_path):
    plug(tmp_path)
    return controller.find(tmp_path)[0]


def test_latest_reads_sonys_list():
    answer = json.dumps({"ApplicationLatestVersion": "2.2.1.2", "FwUpdate0004LatestVersion": "0x0630",
                         "FwUpdate000BLatestVersion": "0x0630", "FwUpdate000ELatestVersion": "0x0641",
                         "FwUpdate0044LatestVersion": "0x0217"}).encode()
    assert firmware.latest(lambda url: answer) == {0x0004: 0x0630, 0x000B: 0x0630, 0x000E: 0x0641, 0x0044: 0x0217}


@pytest.mark.parametrize("answer", [b"<html>", b"[]", b'{"ApplicationLatestVersion": "2.2.1.2"}'])
def test_latest_says_when_the_list_is_unusable(answer):
    with pytest.raises(firmware.FirmwareError):
        firmware.latest(lambda url: answer)


def test_latest_says_when_the_server_cannot_be_reached():
    def offline(url):
        raise OSError("Name or service not known")
    with pytest.raises(firmware.FirmwareError, match="could not be read"):
        firmware.latest(offline)


def test_header():
    head = firmware.header(image())
    assert head == firmware.Header("Sep 19 2025", "10:14:30", 0x0DF2, 0x0100008B, 0x0044, 0x0217)


def test_header_refuses_other_files():
    with pytest.raises(firmware.FirmwareError):
        firmware.header(b"\x7fELF" + bytes(300))
    with pytest.raises(firmware.FirmwareError):
        firmware.header(image()[:200])


def test_problem_accepts_the_newer_image(edge):
    assert firmware.problem(image(), edge, INFO) == ""


@pytest.mark.parametrize("data, text", [
    (image(product=0x0CE6, target=0x000B), "for the DualSense with target 000B"),
    (image(target=0x000E), "target 000E"),
    (image(update=0x0200), "already runs 0x0200"),
    (image(update=0x0100), "no older or equal"),
    (b"not firmware" + bytes(300), "no firmware header"),
])
def test_problem_refuses(edge, data, text):
    assert text in firmware.problem(data, edge, INFO)


def test_known_images_by_sha256():
    assert firmware.known(image()) is None
    known = firmware.KNOWN["c157eec635f809232e06c255a0847e6b915b0032ca661b12ae35fb2e4eac49df"]
    assert (known.target, known.version, known.size) == (0x0044, 0x0217, 950272)


def test_download_checks_and_keeps_the_image(tmp_path):
    urls = []
    data = image()
    assert firmware.download(0x0044, 0x0217, tmp_path, lambda url: urls.append(url) or data) == data
    assert urls == ["https://fwupdater.dl.playstation.net/fwupdater/fwupdate0044/0x0217/FWUPDATE0044.bin"]
    assert firmware.read(0x0044, 0x0217, tmp_path) == data
    assert firmware.path(0x0044, 0x0217, tmp_path).name == "FWUPDATE0044-0217.bin"
    assert not list(firmware.folder(tmp_path).glob("*.part"))


def test_download_refuses_another_version(tmp_path):
    with pytest.raises(firmware.FirmwareError, match="sent version 0x0216"):
        firmware.download(0x0044, 0x0217, tmp_path, lambda url: image(update=0x0216))
    assert firmware.read(0x0044, 0x0217, tmp_path) is None


def test_download_says_when_it_fails(tmp_path):
    def offline(url):
        raise OSError("timed out")
    with pytest.raises(firmware.FirmwareError, match="could not be downloaded"):
        firmware.download(0x0044, 0x0217, tmp_path, offline)


def test_folder_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert firmware.folder() == tmp_path / "bc250-usb-hdcontrol" / "firmware"
