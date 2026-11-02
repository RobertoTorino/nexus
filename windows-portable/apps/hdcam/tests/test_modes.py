# SPDX-License-Identifier: GPL-3.0-or-later
"""The Picture card's modes (modes.py): the ones that give a picture at each bandwidth, in order, and the chosen one."""

from __future__ import annotations

from usb_hd_cam.modes import Mode, chosen, offered

# What the PS5 HD Camera reports through Windows (the owner's ROG XBOX Ally X, 01-11-2026)
REPORTED = [Mode(w, h, f) for w, h, f in (
    (896, 256, 120), (1920, 1080, 30), (1920, 1080, 15), (1920, 1080, 8), (960, 520, 60), (448, 256, 120),
    (1280, 800, 60), (1280, 800, 30), (1280, 800, 15), (1280, 800, 8), (640, 376, 120), (320, 184, 240),
    (5148, 1088, 30), (5148, 1088, 15), (5148, 1088, 8), (3840, 1080, 30), (3840, 1080, 15), (3840, 1080, 8),
    (1920, 520, 60), (2560, 800, 60), (2560, 800, 30), (2560, 800, 15), (2560, 800, 8), (1280, 376, 120),
    (640, 184, 240), (1920, 1080, 30))]


def keys(listed: list[Mode]) -> list[str]:
    return [mode.key for mode in listed]


def test_each_size_once_one_camera_first_the_largest_first():
    assert keys(offered(REPORTED, "full")) == [
        "1920x1080@30", "1280x800@60", "960x520@60", "640x376@120", "448x256@120", "320x184@240",
        "5148x1088@30", "3840x1080@30", "2560x800@60", "1920x520@60", "1280x376@120", "896x256@120", "640x184@240"]


def test_the_modes_without_a_picture_are_left_out():
    silent = [Mode(1920, 1080, 15), Mode(1920, 1080, 8)]
    assert keys(offered(silent, "full")) == ["1920x1080@8"]            # 15 fps sends nothing: 8 is the fastest
    reduced = keys(offered(REPORTED, "reduced"))
    assert "5148x1088@8" in reduced and "3840x1080@8" in reduced and "2560x800@30" in reduced
    assert not any(key in reduced for key in ("5148x1088@30", "3840x1080@30", "2560x800@60"))


def test_labels():
    assert Mode(1920, 1080, 30).label == "1920 × 1080, 30 fps (one camera)"
    assert Mode(2560, 800, 30).label == "2560 × 800, 30 fps (both cameras)"
    assert Mode(5148, 1088, 30).kind == "both cameras and smaller copies"


def test_the_chosen_mode_else_the_first():
    listed = offered(REPORTED, "full")
    assert chosen(listed, "2560x800@60") == Mode(2560, 800, 60)
    assert chosen(listed, "2560x800@30") == Mode(1920, 1080, 30)        # not offered: the webcam's picture
    assert chosen([], "") is None
