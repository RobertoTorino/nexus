# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture controls (brightness, contrast, gain, exposure, white balance, ...) through V4L2's control
ioctls on its /dev/video<n> node, with the standard library only. Every control the camera reports is offered, with
its own range and default. They work while a picture streams, in this app or another. The camera forgets them when
it is unplugged, so the app keeps the values the user chose and sets them again each time the camera is ready.
Errors come as OSError with the kernel's errno."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
from dataclasses import dataclass, field

INTEGER, BOOLEAN, MENU, BUTTON, INTEGER64, CTRL_CLASS = 1, 2, 3, 4, 5, 6
FLAG_DISABLED, FLAG_READ_ONLY, FLAG_INACTIVE = 0x01, 0x04, 0x10
NEXT_CTRL = 0x80000000


class QueryCtrl(ctypes.Structure):
    """struct v4l2_queryctrl (linux/videodev2.h)."""
    _fields_ = [("id", ctypes.c_uint32), ("type", ctypes.c_uint32), ("name", ctypes.c_char * 32),
                ("minimum", ctypes.c_int32), ("maximum", ctypes.c_int32), ("step", ctypes.c_int32),
                ("default_value", ctypes.c_int32), ("flags", ctypes.c_uint32), ("reserved", ctypes.c_uint32 * 2)]


class QueryMenu(ctypes.Structure):
    """struct v4l2_querymenu, packed in C: the name (or a value) in a 32-byte union. As a char array the union needs
    no padding, so ctypes lays it out the same, at 44 bytes."""
    _fields_ = [("id", ctypes.c_uint32), ("index", ctypes.c_uint32), ("name", ctypes.c_char * 32),
                ("reserved", ctypes.c_uint32)]


class Ctrl(ctypes.Structure):
    """struct v4l2_control."""
    _fields_ = [("id", ctypes.c_uint32), ("value", ctypes.c_int32)]


def _iowr(number: int, size: int) -> int:
    return (3 << 30) | (size << 16) | (ord("V") << 8) | number


QUERYCTRL = _iowr(36, ctypes.sizeof(QueryCtrl))
QUERYMENU = _iowr(37, ctypes.sizeof(QueryMenu))
G_CTRL = _iowr(27, ctypes.sizeof(Ctrl))
S_CTRL = _iowr(28, ctypes.sizeof(Ctrl))


@dataclass(frozen=True)
class Control:
    id: int
    kind: int
    name: str
    minimum: int
    maximum: int
    step: int
    default: int
    value: int
    flags: int
    menu: dict[int, str] = field(default_factory=dict)      # index -> name, for a MENU

    @property
    def key(self) -> str:
        """The name the settings keep it under: the driver's name in lower case, words joined by _."""
        return "_".join("".join(c if c.isalnum() else " " for c in self.name).lower().split())

    @property
    def active(self) -> bool:
        """False while another control decides it (an exposure time while the exposure is automatic)."""
        return not self.flags & (FLAG_DISABLED | FLAG_READ_ONLY | FLAG_INACTIVE)


def _ioctl(fd: int, request: int, argument) -> None:
    fcntl.ioctl(fd, request, argument)


class Camera:
    """An open video node. *ioctl* is (fd, request, ctypes structure) -> None, raising OSError; tests pass their own."""

    def __init__(self, node: str | os.PathLike, ioctl=_ioctl, open_node=None):
        self.fd = (open_node or (lambda path: os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)))(node)
        self._ioctl = ioctl

    def _menu(self, query: QueryCtrl) -> dict[int, str]:
        items = {}
        for index in range(query.minimum, query.maximum + 1):
            item = QueryMenu(id=query.id, index=index)
            try:
                self._ioctl(self.fd, QUERYMENU, item)
            except OSError:
                continue                    # a gap: the camera offers only some of the menu's values
            items[index] = item.name.decode(errors="replace")
        return items

    def list(self) -> list[Control]:
        found = []
        query = QueryCtrl(id=NEXT_CTRL)
        while True:
            try:
                self._ioctl(self.fd, QUERYCTRL, query)
            except OSError as exc:
                if exc.errno == errno.EINVAL:   # no more controls
                    break
                raise
            if query.type in (INTEGER, BOOLEAN, MENU) and not query.flags & FLAG_DISABLED:
                found.append(Control(query.id, query.type, query.name.decode(errors="replace"), query.minimum,
                                     query.maximum, query.step, query.default_value, self.get(query.id),
                                     query.flags, self._menu(query) if query.type == MENU else {}))
            query = QueryCtrl(id=query.id | NEXT_CTRL)
        return found

    def get(self, control_id: int) -> int:
        control = Ctrl(id=control_id)
        self._ioctl(self.fd, G_CTRL, control)
        return control.value

    def set(self, control_id: int, value: int) -> None:
        self._ioctl(self.fd, S_CTRL, Ctrl(id=control_id, value=value))

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


def apply(camera: Camera, chosen: dict[str, int]) -> list[str]:
    """Sets the values the user chose (by key) on the controls the camera has; the names of those it refused. The
    exposure mode goes first, as it decides whether the exposure time may be set. Each is written even when it reads
    the same: the driver answers from what it last set, and a camera that was suspended has forgotten it (owner's
    board, 23-10-2026: Auto Mode read back while the camera exposed in its dark default)."""
    refused = []
    listed = sorted(camera.list(), key=lambda c: c.kind != MENU and c.kind != BOOLEAN)
    for control in listed:
        if control.key in chosen:
            try:
                camera.set(control.id, chosen[control.key])
            except OSError:
                refused.append(control.name)
    return refused
