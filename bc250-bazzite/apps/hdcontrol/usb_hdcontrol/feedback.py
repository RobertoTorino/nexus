# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app sends to the controller besides a firmware update: the vibration test, through the kernel's force
feedback on the controller's input device (hid-playstation turns a rumble into the two motors: strong is the left,
weak the right), and the light bar's color, as an output report on the hidraw node in the layout hid-playstation
sends it (struct dualsense_output_report_common: valid flag 1 bit 0x04 enables the light bar, its red, green and
blue at bytes 44 to 46 of the common part). Over USB that is report 0x02 (63 bytes); over Bluetooth report 0x31 (78
bytes), with a sequence number and the CRC-32 of 0xA2 and the report in its last four bytes.

The light bar keeps the color while the controller is connected, until the kernel's driver, Steam or a game sets
another; the controller forgets it when it disconnects."""

from __future__ import annotations

import fcntl
import os
import struct
import zlib
from pathlib import Path

EV_FF = 0x15
FF_RUMBLE = 0x50
FF_EFFECT_SIZE = 48                 # struct ff_effect on a 64-bit system
EVIOCSFF = (1 << 30) | (FF_EFFECT_SIZE << 16) | (ord("E") << 8) | 0x80
EVIOCRMFF = (1 << 30) | (4 << 16) | (ord("E") << 8) | 0x81
STRONG = 0xC000                     # three quarters: clearly felt, not harsh
RUMBLE_MS = 900
OUTPUT_USB = 0x02
OUTPUT_USB_SIZE = 63
OUTPUT_BT = 0x31
OUTPUT_BT_SIZE = 78
OUTPUT_BT_TAG = 0x10
CRC_SEED = b"\xa2"
LIGHTBAR_CONTROL = 0x04             # valid flag 1
LIGHTBAR_OFFSET = 44                # in the common part


def rumble_effect(strong: int, weak: int, ms: int) -> bytearray:
    """struct ff_effect for FF_RUMBLE: type, id -1 (a new effect), direction, trigger, replay (length, delay), and
    the rumble's strong and weak magnitudes where the union starts (offset 16)."""
    effect = bytearray(FF_EFFECT_SIZE)
    struct.pack_into("<HhH", effect, 0, FF_RUMBLE, -1, 0)
    struct.pack_into("<HH", effect, 10, ms, 0)
    struct.pack_into("<HH", effect, 16, strong, weak)
    return effect


class Rumble:
    """The controller's input device opened for force feedback. play() starts the motors and returns; the effect
    stops by itself after its length. Closing the device removes the effects it uploaded."""

    def __init__(self, event: Path | str):
        self.fd = os.open(str(event), os.O_RDWR | os.O_CLOEXEC)

    def play(self, strong: int, weak: int, ms: int = RUMBLE_MS) -> None:
        effect = rumble_effect(strong, weak, ms)
        fcntl.ioctl(self.fd, EVIOCSFF, effect)
        effect_id = struct.unpack_from("<h", effect, 2)[0]
        os.write(self.fd, struct.pack("<qqHHi", 0, 0, EV_FF, effect_id, 1))

    def close(self) -> None:
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            os.close(fd)


# The vibration test: the left motor, a pause, then the right one, each to be felt on its own side.
# (when in ms, side, strong, weak); the window plays them on its timers, so the drawing shakes in step.
VIBRATION_STEPS = ((0, "left", STRONG, 0), (RUMBLE_MS, "", 0, 0), (RUMBLE_MS + 300, "right", 0, STRONG),
                   (2 * RUMBLE_MS + 300, "", 0, 0))


def lightbar_report(bus: str, rgb: tuple[int, int, int], sequence: int = 0) -> bytes:
    common = bytearray(47)
    common[1] = LIGHTBAR_CONTROL
    common[LIGHTBAR_OFFSET:LIGHTBAR_OFFSET + 3] = bytes(rgb)
    if bus == "usb":
        return (bytes([OUTPUT_USB]) + bytes(common)).ljust(OUTPUT_USB_SIZE, b"\0")
    report = bytearray(OUTPUT_BT_SIZE)
    report[0], report[1], report[2] = OUTPUT_BT, (sequence & 0x0F) << 4, OUTPUT_BT_TAG
    report[3:3 + len(common)] = common
    report[-4:] = zlib.crc32(CRC_SEED + bytes(report[:-4])).to_bytes(4, "little")
    return bytes(report)


def set_lightbar(node: Path, bus: str, rgb: tuple[int, int, int], sequence: int = 0) -> None:
    fd = os.open(str(node), os.O_WRONLY | os.O_CLOEXEC)
    try:
        os.write(fd, lightbar_report(bus, rgb, sequence))
    finally:
        os.close(fd)


def parse_colour(text: str) -> tuple[int, int, int] | None:
    """"#rrggbb" -> (r, g, b); None for anything else (no color chosen)."""
    if len(text) == 7 and text.startswith("#"):
        try:
            return tuple(bytes.fromhex(text[1:]))
        except ValueError:
            return None
    return None
