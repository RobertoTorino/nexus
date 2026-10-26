# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's system information (owner, 20-10-2026): the board, BIOS, CPU, GPU, memory, drives, displays, audio,
network, USB devices, input devices (owner, 26-10-2026), sensors and OS, as the system reports them, in the window
the Sys info pill opens. Everything is
read when the window opens, from sysfs, /proc and /etc, without root and without starting a program; what a system
does not report is left out. The sensors are the readings of that moment.

Nothing personal is shown: no host or user name, no serial number (a monitor's EDID is read only for its name, a USB
device's serial file never), no MAC or IP address (a sensor named after a device's MAC is left out), so the text can
go into an issue as it is."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
from pathlib import Path

PLACEHOLDERS = {"", "default string", "to be filled by o.e.m.", "not specified", "system product name",
                "system manufacturer", "none"}
PCI_IDS = (Path("/usr/share/hwdata/pci.ids"), Path("/usr/share/misc/pci.ids"))
USB_IDS = (Path("/usr/share/hwdata/usb.ids"), Path("/usr/share/misc/usb.ids"))
IMAGE_INFO = Path("/usr/share/ublue-os/image-info.json")
SKIPPED_DRIVES = ("loop", "zram", "ram", "dm-", "sr", "fd", "md")
SECURE_BOOT = "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"    # the EFI global variable: 4 bytes, then 0 or 1
USB_SPEEDS = {"1.5": "USB 1.0", "12": "USB 1.1", "480": "USB 2.0", "5000": "USB 3.0", "10000": "USB 3.1",
              "20000": "USB 3.2"}
EDID_NAME = 0xFC                # the display descriptor with the monitor's name (0xFF holds its serial: never read)
MAC = re.compile(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", re.IGNORECASE)
INPUT_BUSES = {"0003": "USB", "0005": "Bluetooth", "0006": "virtual", "0011": "PS/2", "0018": "I2C",
               "0019": "", "0001": ""}         # host and PCI: the board's own buttons and the GPU's audio jacks

Section = tuple[str, list[tuple[str, str]]]


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _real(*values: str) -> str:
    """The values that say something, joined: DMI's placeholders ("Default string") left out."""
    return " ".join(v for v in values if v.strip().lower() not in PLACEHOLDERS)


def _size(n_bytes: float) -> str:
    for unit, scale in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if n_bytes >= scale:
            return f"{n_bytes / scale:.1f} {unit}".replace(".0 ", " ")
    return f"{n_bytes:.0f} B"


def _gib(n_bytes: float) -> str:
    return f"{n_bytes / 2**30:.1f} GiB".replace(".0 ", " ")


def _cpu_list(text: str) -> list[int]:
    """'0-5,8,10-11' -> [0, 1, 2, 3, 4, 5, 8, 10, 11]."""
    out: list[int] = []
    for part in text.split(","):
        lo, _, hi = part.strip().partition("-")
        if lo.isdigit() and (not hi or hi.isdigit()):
            out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def _uevent(path: Path) -> dict[str, str]:
    return dict(line.partition("=")[::2] for line in _read(path / "uevent").splitlines())


def pci_names(vendor: str, device: str, ids: tuple[Path, ...] = PCI_IDS) -> tuple[str, str]:
    """(vendor name, device name) of a PCI id from the pci.ids database, or of a USB id from usb.ids (the same
    format); empty where it is not listed."""
    vendor, device = vendor.lower(), device.lower()
    for path in ids:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        vendor_name = ""
        for line in lines:
            if not vendor_name:
                if line[:4].lower() == vendor and line[4:6] == "  ":
                    vendor_name = line[6:].strip()
            elif not line.startswith("\t") and line and not line.startswith("#"):
                break                                   # the next vendor
            elif line.startswith("\t") and not line.startswith("\t\t") and line[1:5].lower() == device:
                return vendor_name, line[7:].strip()
        if vendor_name:
            return vendor_name, ""
    return "", ""


def device_name(device: Path, pci_ids: tuple[Path, ...] = PCI_IDS, usb_ids: tuple[Path, ...] = USB_IDS) -> str:
    """The name of a PCI device, a USB device or a USB interface (its device is the parent): from the id databases,
    else what the device itself reports; empty when it is neither."""
    device = device.resolve()                       # sysfs' device links: the parent is the real one's
    pci = _uevent(device).get("PCI_ID", "")
    if pci:
        vendor, _, product = pci.partition(":")
        return " ".join(n for n in pci_names(vendor, product, pci_ids) if n) or pci
    for usb in (device, device.parent):
        vendor, product = _read(usb / "idVendor"), _read(usb / "idProduct")
        if vendor and product:
            names = pci_names(vendor, product, usb_ids)
            return (" ".join(n for n in (_read(usb / "manufacturer"), _read(usb / "product")) if n)
                    or " ".join(n for n in names if n) or f"{vendor}:{product}")
    return ""


def _driver(device: Path) -> str:
    return _uevent(device).get("DRIVER", "") or ((device / "driver").resolve().name if (device / "driver").exists()
                                                 else "")


def board(sys_root: Path) -> Section:
    dmi = sys_root / "class" / "dmi" / "id"
    rows = [("Board", _real(_read(dmi / "board_vendor"), _read(dmi / "board_name"), _read(dmi / "board_version"))),
            ("Product", _real(_read(dmi / "sys_vendor"), _read(dmi / "product_name"),
                              _read(dmi / "product_version")))]
    return "Board", rows


def bios(sys_root: Path) -> Section:
    dmi = sys_root / "class" / "dmi" / "id"
    efi = sys_root / "firmware" / "efi"
    secure = (efi / "efivars" / SECURE_BOOT).read_bytes()[4:5] if (efi / "efivars" / SECURE_BOOT).is_file() else b""
    return "BIOS", [("Version", _real(_read(dmi / "bios_version"))), ("Vendor", _real(_read(dmi / "bios_vendor"))),
                    ("Date", _real(_read(dmi / "bios_date"))),
                    ("Boot", "UEFI" if efi.is_dir() else "Legacy BIOS" if dmi.is_dir() else ""),
                    ("Secure Boot", {b"\x01": "on", b"\x00": "off"}.get(secure, ""))]


def cpu(sys_root: Path, proc_root: Path) -> Section:
    fields: dict[str, str] = {}
    for line in _read(proc_root / "cpuinfo").split("\n\n")[0].splitlines():     # the first processor
        key, _, value = line.partition(":")
        fields.setdefault(key.strip(), value.strip())
    base = sys_root / "devices" / "system" / "cpu"
    online = _cpu_list(_read(base / "online"))
    cores = {(_read(base / f"cpu{n}" / "topology" / "physical_package_id"),
              _read(base / f"cpu{n}" / "topology" / "core_id")) for n in online}
    khz = _read(base / "cpu0" / "cpufreq" / "cpuinfo_max_freq")
    return "CPU", [("Model", fields.get("model name", "")),
                   ("Online", f"{len(cores)} cores, {len(online)} threads" if online else ""),
                   ("Max clock", f"{int(khz) / 1e6:.2f} GHz" if khz.isdigit() else ""),
                   ("Microcode", fields.get("microcode", ""))]


def gpus(sys_root: Path, ids: tuple[Path, ...] = PCI_IDS) -> list[Section]:
    """A section per display controller (PCI class 03xxxx), in the order of the DRM cards."""
    sections: list[Section] = []
    cards = sorted((p for p in (sys_root / "class" / "drm").glob("card*") if p.name[4:].isdigit()),
                   key=lambda p: int(p.name[4:]))
    for card in cards:
        device = card / "device"
        uevent = _uevent(device)
        if not uevent.get("PCI_CLASS", "").zfill(6).startswith("03"):
            continue
        vendor_id, _, device_id = uevent.get("PCI_ID", "").partition(":")
        vendor_name, device_name = pci_names(vendor_id, device_id, ids) if device_id else ("", "")
        name = " ".join(n for n in (vendor_name, device_name) if n) or uevent.get("PCI_ID", "")
        vram, gtt = _read(device / "mem_info_vram_total"), _read(device / "mem_info_gtt_total")
        clocks = [line.split(":", 1)[1].strip(" *") for line in _read(device / "pp_dpm_sclk").splitlines()
                  if ":" in line]
        speed, width = _read(device / "current_link_speed"), _read(device / "current_link_width")
        title = "GPU" if not sections else f"GPU {len(sections) + 1}"
        sections.append((title, [
            ("Name", name), ("PCI id", uevent.get("PCI_ID", "")), ("Driver", uevent.get("DRIVER", "")),
            ("VRAM", _gib(int(vram)) if vram.isdigit() else ""),
            ("Shared memory (GTT)", _gib(int(gtt)) if gtt.isdigit() else ""),
            ("Clock levels", ", ".join(clocks)), ("VBIOS", _read(device / "vbios_version")),
            ("PCIe link", f"{speed} x{width}" if speed and width.isdigit() and width != "0" else "")]))
    return sections


def memory(proc_root: Path) -> Section:
    rows = []
    for line in _read(proc_root / "meminfo").splitlines():
        key, _, value = line.partition(":")
        if key in ("MemTotal", "SwapTotal") and value.split()[0].isdigit():
            rows.append(("RAM" if key == "MemTotal" else "Swap", _gib(int(value.split()[0]) * 1024)))
    return "Memory", rows


def drives(sys_root: Path, home: Path) -> Section:
    rows: list[tuple[str, str]] = []
    for dev in sorted((sys_root / "block").glob("*")):
        sectors = _read(dev / "size")
        if dev.name.startswith(SKIPPED_DRIVES) or not sectors.isdigit() or int(sectors) == 0:
            continue
        kind = ("NVMe" if dev.name.startswith("nvme") else "USB" if _read(dev / "removable") == "1"
                else "HDD" if _read(dev / "queue" / "rotational") == "1" else "SSD")
        model = " ".join(_read(dev / "device" / "model").split())
        rows.append((dev.name, f"{_real(model) or 'unknown model'}, {_size(int(sectors) * 512)} {kind}"))
    try:
        usage = shutil.disk_usage(home)
    except OSError:
        usage = None
    if usage and usage.total:
        rows.append(("Home free", f"{_size(usage.free)} of {_size(usage.total)} ({usage.free / usage.total:.0%})"))
    return "Drives", rows


def edid_name(edid: bytes) -> str:
    """The monitor's name from its EDID: the name descriptor only, never the serial number's."""
    for offset in range(54, 126, 18):
        block = edid[offset:offset + 18]
        if len(block) == 18 and block[:3] == bytes(3) and block[3] == EDID_NAME:
            return block[5:].split(b"\n")[0].decode("ascii", "replace").strip()
    return ""


def displays(sys_root: Path) -> Section:
    """Each output of each GPU: connected (the monitor's name and its preferred mode) or not."""
    rows: list[tuple[str, str]] = []
    for connector in sorted((sys_root / "class" / "drm").glob("card*-*")):
        status = _read(connector / "status")
        if not status:
            continue
        output = connector.name.partition("-")[2]
        if status != "connected":
            rows.append((output, "not connected"))
            continue
        try:
            name = edid_name((connector / "edid").read_bytes())
        except OSError:
            name = ""
        mode = _read(connector / "modes").partition("\n")[0]
        rows.append((output, ", ".join(v for v in (name or "connected", mode and f"{mode} preferred") if v)))
    return "Display", rows


def audio(proc_root: Path) -> Section:
    """The sound cards, with the codec of each (HDMI, analogue) where it reports one."""
    rows: list[tuple[str, str]] = []
    for line in _read(proc_root / "asound" / "cards").splitlines():
        number, _, rest = line.strip().partition(" ")
        if not number.isdigit() or "]:" not in rest:
            continue
        driver, _, name = rest.partition("]:")[2].partition(" - ")
        codec = next((v.strip() for line in _read(proc_root / "asound" / f"card{number}" / "codec#0").splitlines()
                      for k, _, v in [line.partition(":")] if k == "Codec"), "")
        rows.append((f"Card {number}", ", ".join(v for v in (name.strip() or driver.strip(), codec) if v)))
    return "Audio", rows


def network(sys_root: Path, pci_ids: tuple[Path, ...] = PCI_IDS, usb_ids: tuple[Path, ...] = USB_IDS) -> Section:
    """The network adapters (wired and Wi-Fi: the name, driver and link) and the Bluetooth controllers; no MAC or IP
    address."""
    rows: list[tuple[str, str]] = []
    for interface in sorted((sys_root / "class" / "net").glob("*")):
        device = interface / "device"
        if not device.exists():
            continue                                    # lo, bridges, VPNs: not hardware
        wifi = (interface / "wireless").exists() or (interface / "phy80211").exists()
        speed = _read(interface / "speed")
        link = ("not connected" if _read(interface / "operstate") != "up"
                else f"{int(speed) / 1000:g} Gbit/s" if speed.isdigit() and int(speed) >= 1000
                else f"{speed} Mbit/s" if speed.isdigit() and int(speed) > 0 else "connected")
        rows.append((interface.name, ", ".join(v for v in (device_name(device, pci_ids, usb_ids),
                                                            "Wi-Fi" if wifi else "wired", _driver(device), link) if v)))
    for hci in sorted((sys_root / "class" / "bluetooth").glob("hci*")):
        if ":" in hci.name:                             # a connection, not a controller
            continue
        device = hci / "device"
        rows.append((hci.name, ", ".join(v for v in (device_name(device, pci_ids, usb_ids), "Bluetooth",
                                                     _driver(device)) if v)))
    return "Network", rows


def usb(sys_root: Path, usb_ids: tuple[Path, ...] = USB_IDS) -> Section:
    """The USB devices plugged in, hubs left out; the serial number is never read."""
    rows: list[tuple[str, str]] = []
    for device in sorted((sys_root / "bus" / "usb" / "devices").glob("*")):
        vendor, product = _read(device / "idVendor"), _read(device / "idProduct")
        if not vendor or _read(device / "bDeviceClass") == "09":
            continue
        speed = USB_SPEEDS.get(_read(device / "speed"), "")
        rows.append((f"{vendor}:{product}", ", ".join(v for v in (device_name(device, usb_ids=usb_ids), speed) if v)))
    return "USB", rows


def inputs(sys_root: Path) -> Section:
    """The input devices plugged in or paired (keyboards, mice, controllers), each with the bus it is on: USB,
    Bluetooth, PS/2, I2C or a virtual one. The board's own buttons and the GPU's audio jacks (the host and PCI buses)
    are left out, and a device the kernel registers twice under one name is listed once."""
    rows: list[tuple[str, str]] = []
    devices = sorted((sys_root / "class" / "input").glob("input*"),
                     key=lambda p: int(p.name[5:]) if p.name[5:].isdigit() else 0)
    for device in devices:
        name = _read(device / "name")
        bus = INPUT_BUSES.get(_read(device / "id" / "bustype").lower(), "other bus")
        if name and bus and (name, bus) not in rows:
            rows.append((name, bus))
    return "Input", rows


def sensors(sys_root: Path) -> Section:
    """Temperatures, fan speeds and power of every hwmon chip, as they read now; a sensor that reads 0 (a fan header
    or probe with nothing on it) is left out, so is a chip named after a device's MAC address."""
    rows: list[tuple[str, str]] = []
    chips = sorted((sys_root / "class" / "hwmon").glob("hwmon*"), key=lambda p: int(p.name[5:] or 0)
                   if p.name[5:].isdigit() else 0)
    for chip in chips:
        name = _read(chip / "name")
        if not name or MAC.search(name):
            continue
        for kind, unit, scale in (("temp", "°C", 1000), ("fan", "RPM", 1), ("power", "W", 1_000_000)):
            inputs = sorted(chip.glob(f"{kind}*_input"), key=lambda p: int(p.name[len(kind):-6] or 0)
                            if p.name[len(kind):-6].isdigit() else 0)
            if kind == "power" and not inputs:
                inputs = sorted(chip.glob("power*_average"))
            for sensor in inputs:
                value = _read(sensor)
                if not value.lstrip("-").isdigit() or int(value) == 0:
                    continue
                label = _read(sensor.with_name(sensor.name.split("_")[0] + "_label")) or sensor.name.split("_")[0]
                number = int(value) / scale
                rows.append((f"{name} {label}", f"{number:.0f} {unit}" if unit == "RPM" else f"{number:.1f} {unit}"))
    return "Sensors", rows


def os_release(etc_root: Path, image_info: Path = IMAGE_INFO) -> Section:
    fields: dict[str, str] = {}
    for line in _read(etc_root / "os-release").splitlines():
        key, _, value = line.partition("=")
        fields[key] = value.strip().strip("\"'")
    rows = [("System", " ".join(v for v in (fields.get("NAME", ""), fields.get("VERSION", "")) if v)
             or fields.get("PRETTY_NAME", ""))]
    try:
        image = json.loads(image_info.read_text())
    except (OSError, ValueError):
        image = {}
    if isinstance(image, dict) and image.get("image-name"):
        rows.append(("Image", f"{image['image-name']}:{image.get('image-tag', '')}".rstrip(":")
                     + (f", {image['version-pretty']}" if image.get("version-pretty") else "")))
    rows.append(("Kernel", platform.release()))
    session = os.environ.get("XDG_SESSION_TYPE", "")
    rows.append(("Desktop", os.environ.get("XDG_CURRENT_DESKTOP", "") + (f" ({session})" if session else "")))
    return "OS", rows


def collect(sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc"), etc_root: Path = Path("/etc"),
            home: Path | None = None, ids: tuple[Path, ...] = PCI_IDS, image_info: Path = IMAGE_INFO,
            usb_ids: tuple[Path, ...] = USB_IDS) -> list[Section]:
    """Every section with the rows the system reports: one without any is left out."""
    sections = [board(sys_root), bios(sys_root), cpu(sys_root, proc_root), *gpus(sys_root, ids), memory(proc_root),
                drives(sys_root, home or Path.home()), displays(sys_root), audio(proc_root),
                network(sys_root, ids, usb_ids), usb(sys_root, usb_ids), inputs(sys_root), sensors(sys_root),
                os_release(etc_root, image_info)]
    shown = [(title, [(k, v) for k, v in rows if v.strip()]) for title, rows in sections]
    return [(title, rows) for title, rows in shown if rows]


def as_text(sections: list[Section]) -> str:
    """The sections as plain text, for the clipboard."""
    lines: list[str] = []
    for title, rows in sections:
        lines.append(title)
        lines.extend(f"  {key}: {value}" for key, value in rows)
    return "\n".join(lines)
