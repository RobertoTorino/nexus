# SPDX-License-Identifier: GPL-3.0-or-later
"""The firmware upload (loader.py): the transfers as the boot loader expects them, the bandwidth patch, and load()
waiting for the camera to come back, with a fake device and fake cameras."""

from __future__ import annotations

import pytest

from usb_hd_cam import camera, loader
from usb_hd_cam.camera import Camera
from usb_hd_cam.devices import Device

HUB = "USB\\VID_0BDA&PID_0411\\6&1&0&2"
ENDPOINT = loader.VIDEO_ENDPOINT + bytes([15, 2]) + (49152).to_bytes(2, "little")


class FakeDevice:
    def __init__(self, short_at: int | None = None, start_error: bool = False):
        self.sent: list[tuple[int, int, int, int, bytes]] = []
        self.short_at, self.start_error = short_at, start_error
        self.closed = False

    def reset(self):
        pass

    def set_configuration(self, value):
        pass

    def claim_interface(self, number):
        pass

    def control_out(self, request_type, request, value, index, data):
        if (value, index) == loader.START[:2] and self.start_error:
            raise OSError(None, "gone", None, 31)
        self.sent.append((request_type, request, value, index, bytes(data)))
        return len(data) - 1 if self.short_at is not None and len(self.sent) == self.short_at else len(data)

    def close(self):
        self.closed = True


def cam(state: str, instance: str, port: int = 1, parent: str = HUB, webcam: str = "") -> Camera:
    return Camera(state, Device(instance, "", 0, parent, port, ""), None, webcam)


BOOT = cam(camera.BOOT_LOADER, "USB\\VID_05A9&PID_0580\\7&1&0&1")
READY = cam(camera.READY_STATE, "USB\\VID_05A9&PID_058C\\7&1&0&1", webcam="USB Camera-OV580")


def test_chunks_carry_their_offset():
    data = bytes(range(256)) * 520                  # 133120 bytes: past 64 KiB
    got = list(loader.chunks(data))
    assert got[0][:2] == (0, 0x14) and len(got[0][2]) == 512
    assert got[128][:2] == (0, 0x15)                # 65536: the high part goes to wIndex
    assert b"".join(part for _, _, part in got) == data


def test_upload_sends_every_chunk_then_the_start():
    device = FakeDevice()
    loader.upload(device, b"\x01" * 1100)
    assert [len(d) for *_, d in device.sent] == [512, 512, 76, 1]
    assert device.sent[-1][2:] == (0x2200, 0x8018, b"\x5b")
    assert all(rt == loader.VENDOR_OUT for rt, *_ in device.sent)


def test_a_start_left_unanswered_is_fine():
    loader.upload(FakeDevice(start_error=True), b"\x01" * 10)


def test_a_short_transfer_stops_the_upload():
    with pytest.raises(loader.UploadError, match="offset 512"):
        loader.upload(FakeDevice(short_at=2), b"\x01" * 1100)


def test_an_empty_file_is_refused():
    with pytest.raises(loader.UploadError):
        loader.upload(FakeDevice(), b"")


def test_bandwidth_patch():
    firmware = b"head" + ENDPOINT + b"tail"
    reduced = loader.with_bandwidth(firmware, 2)
    at = 4 + len(loader.VIDEO_ENDPOINT)
    assert reduced[at + 1] == 1 and int.from_bytes(reduced[at + 2:at + 4], "little") == 32768
    assert loader.with_bandwidth(firmware, 3) == firmware
    assert loader.with_bandwidth(b"no endpoint", 2) == b"no endpoint"
    assert loader.with_bandwidth(firmware + ENDPOINT, 2) == firmware + ENDPOINT     # two: not the measured file


def test_bursts_default_to_full():
    assert loader.bursts("reduced") == 2 and loader.bursts("full") == 3 and loader.bursts("?") == 3


def test_load_waits_for_the_webcam():
    device = FakeDevice()
    calls = iter([[BOOT], [BOOT], [READY]])
    outcome = loader.load(BOOT, b"\x01" * 600, "full", open_device=lambda instance: device,
                          find=lambda: next(calls), sleep=lambda s: None)
    assert outcome.ok and outcome.camera == READY and "USB Camera-OV580" in outcome.message
    assert device.closed


def test_load_takes_a_camera_that_came_back_on_the_other_hub():
    """A USB 3 socket is a port on a USB 2 hub and one on a USB 3 hub: a camera not ready before counts."""
    elsewhere = cam(camera.READY_STATE, "USB\\VID_05A9&PID_058C\\9&9&0&4", port=4, parent="USB\\OTHER",
                    webcam="USB Camera-OV580")
    calls = iter([[BOOT], [elsewhere]])
    outcome = loader.load(BOOT, b"\x01", "full", open_device=lambda instance: FakeDevice(),
                          find=lambda: next(calls), sleep=lambda s: None)
    assert outcome.ok and outcome.camera == elsewhere


def test_load_says_when_the_camera_does_not_come_back():
    outcome = loader.load(BOOT, b"\x01", "reduced", open_device=lambda instance: FakeDevice(), find=lambda: [BOOT],
                          timeout_s=0, sleep=lambda s: None)
    assert not outcome.ok and "did not come back" in outcome.message


def test_load_says_when_the_camera_cannot_be_opened():
    def refuse(instance):
        raise OSError(None, "Access is denied", None, 5)
    outcome = loader.load(BOOT, b"\x01", "full", open_device=refuse, find=lambda: [BOOT])
    assert not outcome.ok and "Access is denied" in outcome.message
