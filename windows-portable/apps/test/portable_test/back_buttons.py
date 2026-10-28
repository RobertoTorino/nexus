# SPDX-License-Identifier: GPL-3.0-or-later
"""The back buttons M1 and M2 of an ASUS handheld (the ROG Xbox Ally X), which never reach Windows as gamepad buttons:
Armoury Crate keeps them as its own modifiers. Its controller reports them on a vendor HID channel of its own (usage
page 0xFF31, usage 0x76; Linux's hid-asus reads the ROG keys there), which opens for reading without administrator
rights while Armoury Crate runs: report 5A A5 when either back button goes down and 5A 00 when it is let go. Both send
the same code, so Windows cannot tell M1 from M2 (seen on the owner's Ally X, 28-10-2026); held with A they send A0,
Armoury Crate's screenshot. Read with ctypes over setupapi, hid.dll and a blocking ReadFile in a thread."""

from __future__ import annotations

import ctypes
import re
import sys
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

ASUS = 0x0B05                           # the vendor id: every ASUS handheld's controller
PAGE, USAGE = 0xFF31, 0x76              # the vendor channel's top collection
REPORT = 0x5A                           # its report id
PRESSED = 0xA5                          # a back button down (M1 and M2 alike); 0x00: let go
GENERIC_READ, SHARE, OPEN_EXISTING = 0x80000000, 0x3, 3
PRESENT_INTERFACES = 0x12               # DIGCF_PRESENT | DIGCF_DEVICEINTERFACE


def parse(report: bytes) -> bool | None:
    """True for a back button pressed, False for let go, None for a report about something else (a combination with
    another button, the Armoury Crate key)."""
    if len(report) < 2 or report[0] != REPORT:
        return None
    if report[1] == PRESSED:
        return True
    if report[1] == 0:
        return False
    return None


class _Guid(ctypes.Structure):
    _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD), ("data3", wintypes.WORD),
                ("data4", ctypes.c_ubyte * 8)]


class _Interface(ctypes.Structure):     # SP_DEVICE_INTERFACE_DATA
    _fields_ = [("size", wintypes.DWORD), ("guid", _Guid), ("flags", wintypes.DWORD),
                ("reserved", ctypes.c_size_t)]


class _Caps(ctypes.Structure):          # HIDP_CAPS
    _fields_ = [("usage", wintypes.USHORT), ("usage_page", wintypes.USHORT), ("input_length", wintypes.USHORT),
                ("output_length", wintypes.USHORT), ("feature_length", wintypes.USHORT),
                ("reserved", wintypes.USHORT * 17), ("counts", wintypes.USHORT * 10)]


def _apis():
    setupapi, hid = ctypes.WinDLL("setupapi"), ctypes.WinDLL("hid")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    kernel.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_Guid), ctypes.c_wchar_p, ctypes.c_void_p,
                                              wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_Guid),
                                                     wintypes.DWORD, ctypes.POINTER(_Interface)]
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Interface),
                                                          ctypes.c_void_p, wintypes.DWORD,
                                                          ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    hid.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Caps)]
    return setupapi, hid, kernel


def _paths(setupapi, hid):
    """Every present HID interface's path."""
    guid = _Guid()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devices = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, PRESENT_INTERFACES)
    try:
        index = 0
        while True:
            interface = _Interface(size=ctypes.sizeof(_Interface))
            if not setupapi.SetupDiEnumDeviceInterfaces(devices, None, ctypes.byref(guid), index,
                                                        ctypes.byref(interface)):
                return
            index += 1
            need = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(devices, ctypes.byref(interface), None, 0, ctypes.byref(need),
                                                      None)
            detail = ctypes.create_string_buffer(need.value)
            ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(devices, ctypes.byref(interface), detail, need, None, None):
                yield ctypes.wstring_at(ctypes.addressof(detail) + 4)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devices)


def find() -> tuple[str, int] | None:
    """The ASUS vendor channel's path and its report length; None without one, or not on Windows."""
    if sys.platform != "win32":
        return None
    setupapi, hid, kernel = _apis()
    for path in _paths(setupapi, hid):
        if not re.search(rf"vid_{ASUS:04x}&", path, re.I):
            continue
        handle = kernel.CreateFileW(path, 0, SHARE, None, OPEN_EXISTING, 0, None)      # no access: the caps only
        if handle in (None, ctypes.c_void_p(-1).value):
            continue
        caps, preparsed = _Caps(), ctypes.c_void_p()
        try:
            if hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
                hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
                hid.HidD_FreePreparsedData(preparsed)
        finally:
            kernel.CloseHandle(handle)
        if (caps.usage_page, caps.usage) == (PAGE, USAGE) and caps.input_length:
            return path, caps.input_length
    return None


class Reader(QObject):
    """Reads the back buttons in a thread while the app runs; changed(held) arrives on the window's thread."""

    changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._handle = None
        self._kernel = None

    def start(self) -> bool:
        """Opens the channel; False when the handheld has none (another maker's, or no Armoury Crate driver)."""
        found = find()
        if found is None:
            return False
        path, length = found
        _, _, kernel = _apis()
        handle = kernel.CreateFileW(path, GENERIC_READ, SHARE, None, OPEN_EXISTING, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            return False
        self._handle, self._kernel = handle, kernel
        threading.Thread(target=self._run, args=(handle, length), daemon=True).start()
        return True

    def _run(self, handle, length: int) -> None:
        buffer, got = ctypes.create_string_buffer(length), wintypes.DWORD()
        while self._kernel is not None and self._kernel.ReadFile(handle, buffer, length, ctypes.byref(got), None):
            held = parse(buffer.raw[:got.value])
            if held is not None:
                self.changed.emit(held)

    def stop(self) -> None:
        kernel, handle = self._kernel, self._handle
        self._kernel = self._handle = None
        if kernel is not None:
            kernel.CancelIoEx(handle, None)             # ends the thread's waiting ReadFile
            kernel.CloseHandle(handle)
