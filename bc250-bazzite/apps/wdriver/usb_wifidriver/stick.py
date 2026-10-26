# SPDX-License-Identifier: GPL-3.0-or-later
"""What the board says about the stick, the chip and the kernel: read from /sys, /proc and the kernel log, without
root and without Qt, so the window and the tests see the same thing.

An AIC8800D80 stick goes through three USB identities (seen on the owner's UGREEN AX900, 17-10-2026):
 * storage mode, a69c:5723 "Aic MSC": a small virtual disk with the Windows driver; ejecting that disk switches it;
 * loader mode, a69c:8d80 "AIC Wlan": the chip waits for its firmware, which aic_load_fw uploads;
 * Wi-Fi mode, a69c:8d81 "AIC 8800D80": the firmware runs, aic8800_fdrv binds and creates wlan0; the stick's
   Bluetooth comes up beside it on the kernel's own btusb.
The loader prints the chip's revision before it uploads anything ("chip_id=7, chip_mcu_id = 1"); which firmware the
chip takes follows from it (see builder.PINS)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

VENDOR_AIC = 0xA69C
VENDOR_AIC_V2 = 0x368B
STORAGE_PRODUCTS = {0x5721, 0x5722, 0x5723, 0x5724, 0x572C}   # the virtual disk, before the switch
LOADER_PRODUCTS = {0x8D80}                                   # waiting for the firmware
WIFI_PRODUCTS = {0x8D81}                                     # the firmware runs
DRIVER = "aic8800_fdrv"
LOADER = "aic_load_fw"
MODULES = (LOADER, DRIVER)
TOOLS = ("gcc", "make", "git")                               # for building the driver as the user
CHIP_LINE = re.compile(r"chip_id=([0-9a-fA-F]+), chip_mcu_id = (\d+)")
UPLOAD_FAILED = re.compile(r"bin upload fail: 170400")
REVISIONS = {0x1: "U01", 0x3: "U02", 0x7: "U03", 0xF: "U04", 0x1F: "U05"}

Runner = Callable[[list[str]], str]


def run_text(argv: list[str]) -> str:
    """The command's output, "" when it is missing or fails."""
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout


# --- The stick on the USB bus ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Stick:
    path: str                                   # the sysfs name, "2-5"
    vendor: int
    product: int
    name: str                                   # the product string, "AIC 8800D80"
    drivers: tuple[str, ...] = ()               # bound to its interfaces

    @property
    def mode(self) -> str:
        if self.product in STORAGE_PRODUCTS:
            return "storage"
        if self.product in LOADER_PRODUCTS:
            return "loader"
        if self.product in WIFI_PRODUCTS:
            return "wifi"
        return "other"

    @property
    def usb_id(self) -> str:
        return f"{self.vendor:04x}:{self.product:04x}"

    @property
    def mode_text(self) -> str:
        return {"storage": "storage mode", "loader": "waiting for its firmware", "wifi": "Wi-Fi mode"}.get(
            self.mode, "unknown mode")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def find_sticks(sys_root: Path = Path("/sys")) -> tuple[Stick, ...]:
    """Every AIC device on the bus, in whatever mode it is."""
    found = []
    devices = sys_root / "bus/usb/devices"
    if not devices.is_dir():
        return ()
    for device in sorted(devices.iterdir()):
        vendor_text = _read(device / "idVendor")
        if not vendor_text:
            continue
        try:
            vendor, product = int(vendor_text, 16), int(_read(device / "idProduct"), 16)
        except ValueError:
            continue
        if vendor not in (VENDOR_AIC, VENDOR_AIC_V2):
            continue
        drivers = []
        for interface in sorted(devices.glob(f"{device.name}:*")):
            driver = interface / "driver"
            if driver.is_symlink() or driver.exists():
                try:
                    drivers.append(os.path.basename(os.readlink(driver)))
                except OSError:
                    pass
        found.append(Stick(device.name, vendor, product, _read(device / "product"), tuple(drivers)))
    return tuple(found)


@dataclass(frozen=True)
class Interface:
    name: str                                   # wlan0
    operstate: str                              # up, down, dormant
    carrier: bool


def wifi_interfaces(sys_root: Path = Path("/sys")) -> tuple[Interface, ...]:
    """The network interfaces the AIC driver created."""
    found = []
    net = sys_root / "class/net"
    if not net.is_dir():
        return ()
    for interface in sorted(net.iterdir()):
        driver = interface / "device/driver"
        try:
            name = os.path.basename(os.readlink(driver))
        except OSError:
            continue
        if name != DRIVER:
            continue
        found.append(Interface(interface.name, _read(interface / "operstate") or "unknown",
                               _read(interface / "carrier") == "1"))
    return tuple(found)


def loaded_modules(proc_root: Path = Path("/proc")) -> tuple[str, ...]:
    """Which of the driver's modules the kernel has loaded."""
    names = {line.split(" ", 1)[0] for line in _read(proc_root / "modules").splitlines()}
    return tuple(m for m in MODULES if m in names)


# --- The chip, from the kernel log -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Chip:
    chip_id: int
    mcu_id: int
    upload_failed: bool = False                 # the firmware of the other branch broke off at 0x170400

    @property
    def revision(self) -> str:
        return REVISIONS.get(self.chip_id, f"0x{self.chip_id:x}")

    @property
    def branch(self) -> str:
        """The driver branch the chip takes: the older MCU (chip_mcu_id 1) needs the SDK 3 firmware of legacy-mcu1,
        the SDK 5 firmware of main is larger than its upload boundary (shenmintao/aic8800d80 issue 58, 24-07-2026)."""
        return "legacy-mcu1" if self.mcu_id == 1 else "main"

    @property
    def text(self) -> str:
        return f"revision {self.revision}, MCU {self.mcu_id}"


def chip_from_log(text: str) -> Chip | None:
    """The chip's last answer in the kernel log; a chip_id of 0 is a stick wedged by a failed upload (seen
    17-10-2026: a replug clears it), not an answer."""
    answers = [m for m in CHIP_LINE.finditer(text) if int(m.group(1), 16) != 0]
    if not answers:
        return None
    last = answers[-1]
    failed = bool(UPLOAD_FAILED.search(text, last.end()))
    return Chip(int(last.group(1), 16), int(last.group(2)), failed)


def read_kernel_log(runner: Runner = run_text) -> str:
    """The kernel log of every boot the journal keeps; the chip's answer may be from an earlier boot."""
    return runner(["journalctl", "-k", "-o", "cat", "--no-pager"])


# --- The kernel and the tools --------------------------------------------------------------------------------------

def kernel_release() -> str:
    return os.uname().release


def build_tree(kernel: str, usr_root: Path = Path("/usr")) -> Path | None:
    """The kernel's build tree (kernel-devel; Bazzite ships it for its kernel), or None."""
    tree = usr_root / "lib/modules" / kernel / "build"
    return tree if (tree / ".config").is_file() else None


def missing_tools(which: Callable[[str], str | None] = shutil.which) -> tuple[str, ...]:
    return tuple(tool for tool in TOOLS if which(tool) is None)
