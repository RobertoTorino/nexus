# SPDX-License-Identifier: GPL-3.0-or-later
"""The mouse pointer moved by a controller's touchpad (owner, 05-11-2026: as Steam Input does it for the Steam
Controller, now for a DualShock 4 or a DualSense the portal reads itself). Wayland lets no program move the pointer,
so the portal makes a mouse of its own: a virtual one through the kernel's uinput (/dev/uinput), which the desktop
takes as any other mouse. Bazzite gives the user at the seat access to it (Steam's own rules need it too); without
access the touchpad does nothing, and the rest of the controller works as before.

The device is made at the first touch, not at start, so a portal without a touchpad adds no mouse to the system,
and it goes when the portal closes."""

from __future__ import annotations

import fcntl
import os
import struct

DEVICE = "/dev/uinput"
NAME = b"Bazzite Console Suite touchpad"

# linux/uinput.h and linux/input-event-codes.h
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x5501, 0x5502
EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y = 0x00, 0x01
BTN_LEFT, BTN_RIGHT = 0x110, 0x111
BUS_VIRTUAL = 0x06
EVENT = struct.Struct("llHHi")              # struct input_event: the time (the kernel fills it in), type, code, value


class VirtualMouse:
    """move(dx, dy) in pixels (fractions add up), press(button, down) with BTN_LEFT or BTN_RIGHT. Fails silently
    after the first failure: no access, no device."""

    def __init__(self, path: str | None = None):
        self.path = path or DEVICE              # looked up when made: the tests point it elsewhere
        self.fd: int | None = None
        self.failed = False
        self.rest = [0.0, 0.0]                  # the fractions of a pixel not moved yet

    def _open(self) -> bool:
        if self.fd is not None:
            return True
        if self.failed:
            return False
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            self.failed = True
            return False
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            for button in (BTN_LEFT, BTN_RIGHT):
                fcntl.ioctl(fd, UI_SET_KEYBIT, button)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
            for axis in (REL_X, REL_Y):
                fcntl.ioctl(fd, UI_SET_RELBIT, axis)
            # struct uinput_setup: the id (bus, vendor, product, version), the name, ff_effects_max
            fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("HHHH80sI", BUS_VIRTUAL, 0, 0, 1, NAME, 0))
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            self.failed = True
            return False
        self.fd = fd
        return True

    def _send(self, *events: tuple[int, int, int]) -> None:
        if not self._open():
            return
        data = b"".join(EVENT.pack(0, 0, kind, code, value) for kind, code, value in events)
        try:
            os.write(self.fd, data + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
        except OSError:
            pass                                # a full queue drops a move: the next one comes in milliseconds

    def move(self, dx: float, dy: float) -> None:
        self.rest[0] += dx
        self.rest[1] += dy
        x, y = int(self.rest[0]), int(self.rest[1])
        if not x and not y:
            return
        self.rest[0] -= x
        self.rest[1] -= y
        self._send(*[(EV_REL, axis, value) for axis, value in ((REL_X, x), (REL_Y, y)) if value])

    def press(self, button: int, down: bool) -> None:
        self._send((EV_KEY, button, int(down)))

    def close(self) -> None:
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None
