# SPDX-License-Identifier: GPL-3.0-or-later
"""Uploading the firmware to the camera's boot loader. The camera has no flash: a PlayStation sends the firmware each
time the camera is plugged in, and so does this app, on A. The protocol is the one the PS4EYECam driver found and PS
Move API uses, as the BC250 Bazzite Suite's USB HD Cam sends it: the file in 512-byte vendor control transfers, each
at its offset (wValue: the low 16 bits; wIndex: 0x14 plus the rest), then one byte, 0x5b, at 0x2200/0x8018, which
starts the firmware. The boot loader then leaves the bus and the camera comes back under its own ID within a second
(the owner's ROG Xbox Ally X, 31-10-2026: 0.5 s).

The firmware's own USB 3 descriptor asks for the largest isochronous video endpoint there is: 1024-byte packets,
bursts of 16, 3 bursts every 125 us (49152 bytes). Some USB controllers cannot schedule that (the BC-250's); then the
largest modes give no picture. Reduced bandwidth sends the firmware with 2 bursts instead (32768 bytes): the copy
that goes to the camera changes, the file does not. On the owner's ROG Xbox Ally X full bandwidth streams every mode
at its full rate, side by side up to 5148x1088 at 30 fps; reduced every mode but the three largest side-by-side ones
(31-10-2026). Full is the default."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from . import camera
from .camera import Camera

CHUNK = 512
VENDOR_OUT = 0x40                           # bmRequestType: vendor request, host to device
FIRST_INDEX = 0x14
START = (0x2200, 0x8018, b"\x5b")
READY_TIMEOUT_S = 10.0
# The video endpoint (0x81, isochronous, 1024-byte packets, every microframe) and the start of its SuperSpeed
# companion; then bMaxBurst, bmAttributes (Mult: bursts per interval less one) and wBytesPerInterval.
VIDEO_ENDPOINT = bytes.fromhex("07 05 81 05 00 04 01 06 30")
BANDWIDTHS = {"full": 3, "reduced": 2}      # bursts per 125 us
DEFAULT_BANDWIDTH = "full"


class UploadError(Exception):
    pass


@dataclass(frozen=True)
class Outcome:
    ok: bool
    message: str
    camera: Camera | None = None            # the camera as it came back, when it did


def chunks(firmware: bytes):
    """(wValue, wIndex, data) for each transfer."""
    for offset in range(0, len(firmware), CHUNK):
        yield offset & 0xFFFF, FIRST_INDEX + (offset >> 16), firmware[offset:offset + CHUNK]


def bursts(bandwidth: str) -> int:
    """The bursts of a BANDWIDTHS setting; an unknown one is the default."""
    return BANDWIDTHS.get(bandwidth, BANDWIDTHS[DEFAULT_BANDWIDTH])


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
    """Sends *firmware* to an open boot loader (a winusb.Device, or a fake in the tests). The start request may not
    be answered: the boot loader leaves the bus as it starts the firmware, so its error is not one."""
    if not firmware:
        raise UploadError("The firmware file is empty.")
    device.reset()
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
    except OSError:
        pass


def wait_ready(boot: Camera, find: Callable[[], list[Camera]], before: frozenset[str] = frozenset(),
               timeout_s: float = READY_TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> Camera | None:
    """The camera once it is back with its firmware and Windows' webcam driver: on the boot loader's hub and port, or
    one that was not ready before (*before*: the instance IDs of the ready ones); a USB 3 socket is a port on a USB 2
    hub and one on a USB 3 hub, and the boot loader may come up on the other."""
    end = time.monotonic() + timeout_s
    while True:
        for found in find():
            if found.state != camera.READY_STATE or not found.webcam:
                continue
            same_port = found.device.parent == boot.device.parent and found.device.port == boot.device.port
            if same_port or found.instance not in before:
                return found
        if time.monotonic() >= end:
            return None
        sleep(0.25)


def load(boot: Camera, firmware: bytes, bandwidth: str, *, open_device: Callable[[str], object],
         find: Callable[[], list[Camera]] = camera.find, timeout_s: float = READY_TIMEOUT_S,
         sleep: Callable[[float], None] = time.sleep) -> Outcome:
    """Uploads *firmware* at *bandwidth* to *boot* and waits for the camera to come back. Never raises."""
    before = frozenset(found.instance for found in find() if found.state == camera.READY_STATE)
    try:
        device = open_device(boot.instance)
        try:
            upload(device, with_bandwidth(firmware, bursts(bandwidth)))
        finally:
            try:
                device.close()
            except OSError:
                pass
    except UploadError as exc:
        return Outcome(False, str(exc))
    except OSError as exc:
        return Outcome(False, f"The upload failed: {exc.strerror or exc}. Unplug the camera, plug it in again and "
                              "try once more.")
    ready = wait_ready(boot, find, before, timeout_s, sleep)
    if ready is None:
        return Outcome(False, f"The firmware was sent, but the camera did not come back as a webcam within "
                              f"{timeout_s:.0f} s. Unplug it and plug it in again, then try once more.")
    return Outcome(True, f"The {ready.name} is ready: apps list it as \"{ready.webcam}\".", ready)
