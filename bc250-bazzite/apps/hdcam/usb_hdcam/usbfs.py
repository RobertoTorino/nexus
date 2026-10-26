# SPDX-License-Identifier: GPL-3.0-or-later
"""A USB device through the kernel's usbfs (/dev/bus/usb/<bus>/<device>): the few ioctls the firmware upload needs,
with the standard library only, so the app needs no libusb binding in the suite's shared venv. Errors come as
OSError with the kernel's errno."""

from __future__ import annotations

import ctypes
import os

_IOC_WRITE, _IOC_READ = 1, 2


def _ioc(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("U") << 8) | number


class CtrlTransfer(ctypes.Structure):
    """struct usbdevfs_ctrltransfer (linux/usbdevice_fs.h)."""
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8), ("wValue", ctypes.c_uint16),
                ("wIndex", ctypes.c_uint16), ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


CONTROL = _ioc(_IOC_READ | _IOC_WRITE, 0, ctypes.sizeof(CtrlTransfer))
SETCONFIGURATION = _ioc(_IOC_READ, 5, ctypes.sizeof(ctypes.c_uint))
CLAIMINTERFACE = _ioc(_IOC_READ, 15, ctypes.sizeof(ctypes.c_uint))
RELEASEINTERFACE = _ioc(_IOC_READ, 16, ctypes.sizeof(ctypes.c_uint))
RESET = _ioc(0, 20, 0)


def _libc_ioctl():
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.ioctl
    function.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
    function.restype = ctypes.c_int
    return function


class Device:
    """An open usbfs node. *ioctl* is libc's (fd, request, pointer) -> int; tests pass their own."""

    def __init__(self, node: str | os.PathLike, ioctl=None):
        self.fd = os.open(node, os.O_RDWR | os.O_CLOEXEC)
        self._ioctl = ioctl or _libc_ioctl()

    def _call(self, request: int, argument) -> int:
        result = self._ioctl(self.fd, request, ctypes.addressof(argument) if argument is not None else None)
        if result < 0:
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number))
        return result

    def reset(self) -> None:
        self._call(RESET, None)

    def set_configuration(self, value: int) -> None:
        self._call(SETCONFIGURATION, ctypes.c_uint(value))

    def claim_interface(self, number: int) -> None:
        self._call(CLAIMINTERFACE, ctypes.c_uint(number))

    def control_out(self, request_type: int, request: int, value: int, index: int, data: bytes,
                    timeout_ms: int = 1000) -> int:
        """A control transfer from the host to the device; the number of bytes the device took."""
        buffer = ctypes.create_string_buffer(bytes(data), len(data))
        transfer = CtrlTransfer(request_type, request, value, index, len(data), timeout_ms,
                                ctypes.cast(buffer, ctypes.c_void_p))
        return self._call(CONTROL, transfer)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
