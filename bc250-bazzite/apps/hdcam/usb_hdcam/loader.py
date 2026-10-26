# SPDX-License-Identifier: GPL-3.0-or-later
"""Uploading the firmware to the camera's boot loader. The camera has no flash: a PlayStation sends the firmware each
time the camera is plugged in, and so does this app. The protocol is the one the PS4EYECam driver found and PS Move
API uses: the file in 512-byte vendor control transfers, each at its offset (wValue: the low 16 bits; wIndex: 0x14
plus the rest), then one byte, 0x5b, at 0x2200/0x8018, which starts the firmware. The boot loader then leaves the
bus and the camera comes back under its own ID within a few seconds.

The firmware's own USB 3 descriptor asks for the largest isochronous video endpoint there is: 1024-byte packets,
bursts of 16, 3 bursts every 125 us (49152 bytes). Some USB controllers cannot schedule that; the BC-250's (AMD FCH
xHCI 1022:7814) refuses it, and then no mode streams (owner's board, 23-10-2026). Reduced bandwidth sends the
firmware with 2 bursts instead (32768 bytes): the copy that goes to the camera changes, the file does not. On the
owner's board every one-camera mode then streams at its full rate, and the side-by-side modes up to 2560x800 at
30 fps."""

from __future__ import annotations

import errno
import fcntl
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID, camera
from .camera import Camera
from .usbfs import Device

CHUNK = 512
VENDOR_OUT = 0x40                           # bmRequestType: vendor request, host to device
FIRST_INDEX = 0x14
START = (0x2200, 0x8018, b"\x5b")
# The start request may not be answered: the boot loader leaves the bus as it starts the firmware.
GONE = (errno.ENODEV, errno.ESHUTDOWN, errno.EPROTO, errno.EPIPE)
READY_TIMEOUT_S = 10.0
# The video endpoint (0x81, isochronous, 1024-byte packets, every microframe) and the start of its SuperSpeed
# companion; then bMaxBurst, bmAttributes (Mult: bursts per interval less one) and wBytesPerInterval.
VIDEO_ENDPOINT = bytes.fromhex("07 05 81 05 00 04 01 06 30")
BANDWIDTHS = {"reduced": 2, "full": 3}      # bursts per 125 us


class UploadError(Exception):
    pass


@dataclass(frozen=True)
class Outcome:
    ok: bool
    message: str
    camera: Camera | None = None            # the camera as it came back, when it did


def chunks(firmware: bytes) -> Iterator[tuple[int, int, bytes]]:
    """(wValue, wIndex, data) for each transfer."""
    for offset in range(0, len(firmware), CHUNK):
        yield offset & 0xFFFF, FIRST_INDEX + (offset >> 16), firmware[offset:offset + CHUNK]


def bursts(bandwidth: str) -> int:
    """The bursts of a BANDWIDTHS setting; an unknown one is reduced, which works on more controllers."""
    return BANDWIDTHS.get(bandwidth, BANDWIDTHS["reduced"])


def with_bandwidth(firmware: bytes, bursts: int) -> bytes:
    """*firmware* with its video endpoint at *bursts* bursts per interval. A file without exactly one such endpoint
    is sent as it is: it is not the firmware this was measured on."""
    at = firmware.find(VIDEO_ENDPOINT)
    if at < 0 or firmware.find(VIDEO_ENDPOINT, at + 1) >= 0:
        return firmware
    companion = at + len(VIDEO_ENDPOINT)
    burst = firmware[companion] + 1
    patched = bytearray(firmware)
    patched[companion + 1] = bursts - 1
    patched[companion + 2:companion + 4] = (1024 * burst * bursts).to_bytes(2, "little")
    return bytes(patched)


def upload(device, firmware: bytes) -> None:
    """Sends *firmware* to an open boot loader (a usbfs.Device, or a fake in the tests)."""
    if not firmware:
        raise UploadError("The firmware file is empty.")
    device.reset()                          # as PS Move API does: a boot loader left halfway starts clean
    device.set_configuration(1)
    device.claim_interface(0)
    for value, index, data in chunks(firmware):
        sent = device.control_out(VENDOR_OUT, 0, value, index, data)
        if sent != len(data):
            offset = value + (index - FIRST_INDEX) * 0x10000
            raise UploadError(f"The camera took {sent} of {len(data)} bytes at offset {offset}.")
    value, index, data = START
    try:
        device.control_out(VENDOR_OUT, 0, value, index, data)
    except OSError as exc:
        if exc.errno not in GONE:
            raise


@contextmanager
def _lock(runtime: Path):
    """One upload at a time: the window and the login service may see the same camera."""
    runtime.mkdir(parents=True, exist_ok=True)
    with open(runtime / f"{APP_ID}.lock", "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UploadError("Another upload to the camera is running.") from None
        yield


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP_ID}-{os.getuid()}")


def wait_ready(boot: Camera, find: Callable[[], list[Camera]], before: set[str] = frozenset(),
               timeout_s: float = READY_TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> Camera | None:
    """The camera once it is back with its firmware and a video node: on the boot loader's port, or on a port that
    had no ready camera before (*before*); the same socket has another port name on the USB 2 and USB 3 bus."""
    end = time.monotonic() + timeout_s
    while True:
        for found in find():
            if found.booted and found.videos and (found.port == boot.port or found.port not in before):
                return found
        if time.monotonic() >= end:
            return None
        sleep(0.25)


def load(boot: Camera, firmware: bytes, *, open_device: Callable[[Path], object] = Device,
         find: Callable[[], list[Camera]] = camera.find, dev: Path = camera.DEV, runtime: Path | None = None,
         timeout_s: float = READY_TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> Outcome:
    """Uploads *firmware* to *boot* and waits for the camera to come back. Never raises."""
    before = {found.port for found in find() if found.booted}
    try:
        with _lock(runtime or runtime_dir()):
            device = open_device(boot.node(dev))
            try:
                upload(device, firmware)
            finally:
                try:
                    device.close()
                except OSError:
                    pass
    except UploadError as exc:
        return Outcome(False, str(exc))
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM):
            return Outcome(False, "Your user may not use the camera yet: Allow access gives it the camera.")
        if exc.errno == errno.ENOENT:
            return Outcome(False, "The camera is gone: it was unplugged, or something else loaded its firmware.")
        return Outcome(False, f"The upload failed: {exc.strerror or exc}.")
    ready = wait_ready(boot, find, before, timeout_s, sleep)
    if ready is None:
        return Outcome(False, f"The firmware was sent, but the camera did not come back as a camera within "
                              f"{timeout_s:.0f} s. Unplug it and plug it in again, then try once more.")
    return Outcome(True, f"The {ready.name} is ready: {ready.videos[0]}.", ready)
