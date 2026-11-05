# SPDX-License-Identifier: GPL-3.0-or-later
"""udisks as busctl answers it: the owner's board (05-11-2026, a Samsung 970 EVO Plus on NVMe, its serial replaced)
and other setups, a SATA SSD by Crucial, a SATA drive without a known health attribute and a USB stick."""

from __future__ import annotations

import json

DRIVES = "/org/freedesktop/UDisks2/drives/"
SAMSUNG = DRIVES + "Samsung_SSD_970_EVO_Plus_2TB_SERIAL"
CRUCIAL = DRIVES + "CT500MX500SSD1_SERIAL"
OTHER = DRIVES + "Generic_SSD_SERIAL"
STICK = DRIVES + "SanDisk_Cruzer_SERIAL"


def v(kind: str, data) -> dict:
    return {"type": kind, "data": data}


def dev(name: str) -> dict:
    return v("ay", list(f"/dev/{name}".encode()) + [0])


def drive(model: str, size: int, sort: str, vendor: str = "") -> dict:
    return {"Vendor": v("s", vendor), "Model": v("s", model), "Size": v("t", size), "SortKey": v("s", sort),
            "Removable": v("b", False)}


def block(drive_path: str, name: str, partition: bool = False) -> dict:
    found = {"org.freedesktop.UDisks2.Block": {"Device": dev(name), "PreferredDevice": dev(name),
                                               "Drive": v("o", drive_path)}}
    if partition:
        found["org.freedesktop.UDisks2.Partition"] = {"Number": v("u", 1)}
    return found


BOARD = {
    SAMSUNG: {
        "org.freedesktop.UDisks2.Drive": drive("Samsung SSD 970 EVO Plus 2TB", 2000398934016,
                                               "00coldplug/00fixed/nvme0"),
        "org.freedesktop.UDisks2.NVMe.Controller": {
            "SmartUpdated": v("t", 1793842182), "SmartCriticalWarning": v("as", []),
            "SmartPowerOnHours": v("t", 4025), "SmartTemperature": v("q", 319)},
    },
    "/org/freedesktop/UDisks2/block_devices/nvme0n1": block(SAMSUNG, "nvme0n1"),
    "/org/freedesktop/UDisks2/block_devices/nvme0n1p1": block(SAMSUNG, "nvme0n1p1", partition=True),
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
]
OTHER_ROWS = [
    [12, "power-cycle-count", 50, 100, 100, 0, 77, 1, {}],
    [194, "temperature-celsius-2", 34, 67, 50, 0, 306150, 4, {}],
]

SETUPS = {
    **BOARD,
    CRUCIAL: {"org.freedesktop.UDisks2.Drive": drive("CT500MX500SSD1", 500107862016, "00coldplug/00fixed/sda"),
              "org.freedesktop.UDisks2.Drive.Ata": ata(1234 * 3600 + 1800)},
    "/org/freedesktop/UDisks2/block_devices/sda": block(CRUCIAL, "sda"),
    OTHER: {"org.freedesktop.UDisks2.Drive": drive("SSD", 256060514304, "00coldplug/00fixed/sdb", vendor="Generic"),
            "org.freedesktop.UDisks2.Drive.Ata": ata(90000)},
    "/org/freedesktop/UDisks2/block_devices/sdb": block(OTHER, "sdb"),
    STICK: {"org.freedesktop.UDisks2.Drive": drive("Cruzer", 32017047552, "01hotplug/sdc", vendor="SanDisk")},
    "/org/freedesktop/UDisks2/block_devices/sdc": block(STICK, "sdc"),
}
ROWS = {CRUCIAL: CRUCIAL_ROWS, OTHER: OTHER_ROWS}


class FakeBus:
    """A runner for smart.read_drives(): busctl's replies from *objects*, each drive's attributes from
    *attributes*; *fail* the paths whose SmartGetAttributes fails, *down* udisks not running."""

    def __init__(self, objects=None, attributes=None, fail=(), down=False):
        self.objects = BOARD if objects is None else objects
        self.attributes = {SAMSUNG: BOARD_ATTRIBUTES, **ROWS} if attributes is None else attributes
        self.fail, self.down = set(fail), down
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
        if self.down:
            return 1, "Call failed: The name org.freedesktop.UDisks2 was not provided by any .service files"
        path, method = argv[5], argv[7]
        if method == "GetManagedObjects":
            return 0, json.dumps({"type": "a{oa{sa{sv}}}", "data": [self.objects]})
        if method == "SmartGetAttributes":
            if path in self.fail:
                return 1, "Call failed: Error getting SMART data: device busy"
            reply = self.attributes.get(path, {})
            kind = "a{sv}" if isinstance(reply, dict) else "a(ysqiiixia{sv})"
            return 0, json.dumps({"type": kind, "data": [reply]})
        return 1, f"unexpected call {argv}"
