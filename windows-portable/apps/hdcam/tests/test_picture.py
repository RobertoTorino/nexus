# SPDX-License-Identifier: GPL-3.0-or-later
"""Auto Exposure kept (picture.py): set and read back, again while the camera wakes with its old mode, and the
driver closed again when the camera keeps its own exposure. The kernel streaming request has the size the driver
expects."""

from __future__ import annotations

import ctypes

import pytest

from usb_hd_cam import picture


class FakeDriver:
    def __init__(self, auto_after: int):
        self.sets, self.auto_after, self.closed = 0, auto_after, False

    def set_auto(self):
        self.sets += 1

    def auto(self):
        return self.sets >= self.auto_after

    def close(self):
        self.closed = True


def test_auto_exposure_is_set_and_read_back():
    driver = FakeDriver(auto_after=1)
    assert picture.keep("video", open_driver=lambda video: driver, sleep=lambda s: None) is driver
    assert driver.sets == 1 and not driver.closed


def test_a_camera_that_is_waking_is_asked_again():
    """It may answer with its old mode while it wakes (the owner's Ally X, 01-11-2026)."""
    driver = FakeDriver(auto_after=3)
    picture.keep("video", open_driver=lambda video: driver, sleep=lambda s: None)
    assert driver.sets == 3 and not driver.closed


def test_a_camera_that_keeps_its_exposure_is_let_go():
    driver = FakeDriver(auto_after=99)
    with pytest.raises(OSError, match="kept its own exposure"):
        picture.keep("video", open_driver=lambda video: driver, sleep=lambda s: None)
    assert driver.sets == picture.TRIES and driver.closed


def test_the_request_is_the_size_the_driver_expects():
    """KSPROPERTY_CAMERACONTROL_S is 40 bytes on 64-bit Windows: 36 gave ERROR_INSUFFICIENT_BUFFER."""
    assert ctypes.sizeof(picture._CameraControl) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 36)
