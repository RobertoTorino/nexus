# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the camera among Windows' USB devices. Without firmware it is an OmniVision OV580 in boot mode (05a9:0580,
"USB Boot"); with it, a USB video camera: 05a9:058c for the PS5 HD Camera (CFI-ZEY1), which Windows' own webcam
driver (usbvideo) takes, so every app sees it as "USB Camera-OV580". The boot mode looks the same for the PS4 Camera;
on Sony's adapter (CFI-ZAA1) it sits behind the adapter's hub (054c:0d0b), which tells them apart. The PS4 Camera's
firmware is not this app's yet, so such a camera is found but not loaded.

The firmware goes to the boot loader through WinUSB, which Windows does not give it by itself: driver.py binds it,
once for each USB port the camera is plugged into (Windows keeps a device for each port)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import devices
from .devices import Device, Speed

VENDOR = "05a9"                             # OmniVision
BOOT = "0580"
READY = "058c"                              # the PS5 HD Camera with its firmware
ADAPTER = ("054c", "0d0b")                  # the PlayStation Camera Adapter's USB 3 hub
WINUSB = "winusb"
VIDEO = "usbvideo"
NAME = "PS5 HD Camera"
PS4_NAME = "PS4 Camera"

# The states, in the order the camera goes through them
NO_DRIVER = "no-driver"                     # the boot loader, without WinUSB: Allow access binds it
BOOT_LOADER = "boot"                        # the boot loader with WinUSB: the firmware can go
READY_STATE = "ready"                       # a webcam
PS4 = "ps4"                                 # a PS4 Camera's boot loader: not this app's yet


@dataclass(frozen=True)
class Camera:
    state: str
    device: Device
    speed: Speed | None = None
    webcam: str = ""                        # the name apps list it by, when Windows' webcam driver has it
    video: str = ""                         # the instance ID of its video interface, the webcam (picture.py)

    @property
    def name(self) -> str:
        return PS4_NAME if self.state == PS4 else NAME

    @property
    def instance(self) -> str:
        return self.device.instance

    @property
    def slow(self) -> bool:
        """On a port slower than USB 3: the boot loader works there, the video does not."""
        return self.speed is not None and not self.speed.super_speed


def _camera(device: Device, speed: Callable[[Device], Speed | None],
            children: Callable[[str], list[Device]], info: Callable[[str], Device | None]) -> Camera | None:
    vendor, product = device.ids
    if vendor != VENDOR or "&MI_" in device.instance.upper():
        return None
    if product == READY:
        video = next((child for child in children(device.instance) if child.service.lower() == VIDEO), None)
        if video is None:                   # Windows has not set the webcam up yet
            return Camera(READY_STATE, device, speed(device))
        return Camera(READY_STATE, device, speed(device), video.name, video.instance)
    if product != BOOT:
        return None
    parent = info(device.parent) if device.parent else None
    if parent is not None and parent.ids == ADAPTER:
        return Camera(PS4, device, speed(device))
    return Camera(BOOT_LOADER if device.service.lower() == WINUSB else NO_DRIVER, device, speed(device))


def find(present: Callable[[], list[str]] = devices.present, info: Callable[[str], Device | None] = devices.info,
         speed: Callable[[Device], Speed | None] = devices.speed,
         children: Callable[[str], list[Device]] = devices.children) -> list[Camera]:
    """Every camera plugged in, a ready one first."""
    found = []
    for instance in present():
        if f"VID_{VENDOR.upper()}" not in instance.upper():
            continue
        device = info(instance)
        camera = _camera(device, speed, children, info) if device is not None else None
        if camera is not None:
            found.append(camera)
    return sorted(found, key=lambda c: c.state != READY_STATE)
