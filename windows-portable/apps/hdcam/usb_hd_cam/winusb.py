# SPDX-License-Identifier: GPL-3.0-or-later
"""A USB device through Microsoft's WinUSB driver (winusb.dll, ctypes): the few calls the firmware upload needs, with
the standard library only, so the app needs no libusb. The device must have WinUSB as its driver (driver.py binds
it); then a user opens it without an administrator. Errors come as OSError with Windows' error code."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

from . import devices

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_TRANSFER_TIMEOUT = 0x03
TIMEOUT_MS = 2000


class SetupPacket(ctypes.Structure):
    """WINUSB_SETUP_PACKET (winusbio.h)."""
    _pack_ = 1
    _fields_ = [("RequestType", ctypes.c_ubyte), ("Request", ctypes.c_ubyte), ("Value", w.USHORT),
                ("Index", w.USHORT), ("Length", w.USHORT)]


def _apis():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    usb = ctypes.WinDLL("winusb", use_last_error=True)
    usb.WinUsb_Initialize.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    usb.WinUsb_Free.argtypes = [ctypes.c_void_p]
    usb.WinUsb_SetPipePolicy.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, w.ULONG, w.ULONG, ctypes.c_void_p]
    usb.WinUsb_ControlTransfer.argtypes = [ctypes.c_void_p, SetupPacket, ctypes.c_void_p, w.ULONG,
                                           ctypes.POINTER(w.ULONG), ctypes.c_void_p]
    return kernel, usb


def _error(what: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(None, f"{what}: {ctypes.FormatError(code).strip()}", None, code)


class Device:
    """A device opened through WinUSB by its instance ID (the shape of the Bazzite app's usbfs.Device: the upload
    calls reset, set_configuration and claim_interface, which WinUSB does by itself, then control_out)."""

    def __init__(self, instance: str, apis=None):
        self.kernel, self.usb = apis or _apis()
        paths = devices.interfaces(instance, devices.GUID_DEVINTERFACE_USB_DEVICE)
        if not paths:
            raise OSError(None, "The camera is gone, or Windows has not set it up yet.", None, 2)
        self.file = self.kernel.CreateFileW(paths[0], GENERIC_READ | GENERIC_WRITE, 0x3, None, 3,
                                            FILE_FLAG_OVERLAPPED, None)
        if not self.file or self.file == devices.INVALID_HANDLE:
            raise _error("Opening the camera failed")
        self.handle = ctypes.c_void_p()
        if not self.usb.WinUsb_Initialize(self.file, ctypes.byref(self.handle)):
            error = _error("WinUSB did not take the camera")
            self.kernel.CloseHandle(self.file)
            raise error
        timeout = w.ULONG(TIMEOUT_MS)
        self.usb.WinUsb_SetPipePolicy(self.handle, 0, PIPE_TRANSFER_TIMEOUT, ctypes.sizeof(timeout),
                                      ctypes.byref(timeout))

    def reset(self) -> None:
        """WinUSB has no device reset (the Bazzite app's starts a boot loader left halfway clean): after an upload
        that failed halfway, unplugging the camera does it."""

    def set_configuration(self, value: int) -> None:
        """WinUSB selects the first configuration by itself."""

    def claim_interface(self, number: int) -> None:
        """WinUSB's handle is interface 0's."""

    def control_out(self, request_type: int, request: int, value: int, index: int, data: bytes) -> int:
        packet = SetupPacket(request_type, request, value, index, len(data))
        buffer = ctypes.create_string_buffer(bytes(data), len(data))
        sent = w.ULONG()
        if not self.usb.WinUsb_ControlTransfer(self.handle, packet, buffer, len(data), ctypes.byref(sent), None):
            raise _error("The camera did not take the transfer")
        return sent.value

    def close(self) -> None:
        if self.handle:
            self.usb.WinUsb_Free(self.handle)
            self.handle = ctypes.c_void_p()
        if self.file:
            self.kernel.CloseHandle(self.file)
            self.file = None
