# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): a card for each drive with its pane, the values and states of each kind of drive,
X measures, Y reads again, RB saves a screenshot that Explorer then shows; it fits the handheld's screen, B goes back
and View exits; the version and the icons are where the checks expect them."""

from __future__ import annotations

import re
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import AMBER, DOT, EXIT
from ssd_check import APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, drives
from ssd_check.main_window import MainWindow


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def nvme(**changes) -> drives.Drive:
    drive = drives.Drive(number=0, model="Samsung SSD 990 PRO 2TB", size=2_000_398_934_016, bus="NVMe",
                         kind="NVMe drive", smart=True, health=97, power_cycles=1496, hours=4025,
                         data_read=1_700_000_000_000, data_written=2_000_000_000_000, firmware="4B2QJXD7",
                         interface="NVMe 2.0", speed="PCIe 4.0 x4", speed_tip="The link runs as fast as the drive goes",
                         link_mbps=7876, drive_mbps=7876, rated_read=7450, rated_write=6900, letters=["C"])
    for key, value in changes.items():
        setattr(drive, key, value)
    return drive


CARD = drives.Drive(number=1, model="SD Card Reader - SE", size=512_002_883_584, bus="SD card", kind="Memory card",
                    smart_note=drives.NO_SMART_READER, firmware="100", interface="SD card", letters=["D"])


def settle(qapp, window) -> None:
    """Until the reading and the speed test have reported (they run in threads of their own)."""
    for _ in range(500):
        qapp.processEvents()
        if not window.reader.busy and not window.tester.busy:
            qapp.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("the worker did not report")


def make(qapp, tmp_path, found=None, measure=None):
    found = [nvme(), CARD] if found is None else found
    reads = []

    def read():
        reads.append(True)
        if isinstance(found, Exception):
            raise found
        return list(found)
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False), read=read,
                        measure=measure or (lambda folder: (6123.4, 5012.6)), own=tmp_path / "own",
                        pictures=tmp_path / "Pictures")
    window.reads = reads
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    qapp.processEvents()
    window.start()
    settle(qapp, window)
    return window


def value(window, name: str) -> str:
    return window.pane.values[name].text()


def test_the_window_opens_with_the_suites_header(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    window.close()


def test_a_card_for_each_drive_and_the_nvme_drives_values(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert [c.title.text() for c in window.cards] == ["Drive 1", "Drive 2"] and window.cards[0].hasFocus()
    assert window.cards[0].text.text() == "Health 97 % · 2.0 TB"
    assert window.cards[1].text.text() == "Memory card · 512.0 GB"
    pane = window.pane
    assert pane.title.text() == "Samsung SSD 990 PRO 2TB" and pane.kind.text() == "NVMe drive · 2.0 TB · C:"
    assert pane.state.text() == "No problems reported"
    assert [value(window, n) for n in ("Health", "Power cycles", "Power-on hours", "Power-on days", "Host reads",
                                       "Host writes")] == ["97 %", "1,496", "4,025", "167", "1.7 TB", "2.0 TB"]
    assert [value(window, n) for n in ("Firmware", "Interface", "Speed", "Board link", "Rated R / W MB/s",
                                       "Measured R / W MB/s")] == [
        "4B2QJXD7", "NVMe 2.0", "PCIe 4.0 x4", "Not reported", "7,450 / 6,900", "X to test"]
    assert pane.note.text() == "The link runs as fast as the drive goes."
    assert window.legend.items[:3] == [("X", "Test speed"), ("Y", "Read again"), ("RB", "Screenshot")]
    window.close()


def test_the_memory_card_shows_its_specs_and_why(qapp, tmp_path):
    window = make(qapp, tmp_path)
    window.cards[1].setFocus()
    qapp.processEvents()
    assert window.pane.title.text() == "SD Card Reader - SE" and window.pane.state.text() == "No SMART on a memory card"
    assert value(window, "Health") == value(window, "Power cycles") == "—" and value(window, "Firmware") == "100"
    assert window.pane.note.text() == drives.NO_SMART_READER
    window.close()


def test_a_problem_a_used_up_drive_and_the_port_that_holds_it_back(qapp, tmp_path):
    window = make(qapp, tmp_path, [nvme(warnings=["spare", "temperature"])])
    assert window.pane.state.text().startswith("The drive reports a problem: little spare space left, too hot")
    assert DOT in window.pane.state.styleSheet() and window.cards[0].text.text() == "The drive reports a problem"
    window.close()
    window = make(qapp, tmp_path, [nvme(health=0, board_link="PCIe 2.0 x2", board_mbps=1000)])
    assert AMBER in window.pane.state.styleSheet() and "endurance is used up" in window.pane.state.text()
    assert value(window, "Board link") == "PCIe 2.0 x2" and AMBER in window.pane.values["Board link"].styleSheet()
    assert "the port holds it back" in window.pane.note.text()
    window.close()


def test_x_measures_the_drive_in_its_folder(qapp, tmp_path):
    asked = []
    here = [nvme(letters=[str(tmp_path)[0]])]                  # the app's folder is on the drive
    window = make(qapp, tmp_path, here, measure=lambda folder: asked.append(folder) or (6123.4, 5012.6))
    window.on_action("x")
    settle(qapp, window)
    assert asked == [tmp_path / "own"]
    assert value(window, "Measured R / W MB/s") == "6,123 / 5,013" and window.pane.status.text() == ""
    window.close()


def test_a_failed_speed_test_says_why(qapp, tmp_path):
    from ssd_check.speedtest import SpeedError

    def fail(folder):
        raise SpeedError("Not enough free space on the drive: the test needs 2.1 GB")
    window = make(qapp, tmp_path, measure=fail)
    window.on_action("x")
    settle(qapp, window)
    assert window.pane.status.text().startswith("Not enough free space")
    assert value(window, "Measured R / W MB/s") == "X to test"
    window.close()


def test_a_drive_without_a_drive_letter_cannot_be_measured(qapp, tmp_path):
    window = make(qapp, tmp_path, [nvme(letters=[])])
    assert value(window, "Measured R / W MB/s") == "No drive letter"
    assert ("X", "Test speed") not in window.legend.items
    window.close()


def test_y_reads_again_and_keeps_the_drive_shown(qapp, tmp_path):
    window = make(qapp, tmp_path)
    window.cards[1].setFocus()
    qapp.processEvents()
    window.on_action("y")
    settle(qapp, window)
    assert len(window.reads) == 2 and window.pane.title.text() == "SD Card Reader - SE" and window.cards[1].hasFocus()
    window.close()


def test_no_drive_and_a_failed_read(qapp, tmp_path):
    window = make(qapp, tmp_path, [])
    assert window.cards == [] and window.pane.title.text() == "No drive found"
    window.close()
    window = make(qapp, tmp_path, drives.DrivesError("PowerShell did not run"))
    assert window.pane.title.text() == "The drives could not be read" and "PowerShell" in window.pane.state.text()
    assert DOT in window.pane.state.styleSheet()
    window.close()


def test_rb_saves_a_screenshot_that_explorer_shows(qapp, tmp_path, shown):
    window = make(qapp, tmp_path)
    window.on_action("next")
    window.on_action("next")                                    # a second in the same second: its own file
    saved = sorted((tmp_path / "Pictures").glob(f"{APP_NAME} *.png"))
    assert len(saved) == 2 and sorted(shown) == saved
    assert window.pane.status.text().startswith("Saved: ")
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, tmp_path, monkeypatch):
    """The suite's buttons: B goes back (with nowhere to go, nothing happens) and View exits the app."""
    window = make(qapp, tmp_path)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")
    assert closed == []
    window.on_action("view")
    assert closed == [True]
    assert window.legend.items[-1] == EXIT


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)
