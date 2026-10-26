# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the camera in a fake /sys: boot mode, ready with its video node, the PS4 Camera (CUH-ZEY2) on
Sony's adapter."""

from __future__ import annotations

from pathlib import Path

from conftest import plug

from usb_hdcam import camera


def test_nothing_plugged_in(tmp_path):
    assert camera.find(tmp_path) == []


def test_boot_mode_as_on_the_owners_board(tmp_path):
    plug(tmp_path)                                  # 7-1, 05a9:0580, 5000 Mbit/s, bus 7 device 3 (23-10-2026)
    [found] = camera.find(tmp_path)
    assert (found.model, found.booted, found.port, found.videos) == ("cfi-zey1", False, "7-1", ())
    assert found.name == "PS5 HD Camera" and not found.slow
    assert found.node(Path("/dev")) == Path("/dev/bus/usb/007/003")


def test_ready_with_its_capture_node_only(tmp_path):
    plug(tmp_path, product="058c", address=4, videos=(2,))       # video2 the picture, video3 its metadata
    [found] = camera.find(tmp_path)
    assert found.booted and found.model == "cfi-zey1" and found.videos == ("/dev/video2",)


def test_another_device_video_node_is_not_the_cameras(tmp_path):
    plug(tmp_path, product="058c", videos=(2,))
    other = tmp_path / "devices/platform/v4l2loopback-000"
    other.mkdir(parents=True)
    (tmp_path / "class/video4linux/video0").mkdir(parents=True)
    (tmp_path / "class/video4linux/video0/device").symlink_to(other)
    assert camera.find(tmp_path)[0].videos == ("/dev/video2",)


def test_playstation_camera_on_sonys_adapter(tmp_path):
    plug(tmp_path, port="7-1.1", hub="054c:0d0b")
    [found] = camera.find(tmp_path)                 # the adapter's hub is not a camera
    assert found.model == "ps4-camera" and found.name == "PS4 Camera" and not found.booted
    plug(tmp_path, port="7-2", product="058a", videos=(4,))
    assert [c.model for c in camera.find(tmp_path)] == ["ps4-camera", "ps4-camera"]


def test_usb_2_is_too_slow_for_the_video(tmp_path):
    plug(tmp_path, port="1-3", speed=480, bus=1)
    assert camera.find(tmp_path)[0].slow


def test_other_omnivision_devices_are_not_cameras(tmp_path):
    plug(tmp_path, product="1234")
    assert camera.find(tmp_path) == []
