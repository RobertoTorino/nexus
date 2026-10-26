# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the controllers in /sys: each DualSense and DualSense Edge the kernel's hid-playstation drives has a
hidraw node, a connection (USB or Bluetooth) and a battery (its power_supply). The firmware report (0x20) says which
firmware runs. The controller's MAC address names its battery folder and is its HID_UNIQ; the app never shows it."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import hidraw

SYS = Path("/sys")
DEV = Path("/dev")
PROC = Path("/proc")
VENDOR = 0x054C
MODELS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
EDGE = 0x0DF2
BUSES = {0x03: "usb", 0x05: "bluetooth"}
CONNECTIONS = {"usb": "USB cable", "bluetooth": "Bluetooth"}
REPORT_FIRMWARE = 0x20
NOT_FOUND = ("Plug the controller in with a USB cable, or pair it over Bluetooth: hold Create and the PS button "
             "until the light bar flashes, then pair it in the system's Bluetooth settings.")


@dataclass(frozen=True)
class Battery:
    capacity: int | None            # percent; the controller reports it in steps of 10
    status: str                     # "Charging", "Discharging", "Full", "Not charging", "Unknown"


@dataclass(frozen=True)
class Controller:
    node: str                       # "hidraw2"
    product: int
    bus: str                        # BUSES
    sys_path: Path                  # /sys/class/hidraw/<node>/device
    battery: Battery | None

    @property
    def name(self) -> str:
        return MODELS[self.product]

    @property
    def edge(self) -> bool:
        return self.product == EDGE

    @property
    def connection(self) -> str:
        return CONNECTIONS.get(self.bus, self.bus)

    def path(self, dev: Path = DEV) -> Path:
        return dev / self.node

    def sizes(self) -> dict[int, int]:
        try:
            return hidraw.feature_sizes((self.sys_path / "report_descriptor").read_bytes())
        except OSError:
            return {}


@dataclass(frozen=True)
class FirmwareInfo:
    """Report 0x20, as hid-playstation reads it: the update version is what Sony's server lists and the update
    image carries (0x0217), the target is the image's FWUPDATE<target> (the DualSense Edge's is 0x0044)."""
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


def read_info(device: hidraw.Device) -> FirmwareInfo:
    return parse_info(device.get_feature(REPORT_FIRMWARE))


def _uevent(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line)


def _battery(device: Path) -> Battery | None:
    for supply in sorted((device / "power_supply").glob("*")):
        def read(name: str) -> str:
            try:
                return (supply / name).read_text().strip()
            except OSError:
                return ""
        capacity = read("capacity")
        return Battery(int(capacity) if capacity.isdigit() else None, read("status") or "Unknown")
    return None


# hid-playstation's player numbers as the five lights under the touchpad show them, left to right (owner's board,
# 23-10-2026: one controller lit the middle one, a second one two).
PLAYER_LIGHTS = {(False, False, True, False, False): 1, (False, True, False, True, False): 2,
                 (True, False, True, False, True): 3, (True, True, False, True, True): 4, (True,) * 5: 5}


def player_lights(found: Controller) -> tuple[bool, ...] | None:
    """The player indicator as the kernel set it (readable by every user, written only by root), or None when the
    controller has none in /sys."""
    lights = []
    for number in range(1, 6):
        led = next(iter(sorted((found.sys_path / "leds").glob(f"*:white:player-{number}"))), None)
        if led is None:
            return None
        try:
            lights.append((led / "brightness").read_text().strip() not in ("", "0"))
        except OSError:
            return None
    return tuple(lights)


def player_number(found: Controller) -> int | None:
    """The player number the controller's lights show, or None (no lights in /sys, or a pattern that is not
    hid-playstation's)."""
    lights = player_lights(found)
    return PLAYER_LIGHTS.get(lights) if lights else None


def find(sys_root: Path = SYS) -> list[Controller]:
    """Every DualSense and DualSense Edge, USB ones first (only they take a firmware update)."""
    found = []
    for node in sorted((sys_root / "class/hidraw").glob("hidraw*"), key=lambda p: (len(p.name), p.name)):
        device = node / "device"
        hid_id = _uevent(device / "uevent").get("HID_ID", "")
        try:
            bus, vendor, product = (int(part, 16) for part in hid_id.split(":"))
        except ValueError:
            continue
        if vendor != VENDOR or product not in MODELS or bus not in BUSES:
            continue
        found.append(Controller(node.name, product, BUSES[bus], device, _battery(device)))
    return sorted(found, key=lambda c: c.bus != "usb")


def held_back(sys_root: Path = SYS) -> list[int]:
    """The products of controllers on a USB cable that no driver took. hid-playstation drives a controller over one
    connection only: plugged in while still connected over Bluetooth, it stays on Bluetooth and the cable only
    charges it (owner's board, 23-10-2026: "Duplicate device found for MAC address", the USB HID device without a
    driver)."""
    found = []
    for device in sorted((sys_root / "bus/hid/devices").glob("0003:054C:*")):
        try:
            product = int(device.name.split(":")[2].split(".")[0], 16)
        except (IndexError, ValueError):
            continue
        if product in MODELS and not (device / "driver").exists():
            found.append(product)
    return found


def bluetooth_address(found: Controller) -> str:
    """The controller's Bluetooth address, for bluetoothctl only; never shown."""
    return _uevent(found.sys_path / "uevent").get("HID_UNIQ", "") if found.bus == "bluetooth" else ""


def disconnect_bluetooth(address: str, run=subprocess.run) -> str:
    """Asks BlueZ to drop the controller's Bluetooth connection, as the user may; what went wrong, or ""."""
    try:
        result = run(["bluetoothctl", "disconnect", address], capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return "bluetoothctl is not installed."
    except subprocess.TimeoutExpired:
        return "bluetoothctl did not answer within 20 s."
    # BlueZ 5.87 on the owner's board answers "Disconnection successful" (23-10-2026); older ones "Successful
    # disconnected".
    if result.returncode != 0 or "successful" not in (result.stdout or "").lower():
        return "Bluetooth did not let go of the controller."
    return ""


def event_node(found: Controller, dev: Path = DEV) -> Path | None:
    """The controller's own input device, /dev/input/event<n> (not its motion sensors, touchpad or headset jack):
    the one that takes force feedback."""
    for device in sorted((found.sys_path / "input").glob("input*")):
        try:
            name = (device / "name").read_text().strip()
        except OSError:
            continue
        if name.endswith(("Motion Sensors", "Touchpad", "Headset Jack")):
            continue
        for event in sorted(device.glob("event*")):
            return dev / "input" / event.name
    return None


def holders(path: Path, proc: Path = PROC) -> list[str]:
    """The names of the other programs that have *path* open (Steam reads the controller too), as far as /proc lets
    the user see: their own programs."""
    names = set()
    own = os.getpid()
    for process in proc.glob("[0-9]*"):
        if process.name == str(own):
            continue
        try:
            for fd in (process / "fd").iterdir():
                if os.readlink(fd) == str(path):
                    names.add((process / "comm").read_text().strip())
                    break
        except OSError:
            continue
    return sorted(names)


def writable(path: Path) -> bool:
    return os.access(path, os.R_OK | os.W_OK)
