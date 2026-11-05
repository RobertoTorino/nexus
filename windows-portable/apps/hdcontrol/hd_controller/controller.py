# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the controllers: each DualSense and DualSense Edge Windows has as a HID device, by hidapi's list of them
(what Windows reports: its USB IDs, its connection, USB or Bluetooth, and its path), and the firmware report (0x20) that
says which firmware runs. A controller's path names it inside the app only: over Bluetooth it holds the controller's
address, so it is never shown and never logged (the BC250 app's controller.py, with hidapi's list in place of /sys)."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .hiddevice import Device

VENDOR = 0x054C
MODELS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
EDGE = 0x0DF2
BUSES = {1: "usb", 2: "bluetooth"}          # hidapi's bus_type
CONNECTIONS = {"usb": "USB cable", "bluetooth": "Bluetooth"}
BLUETOOTH_HID = "{00001124-0000-1000-8000-00805f9b34fb}"    # in a Bluetooth HID device's path, for an older hidapi
GAMEPAD = (0x01, 0x05)                      # the controller's top-level collection: Generic Desktop, Game Pad
REPORT_FIRMWARE = 0x20
NOT_FOUND = ("Plug the controller in with a USB cable, or pair it over Bluetooth: hold Create and the PS button "
             "until the light bar flashes, then pair it in Windows' Bluetooth settings.")
# The programs that talk to the controller themselves (owner's rule, the BC250 app's: nothing else talks to the
# controller during a firmware update): their program's name, and how they are named on the screen.
TALKERS = {"steam.exe": "Steam", "ds4windows.exe": "DS4Windows", "dsx.exe": "DSX", "dualsensex.exe": "DualSenseX"}


@dataclass(frozen=True)
class Battery:
    capacity: int | None            # percent, as the controller reports it in its input reports
    status: str                     # "Charging", "Discharging", "Full", "Not charging", "Unknown"


@dataclass(frozen=True)
class Controller:
    path: bytes                     # hidapi's path: the app's own key, never shown
    product: int
    bus: str                        # BUSES

    @property
    def name(self) -> str:
        return MODELS[self.product]

    @property
    def edge(self) -> bool:
        return self.product == EDGE

    @property
    def connection(self) -> str:
        return CONNECTIONS.get(self.bus, self.bus)


@dataclass(frozen=True)
class FirmwareInfo:
    """Report 0x20, as Linux's hid-playstation reads it: the update version is what Sony's server lists and the
    update image carries (0x0217), the target is the image's FWUPDATE<target> (the DualSense Edge's is 0x0044)."""
    build_date: str
    build_time: str
    target: int
    hardware: int
    firmware: int
    update: int


def _ascii(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("ascii", "replace").strip()


def parse_info(data: bytes) -> FirmwareInfo:
    if len(data) < 46 or data[0] != REPORT_FIRMWARE:
        raise ValueError("the controller's firmware report is too short")
    word = lambda offset, size: int.from_bytes(data[offset:offset + size], "little")  # noqa: E731
    return FirmwareInfo(_ascii(data[1:12]), _ascii(data[12:20]), word(22, 2), word(24, 4), word(28, 4), word(44, 2))


def read_info(device: Device) -> FirmwareInfo:
    return parse_info(device.get_feature(REPORT_FIRMWARE))


def _bus(entry: dict[str, Any]) -> str:
    """USB or Bluetooth, as hidapi says it; an older hidapi without bus_type: a Bluetooth HID device's path."""
    bus = BUSES.get(entry.get("bus_type") or 0)
    if bus:
        return bus
    return "bluetooth" if BLUETOOTH_HID in bytes(entry.get("path") or b"").decode("ascii", "replace").lower() else "usb"


def _enumerate() -> list[dict[str, Any]]:
    import hid                                      # hidapi: only where it is needed
    return hid.enumerate(VENDOR, 0)


def find(enumerate_: Callable[[], list[dict[str, Any]]] = _enumerate) -> list[Controller]:
    """Every DualSense and DualSense Edge, USB ones first (only they take a firmware update). [] without hidapi."""
    try:
        entries = enumerate_()
    except (ImportError, OSError):
        return []
    found, seen = [], set()
    for entry in entries:
        product = entry.get("product_id")
        if entry.get("vendor_id") != VENDOR or product not in MODELS:
            continue
        usage = (entry.get("usage_page"), entry.get("usage"))
        if usage != (0, 0) and usage != GAMEPAD:     # another collection of the same device, if Windows has one
            continue
        path = bytes(entry.get("path") or b"")
        if not path or path in seen:
            continue
        seen.add(path)
        found.append(Controller(path, product, _bus(entry)))
    return sorted(found, key=lambda c: c.bus != "usb")


class _Entry(ctypes.Structure):                 # PROCESSENTRY32W
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


def programs() -> set[str]:
    """The program names of the running processes, in lower case (steam.exe); empty off Windows."""
    if sys.platform != "win32":
        return set()
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)    # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return set()
    found = set()
    try:
        entry = _Entry()
        entry.size = ctypes.sizeof(_Entry)
        more = k32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while more:
            found.add(entry.exe.lower())
            more = k32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snapshot))
    return found


def holders(running: Callable[[], set[str]] = programs) -> list[str]:
    """The programs running now that talk to the controller themselves (Steam reads it and sets its light bar):
    Windows does not tell a user which programs have a device open, so they are known by name (TALKERS)."""
    names = running()
    return sorted(name for exe, name in TALKERS.items() if exe in names)
