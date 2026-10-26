# SPDX-License-Identifier: GPL-3.0-or-later
"""The firmware upload against a fake boot loader: the transfers, the start request, the wait for the camera, and
what the user is told when something goes wrong."""

from __future__ import annotations

import errno

import pytest
from conftest import FIRMWARE, plug, unplug

from usb_hdcam import camera, loader


class FakeBootLoader:
    """Records the calls; the start request makes it leave the bus (*gone*), as the real one does on Linux."""

    def __init__(self, gone: int | None = errno.ENODEV, take: int | None = None, on_start=None):
        self.calls = []
        self.gone = gone
        self.take = take
        self.on_start = on_start
        self.closed = False

    def reset(self):
        self.calls.append("reset")

    def set_configuration(self, value):
        self.calls.append(("configuration", value))

    def claim_interface(self, number):
        self.calls.append(("claim", number))

    def control_out(self, request_type, request, value, index, data, timeout_ms=1000):
        self.calls.append((request_type, request, value, index, bytes(data)))
        if (value, index, data) == loader.START:
            if self.on_start:
                self.on_start()
            if self.gone:
                raise OSError(self.gone, "gone")
            return 1
        return len(data) if self.take is None else self.take

    def close(self):
        self.closed = True

    @property
    def sent(self) -> bytes:
        return b"".join(call[4] for call in self.calls if isinstance(call, tuple) and len(call) == 5
                        and (call[2], call[3], call[4]) != loader.START)


def test_chunks_cross_64_kib():
    listed = list(loader.chunks(FIRMWARE))
    assert len(listed) == 135 and len(listed[-1][2]) == 68948 - 134 * 512
    assert listed[0][:2] == (0, 0x14) and listed[1][:2] == (512, 0x14)
    assert listed[127][:2] == (0xFE00, 0x14) and listed[128][:2] == (0, 0x15)     # offset 65536
    assert b"".join(chunk for _v, _i, chunk in listed) == FIRMWARE


def test_upload():
    device = FakeBootLoader()
    loader.upload(device, FIRMWARE)
    assert device.calls[:3] == ["reset", ("configuration", 1), ("claim", 0)]
    assert all(call[:2] == (0x40, 0) for call in device.calls[3:])
    assert device.sent == FIRMWARE
    assert device.calls[-1] == (0x40, 0, 0x2200, 0x8018, b"\x5b")


@pytest.mark.parametrize("gone", [None, errno.ENODEV, errno.ESHUTDOWN, errno.EPROTO])
def test_the_start_request_may_go_unanswered(gone):
    loader.upload(FakeBootLoader(gone=gone), FIRMWARE)


def test_other_errors_on_start_are_errors():
    with pytest.raises(OSError):
        loader.upload(FakeBootLoader(gone=errno.EIO), FIRMWARE)


def test_a_short_transfer_stops_the_upload():
    with pytest.raises(loader.UploadError, match="took 100 of 512 bytes at offset 0"):
        loader.upload(FakeBootLoader(take=100), FIRMWARE)


def test_an_empty_file_is_not_sent():
    device = FakeBootLoader()
    with pytest.raises(loader.UploadError):
        loader.upload(device, b"")
    assert device.calls == []


def _boot(tmp_path):
    plug(tmp_path)
    return camera.find(tmp_path)[0]


def test_load_waits_for_the_camera(tmp_path):
    boot = _boot(tmp_path)

    def come_back():                                # the boot loader leaves, the camera arrives on the same port
        unplug(tmp_path)
        plug(tmp_path, product="058c", address=4, videos=(2,))

    device = FakeBootLoader(on_start=come_back)
    opened = []
    outcome = loader.load(boot, FIRMWARE, open_device=lambda node: opened.append(node) or device,
                          find=lambda: camera.find(tmp_path), dev=tmp_path / "dev", sleep=lambda s: None)
    assert outcome.ok and outcome.message == "The PS5 HD Camera is ready: /dev/video2."
    assert opened == [tmp_path / "dev/bus/usb/007/003"] and device.closed
    assert outcome.camera.videos == ("/dev/video2",)


def test_load_finds_the_camera_on_the_other_bus(tmp_path):
    """The same socket is 6-1 on the USB 2 bus and 7-1 on the USB 3 bus."""
    plug(tmp_path, port="7-2", product="058c", address=9, videos=(0,))     # another camera, ready before
    plug(tmp_path, port="6-1", bus=6)
    boot = [c for c in camera.find(tmp_path) if not c.booted][0]

    def come_back():
        unplug(tmp_path, "6-1")
        plug(tmp_path, port="7-1", product="058c", address=4, videos=(2,))

    outcome = loader.load(boot, FIRMWARE, open_device=lambda node: FakeBootLoader(on_start=come_back),
                          find=lambda: camera.find(tmp_path), sleep=lambda s: None)
    assert outcome.ok and outcome.camera.port == "7-1"


def test_load_says_when_the_camera_does_not_come_back(tmp_path):
    boot = _boot(tmp_path)
    outcome = loader.load(boot, FIRMWARE, open_device=lambda node: FakeBootLoader(),
                          find=lambda: camera.find(tmp_path), timeout_s=0, sleep=lambda s: None)
    assert not outcome.ok and "did not come back" in outcome.message


@pytest.mark.parametrize("number, words", [(errno.EACCES, "Allow access"), (errno.ENOENT, "gone"),
                                           (errno.EIO, "The upload failed")])
def test_load_explains_errors(tmp_path, number, words):
    boot = _boot(tmp_path)

    def refuse(node):
        raise OSError(number, "error")

    outcome = loader.load(boot, FIRMWARE, open_device=refuse, find=lambda: camera.find(tmp_path))
    assert not outcome.ok and words in outcome.message


def test_one_upload_at_a_time(tmp_path):
    boot = _boot(tmp_path)
    inner = []

    def nested(node):
        inner.append(loader.load(boot, FIRMWARE, open_device=lambda n: FakeBootLoader(),
                                 find=lambda: camera.find(tmp_path), timeout_s=0, sleep=lambda s: None))
        return FakeBootLoader()

    loader.load(boot, FIRMWARE, open_device=nested, find=lambda: camera.find(tmp_path), timeout_s=0,
                sleep=lambda s: None)
    assert not inner[0].ok and "Another upload" in inner[0].message


def _with_endpoint(attributes: int = 2) -> bytes:
    """The stand-in file with the video endpoint as the real firmware has it (at offset 61414 there)."""
    endpoint = loader.VIDEO_ENDPOINT + bytes([15, attributes]) + (1024 * 16 * (attributes + 1)).to_bytes(2, "little")
    return FIRMWARE[:61414] + endpoint + FIRMWARE[61414 + len(endpoint):]


def test_reduced_bandwidth_patches_the_video_endpoint_only():
    original = _with_endpoint()
    reduced = loader.with_bandwidth(original, loader.BANDWIDTHS["reduced"])
    assert reduced[61421:61427] == bytes.fromhex("06 30 0f 01 00 80")          # as measured on the owner's board
    assert len(reduced) == len(original) and sum(a != b for a, b in zip(original, reduced)) == 2
    assert loader.with_bandwidth(original, loader.BANDWIDTHS["full"]) == original
    assert loader.with_bandwidth(reduced, 3) == original
    assert loader.with_bandwidth(original, 1)[61421:61427] == bytes.fromhex("06 30 0f 00 00 40")


def test_a_file_without_one_such_endpoint_is_sent_as_it_is():
    assert loader.with_bandwidth(FIRMWARE, 2) == FIRMWARE
    twice = _with_endpoint() + _with_endpoint()[61414:61427]
    assert loader.with_bandwidth(twice, 2) == twice


def test_bursts():
    assert (loader.bursts("reduced"), loader.bursts("full"), loader.bursts("other")) == (2, 3, 2)
