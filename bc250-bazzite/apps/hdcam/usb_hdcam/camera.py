# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the camera in /sys. Without firmware it is an OmniVision OV580 in boot mode (05a9:0580, "USB Boot"); with
it, a USB video camera: 05a9:058c for the PS5 HD Camera (CFI-ZEY1), 05a9:058a for the PS4 Camera. The boot mode
looks the same for both; a PS4 Camera on Sony's adapter (CFI-ZAA1) sits behind the adapter's hub (054c:0d0b), which
tells them apart. Its two models (CUH-ZEY1, CUH-ZEY2) look the same. A camera that is ready has a video node,
/dev/video<n>, from uvcvideo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SYS = Path("/sys")
DEV = Path("/dev")
VENDOR = "05a9"                             # OmniVision
BOOT = "0580"
READY = {"058c": "cfi-zey1", "058a": "ps4-camera"}
ADAPTER = ("054c", "0d0b")                  # the PlayStation Camera Adapter's USB 3 hub
MODELS = {"cfi-zey1": "PS5 HD Camera", "ps4-camera": "PS4 Camera"}      # the PS4 Camera: CUH-ZEY1 or CUH-ZEY2
FULL_SPEED_MBPS = 5000                      # the video needs USB 3; the boot mode also runs on USB 2
# A restart keeps the USB ports powered: the camera keeps its firmware but does not connect to the restarted system,
# and Linux cannot power-cycle the BC-250's ports (owner's board, 23-10-2026). A replug or a cold start brings it back.
NOT_FOUND = ("If it is plugged in: after a restart of the board the camera stays silent. Unplug it and plug it in "
             "again, or shut the board down and switch it on again.")


@dataclass(frozen=True)
class Camera:
    model: str                              # "cfi-zey1" or "ps4-camera" (MODELS)
    booted: bool                            # True: firmware loaded, a video camera
    sysfs: Path                             # /sys/bus/usb/devices/<port>
    bus: int
    address: int
    speed_mbps: int                         # 0: not known
    videos: tuple[str, ...] = field(default=())     # /dev/video<n> for capture

    @property
    def name(self) -> str:
        return MODELS[self.model]

    @property
    def port(self) -> str:
        return self.sysfs.name

    def node(self, dev: Path = DEV) -> Path:
        """Its usbfs node, which the firmware upload opens."""
        return dev / "bus/usb" / f"{self.bus:03d}" / f"{self.address:03d}"

    @property
    def slow(self) -> bool:
        return 0 < self.speed_mbps < FULL_SPEED_MBPS


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _number(text: str) -> int:
    try:
        return int(float(text))
    except ValueError:
        return 0


def _ids(device: Path) -> tuple[str, str]:
    return _read(device / "idVendor").lower(), _read(device / "idProduct").lower()


def _behind_adapter(device: Path) -> bool:
    parent = device.resolve().parent
    return _ids(parent) == ADAPTER


def videos(device: Path, sys_root: Path = SYS) -> tuple[str, ...]:
    """The capture nodes of a USB device: uvcvideo makes two per camera, the picture (index 0) and its metadata."""
    found = []
    base = device.resolve()
    for entry in sorted((sys_root / "class/video4linux").glob("video*"), key=lambda p: _number(p.name[5:])):
        try:
            interface = (entry / "device").resolve()
        except OSError:
            continue
        if base in interface.parents and _read(entry / "index") in ("", "0"):
            found.append(f"/dev/{entry.name}")
    return tuple(found)


def find(sys_root: Path = SYS) -> list[Camera]:
    """Every camera plugged in, in boot mode or ready, by port."""
    cameras = []
    for device in sorted((sys_root / "bus/usb/devices").glob("[0-9]*")):
        if ":" in device.name:                  # an interface, not a device
            continue
        vendor, product = _ids(device)
        if vendor != VENDOR or (product != BOOT and product not in READY):
            continue
        booted = product != BOOT
        model = READY[product] if booted else ("ps4-camera" if _behind_adapter(device) else "cfi-zey1")
        cameras.append(Camera(model=model, booted=booted, sysfs=device, bus=_number(_read(device / "busnum")),
                              address=_number(_read(device / "devnum")),
                              speed_mbps=_number(_read(device / "speed")),
                              videos=videos(device, sys_root) if booted else ()))
    return cameras


def writable(path: Path) -> bool:
    return os.access(path, os.W_OK)
