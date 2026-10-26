# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, a fake /sys, /proc and /usr as the owner's
board reported them on 17-10-2026 (a UGREEN AX900 in its three USB modes, kernel 7.2.9-ogc3.1 with its build
tree), the kernel log lines the loader printed, and system paths in a temp folder for the driver helper."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

KERNEL = "7.2.9-ogc3.1.fc44.x86_64"
# The loader's lines in the kernel log on the owner's board, 17-10-2026: the first attempt with the main branch's
# firmware (the upload broke off at 0x170400), then the legacy-mcu1 branch, which worked.
LOG_FAILED = ("usb 2-5: New USB device found, idVendor=a69c, idProduct=8d80, bcdDevice= 1.00\n"
              "AICWFDBG(LOGINFO)\taicloadfw_chipmatch USE AIC8800D80\n"
              "chip_id=7, chip_mcu_id = 1\n"
              "### Upload fmacfw_8800d80_u02.bin firmware, @ = 120000  size=358072\n"
              "bin upload fail: 170400, err:-32\n"
              "usb_err:<aicwf_usb_probe,1792>: failed with errno 0\n")
LOG_WEDGED = "chip_id=0, chip_mcu_id = 1\n40100020 rd fail: -32\n"
LOG_WORKED = ("usb 2-5: New USB device found, idVendor=a69c, idProduct=8d80, bcdDevice= 1.00\n"
              "chip_id=7, chip_mcu_id = 1\n"
              "AIC8800D80 legacy: using Radxa SDK V3 loader profile\n"
              "usb 2-5: New USB device found, idVendor=a69c, idProduct=8d81, bcdDevice= 1.00\n"
              "AICWFDBG(LOGINFO)\tNew interface create wlan0\n")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def usb_device(sys_root: Path, name: str, vendor: str, product: str, product_name: str,
               interfaces: dict[str, str | None]) -> None:
    """A USB device in the fake /sys: interfaces map "1.0" to the driver bound there (None: no driver)."""
    device = sys_root / "bus/usb/devices" / name
    write(device / "idVendor", vendor)
    write(device / "idProduct", product)
    write(device / "product", product_name)
    write(device / "manufacturer", "aicsemi")
    for suffix, driver in interfaces.items():
        interface = sys_root / "bus/usb/devices" / f"{name}:{suffix}"
        interface.mkdir(parents=True, exist_ok=True)
        if driver:
            target = sys_root / "bus/usb/drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            (interface / "driver").symlink_to(os.path.relpath(target, interface))


def set_stick(sys_root: Path, mode: str | None) -> None:
    """The owner's stick in one of its modes, or unplugged (None)."""
    for old in (sys_root / "bus/usb/devices").glob("2-5*") if (sys_root / "bus/usb/devices").is_dir() else []:
        import shutil
        shutil.rmtree(old)
    for old in (sys_root / "class/net").glob("wlan*") if (sys_root / "class/net").is_dir() else []:
        import shutil
        shutil.rmtree(old)
    if mode == "storage":
        usb_device(sys_root, "2-5", "a69c", "5723", "Aic MSC", {"1.0": "usb-storage"})
        write(sys_root / "block/sda/device/vendor", "AIC     ")
        write(sys_root / "block/sda/device/model", "flash")
    else:
        import shutil
        shutil.rmtree(sys_root / "block/sda", ignore_errors=True)
    if mode == "loader":
        usb_device(sys_root, "2-5", "a69c", "8d80", "AIC Wlan", {"1.0": "aic_load_fw"})
    if mode == "wifi":
        usb_device(sys_root, "2-5", "a69c", "8d81", "AIC 8800D80",
                   {"1.0": "btusb", "1.1": "btusb", "1.2": "aic8800_fdrv"})
        wlan = sys_root / "class/net/wlan0"
        write(wlan / "operstate", "up")
        write(wlan / "carrier", "1")
        (wlan / "wireless").mkdir()
        part = sys_root / "bus/usb/devices/2-5:1.2"                    # as in /sys: the device is the interface
        (wlan / "device").symlink_to(os.path.relpath(part, wlan))


@pytest.fixture
def sys_root(tmp_path) -> Path:
    root = tmp_path / "sys"
    (root / "bus/usb/devices").mkdir(parents=True)
    write(root / "class/net/enp4s0/operstate", "up")
    (root / "class/net/enp4s0/device").mkdir(parents=True)
    r8169 = root / "bus/pci/drivers/r8169"
    r8169.mkdir(parents=True)
    (root / "class/net/enp4s0/device/driver").symlink_to(os.path.relpath(r8169, root / "class/net/enp4s0/device"))
    write(root / "class/net/lo/operstate", "unknown")
    set_stick(root, "wifi")
    return root


@pytest.fixture
def proc_root(tmp_path) -> Path:
    root = tmp_path / "proc"
    write(root / "modules", "aic8800_fdrv 1126400 0 - Live 0x0000000000000000 (OE)\n"
                            "aic_load_fw 155648 1 aic8800_fdrv, Live 0x0000000000000000 (OE)\n"
                            "cfg80211 1691648 1 aic8800_fdrv, Live 0x0000000000000000")
    return root


@pytest.fixture
def usr_root(tmp_path) -> Path:
    root = tmp_path / "usr"
    write(root / "lib/modules" / KERNEL / "build/.config", "CONFIG_CFG80211=m")
    write(root / "lib/modules" / KERNEL / "build/Makefile", "# the kernel's")
    return root


@pytest.fixture
def paths(tmp_path, usr_root, sys_root, proc_root):
    from usb_wifidriver import driver
    return driver.Paths(tmp_path / "etc", tmp_path / "var/lib", tmp_path / "run", usr_root, sys_root, proc_root,
                        tmp_path / "dev")


def fake_build(folder: Path, log: str = "built") -> None:
    """A build output as builder.collect leaves it: the two modules and the firmware folder with its self link."""
    folder.mkdir(parents=True, exist_ok=True)
    for module in ("aic_load_fw", "aic8800_fdrv"):
        (folder / f"{module}.ko").write_bytes(b"\x7fELF " + module.encode())
    fw = folder / "fw"
    fw.mkdir(exist_ok=True)
    (fw / "fmacfw_8800d80_u02.bin").write_bytes(b"\x00" * 64)
    (fw / "aic_userconfig_8800d80.txt").write_text("xtal_cap=24\n")
    if not (fw / "aic8800D80").exists():
        (fw / "aic8800D80").symlink_to(".")
    (folder / "build.log").write_text(log + "\n")


def fake_source(folder: Path) -> None:
    """A checkout as the fetch leaves it: the Makefile and the firmware folder."""
    write(folder / "drivers/aic8800/Makefile", "obj-m += aic_load_fw/ aic8800_fdrv/")
    write(folder / "drivers/aic8800/aic_load_fw/aicwf_usb.c", "// the loader")
    write(folder / "drivers/aic8800/aic_load_fw/aicwf_usb.o", "stale object")
    write(folder / "fw/aic8800D80/fmacfw_8800d80_u02.bin", "firmware")
    write(folder / "fw/aic8800D80/aic_userconfig_8800d80.txt", "xtal_cap=24")
