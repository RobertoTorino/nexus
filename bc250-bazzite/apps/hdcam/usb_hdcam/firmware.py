# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's firmware: Sony's, so the suite does not ship it. The app downloads one pinned file per model and
checks its SHA-256: for the PS5 HD Camera the firmware 21.01-03.20.00.04 as the prosperodev/hdcamera project
publishes it, for the PS4 Camera the firmware of PS4 system software 1.50 to 3.15 from psxdev/luke_firmwares (the
file PS Move API tested on a CUH-ZEY2). Or the user picks a file of their own. Each model keeps its file in
~/.local/share/bc250-usb-hdcam/firmware/<model>.bin. The app knows a file by its SHA-256, and shows whether the
file it has is one it knows; the table keeps each file's SHA-1 too, the hash the projects that publish them quote."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID

TIMEOUT = 30
MAX_SIZE = 1024 * 1024                      # the known files are 67 KiB; anything far larger is not firmware


@dataclass(frozen=True)
class Known:
    model: str
    name: str
    short: str                              # in the window's Firmware box
    sha1: str                               # as the projects that publish it quote it


KNOWN = {   # by SHA-256
    "10af1aee76fe0057a88db7ebf5f3ebf32430633effb93722be4cd0a9ed4fce54":
        Known("cfi-zey1", "21.01-03.20.00.04", "21.01", "0fa4da31a12b662a9a80abc8b84932770df8f7e1"),
    # The same with 8 bytes changed (a Windows driver package for the camera, 2024): one mode's 60 fps becomes 30,
    # and one value 4 becomes 2.
    "42ce5f7033a1115988cada3ebb8e0a143e8b241661f203a12275354dd2ba0bf6":
        Known("cfi-zey1", "21.01-03.20.00.04 with the Discord and gamma fix", "21.01 fix",
              "a5d8aadab91d78e33f4c038798c047066e6713d7"),
    # The PS4 Camera's, as the PS4's system software carried them (psxdev/luke_firmwares, 2021).
    "8262c2a785128a04273bbcf360e29e30c10c9f3b1c3e2571a5eea5b929f41e16":
        Known("ps4-camera", "PS4 system software 1.00 to 1.05", "PS4 1.00", "7390be76a163c2d4a68d939577d46d7c20165881"),
    "d550c4abc416385810ca181867f4dd650198e1214d371ba058005a10f420fd9b":
        Known("ps4-camera", "PS4 system software 1.50 to 3.15", "PS4 1.50", "fe86162309518a0ffe267075a2fcf728c5856b3e"),
    "a6f99b283b707ece098602aea823415e614db3d64b21a22c53d45476e5405b24":
        Known("ps4-camera", "PS4 system software 3.50 to 5.05", "PS4 3.50", "c556911796202deef1cbb051390b5c3a2e6c0a7a"),
    "09513d1068b9b5e23b09e03bca5640ed4d01830b034b9802395006b14a927b01":
        Known("ps4-camera", "PS4 system software 6.00 to 7.02", "PS4 6.00", "8b8a6621d358f6782c2e3b31aac2cdfb25102c00"),
}


@dataclass(frozen=True)
class Pinned:
    url: str
    sha256: str
    size: int
    source: str                             # where it is published, as the window names it


PINNED = {
    "cfi-zey1": Pinned(url="https://raw.githubusercontent.com/prosperodev/hdcamera/"
                           "8773610978d5a4d91a6a6d8063d48a4f3afcfe5b/firmware/21.01-03.20.00.04-00.00.00.bin",
                       sha256="10af1aee76fe0057a88db7ebf5f3ebf32430633effb93722be4cd0a9ed4fce54", size=68948,
                       source="github.com/prosperodev/hdcamera"),
    "ps4-camera": Pinned(url="https://raw.githubusercontent.com/psxdev/luke_firmwares/"
                             "f90eeade2256d6617753e71832c729bec86c5479/315_913F00_66608.bin",
                         sha256="d550c4abc416385810ca181867f4dd650198e1214d371ba058005a10f420fd9b", size=66608,
                         source="github.com/psxdev/luke_firmwares"),
}

Get = Callable[[str], bytes]


class FirmwareError(Exception):
    pass


def folder() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / APP_ID / "firmware"


def path(model: str, home: Path | None = None) -> Path:
    return (home or folder()) / f"{model}.bin"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def known(data: bytes) -> Known | None:
    """The file, if its SHA-256 is one the app knows."""
    return KNOWN.get(sha256(data))


def describe(data: bytes) -> str:
    found = known(data)
    return found.name if found else f"Unknown file (SHA-256 {sha256(data)[:12]}…)"


def short(data: bytes) -> str:
    found = known(data)
    return found.short if found else "Own file"


def read(model: str, home: Path | None = None) -> bytes | None:
    try:
        return path(model, home).read_bytes() or None
    except OSError:
        return None


def check(model: str, data: bytes) -> None:
    """Refuses what cannot be this model's firmware; an unknown file of a sane size is the user's choice."""
    if not data:
        raise FirmwareError("The file is empty.")
    if len(data) > MAX_SIZE:
        raise FirmwareError(f"The file is {len(data) // 1024} KiB: too large for the camera's firmware.")
    found = known(data)
    if found and found.model != model:
        raise FirmwareError(f"This is the firmware of another camera ({found.name}).")


def store(model: str, data: bytes, home: Path | None = None) -> Path:
    check(model, data)
    target = path(model, home)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(target)
    return target


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": APP_ID})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(MAX_SIZE + 1)


def download(model: str, home: Path | None = None, get: Get = _get) -> Path:
    """Fetches the model's pinned file, checks it and stores it. Raises FirmwareError with what went wrong."""
    pinned = PINNED[model]
    try:
        data = get(pinned.url)
    except OSError as exc:
        reason = getattr(exc, "reason", None) or exc
        raise FirmwareError(f"The download from {pinned.source} failed: {reason}.") from None
    if len(data) != pinned.size or hashlib.sha256(data).hexdigest() != pinned.sha256:
        raise FirmwareError(f"The file from {pinned.source} is not the expected one (size or SHA-256 differs), so it "
                            "was not used.")
    return store(model, data, home)
