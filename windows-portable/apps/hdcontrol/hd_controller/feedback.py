# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app sends to the controller besides a firmware update: the light bar's color and the vibration test, each
an output report in the layout hid-playstation sends it (struct dualsense_output_report_common). The light bar: valid
flag 1 bit 0x04, its red, green and blue at bytes 44 to 46 of the common part. The motors: the right one (weak) at
byte 2 and the left one (strong) at byte 3, with valid flag 0's haptics select (0x02), and the compatible vibration
in valid flag 0 (0x01) or, on the DualSense Edge and a DualSense from firmware 0x0215 (2.21), in valid flag 2 (0x04),
as hid-playstation chooses it. Over USB that is report 0x02 (63 bytes); over Bluetooth report 0x31 (78 bytes), with a
sequence number and the CRC-32 of 0xA2 and the report in its last four bytes.

On Linux the kernel's driver turns a rumble into that report (the BC250 app asks it through force feedback); Windows
has no such driver for the controller, so the app writes the report itself, through hidapi. A rumble runs until
the next report stops it: the window sends one with both motors at zero after each step.

The light bar keeps the color while the controller is connected, until Steam or a game sets another; the controller
forgets it when it disconnects."""

from __future__ import annotations

import zlib

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
COMPATIBLE_VIBRATION = 0x01         # valid flag 0
HAPTICS_SELECT = 0x02               # valid flag 0
COMPATIBLE_VIBRATION2 = 0x04        # valid flag 2, at byte 38 of the common part
VALID_FLAG2 = 38
MOTOR_RIGHT, MOTOR_LEFT = 2, 3
VIBRATION_V2 = 0x0215               # hid-playstation: a DualSense from this update version takes the second flag

# The vibration test: the left motor, a pause, then the right one, each to be felt on its own side.
# (when in ms, side, strong, weak); the window plays them on its timers, so the drawing shakes in step.
VIBRATION_STEPS = ((0, "left", STRONG, 0), (RUMBLE_MS, "", 0, 0), (RUMBLE_MS + 300, "right", 0, STRONG),
                   (2 * RUMBLE_MS + 300, "", 0, 0))


def _report(bus: str, common: bytearray, sequence: int) -> bytes:
    """The common part as the USB or the Bluetooth output report."""
    if bus == "usb":
        return (bytes([OUTPUT_USB]) + bytes(common)).ljust(OUTPUT_USB_SIZE, b"\0")
    report = bytearray(OUTPUT_BT_SIZE)
    report[0], report[1], report[2] = OUTPUT_BT, (sequence & 0x0F) << 4, OUTPUT_BT_TAG
    report[3:3 + len(common)] = common
    report[-4:] = zlib.crc32(CRC_SEED + bytes(report[:-4])).to_bytes(4, "little")
    return bytes(report)


def lightbar_report(bus: str, rgb: tuple[int, int, int], sequence: int = 0) -> bytes:
    common = bytearray(47)
    common[1] = LIGHTBAR_CONTROL
    common[LIGHTBAR_OFFSET:LIGHTBAR_OFFSET + 3] = bytes(rgb)
    return _report(bus, common, sequence)


def vibration_v2(edge: bool, update: int | None) -> bool:
    """Whether the controller takes the second compatible vibration flag, as hid-playstation decides it."""
    return edge or (update is not None and update >= VIBRATION_V2)


def rumble_report(bus: str, strong: int, weak: int, v2: bool, sequence: int = 0) -> bytes:
    """Both motors: *strong* (the left) and *weak* (the right), 0 to 0xFFFF as force feedback has them, sent as the
    kernel sends them, in their high byte."""
    common = bytearray(47)
    common[0] = HAPTICS_SELECT | (0 if v2 else COMPATIBLE_VIBRATION)
    if v2:
        common[VALID_FLAG2] = COMPATIBLE_VIBRATION2
    common[MOTOR_LEFT], common[MOTOR_RIGHT] = strong >> 8, weak >> 8
    return _report(bus, common, sequence)


def parse_colour(text: str) -> tuple[int, int, int] | None:
    """"#rrggbb" -> (r, g, b); None for anything else (no color chosen)."""
    if len(text) == 7 and text.startswith("#"):
        try:
            return tuple(bytes.fromhex(text[1:]))
        except ValueError:
            return None
    return None
