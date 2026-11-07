# SPDX-License-Identifier: GPL-3.0-or-later
"""The drives' SMART values as udisks2 reads them (owner, 04-11-2026: much simpler than CrystalDiskInfo, only the
health percentage, the power cycle count and the power-on hours). udisks answers on the system bus without root:
direct SMART access may need elevated privileges. busctl (provided by systemd on Bazzite)
makes the calls and writes JSON, each property a {"type", "data"} pair.

- NVMe (org.freedesktop.UDisks2.NVMe.Controller): the hours are a property, the power cycles and "percent_used"
  come from SmartGetAttributes; health is 100 minus percent_used (it passes 100 when the drive outlives its rated
  endurance, so health stops at 0). SmartCriticalWarning lists what the drive itself flags (spare, temperature,
  degraded, readonly, ...).
- SATA (org.freedesktop.UDisks2.Drive.Ata): the hours are SmartPowerOnSeconds, the power cycles attribute 12. Its
  health is a vendor's attribute, whose normalized value is the life left in percent: HEALTH_ATTRIBUTES, in order.
  A drive with none of them shows "health not reported". "Start/stop cycles" (attribute 4) is a hard disk's; an
  SSD counts power cycles.

The specs come from the same places: the firmware and the serial from the drive's properties, the data read and
written from SmartGetAttributes (NVMe's total_data_read and total_data_written; a SATA drive's attributes 242 and 241,
counted as 512-byte sectors, as most makers do), the interface and the link's speed from sysfs (the PCIe link of an
NVMe drive, the SATA link, the USB port), and whether a newer firmware exists from fwupd, also on the system bus
without root. A drive on USB is listed too: its adapter often hides the SMART values, then only the specs show.

A drive's D-Bus object path, its Id and its serial number are personal data: never logged, and the window shows the
serial only when asked (owner, 05-11-2026)."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import rated

SERVICE = "org.freedesktop.UDisks2"
ROOT_PATH = "/org/freedesktop/UDisks2"
DRIVE = "org.freedesktop.UDisks2.Drive"
BLOCK = "org.freedesktop.UDisks2.Block"
PARTITION = "org.freedesktop.UDisks2.Partition"
FILESYSTEM = "org.freedesktop.UDisks2.Filesystem"
NVME = "org.freedesktop.UDisks2.NVMe.Controller"
ATA = "org.freedesktop.UDisks2.Drive.Ata"
FWUPD = "org.freedesktop.fwupd"
FWUPD_UPDATABLE = 1 << 1        # fwupd's device flag: its firmware can be updated
SYSFS = Path("/sys")
TIMEOUT_S = 15                  # udisks may wake a sleeping drive to answer

POWER_CYCLES_ID = 12
WRITTEN_ID, READ_ID = 241, 242  # total LBAs written and read
SECTOR = 512
PCIE_GENERATIONS = {"2.5": "1.0", "5.0": "2.0", "8.0": "3.0", "16.0": "4.0", "32.0": "5.0", "64.0": "6.0"}
SATA_GENERATIONS = {"1.5": "SATA I", "3.0": "SATA II", "6.0": "SATA III"}
# What a link carries at most, in MB/s, after its line code: per PCIe lane by generation, per SATA and USB speed
PCIE_LANE_MBPS = {"1.0": 250, "2.0": 500, "3.0": 985, "4.0": 1969, "5.0": 3938, "6.0": 7563}
SATA_MBPS = {"1.5": 150, "3.0": 300, "6.0": 600}
USB_MBPS = {"1.5": 0, "12": 1, "480": 60, "5000": 500, "10000": 1212, "20000": 2424}
# USB bridges to an NVMe drive (an M.2 enclosure), by vendor and product id: the drive inside is NVMe
NVME_BRIDGES = {"0bda:9210": "Realtek RTL9210", "174c:2362": "ASMedia ASM2362", "152d:0583": "JMicron JMS583"}
USB_SPEEDS = {"1.5": "USB 1.0", "12": "USB 1.1", "480": "USB 2.0", "5000": "USB 3.2 Gen 1",
              "10000": "USB 3.2 Gen 2", "20000": "USB 3.2 Gen 2x2"}     # Mb/s as sysfs gives them
# (id, name) of the attributes whose normalized value is the life left in percent, the first found wins
HEALTH_ATTRIBUTES = (
    (231, "SSD life left"),                 # Kingston, SandForce and many others
    (169, "Remaining lifetime"),            # Western Digital
    (202, "Percent lifetime remaining"),    # Crucial, Micron
    (233, "Media wearout indicator"),       # Intel
    (177, "Wear leveling count"),           # Samsung
)

NO_BUSCTL = "busctl is missing: it comes with systemd, which every Bazzite has."
NO_UDISKS = "udisks does not answer on the system bus"
# Firmware updates, as fwupd answers (Drive.update)
AVAILABLE, UP_TO_DATE, UNKNOWN, NOT_SUPPORTED = "Available", "Up to date", "Unknown", "Not supported"
NO_METADATA = "fwupd has no firmware list yet: fwupdmgr refresh downloads it from the LVFS."

# argv -> (exit code, output); tests pass a fake
Run = Callable[[list[str]], tuple[int, str]]


def run(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S)
    except FileNotFoundError:
        return 127, NO_BUSCTL
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return done.returncode, (done.stdout if done.returncode == 0 else done.stderr).strip()


class SmartError(RuntimeError):
    pass


@dataclass
class Drive:
    path: str = field(repr=False)           # the D-Bus object: holds the serial, never shown
    model: str
    device: str = ""                        # nvme0n1, sda
    size: int = 0                           # bytes
    bus: str = ""                           # "NVMe", "SATA" or "USB"
    smart: bool = True                      # False: a USB drive whose adapter hides SMART
    health: int | None = None               # percent of its life left; None: not reported
    health_source: str = ""                 # where the health comes from
    power_cycles: int | None = None
    hours: int | None = None
    warnings: list[str] = field(default_factory=list)   # what the drive itself flags
    updated: int = 0                        # when udisks last read SMART (Unix time); 0: unknown
    error: str = ""                         # SmartGetAttributes failed: what it said
    firmware: str = ""                      # the firmware's version (Revision)
    serial: str = field(default="", repr=False)     # personal data: shown only when asked, never logged
    interface: str = ""                     # "NVMe 1.3", "SATA", "USB"
    speed: str = ""                         # the link now: "PCIe 2.0 x2", "6.0 Gb/s", "5 Gb/s"
    speed_tip: str = ""                     # what the link could do, the standard's name
    slow_link: str = ""                     # the link is slower than the board's port allows: why, what to try
    link_mbps: int | None = None            # what the link now carries at most, MB/s
    drive_mbps: int | None = None           # what the drive's own fastest link carries
    board_link: str = ""                    # the board's port: the most it offers ("PCIe 2.0 x2", "6.0 Gb/s")
    board_mbps: int | None = None           # what that carries at most, MB/s
    rated_read: int | None = None           # the maker's rated speeds, MB/s (rated.py); None: not in the list
    rated_write: int | None = None
    mounts: list[str] = field(default_factory=list, repr=False)  # where its file systems are mounted
    data_read: int | None = None            # bytes the host read and wrote in all
    data_written: int | None = None
    update: str = UNKNOWN                   # a newer firmware: AVAILABLE, UP_TO_DATE, UNKNOWN, NOT_SUPPORTED
    update_tip: str = ""

    @property
    def label(self) -> str:
        """The drive as the window names it: model, device and size (never the serial)."""
        parts = [p for p in (self.device, size_text(self.size) if self.size else "") if p]
        return f"{self.model or 'Unknown drive'} ({', '.join(parts)})" if parts else (self.model or "Unknown drive")


def size_text(size: int) -> str:
    """Bytes as a drive's label gives them: decimal units (a 2 TB drive is 2.0 TB)."""
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "kB") else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def number(text: str) -> str:
    """The number a sysfs speed starts with: "8.0" of "8.0 GT/s PCIe"; "" when there is none."""
    found = re.match(r"\s*([0-9.]+)", text)
    return found.group(1) if found else ""


def link(drive: Drive, sysfs: Path = SYSFS) -> None:
    """The drive's link from sysfs, walking up from its block device: the first USB device (a "speed" in Mb/s), SATA
    port (ataN: its link's sata_spd) or PCIe function (current_link_speed and _width) on the way gives it. The board's
    side is the most its port offers: the PCIe port above the drive, the SATA port's hardware limit, the USB bus."""
    if not drive.device:
        return
    try:
        real = (sysfs / "block" / drive.device).resolve(strict=True)
    except OSError:
        return
    top = (sysfs / "devices").resolve()
    for folder in (real, *real.parents):
        if folder == top or top not in folder.parents:
            break
        if (folder / "idVendor").exists() and (folder / "speed").exists():
            usb_link(drive, folder)
            return
        if re.fullmatch(r"ata\d+", folder.name):
            port = sysfs / "class" / "ata_link" / f"link{folder.name[3:]}"
            now = number(sysfs_text(port / "sata_spd"))
            if now:
                drive.speed, drive.speed_tip = f"{now} Gb/s", SATA_GENERATIONS.get(now, "")
                drive.link_mbps = drive.drive_mbps = SATA_MBPS.get(now)
            most = number(sysfs_text(port / "hw_sata_spd_limit"))
            if most:
                drive.board_link, drive.board_mbps = f"{most} Gb/s", SATA_MBPS.get(most)
            return
        if (folder / "current_link_speed").exists() and (folder / "current_link_width").exists():
            speed, width = sysfs_text(folder / "current_link_speed"), sysfs_text(folder / "current_link_width")
            best = sysfs_text(folder / "max_link_speed"), sysfs_text(folder / "max_link_width")
            now, most = pcie(speed, width), pcie(*best)
            if now:
                drive.speed = now
                drive.speed_tip = f"The drive can do {most}" if most and most != now else "As fast as the drive goes"
                drive.link_mbps, drive.drive_mbps = pcie_mbps(speed, width), pcie_mbps(*best)
            port = folder.parent                # the port the drive sits in: what the board offers
            board = sysfs_text(port / "max_link_speed"), sysfs_text(port / "max_link_width")
            if pcie(*board):
                drive.board_link, drive.board_mbps = pcie(*board), pcie_mbps(*board)
            return


def usb_bus_speed(port: Path) -> str:
    """The speed of the bus a hub port is on ("480", "5000"): its usbN folder's."""
    bus = next((f for f in (port, *port.parents) if re.fullmatch(r"usb\d+", f.name)), None)
    return sysfs_text(bus / "speed") if bus else ""


def usb_link(drive: Drive, device: Path) -> None:
    """A drive on USB: the device's link now, and the most its port offers. A USB 3 port is two ports to Linux, one
    on the controller's USB 2 bus and its peer on the USB 3 bus; a device that came up at USB 2.0 sits on the first,
    so the port's peer says what the port could do. A drive stuck at USB 2.0 in a USB 3 port gets slow_link: often a
    cable that carries only USB 2, or a hub between. An enclosure of a known NVMe bridge is "NVMe over USB"."""
    ids = f"{sysfs_text(device / 'idVendor')}:{sysfs_text(device / 'idProduct')}"
    bridge = NVME_BRIDGES.get(ids, "")
    drive.interface = "NVMe over USB" if bridge else "USB"
    if bridge:
        drive.speed_tip = f"{bridge} enclosure"
    speed = sysfs_text(device / "speed")
    if speed:
        drive.speed = usb_text(speed)
        drive.speed_tip = ", ".join(t for t in (USB_SPEEDS.get(speed, ""), drive.speed_tip) if t)
        drive.link_mbps = USB_MBPS.get(speed)
        if float(speed) >= 5000:            # at USB 2.0 a USB 3 device cannot be told from a USB 2 one
            drive.drive_mbps = drive.link_mbps
    port = device / "port"
    most = usb_bus_speed(port.resolve()) if port.exists() else ""
    peer = port / "peer"
    if peer.exists():
        most = max(most, usb_bus_speed(peer.resolve()), key=lambda s: float(s or 0))
    if not most:
        bus = next((f for f in device.parents if re.fullmatch(r"usb\d+", f.name)), None)
        most = sysfs_text(bus / "speed") if bus else ""
    if most:
        drive.board_link, drive.board_mbps = usb_text(most), USB_MBPS.get(most)
        # Stuck at USB 2.0 in a USB 3 port: a cable or a hub, not the drive (a 5 Gb/s drive in a 10 Gb/s port is not)
        if speed and float(speed) <= 480 < 5000 <= float(most):
            drive.slow_link = (f"The drive linked at {USB_SPEEDS.get(speed, usb_text(speed))}, though its port does "
                               f"{USB_SPEEDS.get(most, usb_text(most))} ({usb_text(most)}). Try another cable (many "
                               "USB-C cables carry only USB 2.0), plug it straight into the board, or plug it in again.")


def usb_text(speed: str) -> str:
    """USB's "speed" (Mb/s) as the window gives it: "5 Gb/s", "480 Mb/s"."""
    mbps = float(speed)
    return f"{mbps / 1000:g} Gb/s" if mbps >= 1000 else f"{mbps:g} Mb/s"


def pcie_mbps(speed: str, width: str) -> int | None:
    """What a PCIe link carries at most, MB/s: its lanes times a lane of its generation."""
    lane = PCIE_LANE_MBPS.get(PCIE_GENERATIONS.get(number(speed), ""))
    return lane * int(width) if lane and width.isdigit() else None


def held_back(drive: Drive) -> bool | None:
    """Whether the board's port carries less than the drive can do (its rated read, else its fastest link); None
    when either is unknown."""
    can = drive.rated_read or drive.drive_mbps
    return None if not (can and drive.board_mbps) else drive.board_mbps < can


def pcie(speed: str, width: str) -> str:
    """"PCIe 3.0 x4" from sysfs' "8.0 GT/s PCIe" and "4"; "" when unknown."""
    generation = PCIE_GENERATIONS.get(number(speed), "")
    return f"PCIe {generation} x{width}" if generation and width.isdigit() else ""


def value(prop) -> object:
    """A property from busctl's JSON: the data of its {"type", "data"} pair."""
    return prop.get("data") if isinstance(prop, dict) and "type" in prop else prop


def call(run_: Run, path: str, interface: str, method: str, *args: str, service: str = SERVICE) -> object:
    """One udisks (or fwupd) call through busctl; its reply's first value, as JSON."""
    code, out = run_(["busctl", "--system", "--json=short", "call", service, path, interface, method, *args])
    if code != 0:
        raise SmartError(out if code == 127 else f"{NO_UDISKS}: {out or code}")
    try:
        data = json.loads(out).get("data") or [None]
    except (ValueError, AttributeError) as exc:
        raise SmartError(f"{NO_UDISKS}: the reply is not JSON ({exc})") from exc
    return data[0]


def devices(objects: dict) -> dict[str, str]:
    """Drive path -> its whole-disk device name (nvme0n1, sda), from the block devices that are not partitions."""
    found: dict[str, str] = {}
    for interfaces in objects.values():
        block = interfaces.get(BLOCK)
        if not block or PARTITION in interfaces:
            continue
        drive = value(block.get("Drive"))
        raw = value(block.get("PreferredDevice")) or value(block.get("Device")) or []
        name = bytes(b for b in raw if b).decode(errors="replace").rsplit("/", 1)[-1]
        if drive and drive != "/" and name and drive not in found:
            found[drive] = name
    return found


def mount_points(objects: dict) -> dict[str, list[str]]:
    """Drive path -> where its file systems are mounted (udisks' Filesystem.MountPoints)."""
    found: dict[str, list[str]] = {}
    for interfaces in objects.values():
        block, filesystem = interfaces.get(BLOCK), interfaces.get(FILESYSTEM)
        if not block or not filesystem:
            continue
        drive = value(block.get("Drive"))
        for raw in value(filesystem.get("MountPoints")) or []:
            point = bytes(b for b in raw if b).decode(errors="replace")
            if drive and drive != "/" and point:
                found.setdefault(drive, []).append(point)
    return found


def nvme_values(drive: Drive, controller: dict, attributes: dict) -> None:
    drive.bus = "NVMe"
    drive.hours = int(value(controller.get("SmartPowerOnHours")) or 0) or None
    drive.updated = int(value(controller.get("SmartUpdated")) or 0)
    drive.warnings = [str(w) for w in value(controller.get("SmartCriticalWarning")) or []]
    used = value(attributes.get("percent_used"))
    if used is not None:
        drive.health, drive.health_source = max(0, 100 - int(used)), "100 minus percent used"
    cycles = value(attributes.get("power_cycles"))
    drive.power_cycles = int(cycles) if cycles is not None else None
    for name, key in (("data_read", "total_data_read"), ("data_written", "total_data_written")):
        amount = value(attributes.get(key))
        setattr(drive, name, int(amount) if amount is not None else None)


def ata_values(drive: Drive, ata: dict, rows: list) -> None:
    """*rows* are SmartGetAttributes' (id, name, flags, value, worst, threshold, pretty, pretty_unit, expansion)."""
    drive.bus = "SATA"
    seconds = int(value(ata.get("SmartPowerOnSeconds")) or 0)
    drive.hours = seconds // 3600 if seconds else None
    drive.updated = int(value(ata.get("SmartUpdated")) or 0)
    if value(ata.get("SmartFailing")):
        drive.warnings = ["failing"]
    by_id = {int(row[0]): row for row in rows if isinstance(row, list) and len(row) >= 7}
    if POWER_CYCLES_ID in by_id:
        drive.power_cycles = int(by_id[POWER_CYCLES_ID][6])
    for name, number_ in (("data_read", READ_ID), ("data_written", WRITTEN_ID)):
        if number_ in by_id:
            setattr(drive, name, int(by_id[number_][6]) * SECTOR)
    for number, name in HEALTH_ATTRIBUTES:
        normalized = int(by_id[number][3]) if number in by_id else -1
        if 0 <= normalized <= 100:
            drive.health, drive.health_source = normalized, f"attribute {number}, {name}"
            break


def listed(interfaces: dict) -> bool:
    """A drive the window lists: NVMe, SATA with SMART, or on USB with a medium in it (not an optical drive)."""
    props = interfaces.get(DRIVE)
    if props is None:
        return False
    if NVME in interfaces or (ATA in interfaces and value(interfaces[ATA].get("SmartSupported"))):
        return True
    return (value(props.get("ConnectionBus")) == "usb" and int(value(props.get("Size")) or 0) > 0
            and not value(props.get("Optical")))


def read_drives(run_: Run = run, sysfs: Path = SYSFS) -> list[Drive]:
    """Every drive that reports SMART through udisks, and every drive on USB, as udisks sorts them. SmartError when
    udisks does not answer; a drive whose attributes fail keeps its error and the values its properties gave."""
    objects = call(run_, ROOT_PATH, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects") or {}
    if not isinstance(objects, dict):
        raise SmartError(f"{NO_UDISKS}: an unexpected reply")
    names, mounted = devices(objects), mount_points(objects)
    drives = []
    for path, interfaces in sorted(objects.items(), key=lambda item: str(value(
            item[1].get(DRIVE, {}).get("SortKey")) or item[0])):
        if not listed(interfaces):
            continue
        props = interfaces[DRIVE]
        drive = Drive(path=path, model=" ".join(str(value(props.get(k)) or "") for k in ("Vendor", "Model")).strip(),
                      device=names.get(path, ""), size=int(value(props.get("Size")) or 0),
                      firmware=str(value(props.get("Revision")) or "").strip(),
                      serial=str(value(props.get("Serial")) or "").strip(), mounts=mounted.get(path, []))
        drive.rated_read, drive.rated_write = rated.speeds(drive.model) or (None, None)
        usb = value(props.get("ConnectionBus")) == "usb"
        try:
            if NVME in interfaces:
                attributes = call(run_, path, NVME, "SmartGetAttributes", "a{sv}", "0") or {}
                nvme_values(drive, interfaces[NVME], attributes if isinstance(attributes, dict) else {})
            elif ATA in interfaces and value(interfaces[ATA].get("SmartSupported")):
                rows = call(run_, path, ATA, "SmartGetAttributes", "a{sv}", "0") or []
                ata_values(drive, interfaces[ATA], rows if isinstance(rows, list) else [])
            else:
                drive.smart = False
        except SmartError as exc:
            drive.bus = drive.bus or ("NVMe" if NVME in interfaces else "SATA")
            drive.error = str(exc)
            if NVME in interfaces:
                nvme_values(drive, interfaces[NVME], {})
            else:
                ata_values(drive, interfaces[ATA], [])
        if usb:
            drive.bus = "USB"
        revision = str(value(interfaces.get(NVME, {}).get("NVMeRevision")) or "")
        drive.interface = (f"NVMe {revision}" if revision else "NVMe") if NVME in interfaces and not usb \
            else drive.bus
        link(drive, sysfs)
        drives.append(drive)
    firmware_updates(run_, drives)
    return drives


def firmware_updates(run_: Run, drives: list[Drive]) -> None:
    """Whether fwupd has a newer firmware for each drive: its device is found by the drive's serial (compared here,
    never shown), and GetUpgrades answers. fwupd not running, or without its firmware list, is UNKNOWN with why."""
    if not drives:
        return
    try:
        known = call(run_, "/", FWUPD, "GetDevices", service=FWUPD) or []
    except SmartError as exc:
        for drive in drives:
            drive.update, drive.update_tip = UNKNOWN, f"fwupd does not answer: {str(exc).split(': ', 1)[-1]}"
        return
    by_serial = {str(value(d.get("Serial")) or "").strip(): d for d in known if isinstance(d, dict)}
    for drive in drives:
        device = by_serial.get(drive.serial) if drive.serial else None
        if device is None:
            drive.update, drive.update_tip = NOT_SUPPORTED, "fwupd knows no firmware for this drive"
            continue
        if not int(value(device.get("Flags")) or 0) & FWUPD_UPDATABLE:
            drive.update, drive.update_tip = NOT_SUPPORTED, "fwupd cannot update this drive's firmware"
            continue
        code, out = run_(["busctl", "--system", "--json=short", "call", FWUPD, "/", FWUPD, "GetUpgrades", "s",
                          str(value(device.get("DeviceId")) or "")])
        if code == 0:
            try:
                releases = json.loads(out).get("data") or [[]]
                newest = str(value((releases[0] or [{}])[0].get("Version")) or "")
            except (ValueError, AttributeError, IndexError):
                newest = ""
            drive.update = AVAILABLE
            drive.update_tip = (f"Firmware {newest} is on the LVFS" if newest else "A newer firmware is on the LVFS") \
                + ": GNOME Software or fwupdmgr update installs it. Back up first."
            continue
        said = out.lower()
        if "silo" in said or "metadata" in said:
            drive.update, drive.update_tip = UNKNOWN, NO_METADATA
        elif any(word in said for word in ("no upgrades", "no releases", "latest", "nothing to do",
                                           "does not currently have")):
            drive.update, drive.update_tip = UP_TO_DATE, "fwupd knows no newer firmware for this drive"
        else:
            drive.update, drive.update_tip = UNKNOWN, f"fwupd answered: {out or code}"
