# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's modes, as the PS5 HD Camera reports them with its firmware (prosperodev/hdcamera's lsusb), and
what a view shows of a frame."""

from __future__ import annotations

from usb_hdcam import modes
from usb_hdcam.modes import Mode

# (width, height, the fastest rate) of each frame the camera reports, in its own order.
REPORTED = [(896, 256, 120), (1920, 1080, 30), (960, 520, 60), (448, 256, 120), (1280, 800, 60), (640, 376, 120),
            (320, 184, 240), (5148, 1088, 30), (3840, 1080, 30), (1920, 520, 60), (2560, 800, 60), (1280, 376, 120),
            (640, 184, 240)]


def reported() -> list[Mode]:
    return [Mode(w, h, fps, "YUYV") for w, h, fps in REPORTED] + [Mode(1280, 800, 30, "YUYV")]


def test_one_camera_or_both():
    one = {m.key for m in reported() if not m.stereo}
    assert one == {"1920x1080@30", "960x520@60", "448x256@120", "1280x800@60", "1280x800@30", "640x376@120",
                   "320x184@240"}
    assert Mode(3840, 1080, 30).label == "3840 × 1080, 30 fps (both cameras)"
    assert Mode(1280, 800, 60).label == "1280 × 800, 60 fps (one camera)"


def test_order_and_default():
    listed = modes.ordered(reported() + [Mode(1920, 1080, 30, "YUYV")])            # a duplicate goes
    assert [m.key for m in listed][:3] == ["1920x1080@30", "1280x800@60", "1280x800@30"]
    assert listed[7].key == "5148x1088@30" and len(listed) == 14
    assert modes.default(reported()).key == "1920x1080@30"
    assert modes.default([]) is None


def test_chosen_falls_back_to_the_default():
    assert modes.chosen(reported(), "2560x800@60").key == "2560x800@60"
    assert modes.chosen(reported(), "").key == "1920x1080@30"
    assert modes.chosen(reported(), "9999x1@1").key == "1920x1080@30"


def test_crop():
    assert modes.crop(3840, 1080, "both") == (0, 0, 3840, 1080)
    assert modes.crop(3840, 1080, "left") == (0, 0, 1920, 1080)
    assert modes.crop(3840, 1080, "right") == (1920, 0, 1920, 1080)
    assert modes.crop(5147, 1088, "right") == (2573, 0, 2574, 1088)
