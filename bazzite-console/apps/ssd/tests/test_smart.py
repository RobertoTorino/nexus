# SPDX-License-Identifier: GPL-3.0-or-later
"""smart.read_drives() on the owner's board and on other setups: the three values, the specs, which drives are listed,
and what happens when udisks, fwupd or a drive does not answer."""

from __future__ import annotations

import pytest
from fakes import CRUCIAL, ENCLOSED, FWUPD_DEVICES, OTHER, SAMSUNG, SETUPS, FakeBus, sysfs, v

from ssd_check import smart


@pytest.fixture(autouse=True)
def no_real_sysfs(tmp_path, monkeypatch):
    """A test that passes no sysfs gets an empty one, not the machine's /sys: a drive plugged into the board (an
    enclosure at sdc) would otherwise give the fake drive of that name its link."""
    monkeypatch.setattr(smart.read_drives, "__defaults__", (smart.run, tmp_path / "no-sys"))


def test_the_boards_nvme_drive_gives_all_three_values():
    bus = FakeBus()
    [drive] = smart.read_drives(bus)
    assert (drive.model, drive.device, drive.bus) == ("Samsung SSD 970 EVO Plus 2TB", "nvme0n1", "NVMe")
    assert (drive.health, drive.power_cycles, drive.hours) == (100, 1103, 4025)
    assert drive.warnings == [] and drive.error == "" and drive.updated == 1793842182
    assert drive.label == "Samsung SSD 970 EVO Plus 2TB (nvme0n1, 2.0 TB)"
    assert bus.calls[0][:3] == ["busctl", "--system", "--json=short"]
    assert bus.calls[1][5:] == [SAMSUNG, smart.NVME, "SmartGetAttributes", "a{sv}", "0"]


def test_the_label_never_holds_the_serial():
    drives = smart.read_drives(FakeBus(SETUPS))
    assert drives and all("SERIAL" not in d.label for d in drives)


def test_health_is_100_minus_percent_used_and_stops_at_zero():
    for used, health in ((3, 97), (100, 0), (255, 0)):
        attributes = {SAMSUNG: {"percent_used": v("y", used), "power_cycles": v("t", 1)}}
        [drive] = smart.read_drives(FakeBus(attributes=attributes))
        assert drive.health == health


def test_a_critical_warning_is_kept():
    objects = {k: dict(i) for k, i in FakeBus().objects.items()}
    controller = dict(objects[SAMSUNG][smart.NVME])
    controller["SmartCriticalWarning"] = v("as", ["spare", "temperature"])
    objects[SAMSUNG] = {**objects[SAMSUNG], smart.NVME: controller}
    [drive] = smart.read_drives(FakeBus(objects))
    assert drive.warnings == ["spare", "temperature"]


def test_sata_drives_and_a_usb_stick_without_smart():
    drives = smart.read_drives(FakeBus(SETUPS))
    assert [d.device for d in drives] == ["nvme0n1", "sda", "sdb", "sdc"]   # by udisks' sort key; no empty reader
    stick = drives[3]
    assert (stick.bus, stick.interface, stick.smart, stick.model) == ("USB", "USB", False, "SanDisk Cruzer")
    assert (stick.health, stick.hours, stick.power_cycles, stick.firmware) == (None, None, None, "1.00")
    crucial, other = drives[1], drives[2]
    assert (crucial.bus, crucial.health, crucial.power_cycles, crucial.hours) == ("SATA", 94, 321, 1234)
    assert crucial.health_source == "attribute 202, Percent lifetime remaining"
    assert (other.health, other.power_cycles, other.hours, other.model) == (None, 77, 25, "Generic SSD")


def test_the_first_known_health_attribute_wins_and_odd_values_are_skipped():
    rows = [[177, "wear-leveling-count", 0, 88, 88, 0, 120, 1, {}], [231, "ssd-life-left", 0, 253, 253, 0, 0, 1, {}]]
    drives = smart.read_drives(FakeBus(SETUPS, attributes={CRUCIAL: rows, OTHER: []}))
    assert drives[1].health == 88 and drives[1].health_source.startswith("attribute 177")


def test_a_failing_sata_drive_is_flagged():
    objects = dict(SETUPS)
    objects[CRUCIAL] = {**SETUPS[CRUCIAL], smart.ATA: {**SETUPS[CRUCIAL][smart.ATA], "SmartFailing": v("b", True)}}
    assert smart.read_drives(FakeBus(objects))[1].warnings == ["failing"]


def test_a_drive_whose_attributes_fail_keeps_its_properties_and_the_error():
    drives = smart.read_drives(FakeBus(SETUPS, fail={SAMSUNG, CRUCIAL}))
    assert (drives[0].hours, drives[0].health, drives[0].power_cycles) == (4025, None, None)
    assert (drives[1].hours, drives[1].health) == (1234, None)
    assert "device busy" in drives[0].error and drives[2].error == ""


def test_udisks_not_answering_is_an_error_with_its_reason():
    with pytest.raises(smart.SmartError, match="udisks does not answer.*not provided"):
        smart.read_drives(FakeBus(down=True))
    with pytest.raises(smart.SmartError, match="not JSON"):
        smart.read_drives(lambda argv: (0, "<html>"))


def test_without_busctl():
    assert smart.run(["/nonexistent/busctl"]) == (127, smart.NO_BUSCTL)
    with pytest.raises(smart.SmartError, match="busctl is missing"):
        smart.read_drives(lambda argv: (127, smart.NO_BUSCTL))


@pytest.mark.parametrize("size, text", [(999, "999 B"), (500107862016, "500.1 GB"), (2000398934016, "2.0 TB"),
                                        (16 * 10**15, "16000.0 TB")])
def test_sizes_in_decimal_units(size, text):
    assert smart.size_text(size) == text


def test_the_boards_specs(tmp_path):
    [drive] = smart.read_drives(FakeBus(), sysfs(tmp_path))
    assert (drive.firmware, drive.interface, drive.serial) == ("2B2QEXM7", "NVMe 1.3", "SAMSUNG-SERIAL")
    assert (drive.speed, drive.speed_tip) == ("PCIe 2.0 x2", "The drive can do PCIe 3.0 x4")
    assert (smart.size_text(drive.data_read), smart.size_text(drive.data_written)) == ("15.0 TB", "21.6 TB")


def test_the_serial_stays_out_of_the_repr():
    assert all("SERIAL" not in repr(d) for d in smart.read_drives(FakeBus(SETUPS)))


def test_sata_and_usb_links_and_the_sata_data_in_sectors(tmp_path):
    drives = smart.read_drives(FakeBus(SETUPS), sysfs(tmp_path))
    crucial, other, stick = drives[1], drives[2], drives[3]
    assert (crucial.interface, crucial.speed, crucial.speed_tip) == ("SATA", "6.0 Gb/s", "SATA III")
    assert (crucial.data_written, crucial.data_read) == (9765625000 * 512, 3906250000 * 512)
    assert (other.speed, other.data_read) == ("", None)            # no sysfs entry, no attributes 241 and 242
    assert (stick.speed, stick.speed_tip) == ("5 Gb/s", "USB 3.2 Gen 1")


def test_no_sysfs_leaves_the_speed_empty(tmp_path):
    [drive] = smart.read_drives(FakeBus(), tmp_path)
    assert drive.speed == "" and drive.interface == "NVMe 1.3"


@pytest.mark.parametrize("speed, width, text", [("8.0 GT/s PCIe", "4", "PCIe 3.0 x4"), ("16.0 GT/s PCIe", "4",
                                                "PCIe 4.0 x4"), ("Unknown", "4", ""), ("8.0 GT/s PCIe", "", "")])
def test_pcie_names(speed, width, text):
    assert smart.pcie(speed, width) == text


def test_firmware_updates_from_fwupd():
    drives = smart.read_drives(FakeBus(SETUPS, fwupd=FWUPD_DEVICES))
    assert (drives[0].update, drives[0].update_tip) == (smart.UNKNOWN, smart.NO_METADATA)    # the board, today
    assert drives[1].update == smart.NOT_SUPPORTED and "cannot update" in drives[1].update_tip
    assert drives[2].update == smart.NOT_SUPPORTED and "knows no firmware" in drives[2].update_tip
    newer = FakeBus(fwupd=FWUPD_DEVICES, upgrades={"samsung-id": [{"Version": v("s", "4B2QEXM7")}]})
    [drive] = smart.read_drives(newer)
    assert drive.update == smart.AVAILABLE and "4B2QEXM7" in drive.update_tip
    assert newer.calls[-1][4:] == ["org.freedesktop.fwupd", "/", "org.freedesktop.fwupd", "GetUpgrades", "s",
                                   "samsung-id"]
    latest = FakeBus(fwupd=FWUPD_DEVICES, upgrades={"samsung-id": "Call failed: No upgrades for SSD 970 EVO Plus "
                                                                  "2TB, current is 2B2QEXM7"})
    assert smart.read_drives(latest)[0].update == smart.UP_TO_DATE
    odd = FakeBus(fwupd=FWUPD_DEVICES, upgrades={"samsung-id": "Call failed: Access denied"})
    [drive] = smart.read_drives(odd)
    assert drive.update == smart.UNKNOWN and "Access denied" in drive.update_tip


def test_without_fwupd_the_update_is_unknown():
    [drive] = smart.read_drives(FakeBus())
    assert drive.update == smart.UNKNOWN and drive.update_tip.startswith("fwupd does not answer")


def test_the_board_holds_the_boards_drive_back(tmp_path):
    [drive] = smart.read_drives(FakeBus(), sysfs(tmp_path))
    assert (drive.board_link, drive.board_mbps, drive.link_mbps, drive.drive_mbps) == ("PCIe 2.0 x2", 1000, 1000,
                                                                                      3940)
    assert (drive.rated_read, drive.rated_write) == (3500, 3300) and smart.held_back(drive) is True


def test_a_port_fast_enough_and_the_sata_and_usb_ports(tmp_path):
    drives = smart.read_drives(FakeBus(SETUPS), sysfs(tmp_path))
    crucial, stick = drives[1], drives[3]
    assert (crucial.board_link, crucial.board_mbps, crucial.rated_read) == ("6.0 Gb/s", 600, 560)
    assert smart.held_back(crucial) is False
    assert (stick.board_link, stick.board_mbps, stick.drive_mbps, stick.rated_read) == ("10 Gb/s", 1212, 500, None)
    assert smart.held_back(stick) is False                          # not rated: its fastest link counts
    assert smart.held_back(drives[2]) is None                       # no sysfs entry: unknown


def test_the_mount_points_of_each_drive():
    drives = smart.read_drives(FakeBus(SETUPS))
    assert drives[0].mounts == ["/boot/efi", "/sysroot", "/var", "/var/home"] and drives[1].mounts == []


@pytest.mark.parametrize("speed, width, mbps", [("5.0 GT/s PCIe", "2", 1000), ("8.0 GT/s PCIe", "4", 3940),
                                                ("32.0 GT/s PCIe", "4", 15752), ("Unknown", "4", None)])
def test_what_a_pcie_link_carries(speed, width, mbps):
    assert smart.pcie_mbps(speed, width) == mbps


def test_an_nvme_enclosure_linked_at_usb_2_in_a_usb_3_port(tmp_path):
    """The owner's enclosure: its port does 5 Gb/s (its peer on the USB 3 bus), the drive linked at 480 Mb/s."""
    drive = smart.read_drives(FakeBus(ENCLOSED), sysfs(tmp_path))[1]
    assert (drive.model, drive.bus, drive.interface, drive.smart) == ("SAMSUNG MZVL21T0HCLR-00BH1", "USB",
                                                                      "NVMe over USB", False)
    assert (drive.speed, drive.speed_tip) == ("480 Mb/s", "USB 2.0, Realtek RTL9210 enclosure")
    assert (drive.board_link, drive.board_mbps, drive.drive_mbps) == ("5 Gb/s", 500, None)
    assert "linked at USB 2.0" in drive.slow_link and "cable" in drive.slow_link
    assert smart.held_back(drive) is None                           # at USB 2.0 its own top speed is unknown
    assert drive.mounts == ["/run/media/user/bazzite"]


def test_a_usb_3_drive_in_a_faster_port_has_no_slow_link(tmp_path):
    stick = smart.read_drives(FakeBus(SETUPS), sysfs(tmp_path))[3]
    assert (stick.speed, stick.board_link, stick.slow_link) == ("5 Gb/s", "10 Gb/s", "")    # the stick's own limit
