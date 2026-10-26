# SPDX-License-Identifier: GPL-3.0-or-later
"""The input channel's reports, byte for byte as the reference writes them."""

from __future__ import annotations

import struct

from console_linkb import inputs
from console_linkb.inputs import FrameTimes, PadState


def test_client_metadata_is_the_header_and_the_touch_points():
    data = inputs.client_metadata(1, 1234.5)
    assert len(data) == 15
    assert struct.unpack("<HId", data[:14]) == (inputs.CLIENT_METADATA, 1, 1234.5)
    assert data[14] == 1


def test_a_gamepad_report():
    pad = PadState(0, frozenset({"a", "menu", "dpad_up", "right_thumb"}), left_x=1.0, left_y=-0.5, right_x=-1.0,
                   right_y=0.25, left_trigger=1.0, right_trigger=0.5)
    data = inputs.report(7, 100.0, [pad])
    assert len(data) == 14 + 1 + 23
    assert struct.unpack("<HId", data[:14]) == (inputs.GAMEPAD, 7, 100.0)
    assert data[14] == 1
    frame = struct.unpack("<BHhhhhHH", data[15:15 + 15])
    assert frame == (0, 16 | 4 | 256 | 32768, 32767, 16384, -32767, -8192, 65535, 32767)
    assert data[30:34] == bytes([1, 0, 0, 0])           # PhysicalPhysicality 1, little-endian
    assert data[34:38] == bytes([0, 0, 0, 1])           # VirtualPhysicality 1, written big-endian


def test_axes_and_triggers_are_clamped():
    assert inputs.axis(2.0) == 32767 and inputs.axis(-2.0) == -32767 and inputs.axis(float("nan")) == 0
    assert inputs.trigger(-0.1) == 0 and inputs.trigger(1.5) == 65535 and inputs.trigger(float("nan")) == 0


def test_metadata_and_gamepad_in_one_report():
    frames = [FrameTimes(90000, 10, 12, 13), FrameTimes(2**32 + 5, 20, 22, 23)]
    data = inputs.report(2, 50.0, [PadState()], frames)
    assert struct.unpack("<H", data[:2])[0] == inputs.METADATA | inputs.GAMEPAD
    assert data[14] == 2
    first = struct.unpack("<7I", data[15:15 + 28])
    assert first == (90000, 10, 10, 12, 13, 50, 50)
    assert struct.unpack("<I", data[43:47])[0] == 5          # wraps at 32 bits
    assert data[15 + 56] == 1 and len(data) == 14 + 1 + 56 + 1 + 23


def test_at_most_thirty_frames_the_newest():
    data = inputs.report(1, 0, [PadState(i) for i in range(40)])
    assert data[14] == 30 and data[15] == 10


def test_vibration_and_server_size_from_the_service():
    vibration = bytes([128, 0, 0, 1, 50, 100, 0, 25]) + struct.pack("<HH", 200, 0) + bytes([1])
    assert inputs.parse(vibration) == inputs.Vibration(1, 0.5, 1.0, 0.0, 0.25, 200, 0, 1)
    size = bytes([16, 0]) + struct.pack("<II", 1080, 1920)
    assert inputs.parse(size) == inputs.ServerSize(1920, 1080)
    assert inputs.parse(b"") is None and inputs.parse(bytes([128, 0])) is None and inputs.parse(b"\x02" * 20) is None
