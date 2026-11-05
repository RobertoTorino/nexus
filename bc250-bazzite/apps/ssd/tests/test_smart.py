# SPDX-License-Identifier: GPL-3.0-or-later
"""smart.read_drives() on the owner's board and on other setups: the three values, which drives are listed, and what
happens when udisks or a drive does not answer."""

from __future__ import annotations

import pytest
from fakes import CRUCIAL, OTHER, SAMSUNG, SETUPS, FakeBus, v

from ssd_check import smart


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
    assert [d.device for d in drives] == ["nvme0n1", "sda", "sdb"]      # by udisks' sort key; the stick has none
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
