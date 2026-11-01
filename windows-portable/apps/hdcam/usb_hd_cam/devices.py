# SPDX-License-Identifier: GPL-3.0-or-later
"""The USB devices Windows has, through its own Configuration Manager (cfgmgr32, ctypes): the present devices by
instance ID, each one's driver (its service), problem code, parent and port, its children, its interface paths, and
the speed its hub reports for it (IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2, as USBView reads it). Nothing here
needs an administrator. Off Windows every read finds nothing."""

from __future__ import annotations

import ctypes
import sys
import uuid
from dataclasses import dataclass
from ctypes import wintypes as w

CR_SUCCESS = 0
CM_GETIDLIST_FILTER_ENUMERATOR = 0x00000001
CM_GETIDLIST_FILTER_PRESENT = 0x00000100
CM_DRP_DEVICEDESC = 0x01
CM_DRP_SERVICE = 0x05
CM_DRP_FRIENDLYNAME = 0x0D
CM_DRP_ADDRESS = 0x1D
DN_HAS_PROBLEM = 0x00000400
GUID_DEVINTERFACE_USB_DEVICE = "A5DCBF10-6530-11D2-901F-00C04FB951ED"
GUID_DEVINTERFACE_USB_HUB = "F18A0E88-C30C-11D0-8815-00A0C906BED8"
IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2 = 0x22045C
USB300 = 0x4                                # USB_PROTOCOLS: ask about USB 3
OPERATING_SUPER, CAPABLE_SUPER, OPERATING_SUPER_PLUS = 0x1, 0x2, 0x4
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2
OPEN_EXISTING = 3
INVALID_HANDLE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class _ConnectionV2(ctypes.Structure):
    """USB_NODE_CONNECTION_INFORMATION_EX_V2 (usbioctl.h)."""
    _fields_ = [("ConnectionIndex", w.ULONG), ("Length", w.ULONG), ("SupportedUsbProtocols", w.ULONG),
                ("Flags", w.ULONG)]


@dataclass(frozen=True)
class Device:
    instance: str                           # USB\VID_05A9&PID_0580\7&1B484A56&0&1
    service: str                            # the driver's service: "WinUSB", "usbccgp", "" for none
    problem: int                            # 0: none; 28 (CM_PROB_FAILED_INSTALL): no driver
    parent: str
    port: int                               # its port on the parent hub; 0: not known
    name: str                               # the friendly name, else the description

    @property
    def ids(self) -> tuple[str, str]:
        """(vendor, product), lower case: ("05a9", "0580")."""
        head = self.instance.split("\\")[1].upper() if self.instance.count("\\") >= 2 else ""
        parts = dict(part.split("_", 1) for part in head.split("&") if "_" in part)
        return parts.get("VID", "").lower(), parts.get("PID", "").lower()


@dataclass(frozen=True)
class Speed:
    super_speed: bool                       # running at 5 Gbit/s or more
    capable: bool                           # the device could (on a USB 3 port)
    super_speed_plus: bool = False

    @property
    def text(self) -> str:
        if self.super_speed_plus:
            return "USB 3, 10 Gbit/s"
        if self.super_speed:
            return "USB 3, 5 Gbit/s"
        return "USB 2 or slower"


def _api():
    cfg = ctypes.WinDLL("cfgmgr32")
    cfg.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(w.ULONG), w.LPCWSTR, w.ULONG]
    cfg.CM_Get_Device_ID_ListW.argtypes = [w.LPCWSTR, ctypes.c_void_p, w.ULONG, w.ULONG]
    cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(w.DWORD), w.LPCWSTR, w.ULONG]
    cfg.CM_Get_Parent.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD, w.ULONG]
    cfg.CM_Get_Child.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD, w.ULONG]
    cfg.CM_Get_Sibling.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD, w.ULONG]
    cfg.CM_Get_Device_IDW.argtypes = [w.DWORD, ctypes.c_void_p, w.ULONG, w.ULONG]
    cfg.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(w.ULONG), ctypes.POINTER(w.ULONG), w.DWORD, w.ULONG]
    cfg.CM_Get_DevNode_Registry_PropertyW.argtypes = [w.DWORD, w.ULONG, ctypes.POINTER(w.ULONG), ctypes.c_void_p,
                                                      ctypes.POINTER(w.ULONG), w.ULONG]
    cfg.CM_Get_Device_Interface_List_SizeW.argtypes = [ctypes.POINTER(w.ULONG), ctypes.POINTER(GUID), w.LPCWSTR,
                                                       w.ULONG]
    cfg.CM_Get_Device_Interface_ListW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR, ctypes.c_void_p, w.ULONG, w.ULONG]
    return cfg


_cfg = None


def cfg():
    global _cfg
    if _cfg is None:
        _cfg = _api()
    return _cfg


def _multi(buffer) -> list[str]:
    return [part for part in ctypes.wstring_at(ctypes.addressof(buffer), len(buffer)).split("\0") if part]


def present(enumerator: str = "USB") -> list[str]:
    """The instance IDs of the present devices of *enumerator*."""
    if sys.platform != "win32":
        return []
    flags = CM_GETIDLIST_FILTER_ENUMERATOR | CM_GETIDLIST_FILTER_PRESENT
    size = w.ULONG()
    if cfg().CM_Get_Device_ID_List_SizeW(ctypes.byref(size), enumerator, flags) != CR_SUCCESS:
        return []
    buffer = ctypes.create_unicode_buffer(size.value + 1)
    if cfg().CM_Get_Device_ID_ListW(enumerator, buffer, len(buffer), flags) != CR_SUCCESS:
        return []
    return _multi(buffer)


def _node(instance: str) -> int | None:
    node = w.DWORD()
    return node.value if cfg().CM_Locate_DevNodeW(ctypes.byref(node), instance, 0) == CR_SUCCESS else None


def _id(node: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    return buffer.value if cfg().CM_Get_Device_IDW(node, buffer, len(buffer), 0) == CR_SUCCESS else ""


def _property(node: int, key: int) -> str | int | None:
    kind, size = w.ULONG(), w.ULONG(1024)
    buffer = ctypes.create_string_buffer(size.value)
    if cfg().CM_Get_DevNode_Registry_PropertyW(node, key, ctypes.byref(kind), buffer, ctypes.byref(size),
                                               0) != CR_SUCCESS:
        return None
    if kind.value == 4:                     # REG_DWORD
        return int.from_bytes(buffer.raw[:4], "little")
    return ctypes.wstring_at(ctypes.addressof(buffer), size.value // 2).split("\0")[0]


def info(instance: str) -> Device | None:
    """What Windows knows of a present device; None when it is not there."""
    if sys.platform != "win32":
        return None
    node = _node(instance)
    if node is None:
        return None
    status, problem = w.ULONG(), w.ULONG()
    if cfg().CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), node, 0) != CR_SUCCESS:
        return None
    parent = w.DWORD()
    parent_id = _id(parent.value) if cfg().CM_Get_Parent(ctypes.byref(parent), node, 0) == CR_SUCCESS else ""
    port = _property(node, CM_DRP_ADDRESS)
    name = _property(node, CM_DRP_FRIENDLYNAME) or _property(node, CM_DRP_DEVICEDESC) or ""
    return Device(instance=_id(node) or instance, service=str(_property(node, CM_DRP_SERVICE) or ""),
                  problem=problem.value if status.value & DN_HAS_PROBLEM else 0, parent=parent_id,
                  port=port if isinstance(port, int) else 0, name=str(name))


def children(instance: str) -> list[Device]:
    """The device's children (a composite device's interfaces, a hub's devices)."""
    node = _node(instance) if sys.platform == "win32" else None
    if node is None:
        return []
    found, child = [], w.DWORD()
    ok = cfg().CM_Get_Child(ctypes.byref(child), node, 0) == CR_SUCCESS
    while ok:
        device = info(_id(child.value))
        if device is not None:
            found.append(device)
        ok = cfg().CM_Get_Sibling(ctypes.byref(child), child.value, 0) == CR_SUCCESS
    return found


def interfaces(instance: str, guid: str) -> list[str]:
    """The device's interface paths of the class *guid* (what CreateFile opens)."""
    if sys.platform != "win32":
        return []
    key, size = GUID.of(guid), w.ULONG()
    if cfg().CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(key), instance, 0) != CR_SUCCESS:
        return []
    buffer = ctypes.create_unicode_buffer(size.value + 1)
    if cfg().CM_Get_Device_Interface_ListW(ctypes.byref(key), instance, buffer, len(buffer), 0) != CR_SUCCESS:
        return []
    return _multi(buffer)


def speed(device: Device) -> Speed | None:
    """How fast the device's port runs it, as its hub reports; None when the hub cannot be asked."""
    if sys.platform != "win32" or not device.port or not device.parent:
        return None
    hubs = interfaces(device.parent, GUID_DEVINTERFACE_USB_HUB)
    if not hubs:
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, w.DWORD,
                                       ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(hubs[0], GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0,
                                None)
    if not handle or handle == INVALID_HANDLE:
        return None
    try:
        asked = _ConnectionV2(ConnectionIndex=device.port, Length=ctypes.sizeof(_ConnectionV2),
                              SupportedUsbProtocols=USB300)
        got = w.DWORD()
        if not kernel.DeviceIoControl(handle, IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2, ctypes.byref(asked),
                                      ctypes.sizeof(asked), ctypes.byref(asked), ctypes.sizeof(asked),
                                      ctypes.byref(got), None):
            return None
        return Speed(super_speed=bool(asked.Flags & OPERATING_SUPER), capable=bool(asked.Flags & CAPABLE_SUPER),
                     super_speed_plus=bool(asked.Flags & OPERATING_SUPER_PLUS))
    finally:
        kernel.CloseHandle(handle)
