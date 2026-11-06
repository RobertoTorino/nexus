# SPDX-License-Identifier: GPL-3.0-or-later
"""drives.py: the drives from Windows' answers (the CIM query's JSON, the NVMe health log and Identify data, the
devices' links), each kind of drive, and a real read on Windows."""

from __future__ import annotations

import json
import sys

import pytest

from ssd_check import drives


def health_log(used=3, warning=0, cycles=496, hours=182, read_units=3_231_872, written_units=3_916_861) -> bytes:
    log = bytearray(512)
    log[0], log[5] = warning, used
    log[32:48] = read_units.to_bytes(16, "little")
    log[48:64] = written_units.to_bytes(16, "little")
    log[112:128] = cycles.to_bytes(16, "little")
    log[128:144] = hours.to_bytes(16, "little")
    return bytes(log)


def identify(major=1, minor=4, tertiary=0) -> bytes:
    data = bytearray(4096)
    data[80], data[81], data[82:84] = tertiary, minor, major.to_bytes(2, "little")
    return bytes(data)


def answers(log: bytes | None = None, ident: bytes | None = None):
    asked = []

    def query(number, data_type, request, length):
        asked.append((number, data_type, request, length))
        if data_type == drives.NVME_LOG_PAGE:
            return log
        return ident
    return query, asked


def walk_of(links=(), usb=False, reader=False):
    return lambda device: drives.DevicePath([list(row) for row in links], usb, reader)


NVME = {"number": 0, "model": "Samsung SSD 990 PRO 2TB", "bus": 17, "media": 4, "size": 2_000_398_934_016,
        "firmware": "4B2QJXD7", "device": r"SCSI\DISK&VEN_NVME", "letters": ["C"]}
ALLY_LINKS = [(0, 0, 0, 0), (4, 4, 4, 4), (0, 0, 0, 0)]        # the disk, its controller, a port that says nothing


def test_an_nvme_drive_gives_its_health_log_and_version():
    query, asked = answers(health_log(), identify(2, 0))
    drive = drives.drive_from(NVME, query, walk_of(ALLY_LINKS))
    assert (drive.health, drive.power_cycles, drive.hours, drive.warnings) == (97, 496, 182, [])
    assert drive.data_read == 3_231_872 * 512_000 and drives.size_text(drive.data_written) == "2.0 TB"
    assert (drive.kind, drive.bus, drive.interface, drive.smart) == ("NVMe drive", "NVMe", "NVMe 2.0", True)
    assert (drive.rated_read, drive.rated_write) == (7450, 6900)               # in rated.py's list
    assert (drive.speed, drive.link_mbps, drive.drive_mbps) == ("PCIe 4.0 x4", 7876, 7876)
    assert drive.board_link == "" and drives.held_back(drive) is None          # the port says nothing
    assert asked == [(0, drives.NVME_LOG_PAGE, drives.HEALTH_LOG, 512),
                     (0, drives.NVME_IDENTIFY, drives.IDENTIFY_CONTROLLER, 4096)]


def test_health_stops_at_0_and_the_warnings_are_named():
    query, _ = answers(health_log(used=105, warning=0b1001))
    drive = drives.drive_from(NVME, query, walk_of())
    assert drive.health == 0 and drive.warnings == ["spare", "readonly"]
    assert drive.interface == "NVMe"                                           # no Identify data


def test_an_nvme_drive_without_its_log_says_so():
    query, _ = answers(None, None)
    drive = drives.drive_from(NVME, query, walk_of())
    assert not drive.smart and drive.health is None and drive.smart_note == drives.NO_SMART


def test_the_port_that_holds_the_drive_back():
    query, _ = answers(health_log())
    drive = drives.drive_from(NVME, query, walk_of([(0, 0, 0, 0), (2, 2, 4, 4), (2, 2, 2, 2)]))
    assert drive.speed == "PCIe 2.0 x2" and drive.speed_tip == "The link could do PCIe 4.0 x4"
    assert (drive.board_link, drive.board_mbps) == ("PCIe 2.0 x2", 1000) and drives.held_back(drive) is True


@pytest.mark.parametrize("data, walk, kind, bus, note", [
    (dict(NVME, bus=11, model="CT1000MX500SSD1"), walk_of(), "SATA drive", "SATA", drives.NO_SMART_SATA),
    (dict(NVME, bus=3, media=3, model="ST1000LM048"), walk_of(), "SATA hard disk", "SATA", drives.NO_SMART_SATA),
    (dict(NVME, bus=7, model="SanDisk Extreme"), walk_of(), "Drive on USB", "USB", drives.NO_SMART_USB),
    (dict(NVME, bus=1, model="SD Card Reader - SE"), walk_of([(0, 0, 0, 0), (2, 1, 2, 1)], reader=True),
     "Memory card", "SD card", drives.NO_SMART_READER),
    (dict(NVME, bus=17, model="Samsung SSD 980 1TB"), walk_of(usb=True), "Drive on USB", "USB", drives.NO_SMART_USB),
])
def test_drives_without_smart_show_their_specs(data, walk, kind, bus, note):
    query, asked = answers(health_log(), identify())
    drive = drives.drive_from(data, query, walk)
    assert (drive.kind, drive.bus, drive.smart, drive.smart_note, drive.health) == (kind, bus, False, note, None)
    assert asked == []                                                         # only an NVMe drive's own bus is asked
    assert drive.firmware == "4B2QJXD7" and drive.letters == ["C"]


def test_the_card_readers_link_is_the_readers():
    query, _ = answers()
    reader = dict(NVME, bus=1, model="SD Card Reader - SE")
    drive = drives.drive_from(reader, query, walk_of([(0, 0, 0, 0), (2, 1, 2, 1)], reader=True))
    assert drive.speed == "PCIe 2.0 x1" and "card reader's link" in drive.speed_tip


def test_a_virtual_drive_is_left_out_and_the_drives_are_in_their_order():
    query, _ = answers(health_log())
    data = [dict(NVME, number=2, bus=15), dict(NVME, number=1, bus=1), NVME]
    found = drives.read_drives(run=lambda argv: json.dumps(data), query=query, walk=walk_of())
    assert [d.number for d in found] == [0, 1]
    one = drives.read_drives(run=lambda argv: json.dumps(NVME), query=query, walk=walk_of())
    assert [d.model for d in one] == ["Samsung SSD 990 PRO 2TB"]               # ConvertTo-Json: one, without a list
    assert drives.read_drives(run=lambda argv: "", query=query, walk=walk_of()) == []


def test_an_answer_that_is_not_json_says_so():
    with pytest.raises(drives.DrivesError, match="not JSON"):
        drives.read_drives(run=lambda argv: "Get-CimInstance: Access denied", query=answers()[0], walk=walk_of())


def test_the_query_is_one_powershell_query_and_never_asks_for_a_serial():
    seen = []
    drives.read_drives(run=lambda argv: seen.append(argv) or "[]", query=answers()[0], walk=walk_of())
    assert seen[0][0] == "powershell.exe" and "-EncodedCommand" in seen[0]
    assert "serial" not in drives.QUERY.lower() and "MSFT_PhysicalDisk" in drives.QUERY


def test_nvme_version_and_sizes():
    assert drives.nvme_version(identify(1, 4)) == "NVMe 1.4"
    assert drives.nvme_version(identify(1, 3, 1)) == "NVMe 1.3.1"
    assert drives.nvme_version(identify(0, 0)) == drives.nvme_version(b"") == "NVMe"
    assert drives.size_text(1_024_209_543_168) == "1.0 TB" and drives.size_text(512_002_883_584) == "512.0 GB"
    assert drives.pcie(4, 4) == "PCIe 4.0 x4" and drives.pcie(0, 4) == drives.pcie(4, 0) == ""


@pytest.mark.skipif(sys.platform != "win32", reason="reads this computer's drives through Windows")
def test_this_computers_drives():
    """Windows' own answers on this computer: no administrator needed, every drive with a model."""
    found = drives.read_drives()
    assert all(d.model for d in found)
    nvme = [d for d in found if d.bus == "NVMe" and d.smart]
    assert all(0 <= d.health <= 100 and d.hours is not None for d in nvme)
