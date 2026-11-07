# SPDX-License-Identifier: GPL-3.0-or-later
"""udisks as busctl answers it: the owner's board (05-11-2026, a Samsung 970 EVO Plus on NVMe, its serial replaced)
and other setups, a SATA SSD by Crucial, a SATA drive without a known health attribute and a USB stick; fwupd's
devices and sysfs' links for the same drives."""

from __future__ import annotations

import json
from pathlib import Path

DRIVES = "/org/freedesktop/UDisks2/drives/"
SAMSUNG = DRIVES + "Samsung_SSD_970_EVO_Plus_2TB_SERIAL"
CRUCIAL = DRIVES + "CT500MX500SSD1_SERIAL"
OTHER = DRIVES + "Generic_SSD_SERIAL"
STICK = DRIVES + "SanDisk_Cruzer_SERIAL"
EMPTY = DRIVES + "Card_Reader_SERIAL"
ENCLOSURE = DRIVES + "SAMSUNG_MZVL21T0HCLR_00BH1_SERIAL"


def v(kind: str, data) -> dict:
    return {"type": kind, "data": data}


def dev(name: str) -> dict:
    return v("ay", list(f"/dev/{name}".encode()) + [0])


def drive(model: str, size: int, sort: str, vendor: str = "", revision: str = "", serial: str = "",
          bus: str = "") -> dict:
    return {"Vendor": v("s", vendor), "Model": v("s", model), "Size": v("t", size), "SortKey": v("s", sort),
            "Removable": v("b", bus == "usb"), "Revision": v("s", revision), "Serial": v("s", serial),
            "ConnectionBus": v("s", bus), "Optical": v("b", False)}


def block(drive_path: str, name: str, partition: bool = False, mounts: tuple[str, ...] = ()) -> dict:
    found = {"org.freedesktop.UDisks2.Block": {"Device": dev(name), "PreferredDevice": dev(name),
                                               "Drive": v("o", drive_path)}}
    if partition:
        found["org.freedesktop.UDisks2.Partition"] = {"Number": v("u", 1)}
    if mounts:
        found["org.freedesktop.UDisks2.Filesystem"] = {
            "MountPoints": v("aay", [list(m.encode()) + [0] for m in mounts])}
    return found


BOARD = {
    SAMSUNG: {
        "org.freedesktop.UDisks2.Drive": drive("Samsung SSD 970 EVO Plus 2TB", 2000398934016,
                                               "00coldplug/00fixed/nvme0", revision="2B2QEXM7",
                                               serial="SAMSUNG-SERIAL"),
        "org.freedesktop.UDisks2.NVMe.Controller": {
            "NVMeRevision": v("s", "1.3"),
            "SmartUpdated": v("t", 1793842182), "SmartCriticalWarning": v("as", []),
            "SmartPowerOnHours": v("t", 4025), "SmartTemperature": v("q", 319)},
    },
    "/org/freedesktop/UDisks2/block_devices/nvme0n1": block(SAMSUNG, "nvme0n1"),
    "/org/freedesktop/UDisks2/block_devices/nvme0n1p1": block(SAMSUNG, "nvme0n1p1", partition=True,
                                                              mounts=("/boot/efi",)),
    "/org/freedesktop/UDisks2/block_devices/nvme0n1p3": block(SAMSUNG, "nvme0n1p3", partition=True,
                                                              mounts=("/sysroot", "/var", "/var/home")),
    "/org/freedesktop/UDisks2/Manager": {"org.freedesktop.UDisks2.Manager": {"Version": v("s", "2.11.2")}},
}
BOARD_ATTRIBUTES = {
    "avail_spare": v("y", 100), "spare_thresh": v("y", 10), "percent_used": v("y", 0),
    "total_data_read": v("t", 15021591552000), "total_data_written": v("t", 21579876352000),
    "ctrl_busy_time": v("t", 1614), "power_cycles": v("t", 1103), "unsafe_shutdowns": v("t", 9),
    "media_errors": v("t", 0), "num_err_log_entries": v("t", 1447),
    "temp_sensors": v("aq", [319, 314, 0, 0, 0, 0, 0, 0]), "wctemp": v("q", 358), "cctemp": v("q", 358),
}


def ata(seconds: int, failing: bool = False) -> dict:
    return {"SmartSupported": v("b", True), "SmartEnabled": v("b", True), "SmartUpdated": v("t", 1793840000),
            "SmartFailing": v("b", failing), "SmartPowerOnSeconds": v("t", seconds)}


# SmartGetAttributes rows: id, name, flags, value, worst, threshold, pretty, pretty_unit, expansion
CRUCIAL_ROWS = [
    [1, "raw-read-error-rate", 47, 100, 100, 0, 0, 1, {}],
    [9, "power-on-hours", 50, 100, 100, 0, 3600000 * 1234, 2, {}],
    [12, "power-cycle-count", 50, 100, 100, 0, 321, 1, {}],
    [202, "percent-lifetime-remain", 48, 94, 94, 1, 6, 1, {}],
    [241, "total-lbas-written", 50, 100, 100, 0, 9765625000, 1, {}],
    [242, "total-lbas-read", 50, 100, 100, 0, 3906250000, 1, {}],
]
OTHER_ROWS = [
    [12, "power-cycle-count", 50, 100, 100, 0, 77, 1, {}],
    [194, "temperature-celsius-2", 34, 67, 50, 0, 306150, 4, {}],
]

SETUPS = {
    **BOARD,
    CRUCIAL: {"org.freedesktop.UDisks2.Drive": drive("CT500MX500SSD1", 500107862016, "00coldplug/00fixed/sda",
                                                     revision="M3CR046", serial="CRUCIAL-SERIAL"),
              "org.freedesktop.UDisks2.Drive.Ata": ata(1234 * 3600 + 1800)},
    "/org/freedesktop/UDisks2/block_devices/sda": block(CRUCIAL, "sda"),
    OTHER: {"org.freedesktop.UDisks2.Drive": drive("SSD", 256060514304, "00coldplug/00fixed/sdb", vendor="Generic"),
            "org.freedesktop.UDisks2.Drive.Ata": ata(90000)},
    "/org/freedesktop/UDisks2/block_devices/sdb": block(OTHER, "sdb"),
    STICK: {"org.freedesktop.UDisks2.Drive": drive("Cruzer", 32017047552, "01hotplug/sdc", vendor="SanDisk",
                                                   revision="1.00", serial="STICK-SERIAL", bus="usb")},
    "/org/freedesktop/UDisks2/block_devices/sdc": block(STICK, "sdc"),
    EMPTY: {"org.freedesktop.UDisks2.Drive": drive("Card reader", 0, "01hotplug/sdd", bus="usb")},
}
ROWS = {CRUCIAL: CRUCIAL_ROWS, OTHER: OTHER_ROWS}

# The owner's USB enclosure (05-11-2026): a Samsung PM9A1 in a Realtek RTL9210 (0bda:9210), linked at USB 2.0 in a
# port that does USB 3 (its peer on the 5 Gb/s bus), with another system on it, mounted but owned by root
ENCLOSED = {
    **BOARD,
    ENCLOSURE: {"org.freedesktop.UDisks2.Drive": drive("SAMSUNG MZVL21T0HCLR-00BH1", 1024209543168,
                                                       "01hotplug/1793890681067371", revision="HPS3NGXH",
                                                       serial="ENCLOSURE-SERIAL", bus="usb")},
    "/org/freedesktop/UDisks2/block_devices/sdd": block(ENCLOSURE, "sdd"),
    "/org/freedesktop/UDisks2/block_devices/sdd3": block(ENCLOSURE, "sdd3", partition=True,
                                                         mounts=("/run/media/user/bazzite",)),
}

# fwupd's GetDevices: the board's drive, updatable (fwupd 2.1.8 on the board, 05-11-2026), and the Crucial, not
FWUPD_DEVICES = [
    {"DeviceId": v("s", "samsung-id"), "Name": v("s", "SSD 970 EVO Plus 2TB"), "Serial": v("s", "SAMSUNG-SERIAL"),
     "Flags": v("t", 4644337652597003), "Version": v("s", "2B2QEXM7"), "Plugin": v("s", "nvme")},
    {"DeviceId": v("s", "crucial-id"), "Name": v("s", "CT500MX500SSD1"), "Serial": v("s", "CRUCIAL-SERIAL"),
     "Flags": v("t", 1), "Version": v("s", "M3CR046")},
]
NO_SILO = "Call failed: no components in silo"      # the board's answer before fwupdmgr refresh


def sysfs(root: Path) -> Path:
    """A /sys with the board's NVMe link (PCIe 2.0 x2 of 3.0 x4, in a port of PCIe 2.0 x2), a SATA link at 6 Gb/s
    (the port's limit too) and a USB stick at 5 Gb/s on a 10 Gb/s bus."""
    def folder(path: str, files: dict[str, str]) -> Path:
        where = root / path
        where.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (where / name).write_text(text + "\n")
        return where

    folder("devices/pci0000:00/0000:00:15.0", {"current_link_speed": "5.0 GT/s PCIe", "current_link_width": "2",
                                               "max_link_speed": "5.0 GT/s PCIe", "max_link_width": "2"})
    pci = "devices/pci0000:00/0000:00:15.0/0000:03:00.0"
    folder(pci, {"current_link_speed": "5.0 GT/s PCIe", "current_link_width": "2",
                 "max_link_speed": "8.0 GT/s PCIe", "max_link_width": "4"})
    ahci = "devices/pci0000:00/0000:00:11.0"
    folder(ahci, {"current_link_speed": "8.0 GT/s PCIe", "current_link_width": "1"})
    xhci = "devices/pci0000:00/0000:00:14.0"
    folder(xhci, {"current_link_speed": "8.0 GT/s PCIe", "current_link_width": "1"})
    folder(f"{xhci}/usb2", {"idVendor": "1d6b", "speed": "10000"})
    folder(f"{xhci}/usb2/2-1", {"idVendor": "0781", "speed": "5000"})
    folder("class/ata_link/link1", {"sata_spd": "6.0 Gbps", "hw_sata_spd_limit": "6.0 Gbps"})
    board_xhci = "devices/pci0000:00/0000:00:10.0"
    folder(f"{board_xhci}/usb6", {"idVendor": "1d6b", "speed": "480"})
    folder(f"{board_xhci}/usb7", {"idVendor": "1d6b", "speed": "5000"})
    port2, peer2 = (root / f"{board_xhci}/usb6/6-0:1.0/usb6-port2", root / f"{board_xhci}/usb7/7-0:1.0/usb7-port2")
    port2.mkdir(parents=True)
    peer2.mkdir(parents=True)
    (port2 / "peer").symlink_to(peer2)
    enclosure = folder(f"{board_xhci}/usb6/6-2", {"idVendor": "0bda", "idProduct": "9210", "speed": "480"})
    (enclosure / "port").symlink_to(port2)
    blocks = {"nvme0n1": f"{pci}/nvme/nvme0/nvme0n1",
              "sdd": f"{board_xhci}/usb6/6-2/6-2:1.0/host7/target7:0:0/7:0:0:0/block/sdd", "sda": f"{ahci}/ata1/host0/target0:0:0/0:0:0:0/block/sda",
              "sdc": f"{xhci}/usb2/2-1/2-1:1.0/host6/target6:0:0/6:0:0:0/block/sdc"}
    (root / "block").mkdir(parents=True, exist_ok=True)
    for name, path in blocks.items():
        folder(path, {})
        (root / "block" / name).symlink_to(root / path)
    return root


class FakeBus:
    """A runner for smart.read_drives(): busctl's replies from *objects*, each drive's attributes from
    *attributes*; *fail* the paths whose SmartGetAttributes fails, *down* udisks not running; *fwupd* fwupd's devices
    (None: not running), *upgrades* GetUpgrades' reply per device id (a list, or busctl's error)."""

    def __init__(self, objects=None, attributes=None, fail=(), down=False, fwupd=None, upgrades=None):
        self.objects = BOARD if objects is None else objects
        self.attributes = {SAMSUNG: BOARD_ATTRIBUTES, **ROWS} if attributes is None else attributes
        self.fail, self.down = set(fail), down
        self.fwupd = fwupd                      # fwupd's devices; None: fwupd not running
        self.upgrades = upgrades or {}          # device id: its releases (a list) or busctl's error (a str)
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
        if self.down:
            return 1, "Call failed: The name org.freedesktop.UDisks2 was not provided by any .service files"
        service, path, method = argv[4], argv[5], argv[7]
        if service == "org.freedesktop.fwupd":
            if self.fwupd is None:
                return 1, "Call failed: The name org.freedesktop.fwupd was not provided by any .service files"
            if method == "GetDevices":
                return 0, json.dumps({"type": "aa{sv}", "data": [self.fwupd]})
            reply = self.upgrades.get(argv[9], NO_SILO)
            if isinstance(reply, str):
                return 1, reply
            return 0, json.dumps({"type": "aa{sv}", "data": [reply]})
        if method == "GetManagedObjects":
            return 0, json.dumps({"type": "a{oa{sa{sv}}}", "data": [self.objects]})
        if method == "SmartGetAttributes":
            if path in self.fail:
                return 1, "Call failed: Error getting SMART data: device busy"
            reply = self.attributes.get(path, {})
            kind = "a{sv}" if isinstance(reply, dict) else "a(ysqiiixia{sv})"
            return 0, json.dumps({"type": kind, "data": [reply]})
        return 1, f"unexpected call {argv}"
