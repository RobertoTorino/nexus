# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's input reports, read through hidapi beside Windows' own HID driver (every program that opens the
controller gets each report), for the drawing to show what is pressed. The layout is the one hid-playstation reads:
over USB report 0x01, over Bluetooth report 0x31 with one byte more in front. Bytes from the report's start: the sticks
(left x, y, right x, y), the triggers (L2, R2), a counter, then three bytes of buttons: the d-pad as a hat (0 up,
clockwise to 7, 8 none) with Square, Cross, Circle, Triangle; L1, R1, L2, R2, Create, Options, L3, R3; PS, the
touchpad's click, Mute and, on the DualSense Edge, the left and right Fn and back buttons (those four bits as SDL
reads them; the left Fn's read on the owner's Edge, 23-10-2026). On the Edge byte 49 of the USB report (in the part
hid-playstation leaves reserved) holds the active profile in its upper four bits: 1 Fn + Triangle, 2 Square, 3 Cross,
4 Circle (read on the owner's Edge, 23-10-2026: 1 and 2; over Bluetooth one byte further, not yet read).

Windows has no battery of the controller's to read, as Linux's driver gives one: the battery is read from the same
reports, its status byte (byte 53 of the USB report) as hid-playstation reads it, the level in the low four bits (in
tens of percent) and the charging state in the high four. Over Bluetooth the controller sends the short report 0x01
until a program reads its calibration (feature report 0x05), as Linux's driver and Steam do; the reader does that
too (Reader), and only that: it changes nothing on the controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .controller import Battery
from .hiddevice import Device
from .profiles import SLOTS

REPORT_USB = 0x01
REPORT_BT = 0x31
HAT = {0: ("up",), 1: ("up", "right"), 2: ("right",), 3: ("down", "right"), 4: ("down",), 5: ("down", "left"),
       6: ("left",), 7: ("up", "left")}
BITS = (
    (0, 0x10, "square"), (0, 0x20, "cross"), (0, 0x40, "circle"), (0, 0x80, "triangle"),
    (1, 0x01, "l1"), (1, 0x02, "r1"), (1, 0x04, "l2"), (1, 0x08, "r2"), (1, 0x10, "create"), (1, 0x20, "options"),
    (1, 0x40, "l3"), (1, 0x80, "r3"),
    (2, 0x01, "ps"), (2, 0x02, "touchpad"), (2, 0x04, "mute"),
    (2, 0x10, "fn_left"), (2, 0x20, "fn_right"), (2, 0x40, "back_left"), (2, 0x80, "back_right"),
)


@dataclass(frozen=True)
class Reading:
    pressed: frozenset[str] = field(default_factory=frozenset)
    sticks: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)    # -1 (left, up) to 1 (right, down)
    triggers: tuple[float, float] = (0.0, 0.0)                          # 0 to 1
    profile: str = ""                                                   # the DualSense Edge's active slot, SLOTS
    battery: Battery | None = None                                      # None: the report is too short to say


REPORT_CALIBRATION = 0x05
STATUS = 52                         # the status byte, from the report's common part (after the ID, over Bluetooth
                                    # after the ID and one byte more)


def _axis(value: int) -> float:
    return max(-1.0, (value - 128) / 127)


def battery(status: int) -> Battery:
    """The battery from the input report's status byte, as hid-playstation reads it (dualsense_parse_report)."""
    level, charging = status & 0x0F, (status & 0xF0) >> 4
    if charging in (0x0, 0x1):
        return Battery(min(level * 10 + 5, 100), "Discharging" if charging == 0x0 else "Charging")
    if charging == 0x2:
        return Battery(100, "Full")
    if charging in (0xA, 0xB):                      # voltage or temperature out of range, a temperature error
        return Battery(0, "Not charging")
    return Battery(0, "Unknown")


def parse(data: bytes) -> Reading | None:
    """A reading from an input report; None for another report, or one too short."""
    if len(data) >= 12 and data[0] == REPORT_USB:
        base = 1
    elif len(data) >= 13 and data[0] == REPORT_BT:
        base = 2
    else:
        return None
    sticks = tuple(_axis(value) for value in data[base:base + 4])
    triggers = (data[base + 4] / 255, data[base + 5] / 255)
    buttons = data[base + 7:base + 10]
    pressed = set(HAT.get(buttons[0] & 0x0F, ()))
    pressed |= {name for index, bit, name in BITS if buttons[index] & bit}
    profile = data[base + 48] >> 4 if len(data) > base + 48 else 0
    return Reading(frozenset(pressed), sticks, triggers, SLOTS[profile - 1] if 1 <= profile <= len(SLOTS) else "",
                   battery(data[base + STATUS]) if len(data) > base + STATUS else None)


class Reader:
    """The controller opened for reading, without blocking: read() gives the newest reading of the reports waiting,
    or None when none came. The window calls it from a timer (Windows has no file descriptor to wait on), often
    enough for Windows' buffer of 32 reports. Over Bluetooth it reads the calibration report first, so that the
    controller sends its full reports (see above)."""

    count = 0                               # input reports read: the window's report rate

    def __init__(self, path: bytes, bus: str = "usb", open_device: Callable[..., Device] = Device):
        self.device = open_device(path, None, blocking=False)
        if bus == "bluetooth":
            try:
                self.device.get_feature(REPORT_CALIBRATION)
            except OSError:
                pass                        # the short reports then: the drawing waits for full ones
        self.battery: Battery | None = None

    def read(self) -> Reading | None:
        newest = None
        while True:
            data = self.device.read(128)
            if not data:
                return newest
            self.count += 1
            reading = parse(data)
            if reading is not None:
                newest = reading
                if reading.battery is not None:
                    self.battery = reading.battery

    def close(self) -> None:
        self.device.close()


