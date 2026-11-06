# SPDX-License-Identifier: GPL-3.0-or-later
"""The drives as Windows reports them, read without an administrator (owner, 06-11-2026: the BC250 Bazzite Suite's
SSD Check on the handheld; no serial number, no firmware update check, a SATA drive's specs only).

- The list: one PowerShell query of Windows' storage inventory (CIM's MSFT_PhysicalDisk: the model, the bus, the
  size, the firmware; MSFT_Partition: the drive letters; Win32_DiskDrive: the drive's device), returned as JSON. The
  serial number is never asked for.
- The link: from the drive's device up its parents in Device Manager (cfgmgr32's CM_Get_Parent and the devices'
  DEVPKEY_PciDevice_CurrentLinkSpeed and _Width, and the Max of each): the first with a link is the NVMe controller
  (or the card reader), the one above it the port. Through Windows' own API, as Get-PnpDeviceProperty took half a
  second a device. The devices' instance IDs, which can carry a serial number, are used for this walk only: never
  shown, logged or kept.
- NVMe: the drive's SMART / health log (log page 2) through the storage driver (IOCTL_STORAGE_QUERY_PROPERTY,
  StorageDeviceProtocolSpecificProperty) on \\\\.\\PhysicalDriveN, opened without any access right: that needs no
  administrator. It gives the percentage used (health is 100 minus it; it passes 100 when the drive outlives its
  rated endurance, so health stops at 0), the power cycles, the power-on hours, the data read and written (in units
  of 512,000 bytes) and the critical warning's flags. The controller's Identify data gives its NVMe version (only
  that field is read from it).
- SATA: its SMART values need an administrator on Windows (SMART_RCV_DRIVE_DATA opens the drive for reading), so a
  SATA drive shows its specs only (owner, 06-11-2026). A drive on USB or in the card reader has no SMART that Windows
  passes on; its specs show.

Windows does not report the PCIe link of every port: the Ally X's NVMe controller gives its link (PCIe 4.0 x4, now
and at most), its port gives none, so the board's side stays unknown there."""

from __future__ import annotations

import ctypes
import json
import struct
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from bc250_core.platform import powershell_argv

from . import rated

QUERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$letters = @{}
Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_Partition | Where-Object { [int]$_.DriveLetter } |
    ForEach-Object { $letters[[string]$_.DiskNumber] = @($letters[[string]$_.DiskNumber]) + @([string][char]$_.DriveLetter) }
$pnp = @{}
Get-CimInstance Win32_DiskDrive | ForEach-Object { $pnp[[string]$_.Index] = [string]$_.PNPDeviceID }
$drives = @(Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk | ForEach-Object {
    $raw = $_.CimInstanceProperties
    [pscustomobject]@{ number = [int]$_.DeviceId; model = ([string]$_.FriendlyName).Trim(); bus = [int]$raw['BusType'].Value
                       media = [int]$raw['MediaType'].Value; size = [int64]$_.Size
                       firmware = ([string]$_.FirmwareVersion).Trim(); device = $pnp[[string]$_.DeviceId]
                       letters = @($letters[[string]$_.DeviceId] | Where-Object { $_ }) } })
ConvertTo-Json -InputObject $drives -Depth 3 -Compress
"""
TIMEOUT = 60                    # s: the query took about a second on the Ally X (06-11-2026)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# MSFT_PhysicalDisk's BusType
BUSES = {1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre Channel", 7: "USB", 8: "RAID", 9: "iSCSI",
         10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 17: "NVMe"}
NVME, SATA_BUSES, USB = 17, (3, 11), 7
VIRTUAL = (14, 15, 16)          # a virtual drive, a file-backed one (a VHD), Storage Spaces: not a drive to check
HDD = 3                         # MSFT_PhysicalDisk's MediaType
# DEVPKEY_PciDevice_*LinkSpeed: the PCIe generation; what a lane of it carries at most, in MB/s, after its line code
PCIE_GENERATIONS = {1: "1.0", 2: "2.0", 3: "3.0", 4: "4.0", 5: "5.0", 6: "6.0"}
PCIE_LANE_MBPS = {"1.0": 250, "2.0": 500, "3.0": 985, "4.0": 1969, "5.0": 3938, "6.0": 7563}

# The NVMe health log's critical warning, bit by bit
WARNINGS = ("spare", "temperature", "degraded", "readonly", "volatile_mem", "pmr_readonly")
DATA_UNIT = 512_000             # the log's data units: thousands of 512-byte blocks

IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
PROTOCOL_SPECIFIC_PROPERTY = 50     # StorageDeviceProtocolSpecificProperty
PROTOCOL_NVME = 3
NVME_IDENTIFY, NVME_LOG_PAGE = 1, 2  # NVMeDataTypeIdentify, NVMeDataTypeLogPage
IDENTIFY_CONTROLLER, HEALTH_LOG = 1, 2
QUERY_HEADER = 8                    # STORAGE_PROPERTY_QUERY: PropertyId, QueryType
SPECIFIC_DATA = 40                  # STORAGE_PROTOCOL_SPECIFIC_DATA

NO_SMART_SATA = ("Windows lets only an administrator read a SATA drive's SMART values: its health, power cycles and "
                 "hours stay empty. Its specs show.")
NO_SMART_USB = ("Windows passes no SMART values through the drive's USB adapter: health, power cycles, hours and the "
                "data read and written stay empty. Its specs show.")
NO_SMART_READER = ("A memory card reports no SMART values: health, power cycles, hours and the data read and written "
                   "stay empty. Its specs show.")
NO_SMART = "The drive gave no SMART values to Windows' storage driver."

Run = Callable[[list[str]], str]                    # powershell argv -> its output
Query = Callable[[int, int, int, int], bytes | None]   # drive, data type, request, length -> the data, or None
Walk = Callable[[str], "DevicePath"]                      # a device's instance ID -> its path up to the root (device_path)


class DrivesError(RuntimeError):
    pass


@dataclass
class Drive:
    number: int                             # \\.\PhysicalDriveN, as Disk Management numbers it
    model: str
    size: int = 0                           # bytes
    bus: str = ""                           # "NVMe", "SATA", "USB", "SD card", ...
    kind: str = ""                          # what the window calls it: "NVMe drive", "SD card", ...
    smart: bool = False                     # the health log was read
    smart_note: str = ""                    # why there are no SMART values
    health: int | None = None               # percent of its life left
    power_cycles: int | None = None
    hours: int | None = None
    warnings: list[str] = field(default_factory=list)   # what the drive itself flags
    data_read: int | None = None            # bytes the host read and wrote in all
    data_written: int | None = None
    firmware: str = ""
    interface: str = ""                     # "NVMe 2.0", "SATA", "USB", "SD card"
    speed: str = ""                         # the link now: "PCIe 4.0 x4"
    speed_tip: str = ""                     # what the drive's link could do
    link_mbps: int | None = None            # what the link now carries at most, MB/s
    drive_mbps: int | None = None           # what the drive's own fastest link carries
    board_link: str = ""                    # the port: the most it offers
    board_mbps: int | None = None
    rated_read: int | None = None           # the maker's rated speeds, MB/s (rated.py); None: not in the list
    rated_write: int | None = None
    letters: list[str] = field(default_factory=list)    # its partitions' drive letters

    @property
    def label(self) -> str:
        return " · ".join(p for p in (self.model or "Unknown drive", size_text(self.size) if self.size else "") if p)


def size_text(size: int) -> str:
    """Bytes as a drive's label gives them: decimal units (a 2 TB drive is 2.0 TB)."""
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "kB") else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def pcie(speed: int, width: int) -> str:
    """"PCIe 4.0 x4" from Windows' link speed (the generation, 4) and width; "" when unknown."""
    generation = PCIE_GENERATIONS.get(speed, "")
    return f"PCIe {generation} x{width}" if generation and width > 0 else ""


def pcie_mbps(speed: int, width: int) -> int | None:
    lane = PCIE_LANE_MBPS.get(PCIE_GENERATIONS.get(speed, ""))
    return lane * width if lane and width > 0 else None


def held_back(drive: Drive) -> bool | None:
    """Whether the port carries less than the drive can do (its rated read, else its fastest link); None when either
    is unknown."""
    can = drive.rated_read or drive.drive_mbps
    return None if not (can and drive.board_mbps) else drive.board_mbps < can


def link(drive: Drive, links: list) -> None:
    """The drive's PCIe link from its devices, the disk first and then up its parents: the first with a link now is
    the drive's controller (now and its most), and the device above it is the port (its most is the board's side)."""
    rows = [[int(n or 0) for n in row] + [0] * (4 - len(row)) for row in links if isinstance(row, list)]
    for n, (speed, width, most_speed, most_width) in enumerate(rows):
        if not pcie(speed, width):
            continue
        now, most = pcie(speed, width), pcie(most_speed, most_width)
        drive.speed = now
        drive.speed_tip = (f"The link could do {most}" if most and most != now else
                           "The link runs as fast as the drive goes")
        drive.link_mbps, drive.drive_mbps = pcie_mbps(speed, width), pcie_mbps(most_speed, most_width)
        if n + 1 < len(rows) and pcie(rows[n + 1][2], rows[n + 1][3]):
            port = rows[n + 1]
            drive.board_link, drive.board_mbps = pcie(port[2], port[3]), pcie_mbps(port[2], port[3])
        return


def health_values(drive: Drive, log: bytes) -> None:
    """The NVMe SMART / health log (512 bytes) into *drive*."""
    def number(start: int, length: int) -> int:
        return int.from_bytes(log[start:start + length], "little")
    drive.smart = True
    drive.warnings = [name for bit, name in enumerate(WARNINGS) if log[0] >> bit & 1]
    drive.health = max(0, 100 - log[5])
    drive.data_read, drive.data_written = number(32, 16) * DATA_UNIT, number(48, 16) * DATA_UNIT
    drive.power_cycles, drive.hours = number(112, 16), number(128, 16)


def nvme_version(identify: bytes) -> str:
    """"NVMe 2.0" from the controller's Identify data (VER, bytes 80 to 83); "NVMe" when it does not say."""
    if len(identify) < 84:
        return "NVMe"
    tertiary, minor, major = identify[80], identify[81], int.from_bytes(identify[82:84], "little")
    if not major:
        return "NVMe"
    return f"NVMe {major}.{minor}" + (f".{tertiary}" if tertiary else "")


def protocol_query(number: int, data_type: int, request: int, length: int) -> bytes | None:
    """The drive's NVMe data (Identify or a log page) through the storage driver, on the drive opened without any
    access right, so no administrator is needed; None when Windows or the drive does not give it."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                         ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateFileW(rf"\\.\PhysicalDrive{number}", 0, 3, None, 3, 0, None)    # no access right
    if handle in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        # STORAGE_PROPERTY_QUERY (PropertyId, QueryType: PropertyStandardQuery), then STORAGE_PROTOCOL_SPECIFIC_DATA
        # (ProtocolType, DataType, RequestValue, RequestSubValue, DataOffset, DataLength, then reserved fields)
        query = struct.pack("<II", PROTOCOL_SPECIFIC_PROPERTY, 0) + struct.pack(
            "<IIIIII", PROTOCOL_NVME, data_type, request, 0, SPECIFIC_DATA, length) + bytes(16)
        buffer = ctypes.create_string_buffer(query, len(query) + length)
        got = wintypes.DWORD()
        if not kernel32.DeviceIoControl(handle, IOCTL_STORAGE_QUERY_PROPERTY, buffer, len(buffer), buffer,
                                        len(buffer), ctypes.byref(got), None):
            return None
        start = QUERY_HEADER + SPECIFIC_DATA
        return buffer.raw[start:start + length] if got.value >= start + length else None
    finally:
        kernel32.CloseHandle(handle)


@dataclass
class DevicePath:
    """A drive's device and its parents, as device_path() found them: each one's PCIe link (current speed and width,
    then the most of each; zeros when it has none), and whether a USB device or a card reader is on the way."""
    links: list[list[int]] = field(default_factory=list)
    usb: bool = False
    reader: bool = False


USB_IDS = ("USB\\", "USBSTOR\\", "UASPSTOR\\")
READER_IDS = ("SD\\", "SDBUS\\", "GLREADER\\", "RTSUER\\", "RTSPER\\")      # SD host, Genesys's, Realtek's
DEPTH = 8                           # parents looked at at most
# DEVPKEY_PciDevice_CurrentLinkSpeed, _CurrentLinkWidth, _MaxLinkSpeed, _MaxLinkWidth (pciprop.h)
PCI_PROPERTIES = "{3AB22E31-8264-4B4E-9AF5-A8D2D8E33E62}"
LINK_KEYS = (9, 10, 11, 12)


def device_path(instance_id: str) -> DevicePath:
    """The PCIe links of the device *instance_id* and its parents, through cfgmgr32 (CM_Locate_DevNodeW,
    CM_Get_DevNode_PropertyW, CM_Get_Parent); an empty DevicePath off Windows or when the device is not found. The IDs
    stay in this function."""
    found = DevicePath()
    if sys.platform != "win32" or not instance_id:
        return found
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class DEVPROPKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]

    cfgmgr = ctypes.WinDLL("cfgmgr32")
    ole32 = ctypes.WinDLL("ole32")
    guid = GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(PCI_PROPERTIES), ctypes.byref(guid))
    keys = [DEVPROPKEY(guid, pid) for pid in LINK_KEYS]
    node = wintypes.DWORD()
    if cfgmgr.CM_Locate_DevNodeW(ctypes.byref(node), ctypes.c_wchar_p(instance_id), 0) != 0:
        return found
    found.usb = instance_id.upper().startswith(USB_IDS)
    found.reader = instance_id.upper().startswith(READER_IDS)
    for _ in range(DEPTH):
        row = []
        for key in keys:
            kind, value, size = wintypes.ULONG(), wintypes.ULONG(), wintypes.ULONG(4)
            done = cfgmgr.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(kind),
                                                   ctypes.byref(value), ctypes.byref(size), 0)
            row.append(value.value if done == 0 else 0)
        found.links.append(row)
        parent = wintypes.DWORD()
        if cfgmgr.CM_Get_Parent(ctypes.byref(parent), node, 0) != 0:
            break
        node = parent
        length = wintypes.ULONG()
        if cfgmgr.CM_Get_Device_ID_Size(ctypes.byref(length), node, 0) == 0:
            text = ctypes.create_unicode_buffer(length.value + 1)
            if cfgmgr.CM_Get_Device_IDW(node, text, length.value + 1, 0) == 0:
                upper = text.value.upper()
                found.usb = found.usb or upper.startswith(USB_IDS)
                found.reader = found.reader or upper.startswith(READER_IDS)
    return found


def run_powershell(argv: list[str]) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as error:
        raise DrivesError(f"PowerShell did not run: {error}") from error
    if result.returncode != 0:
        raise DrivesError(result.stderr.strip() or f"PowerShell ended with {result.returncode}")
    return result.stdout


def _list(value) -> list:
    """ConvertTo-Json gives one object without a list around it."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse(text: str) -> list[dict]:
    try:
        return [d for d in _list(json.loads(text or "[]")) if isinstance(d, dict)]
    except ValueError as error:
        raise DrivesError(f"Windows' answer is not JSON: {error}") from error


def drive_from(data: dict, query: Query, walk: Walk = device_path) -> Drive | None:
    """One drive of the query, with its health log when it is NVMe; None for a virtual drive."""
    bus = int(data.get("bus") or 0)
    if bus in VIRTUAL:
        return None
    drive = Drive(number=int(data.get("number") or 0), model=str(data.get("model") or "").strip(),
                  size=int(data.get("size") or 0), firmware=str(data.get("firmware") or "").strip(),
                  letters=[str(x) for x in _list(data.get("letters")) if x])
    drive.rated_read, drive.rated_write = rated.speeds(drive.model) or (None, None)
    path = walk(str(data.get("device") or ""))
    usb, reader = path.usb or bus == USB, path.reader or bus in (12, 13)
    media = int(data.get("media") or 0)
    if usb:
        drive.bus = drive.interface = "USB"
        drive.kind, drive.smart_note = "Drive on USB", NO_SMART_USB
    elif reader:
        drive.bus = drive.interface = "SD card"
        drive.kind, drive.smart_note = "Memory card", NO_SMART_READER
    elif bus in SATA_BUSES:
        drive.bus = drive.interface = "SATA"
        drive.kind, drive.smart_note = "SATA hard disk" if media == HDD else "SATA drive", NO_SMART_SATA
    elif bus == NVME:
        drive.bus, drive.interface, drive.kind = "NVMe", "NVMe", "NVMe drive"
    else:
        drive.bus = drive.interface = BUSES.get(bus, "Unknown bus")
        drive.kind, drive.smart_note = "Drive", NO_SMART
    if bus == NVME and not usb:
        log = query(drive.number, NVME_LOG_PAGE, HEALTH_LOG, 512)
        if log is not None and len(log) >= 144:
            health_values(drive, log)
        else:
            drive.smart_note = NO_SMART
        identify = query(drive.number, NVME_IDENTIFY, IDENTIFY_CONTROLLER, 4096)
        if identify is not None:
            drive.interface = nvme_version(identify)
    link(drive, path.links)
    if reader and drive.speed:
        drive.speed_tip = "The speed is the card reader's link, not the card's"
    return drive


def read_drives(run: Run = run_powershell, query: Query = protocol_query, walk: Walk = device_path) -> list[Drive]:
    """Every drive Windows lists, as Disk Management numbers them, with what Windows gives of each. A few seconds:
    call it off the window's thread. DrivesError when PowerShell gives no answer."""
    drives = [drive_from(d, query, walk) for d in parse(run(powershell_argv(QUERY)))]
    return sorted((d for d in drives if d is not None), key=lambda d: d.number)
