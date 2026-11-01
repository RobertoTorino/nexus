# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's picture: Auto Exposure, kept while the app is open. In its own default exposure mode, Shutter Priority,
the camera keeps a short exposure and the picture is close to black (1920 x 1080 at 30 fps: an average of 0 of 255 in
a dim room); in Auto it is a normal picture (112). The BC250 Bazzite Suite's USB HD Cam sets Auto once after the load.
On Windows that does not last: Windows' webcam driver powers the camera down as soon as no program has it open (D3,
within seconds, whatever the power plan's USB selective suspend says), and the camera, which has no memory, wakes in
Shutter Priority again (the owner's ROG Xbox Ally X, 01-11-2026). So the app sets Auto through the driver and keeps
the camera's driver open, without taking its picture, while it runs: every app that shows the camera meanwhile gets
the bright picture.

The exposure is the kernel streaming property DirectShow's IAMCameraControl uses (PROPSETID_VIDCAP_CAMERACONTROL,
KSPROPERTY_CAMERACONTROL_EXPOSURE, IOCTL_KS_PROPERTY on the camera's KSCATEGORY_VIDEO_CAMERA interface), with the
standard library only. Nothing here needs an administrator."""

from __future__ import annotations

import ctypes
import time
import uuid
from collections.abc import Callable
from ctypes import wintypes as w

from . import devices

KSCATEGORY_VIDEO_CAMERA = "E5323777-F976-4F5B-9B55-B94699C46E44"
PROPSETID_VIDCAP_CAMERACONTROL = "C6E13370-30AC-11D0-A18C-00A0C9118956"
IOCTL_KS_PROPERTY = 0x2F0003
KSPROPERTY_TYPE_GET, KSPROPERTY_TYPE_SET = 0x1, 0x2
KSPROPERTY_CAMERACONTROL_EXPOSURE = 4
FLAGS_AUTO, FLAGS_MANUAL = 0x1, 0x2
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
TRIES, PAUSE_S = 6, 0.5                     # the camera may answer with its old mode while it wakes


class _Property(ctypes.Structure):
    _fields_ = [("Set", ctypes.c_ubyte * 16), ("Id", w.ULONG), ("Flags", w.ULONG)]


class _CameraControl(ctypes.Structure):
    """KSPROPERTY_CAMERACONTROL_S; 40 bytes on 64-bit Windows (KSPROPERTY's union aligns it to 8)."""
    _fields_ = [("Property", _Property), ("Value", w.LONG), ("Flags", w.ULONG), ("Capabilities", w.ULONG),
                ("Padding", w.ULONG)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, w.DWORD,
                                       ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    return kernel


class Driver:
    """The camera's driver, opened: the exposure mode read and set. *video* is the instance ID of the camera's video
    interface (camera.Camera.video)."""

    def __init__(self, video: str, kernel=None):
        self.kernel = kernel or _kernel()
        paths = devices.interfaces(video, KSCATEGORY_VIDEO_CAMERA)
        if not paths:
            raise OSError(None, "Windows has not set the webcam up yet.", None, 2)
        self.handle = self.kernel.CreateFileW(paths[0], GENERIC_READ | GENERIC_WRITE, 0x3, None, 3, 0, None)
        if not self.handle or self.handle == devices.INVALID_HANDLE:
            code = ctypes.get_last_error()
            raise OSError(None, f"The webcam could not be opened: {ctypes.FormatError(code).strip()}", None, code)

    def _call(self, kind: int, flags: int = 0) -> _CameraControl:
        request = _CameraControl()
        request.Property.Set[:] = list(uuid.UUID(PROPSETID_VIDCAP_CAMERACONTROL).bytes_le)
        request.Property.Id, request.Property.Flags = KSPROPERTY_CAMERACONTROL_EXPOSURE, kind
        request.Flags = flags
        answer = _CameraControl()
        got = w.DWORD()
        out = answer if kind == KSPROPERTY_TYPE_GET else request
        if not self.kernel.DeviceIoControl(self.handle, IOCTL_KS_PROPERTY, ctypes.byref(request),
                                           ctypes.sizeof(request), ctypes.byref(out), ctypes.sizeof(out),
                                           ctypes.byref(got), None):
            code = ctypes.get_last_error()
            raise OSError(None, f"The webcam did not answer: {ctypes.FormatError(code).strip()}", None, code)
        return answer

    def auto(self) -> bool:
        """Whether the exposure is automatic now."""
        return bool(self._call(KSPROPERTY_TYPE_GET).Flags & FLAGS_AUTO)

    def set_auto(self) -> None:
        self._call(KSPROPERTY_TYPE_SET, FLAGS_AUTO)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def keep(video: str, open_driver: Callable[[str], Driver] = Driver,
         sleep: Callable[[float], None] = time.sleep) -> Driver:
    """The camera's driver, opened and kept open by the caller, with Auto Exposure set and read back. Raises OSError
    with what went wrong (the driver closed again)."""
    driver = open_driver(video)
    try:
        for _ in range(TRIES):
            driver.set_auto()
            sleep(PAUSE_S)
            if driver.auto():
                return driver
        raise OSError(None, "The webcam kept its own exposure.", None, 0)
    except OSError:
        driver.close()
        raise
