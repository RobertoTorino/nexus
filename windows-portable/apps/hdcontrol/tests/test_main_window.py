# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py), against a fake controller, never a real one: it opens on the portable window with the
header's battery, date and time and fits the handheld's screen; every action is a button in the row at the bottom, A
too, and no pill is left (owner, 29-10-2026); B goes back and View exits. Nothing is read from the controller before
A; then its firmware, profiles and battery show, and the introduction once. The firmware update asks for a second
press, refuses while Steam runs or over Bluetooth, runs off the window's thread, backs up the profiles first and keeps
the app open until it is done; a file of your own is picked in core's browser. The test lights the drawing and keeps
the buttons from the app until B is held; the motors and the light bar get their reports. The Edge's profiles are
created, edited and cleared (a second press), the default one never; the settings change with A."""

from __future__ import annotations

import json
import re
import time

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from bc250_core.portable import BACK, EXIT, KEYBOARD
from bc250_core.portable import INFO as MENU_INFO
from conftest import BT_PATH, USB_PATH, FakeDevice, input_report, profile_reports
from hd_controller import (APP_ID, APP_NAME, EXE_NAME, INFO, LOGO_PATH, ROOT, __version__, controller, feedback,
                           firmware)
from hd_controller.main_window import ENDED, NOT_READ, TESTING, MainWindow
from test_firmware import image

EDGE = controller.Controller(USB_PATH, 0x0DF2, "usb")
ON_BLUETOOTH = controller.Controller(BT_PATH, 0x0CE6, "bluetooth")
LATEST = json.dumps({"FwUpdate0044LatestVersion": "0x0217", "FwUpdate000ELatestVersion": "0x0641"}).encode()


class FakePad:
    def events(self):
        return []

    def close(self):
        pass

    def names(self):
        return []


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


class Server:
    """Sony's update server: the list of versions, and the image of the Edge's latest."""

    def __init__(self, data: bytes | None = None):
        self.urls: list[str] = []
        self.data = data if data is not None else image()

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        return LATEST if url == firmware.INFO_URL else self.data


def make(qapp, tmp_path, found=(EDGE,), device=None, **more):
    controllers = list(found)
    device = device if device is not None else FakeDevice()
    more.setdefault("get", Server())
    more.setdefault("holders", lambda: [])
    more.setdefault("roots", lambda: [])
    window = MainWindow(gamepad=Gamepad(source_factory=FakePad), battery=lambda: (82, False),
                        find=lambda: controllers, open_device=device, firmware_home=tmp_path / "home",
                        user_home=tmp_path / "me", **more)
    window.found, window.device = controllers, device   # the tests change them
    portable.scale((1280, 720))
    window.resize(1280, 720)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    window.start()
    qapp.processEvents()
    return window


def settle(qapp, window) -> bool:
    """The check for the latest firmware done, and its answer shown."""
    done = wait_for(qapp, lambda: not window.check_worker.busy)
    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.01)
    return done


def read(window):
    """A on the Controller card, and the introduction skipped."""
    window.controller_card.setFocus()
    window.act("accept")
    if window.intro_open:
        window.act("back")


def no_pills(window) -> bool:
    """Every action is in the row at the bottom (owner, 29-10-2026): the panes hold rows and icons, no pill."""
    return [p for p in window.panes.findChildren(portable.Pill)
            if type(p) is portable.Pill and p.isVisibleTo(window)] == []


def test_the_window_opens_with_the_suites_header(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.header.title.text() == APP_NAME and window.header.version.text() == __version__
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d  \|  82%", window.header.status.text())
    assert window.legend.items == [("A", "Read"), MENU_INFO, EXIT]
    assert no_pills(window)
    window.close()


def test_the_window_fits_the_handhelds_screen(qapp, tmp_path):
    window = make(qapp, tmp_path)
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720
    window.close()


def test_b_goes_back_and_view_exits(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("back")                                    # on the Controller card: nothing
    assert closed == [] and window.controller_card.hasFocus()
    window.settings_card.setFocus()
    window.on_action("accept")                                  # into the settings' rows: B Back shows
    qapp.processEvents()
    assert BACK in window.legend.items
    window.on_action("back")
    qapp.processEvents()
    assert window.settings_card.hasFocus() and BACK not in window.legend.items and closed == []
    window.on_action("view")
    assert closed == [True]


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()
    assert re.fullmatch(r"[A-Za-z0-9-]+", EXE_NAME)


def test_without_a_controller_it_asks_to_connect_one(qapp, tmp_path):
    window = make(qapp, tmp_path, found=())
    assert window.controller_card.text.text() == "No controller"
    assert window.controller_pane.heading.text() == "Connect your controller"
    assert window.controller_pane.connect_view.isVisible() and window.controller_pane.connect_view.timer.isActive()
    window.act("accept")
    assert window.controller_pane.status.text().startswith("No controller found. Plug the controller in")
    window.close()


def test_nothing_is_read_before_a_then_the_controller_shows(qapp, tmp_path):
    window = make(qapp, tmp_path)
    device = window.device
    assert device.opened == 0 and device.asked == []
    assert window.controller_card.text.text() == "DualSense Edge on USB: the A button reads it"
    assert window.firmware_card.text.text() == "Not read yet"
    window.act("accept")                                        # A Read
    assert device.asked[:4] == [0x20, 0x70, 0x71, 0x72] and window.info.update == 0x0200
    assert window.intro_open and window.panes.currentWidget() is window.intro_pane      # the first time
    assert window.legend.items == [("A", "Next"), ("B", "Skip"), EXIT]
    window.act("accept")
    window.act("accept")
    assert window.intro_pane.last and window.legend.items[0] == ("A", "Start")
    window.act("x")                                             # the page before
    assert window.intro_pane.index == 1
    window.act("accept")
    window.act("accept")                                        # Start
    assert not window.intro_open and window.settings.get("intro_seen")
    assert window.panes.currentWidget() is window.controller_pane
    device.inputs.append(input_report(status=0x08))
    window._input_ready()
    window.refresh()
    assert window.controller_card.text.text() == "Edge · USB · 85 %"
    rows = {window.controller_pane.grid.itemAt(i).widget().text(): window.controller_pane.grid.itemAt(i + 1).widget()
            .text() for i in range(0, window.controller_pane.grid.count(), 2)}
    assert rows["Installed firmware"] == "0x0200, built Jun 21 2024 19:09:17" and rows["Battery"] == "85 %, discharging"
    assert "Model number: CFI-ZCP1" in window.controller_pane.info.info          # the spec sheet in the information
    assert "aa:bb" not in window.controller_pane.info.info and USB_PATH.decode() not in window.controller_pane.info.info
    assert window.legend.items[0] == ("A", "Read again")
    window.act("accept")                                        # read again: the introduction does not come back
    assert not window.intro_open
    window.close()


def test_lb_and_rb_choose_between_controllers(qapp, tmp_path):
    window = make(qapp, tmp_path, found=(EDGE, ON_BLUETOOTH))
    read(window)
    assert window.legend.items[:3] == [("A", "Read again"), ("LB", "Controller before"), ("RB", "Next controller")]
    assert window.controller_card.text.text().endswith("1 of 2")
    window.act("next")
    assert window.current() == ON_BLUETOOTH and window.controller_card.text.text().endswith("2 of 2")
    assert window.controller_pane.heading.text() == "DualSense"
    window.act("previous")
    assert window.current() == EDGE
    window.close()


def test_the_update_asks_first_runs_off_the_windows_thread_and_backs_up_the_profiles(qapp, tmp_path):
    sent = []

    def update(device, data, progress):
        progress.total = len(data)
        progress.done = len(data)
        sent.append(data)
    server = Server()
    window = make(qapp, tmp_path, get=server, update=update)
    read(window)
    window.firmware_card.setFocus()
    settle(qapp, window)                                        # the check when the app opened
    window.act("y")                                             # Check for an update
    assert settle(qapp, window) and window.settings.latest()
    assert window.firmware_card.text.text() == "0x0200: 0x0217 is out"
    assert "The A button downloads it" in window.firmware_pane.status.text()
    window.act("accept")                                        # A Update: the question
    status = window.firmware_pane.status.text()
    assert status.startswith("This sends firmware 0x0217 to the DualSense Edge, which runs 0x0200.")
    assert status.endswith("Press the A button again to update the controller now.")
    assert window.legend.items[0] == ("A", "Press again") and sent == []
    window.act("accept")                                        # the second press
    assert window.updating and window.legend.items == [MENU_INFO, EXIT]
    window.act("view")                                          # the update is not cut off
    assert window.isVisible() and "still running" in window.firmware_pane.status.text()
    assert wait_for(qapp, lambda: not window.updating)
    assert sent == [image()] and server.urls[-1].endswith("/0x0217/FWUPDATE0044.bin")
    assert window.firmware_pane.status.text().startswith("Firmware 0x0217 is sent")
    backups = list((tmp_path / "home" / "profiles").glob("profiles-*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["app"] == APP_ID
    assert firmware.read(0x0044, 0x0217, tmp_path / "home") == image()           # kept for a second try
    window.close()


def test_the_question_runs_out_after_five_seconds(qapp, tmp_path):
    window = make(qapp, tmp_path)
    read(window)
    window.settings.set_latest({0x0044: 0x0217}, "2026-11-05 12:00")
    window.firmware_card.setFocus()
    window.act("accept")
    assert window.confirm == "update"
    window._confirm_over()                                      # the five seconds are over
    assert window.confirm == "" and window.legend.items[0] == ("A", "Update")
    assert "Press the A button again" not in window.firmware_pane.status.text()
    window.close()


def test_no_update_while_steam_runs_or_over_bluetooth_or_when_up_to_date(qapp, tmp_path):
    window = make(qapp, tmp_path, holders=lambda: ["Steam"])
    read(window)
    window.settings.set_latest({0x0044: 0x0217}, "2026-11-05 12:00")
    window.firmware_card.setFocus()
    window.act("accept")
    assert window.firmware_pane.status.text().startswith("Steam is running. Quit it first") and not window.confirm
    window.settings.set_latest({0x0044: 0x0200}, "2026-11-05 12:00")
    window.act("accept")
    assert "nothing to update" in window.firmware_pane.status.text()
    window.close()
    window = make(qapp, tmp_path, found=(controller.Controller(BT_PATH, 0x0DF2, "bluetooth"),))
    read(window)
    window.settings.set_latest({0x0044: 0x0217}, "2026-11-05 12:00")
    window.firmware_card.setFocus()
    window.act("accept")
    assert window.firmware_pane.status.text() == "The update needs the USB cable: connect the controller with it."
    window.close()


def test_a_file_of_your_own_is_picked_in_the_browser_and_checked(qapp, tmp_path):
    folder = tmp_path / "files"
    folder.mkdir()
    (folder / "old.bin").write_bytes(image(update=0x0100))
    (folder / "FWUPDATE0044.bin").write_bytes(image(update=0x0230))
    window = make(qapp, tmp_path, roots=lambda: [folder])
    read(window)
    window.firmware_card.setFocus()
    window.act("x")                                             # Use a file
    assert window.panes.currentWidget() is window.browse_pane
    window.browse_picked(f"dir:{folder}")
    window.browse_picked(f"file:{folder / 'old.bin'}")
    assert "no older or equal" in window.browse_pane.status.text()
    window.browse_picked(f"file:{folder / 'FWUPDATE0044.bin'}")
    assert window.panes.currentWidget() is window.firmware_pane and window.confirm == "update"
    assert window.firmware_pane.status.text().startswith("This sends firmware 0x0230")
    assert "not a file the app knows" in window.firmware_pane.status.text()
    window._confirm_over()
    window.close()


def test_the_test_lights_the_drawing_and_keeps_the_buttons_until_b_is_held(qapp, tmp_path, monkeypatch):
    window = make(qapp, tmp_path)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.test_card.setFocus()
    window.act("accept")
    assert window.test_pane.status.text() == NOT_READ and not window.testing     # not read yet: says so
    read(window)
    window.test_card.setFocus()
    window.on_action("accept")                                  # A Start the test
    assert window.testing and window.test_pane.status.text() == TESTING
    window.device.inputs.append(input_report((0x28, 0, 0)))    # Cross pressed on the controller tested
    window._input_ready()
    assert window.test_pane.view.pressed == {"cross"}
    window.on_action("down")                                    # ... which the app does not answer to
    window.on_action("back")
    assert window.testing and window.test_card.hasFocus()
    window.gamepad.raw.emit("button", "b", True)               # B held
    assert window.hold_timer.isActive()
    window.gamepad.raw.emit("button", "b", False)              # let go too soon
    assert not window.hold_timer.isActive() and window.testing
    window.gamepad.raw.emit("button", "b", True)
    window.hold_timer.timeout.emit()                            # two seconds later
    assert not window.testing and window.test_pane.status.text() == ENDED
    window.start_test()
    window.act("back")                                          # a tap on B in the legend ends it too
    assert not window.testing
    window.close()


def test_vibration_and_light_bar_get_their_reports(qapp, tmp_path):
    window = make(qapp, tmp_path)
    read(window)
    device = window.device
    window.test_card.setFocus()
    window.act("y")                                             # Light bar: Blue first
    assert window.settings.get("lightbar") == "#0050ff"
    assert device.written[-1] == feedback.lightbar_report("usb", (0x00, 0x50, 0xFF), window.light_sequence)
    window.act("x")                                             # Test vibration
    assert wait_for(qapp, lambda: window.rumble is None, 4.0)
    motors = [report for report in device.written if report[1] & feedback.HAPTICS_SELECT]
    assert [(r[1 + 3], r[1 + 2]) for r in motors] == [(0xC0, 0), (0, 0), (0, 0xC0), (0, 0)]
    assert all(r[1 + 38] == feedback.COMPATIBLE_VIBRATION2 for r in motors)            # the Edge: the second flag
    for _ in range(6):
        window.act("y")                                         # round to "as the system sets it"
    assert window.settings.get("lightbar") == ""
    window.close()


def test_the_edges_profiles_created_edited_and_cleared(qapp, tmp_path):
    window = make(qapp, tmp_path)
    read(window)
    assert window.profiles_card.text.text() == "1 of 4: Default Profile"
    window.profiles_card.setFocus()
    window.act("accept")                                        # into the rows
    assert window.profiles_pane.list.focused() == "Triangle"
    assert window.legend.items[:4] == [("A", "Edit"), ("X", "Clear"), ("Y", "Back up"), ("LT", "Read again")]
    window.act("accept")                                        # the default profile: never changed
    assert window.profiles_pane.status.text() == "Fn + Triangle is the default profile: the app does not change it."
    window.act("down")                                          # Square, empty
    assert window.legend.items[0] == ("A", "Create")
    window.act("accept")
    assert window.panes.currentWidget() is window.editor_pane and window.editor_pane.list.focused() == "name"
    window.act("accept")                                        # the name's page
    assert window.panes.currentWidget() is window.name_pane and window.legend.items[:2] == [("A", "Take the name"),
                                                                                            KEYBOARD]
    window.name_pane.field.setText("Racing")
    window.act("accept")
    assert window.panes.currentWidget() is window.editor_pane and dict(window.editor.rows())["name"] == "Name: Racing"
    window.act("down")                                          # Left stick: Default -> Quick
    window.act("accept")
    window.act("y")                                             # Save to the controller
    assert window.panes.currentWidget() is window.profiles_pane
    assert window.profiles_pane.status.text() == "Racing is saved in Fn + Square."
    assert [report[0] for report in window.device.sent] == [0x60, 0x60, 0x60]
    assert window.profiles[1].name == "Racing" and window.profiles[1].left_curve == "Quick"
    window.profiles_pane.list.pills["Square"].setFocus()
    window.act("x")                                             # Clear: asks first
    assert window.profiles_pane.status.text().startswith("Press the X button again to remove Racing")
    assert window.legend.items[1] == ("X", "Press again")
    window.act("x")
    assert window.profiles[1].empty and window.device.sent[-1][:2] == bytes([0x68, 2])
    assert len(list((tmp_path / "home" / "profiles").glob("*.json"))) >= 1           # a backup before each change
    window.close()


def test_the_editor_and_the_name_go_back_without_saving(qapp, tmp_path):
    reports = dict(zip((0x76, 0x77, 0x78), profile_reports(0x76, "Mine")))
    window = make(qapp, tmp_path, device=FakeDevice(reports))
    read(window)
    window.profiles_card.setFocus()
    window.act("accept")
    window.profiles_pane.list.pills["Cross"].setFocus()
    window.act("accept")                                        # Edit Mine
    assert window.editor_pane.heading.text() == "Edit the profile Fn + Cross"
    window.act("accept")
    window.name_pane.field.setText("Other")
    window.act("back")                                          # the name not taken
    assert dict(window.editor.rows())["name"] == "Name: Mine"
    window.act("back")                                          # nothing saved
    assert window.panes.currentWidget() is window.profiles_pane and window.device.sent == []
    assert window.profiles_pane.status.text() == "Nothing was saved."
    window.close()


def test_profiles_over_bluetooth_are_read_but_not_changed(qapp, tmp_path):
    window = make(qapp, tmp_path, found=(controller.Controller(BT_PATH, 0x0DF2, "bluetooth"),))
    read(window)
    window.profiles_card.setFocus()
    window.act("accept")
    window.act("down")
    window.act("accept")
    assert window.profiles_pane.status.text() == "Plug in the USB cable to change the profiles."
    window.act("y")                                             # Back up works over Bluetooth too
    assert window.profiles_pane.status.text().startswith("The profiles are saved in ")
    window.close()


def test_the_settings_change_with_a(qapp, tmp_path):
    window = make(qapp, tmp_path, found=())
    window.settings_card.setFocus()
    window.act("accept")
    assert window.settings_pane.list.focused() == "check"
    window.act("accept")
    assert not window.settings.get("check_at_start")
    assert window.settings_card.text.text() == "Check at start: Off"
    window.act("down")
    window.act("accept")                                        # Show the introduction
    assert window.intro_open and window.panes.currentWidget() is window.intro_pane
    window.close()


def test_the_check_at_start_asks_once_a_day(qapp, tmp_path):
    server = Server()
    window = make(qapp, tmp_path, get=server)
    assert settle(qapp, window) and window.settings.latest() and server.urls == [firmware.INFO_URL]
    window.close()
    window = make(qapp, tmp_path, get=server)                  # within the day: not again
    qapp.processEvents()
    assert server.urls == [firmware.INFO_URL]
    window.close()


def test_a_controller_that_cannot_be_read_says_why(qapp, tmp_path):
    class Exclusive(FakeDevice):
        def __call__(self, path, sizes=None, blocking=True):
            raise OSError("it could not be opened: another program may have it to itself")
    window = make(qapp, tmp_path, device=Exclusive())
    read(window)
    assert window.controller_pane.status.text().startswith("The controller could not be read: it could not be opened")
    window.close()
