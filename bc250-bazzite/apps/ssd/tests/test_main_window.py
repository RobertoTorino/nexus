# SPDX-License-Identifier: GPL-3.0-or-later
"""The window opens offscreen with the suite's header and shows the chosen drive's three values and its specs; the
version and the icons are where the checks expect them."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QLabel
from fakes import ENCLOSED, FWUPD_DEVICES, SAMSUNG, SETUPS, FakeBus, sysfs, v

from bc250_core.theme import GREEN, GREY, ORANGE, RED
from ssd_check import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, smart
from ssd_check.main_window import HIDDEN, MainWindow


@pytest.fixture
def fake_sys(tmp_path):
    return sysfs(tmp_path / "sys")


def window(bus, sys_=None) -> MainWindow:
    w = MainWindow(run_=bus, threaded=False, sysfs=sys_ or Path("/nonexistent"), home=Path("/var/home/user"))
    w.show()
    return w


def edge(box) -> str:
    return box.styleSheet()


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()


def test_the_boards_drive_in_the_header(qapp):
    w = window(FakeBus())
    assert w.windowTitle() == APP_NAME
    assert w.state.text() == "No problems reported" and w.state.kind == "ok"
    assert [b.caption.text() for b in (w.health_box, w.serial_pill, w.measure_pill, w.refresh_pill)] == [
        "Health", "Serial", "Measured R / W MB/s", "Click to refresh"]
    assert (w.health_box.value.text(), w.cycles_box.value.text(), w.hours_box.value.text(),
            w.days_box.value.text()) == ("100 %", "1,103", "4,025", "167")         # 4,025 h: 167 full days
    assert GREEN.lower() in edge(w.health_box).lower()
    assert "0.5 years" in w.hours_box.toolTip()
    assert w.drive_box.count() == 1 and not w.drive_box.isEnabled() and w.drive_box.currentText() == "Drive 1"
    assert w.model.text() == "Samsung SSD 970 EVO Plus 2TB · 2.0 TB"
    assert w.detail.text().startswith("NVMe drive, read by udisks at ")
    w.close()


def test_several_drives_are_chosen_from_the_list_and_kept_on_refresh(qapp):
    w = window(FakeBus(SETUPS))
    assert w.drive_box.count() == 4 and w.drive_box.isEnabled()
    assert [w.drive_box.itemText(i) for i in range(4)] == ["Drive 1", "Drive 2", "Drive 3", "Drive 4"]
    w.drive_box.setCurrentIndex(2)
    assert w.health_box.value.text() == "Not reported" and w.state.text() == "Health not reported"
    assert GREY.lower() in edge(w.health_box).lower() or "#1565c0" in edge(w.health_box).lower()
    w.refresh()
    assert w.drive_box.currentIndex() == 2 and w.cycles_box.value.text() == "77"
    w.drive_box.setCurrentIndex(1)
    assert w.health_box.value.text() == "94 %" and "attribute 202" in w.health_box.toolTip()
    w.close()


def test_a_warning_turns_the_state_and_the_health_red(qapp):
    objects = dict(FakeBus().objects)
    objects[SAMSUNG] = {**objects[SAMSUNG], smart.NVME: {**objects[SAMSUNG][smart.NVME],
                                                         "SmartCriticalWarning": v("as", ["spare"])}}
    w = window(FakeBus(objects))
    assert w.state.text() == "The drive reports a problem" and w.state.kind == "bad"
    assert "little spare space left" in w.state.toolTip()
    assert RED.lower() in edge(w.health_box).lower()
    w.close()


def test_partly_read_and_no_drive_and_no_udisks(qapp):
    w = window(FakeBus(fail={SAMSUNG}))
    assert w.state.text() == "Partly read" and w.state.kind == "warn"
    assert w.hours_box.value.text() == "4,025" and w.cycles_box.value.text() == "—"
    w.run = FakeBus({})
    w.refresh()
    assert w.state.text() == "No drive found" and w.drive_box.count() == 0
    assert w.health_box.value.text() == "—"
    w.run = FakeBus(down=True)
    w.refresh()
    assert w.state.text() == "udisks does not answer" and w.state.kind == "bad"
    assert "not provided" in w.detail.text() and w.refresh_pill.isEnabled()
    w.close()


def test_the_threaded_read_reports_back(qapp):
    from PyQt6.QtTest import QTest
    w = MainWindow(run_=FakeBus())
    for _ in range(100):
        if w.drives:
            break
        QTest.qWait(20)
    assert w.health_box.value.text() == "100 %" and not w.readers
    w.close()


def test_the_specs_are_pills(qapp, fake_sys):
    w = window(FakeBus(fwupd=FWUPD_DEVICES), fake_sys)
    assert [b.caption.text() for b in w.specs] == [
        "Power cycles", "Power-on hours", "Power-on days", "Drive",
        "Host reads", "Host writes", "Firmware", "Update",
        "Interface", "Speed", "Board link", "Rated R / W MB/s"]
    assert [b.value.text() for b in w.specs] == [
        "1,103", "4,025", "167", "nvme0n1",
        "15.0 TB", "21.6 TB", "2B2QEXM7", "Unknown",
        "NVMe 1.3", "PCIe 2.0 x2", "PCIe 2.0 x2", "3,500 / 3,300"]
    assert w.serial_pill.value.text() == HIDDEN and w.measure_pill.value.text() == "Test"
    assert "fwupdmgr refresh" in w.update_box.toolTip() and "PCIe 3.0 x4" in w.speed_box.toolTip()
    assert len({b.minimumWidth() for b in w.specs}) == 1                 # all as wide as the widest
    w.close()


def test_the_serial_shows_in_a_popup_and_the_pill_keeps_its_width(qapp):
    w = window(FakeBus(SETUPS))
    width = w.serial_pill.width()
    assert w.serial_pill.value.text() == HIDDEN and "SERIAL" not in w.serial_pill.toolTip()
    w.serial_pill.click()
    labels = w.serial_popup.findChildren(QLabel)
    assert [label.text() for label in labels] == ["SAMSUNG-SERIAL"] and w.serial_popup.isVisible()
    assert w.serial_pill.value.text() == HIDDEN and w.serial_pill.width() == width
    w.drive_box.setCurrentIndex(1)                                      # another drive: the popup goes
    assert w.serial_popup is None
    w.serial_pill.click()
    assert w.serial_popup.findChildren(QLabel)[0].text() == "CRUCIAL-SERIAL"
    w.refresh()                                                         # and after Refresh
    assert w.serial_popup is None
    w.close()


def test_a_usb_stick_shows_its_specs_without_smart(qapp, fake_sys):
    w = window(FakeBus(SETUPS), fake_sys)
    w.drive_box.setCurrentIndex(3)
    assert w.state.text() == "No SMART over USB" and w.health_box.value.text() == "—"
    assert w.model.text() == "SanDisk Cruzer · 32.0 GB" and w.detail.text() == "USB drive."
    assert (w.interface_box.value.text(), w.speed_box.value.text(), w.device_box.value.text()) == (
        "USB", "5 Gb/s", "sdc")
    w.close()


def test_an_available_firmware_turns_the_update_pill_orange(qapp):
    bus = FakeBus(fwupd=FWUPD_DEVICES, upgrades={"samsung-id": [{"Version": v("s", "4B2QEXM7")}]})
    w = window(bus)
    assert w.update_box.value.text() == "Available" and ORANGE.lower() in edge(w.update_box).lower()
    w.close()


def test_the_board_holding_the_drive_back_is_orange(qapp, fake_sys):
    w = window(FakeBus(), fake_sys)
    assert ORANGE.lower() in edge(w.board_box).lower()
    assert "about 1,000 MB/s" in w.board_box.toolTip() and "holds it back" in w.board_box.toolTip()
    w.close()


def test_a_drive_not_in_the_list_shows_its_fastest_link(qapp, fake_sys):
    w = window(FakeBus(SETUPS), fake_sys)
    w.drive_box.setCurrentIndex(3)                                      # the USB stick
    assert w.rated_box.value.text() == "Unknown" and "about 500 MB/s" in w.rated_box.toolTip()
    assert GREEN.lower() in edge(w.board_box).lower() and "fast enough" in w.board_box.toolTip()
    w.close()


def test_measuring_shows_the_speeds_per_drive(qapp, tmp_path, monkeypatch):
    from ssd_check import main_window
    monkeypatch.setattr(main_window.speedtest, "measure", lambda folder: (812.4, 549.6))
    w = window(FakeBus(SETUPS))
    monkeypatch.setattr(w, "test_folder", lambda drive: tmp_path if drive.device == "nvme0n1" else None)
    w.show_drive()
    assert w.measure_pill.value.text() == "Test" and w.measure_pill.isEnabled()
    w.measure_pill.click()
    assert w.measure_pill.value.text() == "812 / 550" and w.speed_test is None
    w.drive_box.setCurrentIndex(1)                                      # not mounted: nothing to measure
    assert w.measure_pill.value.text() == "—" and not w.measure_pill.isEnabled()
    w.drive_box.setCurrentIndex(0)
    assert w.measure_pill.value.text() == "812 / 550"
    monkeypatch.setattr(main_window.speedtest, "measure", lambda folder: (_ for _ in ()).throw(
        main_window.speedtest.SpeedError("Not enough free space on the drive")))
    w.measure_pill.click()
    assert w.measure_pill.value.text() == "Failed" and "free space" in w.measure_pill.toolTip()
    w.close()


def test_the_enclosure_on_a_slow_link_and_a_folder_of_roots(qapp, fake_sys):
    w = window(FakeBus(ENCLOSED), fake_sys)
    w.drive_box.setCurrentIndex(1)
    assert w.interface_box.value.text() == "NVMe over USB" and w.state.text() == "No SMART over USB"
    assert ORANGE.lower() in edge(w.speed_box).lower() and "cable" in w.speed_box.toolTip()
    assert w.board_box.value.text() == "5 Gb/s"
    assert w.measure_pill.value.text() == "—" and "belong to root" in w.measure_pill.toolTip()
    w.close()


def test_screenshot_saves_the_window_as_a_png_beside_the_drive_list(qapp, tmp_path):
    from PyQt6.QtGui import QImage
    w = MainWindow(run_=FakeBus(SETUPS), threaded=False, sysfs=Path("/nonexistent"), home=Path("/var/home/user"),
                   pictures_=tmp_path / "shots")
    w.show()
    assert w.shot_button.text() == "Screenshot"
    button, chooser = w.shot_button.geometry(), w.drive_box.geometry()
    assert abs(button.center().y() - chooser.center().y()) <= 2 and button.left() > chooser.right()   # its line
    w.shot_button.click()
    w.shot_button.click()                                                   # a second in the same second: (2)
    files = sorted((tmp_path / "shots").iterdir())
    assert len(files) == 2 and all(f.suffix == ".png" and f.name.startswith("SSD Check ") for f in files)
    image = QImage(str(files[0]))
    assert not image.isNull() and image.width() == w.width()
    assert w.shot_note.text().startswith("Saved: SSD Check ") and w.serial_pill.value.text() == HIDDEN
    w.close()


def test_a_screenshot_that_cannot_be_written_says_so(qapp, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")                                                  # a file where the folder should be
    w = MainWindow(run_=FakeBus(), threaded=False, sysfs=Path("/nonexistent"), pictures_=blocker / "shots")
    w.shot_button.click()
    assert w.shot_note.text() == "The screenshot could not be saved"
    w.close()


def test_screenshot_names_never_overwrite(tmp_path):
    import datetime
    from ssd_check.main_window import screenshot_path
    now = datetime.datetime(2026, 11, 5, 18, 4, 9)
    first = screenshot_path(tmp_path, now)
    assert first.name == "SSD Check 2026-11-05 18-04-09.png"
    first.write_bytes(b"")
    assert screenshot_path(tmp_path, now).name == "SSD Check 2026-11-05 18-04-09 (2).png"
