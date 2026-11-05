# SPDX-License-Identifier: GPL-3.0-or-later
"""The drives' SMART values as udisks2 reads them (owner, 04-11-2026: much simpler than CrystalDiskInfo, only the
health percentage, the power cycle count and the power-on hours). udisks answers on the system bus without root:
the board has no passwordless sudo, and reading SMART ourselves would need it. busctl (systemd's, on every Bazzite)
makes the calls and writes JSON, each property a {"type", "data"} pair.

- NVMe (org.freedesktop.UDisks2.NVMe.Controller): the hours are a property, the power cycles and "percent_used"
  come from SmartGetAttributes; health is 100 minus percent_used (it passes 100 when the drive outlives its rated
  endurance, so health stops at 0). SmartCriticalWarning lists what the drive itself flags (spare, temperature,
  degraded, readonly, ...).
- SATA (org.freedesktop.UDisks2.Drive.Ata): the hours are SmartPowerOnSeconds, the power cycles attribute 12. Its
  health is a vendor's attribute, whose normalized value is the life left in percent: HEALTH_ATTRIBUTES, in order.
  A drive with none of them shows "health not reported". "Start/stop cycles" (attribute 4) is a hard disk's; an
  SSD counts power cycles.

A drive's D-Bus object path and its Id hold its serial number: personal data, never shown or logged here."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

SERVICE = "org.freedesktop.UDisks2"
ROOT_PATH = "/org/freedesktop/UDisks2"
DRIVE = "org.freedesktop.UDisks2.Drive"
BLOCK = "org.freedesktop.UDisks2.Block"
PARTITION = "org.freedesktop.UDisks2.Partition"
NVME = "org.freedesktop.UDisks2.NVMe.Controller"
ATA = "org.freedesktop.UDisks2.Drive.Ata"
TIMEOUT_S = 15                  # udisks may wake a sleeping drive to answer

POWER_CYCLES_ID = 12
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
    path: str                               # the D-Bus object: holds the serial, never shown
    model: str
    device: str = ""                        # nvme0n1, sda
    size: int = 0                           # bytes
    bus: str = ""                           # "NVMe" or "SATA"
    health: int | None = None               # percent of its life left; None: not reported
    health_source: str = ""                 # where the health comes from
    power_cycles: int | None = None
    hours: int | None = None
    warnings: list[str] = field(default_factory=list)   # what the drive itself flags
    updated: int = 0                        # when udisks last read SMART (Unix time); 0: unknown
    error: str = ""                         # SmartGetAttributes failed: what it said

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


def value(prop) -> object:
    """A property from busctl's JSON: the data of its {"type", "data"} pair."""
    return prop.get("data") if isinstance(prop, dict) and "type" in prop else prop


def call(run_: Run, path: str, interface: str, method: str, *args: str) -> object:
    """One udisks call through busctl; its reply's first value, as JSON."""
    code, out = run_(["busctl", "--system", "--json=short", "call", SERVICE, path, interface, method, *args])
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
    for number, name in HEALTH_ATTRIBUTES:
        normalized = int(by_id[number][3]) if number in by_id else -1
        if 0 <= normalized <= 100:
            drive.health, drive.health_source = normalized, f"attribute {number}, {name}"
            break


def read_drives(run_: Run = run) -> list[Drive]:
    """Every drive that reports SMART through udisks, as udisks sorts them. SmartError when udisks does not answer;
    a drive whose attributes fail keeps its error and the values its properties gave."""
    objects = call(run_, ROOT_PATH, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects") or {}
    if not isinstance(objects, dict):
        raise SmartError(f"{NO_UDISKS}: an unexpected reply")
    names = devices(objects)
    drives = []
    for path, interfaces in sorted(objects.items(), key=lambda item: str(value(
            item[1].get(DRIVE, {}).get("SortKey")) or item[0])):
        props = interfaces.get(DRIVE)
        if props is None or (NVME not in interfaces and ATA not in interfaces):
            continue
        if ATA in interfaces and not value(interfaces[ATA].get("SmartSupported")):
            continue
        drive = Drive(path=path, model=" ".join(str(value(props.get(k)) or "") for k in ("Vendor", "Model")).strip(),
                      device=names.get(path, ""), size=int(value(props.get("Size")) or 0))
        try:
            if NVME in interfaces:
                attributes = call(run_, path, NVME, "SmartGetAttributes", "a{sv}", "0") or {}
                nvme_values(drive, interfaces[NVME], attributes if isinstance(attributes, dict) else {})
            else:
                rows = call(run_, path, ATA, "SmartGetAttributes", "a{sv}", "0") or []
                ata_values(drive, interfaces[ATA], rows if isinstance(rows, list) else [])
        except SmartError as exc:
            drive.bus = drive.bus or ("NVMe" if NVME in interfaces else "SATA")
            drive.error = str(exc)
            if NVME in interfaces:
                nvme_values(drive, interfaces[NVME], {})
            else:
                ata_values(drive, interfaces[ATA], [])
        drives.append(drive)
    return drives
