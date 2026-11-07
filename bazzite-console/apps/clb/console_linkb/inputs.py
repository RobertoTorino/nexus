# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/player/src/client/lib/channel/input/packet.ts, queue.ts and channel/input.ts),
# MIT, Copyright (c) 2019 UnknownSKL (Jim Kroon); the MIT notice is in the README's License section.
"""The input channel's binary reports, little-endian as the reference writes them.

Every report starts with a 14-byte header: the report types (a bit each, u16), a sequence number (u32) and the
client's clock in milliseconds (f64). Then, per type present, a count (u8) and its frames:
- client metadata (only in the first report): the number of touch points (u8);
- metadata, one per video frame shown (28 bytes): the frame's RTP timestamp and when it arrived, was decoded and
  shown (u32 each), and the clock twice;
- gamepad (23 bytes): the pad's index (u8), the buttons (u16), the sticks (i16, y up) and the triggers (u16), and
  two physicality words.
From the service: vibration (the pad's index and four motors in percent, with duration, delay and repeat) and the
server's video size."""

from __future__ import annotations

import struct
from dataclasses import dataclass

METADATA = 1
GAMEPAD = 2
CLIENT_METADATA = 8
SERVER_METADATA = 16
VIBRATION = 128

HEADER = struct.Struct("<HId")                                               # 14 bytes
GAMEPAD_FRAME = struct.Struct("<BHhhhhHHII")                                 # 23 bytes
METADATA_FRAME = struct.Struct("<IIIIIII")                                   # 28 bytes
MAX_FRAMES = 30                                                              # per report, as the reference warns

BUTTONS = {                                 # the gamepad report's button bits
    "nexus": 2, "menu": 4, "view": 8, "a": 16, "b": 32, "x": 64, "y": 128,
    "dpad_up": 256, "dpad_down": 512, "dpad_left": 1024, "dpad_right": 2048,
    "left_shoulder": 4096, "right_shoulder": 8192, "left_thumb": 16384, "right_thumb": 32768,
}


@dataclass
class PadState:
    """One pad's state: the pressed buttons (BUTTONS' names), the sticks from -1 to 1 (y down, as SDL gives them)
    and the triggers from 0 to 1."""

    index: int = 0
    buttons: frozenset[str] = frozenset()
    left_x: float = 0.0
    left_y: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0
    left_trigger: float = 0.0
    right_trigger: float = 0.0

    def button_mask(self) -> int:
        mask = 0
        for name in self.buttons:
            mask |= BUTTONS.get(name, 0)
        return mask


@dataclass
class FrameTimes:
    """A shown video frame for the metadata report (all in ms on the client's clock, u32)."""

    rtp_timestamp: int
    arrived: float
    decoded: float
    shown: float


def axis(value: float) -> int:
    """-1..1 to the report's -32767..32767."""
    if value != value:                      # NaN
        return 0
    return max(-32767, min(32767, round(value * 32767)))


def trigger(value: float) -> int:
    """0..1 to the report's 0..65535."""
    if not value > 0:
        return 0
    if value >= 1:
        return 65535
    return int(value * 65535)


def _u32(value: float) -> int:
    return int(value) & 0xFFFFFFFF


def client_metadata(sequence: int, now_ms: float, touch_points: int = 1) -> bytes:
    return HEADER.pack(CLIENT_METADATA, sequence, now_ms) + bytes([max(1, min(touch_points, 255))])


def report(sequence: int, now_ms: float, pads: list[PadState] = (), frames: list[FrameTimes] = ()) -> bytes:
    """A report with the *frames*' metadata and the *pads*' states (at most MAX_FRAMES of each: the newest)."""
    pads, frames = list(pads)[-MAX_FRAMES:], list(frames)[-MAX_FRAMES:]
    kinds = (METADATA if frames else 0) | (GAMEPAD if pads else 0)
    out = bytearray(HEADER.pack(kinds, sequence, now_ms))
    if frames:
        out.append(len(frames))
        for f in frames:
            out += METADATA_FRAME.pack(_u32(f.rtp_timestamp), _u32(f.arrived), _u32(f.arrived), _u32(f.decoded),
                                       _u32(f.shown), _u32(now_ms), _u32(now_ms))
    if pads:
        out.append(len(pads))
        for pad in pads:
            out += GAMEPAD_FRAME.pack(pad.index & 0xFF, pad.button_mask(), axis(pad.left_x), axis(-pad.left_y),
                                      axis(pad.right_x), axis(-pad.right_y), trigger(pad.left_trigger),
                                      trigger(pad.right_trigger), 1, 0x01000000)
            # The second physicality word: the reference writes 1 big-endian (setUint32(..., 1, false))
    return bytes(out)


@dataclass
class Vibration:
    index: int
    left: float                             # 0..1
    right: float
    left_trigger: float
    right_trigger: float
    duration_ms: int
    delay_ms: int
    repeat: int


@dataclass
class ServerSize:
    width: int
    height: int


def parse(data: bytes) -> Vibration | ServerSize | None:
    """A report from the service: vibration or the server's video size; None for anything else."""
    if not data:
        return None
    kind = data[0]
    if kind == VIBRATION and len(data) >= 13:
        index, left, right, left_t, right_t = data[3], data[4], data[5], data[6], data[7]
        duration, delay = struct.unpack_from("<HH", data, 8)
        return Vibration(index, left / 100, right / 100, left_t / 100, right_t / 100, duration, delay, data[12])
    if kind == SERVER_METADATA and len(data) >= 10:
        height, width = struct.unpack_from("<II", data, 2)      # the reference reads the height first
        return ServerSize(width, height)
    return None
