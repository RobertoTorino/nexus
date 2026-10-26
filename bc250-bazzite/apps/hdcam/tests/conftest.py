# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and the XDG folders in a temp folder, and a fake /sys with the
camera plugged in (in boot mode or with its firmware), as the owner's board showed it (23-10-2026)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it

FIRMWARE = bytes(range(256)) * 269 + bytes(84)       # 68948 bytes, the size of the real file; not the real file


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry. The
    firmware folder and the upload's lock go to the temp folder too."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


ROOT_HUB = "devices/pci0000:00/0000:00:08.1/0000:05:00.3/usb7"


def plug(sys_root: Path, port: str = "7-1", product: str = "0580", speed: int = 5000, bus: int = 7,
         address: int = 3, hub: str = "", videos: tuple[int, ...] = ()) -> Path:
    """An OmniVision device as the kernel shows it: /sys/bus/usb/devices/<port> links to the device under its hub
    (the root hub, or *hub*: "vendor:product" of a hub in between, as Sony's PlayStation Camera Adapter is), with an
    interface folder. *videos*: the /dev/video<n> numbers uvcvideo made, each a capture node and a metadata node
    (the camera in boot mode has none)."""
    parent = sys_root / ROOT_HUB
    if hub:
        hub_port = port.rsplit(".", 1)[0]
        parent = parent / hub_port
        hub_vendor, hub_product = hub.split(":")
        write(parent / "idVendor", hub_vendor)
        write(parent / "idProduct", hub_product)
        link = sys_root / "bus/usb/devices" / hub_port
        if not link.exists():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(parent)
    device = parent / port
    interface = device / f"{port}:1.0"
    interface.mkdir(parents=True)
    for key, value in (("idVendor", "05a9"), ("idProduct", product), ("speed", str(speed)), ("busnum", str(bus)),
                       ("devnum", str(address))):
        write(device / key, value)
    link = sys_root / "bus/usb/devices" / port
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(device)
    (sys_root / "bus/usb/devices" / f"{port}:1.0").symlink_to(interface)
    for number in videos:
        for offset, index in ((0, 0), (1, 1)):
            node = sys_root / "class/video4linux" / f"video{number + offset}"
            node.mkdir(parents=True)
            write(node / "index", str(index))
            (node / "device").symlink_to(interface)
    return device


def unplug(sys_root: Path, port: str = "7-1") -> None:
    import shutil
    for link in list((sys_root / "bus/usb/devices").glob(f"{port}*")):
        target = link.resolve()
        link.unlink()
        if target.name == port:
            shutil.rmtree(target)
    for node in list((sys_root / "class/video4linux").glob("video*")):
        if not (node / "device").exists():
            shutil.rmtree(node)

