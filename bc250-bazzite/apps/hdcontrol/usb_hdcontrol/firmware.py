# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers' firmware: Sony's list of the latest versions, the image download, and the checks before an
update. Sony serves the images its Windows app installs, one per target (the controller's sw_series; the DualSense
Edge's is 0x0044), and only the latest version of each (an older version's URL answers 404, 23-10-2026).

An image starts with a 256-byte header, the same in every target measured (23-10-2026): the build date at 0x40, the
time at 0x50, the USB product ID at 0x62, the firmware version at 0x70, the target at 0x74 and the update version at
0x78. The controller checks the image's CMAC itself; the app refuses before that an image for another controller or
one that is not newer, and knows the images it was tried with by their SHA-256."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .controller import Controller, FirmwareInfo

INFO_URL = "https://fwupdater.dl.playstation.net/fwupdater/info.json"
IMAGE_URL = "https://fwupdater.dl.playstation.net/fwupdater/fwupdate{target:04X}/0x{version:04x}/FWUPDATE{target:04X}.bin"
SOURCE = "the official update server (fwupdater.dl.playstation.net)"
TIMEOUT = 30
HEADER = 256
MAX_SIZE = 4 * 1024 * 1024
# Which DualSense revision has which target depends on its chip; only the Edge's is one product.
TARGET_NAMES = {0x0004: "DualSense", 0x000B: "DualSense", 0x000E: "DualSense", 0x0044: "DualSense Edge"}

Get = Callable[[str], bytes]


class FirmwareError(Exception):
    pass


@dataclass(frozen=True)
class Known:
    target: int
    version: int
    size: int


# The images on Sony's server on 23-10-2026, by SHA-256.
KNOWN = {
    "c157eec635f809232e06c255a0847e6b915b0032ca661b12ae35fb2e4eac49df": Known(0x0044, 0x0217, 950272),
    "861ad95a99b16805ff20f5690372988662c4f69c6ad0b266e793d7fc2292315a": Known(0x0004, 0x0630, 950272),
    "b66528795683d214ca06fe4672d298de75bf019bd5046442cbec63fc02974f86": Known(0x000B, 0x0630, 950272),
    "b9c217d8ded5f09f03034e7e5037af0c174c3c77a3cbd201ee5fd219ee448fc8": Known(0x000E, 0x0641, 950272),
}


@dataclass(frozen=True)
class Header:
    build_date: str
    build_time: str
    product: int
    firmware: int
    target: int
    update: int


def version_text(version: int) -> str:
    return f"0x{version:04x}"


def _get(url: str) -> bytes:
    from . import __version__
    request = urllib.request.Request(url, headers={"User-Agent": f"bc250-usb-hdcontrol/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(MAX_SIZE + 1)


def latest(get: Get = _get) -> dict[int, int]:
    """Target -> the latest update version, from Sony's info.json ({"FwUpdate0044LatestVersion": "0x0217", ...})."""
    try:
        data = json.loads(get(INFO_URL))
    except (OSError, ValueError) as exc:
        raise FirmwareError(f"The list of firmware versions could not be read: {exc}") from exc
    versions = {}
    for key, value in (data.items() if isinstance(data, dict) else ()):
        if key.startswith("FwUpdate") and key.endswith("LatestVersion"):
            try:
                versions[int(key[8:-13], 16)] = int(str(value), 16)
            except ValueError:
                continue
    if not versions:
        raise FirmwareError("The list of firmware versions has no version in it.")
    return versions


def header(data: bytes) -> Header:
    if len(data) < HEADER or not data.startswith(b"Copyright"):
        raise FirmwareError("This is not a controller firmware image: it has no firmware header.")
    word = lambda offset, size: int.from_bytes(data[offset:offset + size], "little")  # noqa: E731
    text = lambda offset: data[offset:offset + 16].split(b"\0", 1)[0].decode("ascii", "replace")  # noqa: E731
    return Header(text(0x40), text(0x50), word(0x62, 2), word(0x70, 4), word(0x74, 2), word(0x78, 2))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def known(data: bytes) -> Known | None:
    return KNOWN.get(sha256(data))


def problem(data: bytes, controller: Controller, info: FirmwareInfo) -> str:
    """Why *data* must not be sent to *controller*, or "" when it may."""
    try:
        head = header(data)
    except FirmwareError as exc:
        return str(exc)
    if head.product != controller.product or head.target != info.target:
        name = TARGET_NAMES.get(head.target, "another controller")
        return (f"This image is for the {name} with target {head.target:04X}; this {controller.name} has target "
                f"{info.target:04X}.")
    if head.update <= info.update:
        return (f"This image is version {version_text(head.update)}; the controller already runs "
                f"{version_text(info.update)}. The controller takes no older or equal version.")
    if len(data) > MAX_SIZE:
        return "This image is larger than any controller firmware."
    return ""


def folder(home: Path | None = None) -> Path:
    if home is None:
        home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "bc250-usb-hdcontrol"
    return home / "firmware"


def path(target: int, version: int, home: Path | None = None) -> Path:
    return folder(home) / f"FWUPDATE{target:04X}-{version:04x}.bin"


def read(target: int, version: int, home: Path | None = None) -> bytes | None:
    try:
        return path(target, version, home).read_bytes()
    except OSError:
        return None


def store(data: bytes, home: Path | None = None) -> Path:
    """Keeps an image under its target and version, so the update can be repeated without the network."""
    head = header(data)
    where = path(head.target, head.update, home)
    where.parent.mkdir(parents=True, exist_ok=True)
    temporary = where.with_suffix(".part")
    temporary.write_bytes(data)
    temporary.replace(where)
    return where


def download(target: int, version: int, home: Path | None = None, get: Get = _get) -> bytes:
    url = IMAGE_URL.format(target=target, version=version)
    try:
        data = get(url)
    except OSError as exc:
        raise FirmwareError(f"The firmware could not be downloaded from {SOURCE}: {exc}") from exc
    head = header(data)
    if (head.target, head.update) != (target, version):
        raise FirmwareError(f"The update server sent version {version_text(head.update)} for target {head.target:04X}, "
                            f"not {version_text(version)} for {target:04X}.")
    store(data, home)
    return data
