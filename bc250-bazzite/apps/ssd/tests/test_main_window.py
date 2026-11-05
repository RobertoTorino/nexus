# SPDX-License-Identifier: GPL-3.0-or-later
"""The window opens offscreen with the suite's header and shows the chosen drive's three values; the version and the
icons are where the checks expect them."""

from __future__ import annotations

from fakes import SAMSUNG, SETUPS, FakeBus, v

from bc250_core.theme import GREEN, GREY, RED
from ssd_check import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__, smart
from ssd_check.main_window import MainWindow


def window(bus) -> MainWindow:
    w = MainWindow(run_=bus, threaded=False)
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
    assert [b.caption.text() for b in (w.health_box, w.cycles_box, w.hours_box)] == [
        "Health", "Power cycles", "Power-on hours"]
    assert (w.health_box.value.text(), w.cycles_box.value.text(), w.hours_box.value.text()) == (
        "100 %", "1,103", "4,025")
    assert GREEN.lower() in edge(w.health_box).lower()
    assert "168 days" in w.hours_box.toolTip()
    assert w.drive_box.count() == 1 and not w.drive_box.isEnabled()
    assert w.detail.text().startswith("NVMe drive, read by udisks at ")
    w.close()


def test_several_drives_are_chosen_from_the_list_and_kept_on_refresh(qapp):
    w = window(FakeBus(SETUPS))
    assert w.drive_box.count() == 3 and w.drive_box.isEnabled()
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
    assert w.state.text() == "No drive reports SMART" and w.drive_box.count() == 0
    assert w.health_box.value.text() == "—"
    w.run = FakeBus(down=True)
    w.refresh()
    assert w.state.text() == "udisks does not answer" and w.state.kind == "bad"
    assert "not provided" in w.detail.text() and w.refresh_button.isEnabled()
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
