# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, a fake screen on a fake port and a fake
/sys with the screen plugged in."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def plug(sys_root: Path, tty: str, vendor: str = "1a86", product: str = "5722", name: str = "UsbMonitor",
         serial: str = "USB35INCHIPSV2") -> None:
    """A USB serial device as the kernel shows it: /sys/class/tty/<tty>/device is a link to the USB interface, whose
    parent folder is the USB device with its IDs (as on the owner's board, 22-10-2026)."""
    usb = sys_root / "devices/pci0000:00/0000:00:10.0/usb6" / f"6-{tty[-1]}"
    interface = usb / f"6-{tty[-1]}:1.0"
    interface.mkdir(parents=True)
    for key, value in (("idVendor", vendor), ("idProduct", product), ("product", name), ("serial", serial)):
        write(usb / key, value)
    (sys_root / "class/tty" / tty).mkdir(parents=True)
    (sys_root / "class/tty" / tty / "device").symlink_to(interface)


def interfaces(root: Path) -> Path:
    """/sys/class/net with a wired and a wireless card, a bridge and a VPN tunnel (no device: virtual)."""
    net = root / "class/net"
    for name, arp_type, device, wireless in (("enp4s0", 1, True, False), ("wlan0", 1, True, True),
                                             ("virbr0", 1, False, False), ("tun0", 65534, False, False)):
        write(net / name / "type", str(arp_type))
        if device:
            (net / name / "device").mkdir(exist_ok=True)
        if wireless:
            (net / name / "wireless").mkdir(exist_ok=True)
    return net


class FakePort:
    """A screen on the other end of the port: records what is written, answers HELLO with *reply*, and fails with
    OSError once *fail_after* writes have been made (an unplugged screen)."""

    def __init__(self, reply: bytes = b"", fail_after: int | None = None):
        self.reply = reply
        self.writes: list[bytes] = []
        self.fail_after = fail_after
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise OSError(5, "Input/output error")
        self.writes.append(bytes(data))

    def read(self, size: int, timeout: float) -> bytes:
        return self.reply[:size]

    def close(self) -> None:
        self.closed = True

    @property
    def data(self) -> bytes:
        return b"".join(self.writes)


def wait_until(qapp, condition, timeout: float = 5.0) -> bool:
    """Lets Qt deliver the link thread's signals until *condition* holds."""
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False
