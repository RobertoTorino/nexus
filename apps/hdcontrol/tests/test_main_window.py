# SPDX-License-Identifier: GPL-3.0-or-later
"""The window against a fake /sys, a fake controller and a fake update: its states, the check for the latest
firmware, the update with its checks and its backup of the profiles, and the profiles' table."""

from __future__ import annotations

import json
import time

import pytest
from conftest import FakeDevice, plug, unplug
from PyQt6.QtWidgets import QMessageBox

from usb_hdcontrol import firmware, main_window, updater
from test_firmware import image

NOW = 1_800_000_000.0
MONOTONIC = [5000.0]                                    # the idle service's clock, as a test moves it


class FakeReader:
    """Input reports for the drawing: a pipe's end as its fd, so the window's notifier has something to watch."""

    def __init__(self, path):
        import os
        self.path = path
        self.fd, self.write_end = os.pipe()
        self.queue: list = []
        self.closed = False
        self.count = 0                                  # reports read, as the real reader counts them

    def read(self):
        if not self.queue:
            return None
        self.count += 1
        return self.queue.pop(0)

    def close(self):
        import os
        self.closed = True
        os.close(self.fd)
        os.close(self.write_end)


class FakeRumble:
    def __init__(self, path):
        self.path = path
        self.played: list[tuple[int, int]] = []
        self.closed = False

    def play(self, strong, weak):
        self.played.append((strong, weak))

    def close(self):
        self.closed = True
LATEST = json.dumps({"FwUpdate000BLatestVersion": "0x0630", "FwUpdate0044LatestVersion": "0x0217"}).encode()


@pytest.fixture
def make(qapp, tmp_path, monkeypatch):
    windows = []
    warnings = []
    questions = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: questions.append(args[2]) or QMessageBox.StandardButton.Yes)

    def build(device=None, get=None, update=None, writable=True, check=True, light_error=None, disconnect=None):
        main_window.ControlSettings(main_window.INFO).set("check_at_start", check)
        device = device or FakeDevice()
        updates = []

        def fake_update(dev, data, progress):
            updates.append(data)
            progress.done = progress.total = len(data)
            if update:
                update(dev, data, progress)
        urls = []

        def fake_get(url):
            urls.append(url)
            return (get or (lambda u: LATEST if u == firmware.INFO_URL else image()))(url)
        readers, rumbles, lights = [], [], []

        def open_reader(path):
            readers.append(FakeReader(path))
            return readers[-1]

        def open_rumble(path):
            rumbles.append(FakeRumble(path))
            return rumbles[-1]

        def set_lightbar(path, bus, rgb, sequence):
            if light_error:
                raise light_error
            lights.append((path.name, bus, rgb))
        window = main_window.MainWindow(sys_root=tmp_path / "sys", dev=tmp_path / "dev", proc=tmp_path / "proc",
                                        open_device=lambda path, sizes: device, firmware_home=tmp_path / "home",
                                        get=fake_get, update=fake_update, clock=lambda: NOW,
                                        writable=lambda path: writable, open_reader=open_reader,
                                        open_rumble=open_rumble, set_lightbar=set_lightbar,
                                        disconnect=disconnect or (lambda address: ""),
                                        monotonic=lambda: MONOTONIC[0], idle_state=tmp_path / "idle.json")
        window.device, window.updates, window.urls = device, updates, urls
        window.readers, window.rumbles, window.lights = readers, rumbles, lights
        window.warnings, window.questions = warnings, questions
        windows.append(window)
        wait(qapp, lambda: window.check_job.running)
        return window

    yield build
    for window in windows:
        window.shut_down()
        window.deleteLater()


def wait(qapp, busy) -> None:
    end = time.monotonic() + 5
    while busy() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not busy()


def test_no_controller(make):
    window = make()
    assert window.badge.text() == "No controller" and not window.latest_pill.isEnabled()
    assert window.controller_box.value.text() == "—" and "No controller found" in window.firmware_text.text()
    assert not window.cards_row.isVisibleTo(window) and window.stack.currentWidget() is window.connect_page


def test_an_edge_with_an_update_waiting(make, tmp_path):
    plug(tmp_path / "sys")
    window = make()
    assert window.urls == [firmware.INFO_URL]                   # asked once at start
    assert window.badge.text() == "Update available" and window.latest_pill.isEnabled()
    assert window.controller_box.value.text() == "Edge" and window.controller_box.toolTip() == "DualSense Edge"
    assert window.connection_box.value.text() == "USB"
    assert window.battery_icon.capacity == 100 and window.battery_icon.lit_modules() == 5
    assert window.installed_box.value.text() == "0x0200" and window.latest_pill.value.text() == "0x0217"
    assert window.installed_box.caption.text() == "Installed firmware"
    assert window.latest_pill.caption.text() == "Latest firmware"
    assert "Click to update to firmware 0x0217" in window.latest_pill.toolTip()
    assert "Jun 21 2024" in window.firmware_text.text() and "downloads it" in window.firmware_text.text()
    first, second = window.cards[0], window.cards[1]
    assert first.slot.text() == "Fn + △  Triangle" and first.name.text() == "Default Profile"
    assert "Each its own" in first.details.text() and "Default" in first.details.text()
    assert second.name.text() == "Empty" and "No profile in this slot" in second.details.text()


def test_no_check_at_start_when_switched_off_or_recent(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    window = make(check=False)
    assert window.urls == [] and window.badge.text() == "Ready" and window.latest_pill.value.text() == "—"
    window.latest_pill.click()                        # nothing to update: a click asks the server
    wait(qapp, lambda: window.check_job.running)
    assert window.urls == [firmware.INFO_URL] and window.badge.text() == "Update available"
    main_window.ControlSettings(main_window.INFO).set_latest({0x44: 0x0217}, time.strftime(
        "%Y-%m-%d %H:%M", time.localtime(NOW - 3600)))
    window = make()
    assert window.urls == [] and window.badge.text() == "Update available"


def test_up_to_date(make, tmp_path):
    plug(tmp_path / "sys")
    window = make(get=lambda url: json.dumps({"FwUpdate0044LatestVersion": "0x0200"}).encode())
    assert window.badge.text() == "Up to date" and window.latest_pill.value.text() == "0x0200"
    assert "runs the latest official firmware" in window.latest_pill.toolTip() and window.updates == []


def test_a_failed_check_is_shown(make, tmp_path):
    plug(tmp_path / "sys")

    def offline(url):
        raise OSError("Name or service not known")
    window = make(get=offline)
    assert window.badge.text() == "Ready" and "could not be read" in window.progress_text.text()


def test_a_dualsense_over_bluetooth(make, tmp_path):
    plug(tmp_path / "sys", product=0x0CE6, bus=0x05, battery=("10", "Discharging"))
    device = FakeDevice({0x20: FakeDevice().reports[0x20][:22] + b"\x0b\x00" + FakeDevice().reports[0x20][24:]})
    window = make(device=device)
    assert window.controller_box.value.text() == "DualSense" and window.connection_box.value.text() == "Bluetooth"
    assert "needs the USB cable" in window.firmware_text.text()
    assert "The update needs the USB cable" in window.latest_pill.toolTip()
    assert "has no profiles" in window.profile_text.text() and not window.cards_row.isVisibleTo(window)
    assert window.battery_icon.capacity == 10
    assert window.battery_icon.status == "Discharging" and window.battery_icon.lit_modules() == 1


def test_on_bluetooth_and_up_to_date_the_cable_is_not_mentioned(make, tmp_path):
    plug(tmp_path / "sys", bus=0x05)
    up_to_date = json.dumps({"FwUpdate0044LatestVersion": "0x0200"}).encode()      # what the fake Edge runs
    window = make(get=lambda url: up_to_date)
    assert "It is the latest official firmware" in window.firmware_text.text()
    assert "USB cable" not in window.firmware_text.text()
    assert window.connection_box.toolTip() == "Bluetooth."


def test_no_access(make, tmp_path):
    plug(tmp_path / "sys")
    window = make(writable=False)
    assert window.badge.text() == "Cannot be read" and "uaccess" in window.badge.toolTip()
    assert not window.latest_pill.isEnabled()


def test_update_downloads_backs_up_and_sends(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    seen = []
    window = make(update=lambda dev, data, progress: seen.append(window.badge.text()))
    window.latest_pill.click()
    assert "0x0217" in window.questions[0] and "downloads it from the official update server" in window.questions[0]
    wait(qapp, lambda: window.updating)
    assert window.updates == [image()] and window.warnings == []
    assert window.urls[-1].endswith("/fwupdate0044/0x0217/FWUPDATE0044.bin")
    assert firmware.read(0x44, 0x0217, tmp_path / "home") == image()
    [backup] = (tmp_path / "home" / "profiles").glob("profiles-*.json")
    assert json.loads(backup.read_text())["profiles"][0]["name"] == "Default Profile"
    assert "restarts" in window.progress_text.text() and not window.progress_bar.isVisible()
    assert "pair it again: the update ends the pairing" in window.progress_text.text()


def test_update_with_the_image_kept_names_its_check(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    firmware.store(image(), tmp_path / "home")
    window = make()
    window.latest_pill.click()
    assert "not a file the app knows" in window.questions[0]
    wait(qapp, lambda: window.updating)
    assert window.urls == [firmware.INFO_URL] and window.updates == [image()]


def test_a_failed_update_is_shown(make, tmp_path, qapp):
    plug(tmp_path / "sys")

    def fail(dev, data, progress):
        raise updater.UpdateError("The controller could not write the image to its flash.")
    window = make(update=fail)
    window.latest_pill.click()
    wait(qapp, lambda: window.updating)
    assert "could not write" in window.warnings[0] and "did not finish" in window.progress_text.text()


def test_update_refused_while_steam_holds_the_controller(make, tmp_path):
    plug(tmp_path / "sys")
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "hidraw2").touch()
    (tmp_path / "proc/4242/fd").mkdir(parents=True)
    (tmp_path / "proc/4242/comm").write_text("steam\n")
    (tmp_path / "proc/4242/fd/9").symlink_to(tmp_path / "dev" / "hidraw2")
    window = make()
    window.latest_pill.click()
    assert "steam has the controller open" in window.warnings[0] and window.questions == []
    assert window.updates == []


def test_use_a_file_refuses_one_for_another_controller(make, tmp_path):
    plug(tmp_path / "sys")
    window = make()
    path = tmp_path / "FWUPDATE000B.bin"
    path.write_bytes(image(product=0x0CE6, target=0x000B, update=0x0630))
    window.use_path(path)
    assert "was not sent" in window.warnings[0] and "target 000B" in window.warnings[0]
    assert window.questions == []


def test_use_a_file(make, tmp_path, qapp):
    plug(tmp_path / "sys")
    window = make()
    path = tmp_path / "FWUPDATE0044.bin"
    path.write_bytes(image(update=0x0216))
    window.use_path(path)
    assert "firmware 0x0216" in window.questions[0]
    wait(qapp, lambda: window.updating)
    assert window.updates == [image(update=0x0216)]


def test_reads_again_when_the_controller_comes_back(make, tmp_path):
    plug(tmp_path / "sys")
    window = make()
    assert window.installed_box.value.text() == "0x0200"
    unplug(tmp_path / "sys")
    window.refresh()
    assert window.badge.text() == "No controller"
    newer = bytearray(window.device.reports[0x20])
    newer[44:46] = (0x0217).to_bytes(2, "little")
    window.device.reports[0x20] = bytes(newer)
    plug(tmp_path / "sys", instance=5)
    window.refresh()
    assert window.installed_box.value.text() == "0x0217" and window.badge.text() == "Up to date"


def test_two_controllers_offer_a_choice(make, tmp_path):
    plug(tmp_path / "sys")
    plug(tmp_path / "sys", "hidraw5", product=0x0CE6, bus=0x05, instance=6, battery=("40", "Discharging"),
         players="01010")
    window = make()
    tabs = window.controller_tabs
    assert tabs.isVisibleTo(window) and tabs.count() == 2
    assert [tabs.tabText(i) for i in range(2)] == ["Player 1 · Edge · USB · 100 %",
                                                   "Player 2 · DualSense · Bluetooth · 40 %"]
    tabs.setCurrentIndex(1)                             # a click on the second tab
    assert window.controller_box.value.text() == "DualSense" and window.chosen == "hidraw5"
    window.refresh()                                    # the next look keeps the choice and the tabs
    assert tabs.currentIndex() == 1 and tabs.count() == 2
    unplug(tmp_path / "sys", "hidraw5")
    window.refresh()
    assert not tabs.isVisibleTo(window) and window.controller_box.value.text() == "Edge"


def test_backup_by_hand(make, tmp_path, monkeypatch):
    plug(tmp_path / "sys")
    window = make()
    target = tmp_path / "mine.json"
    monkeypatch.setattr(main_window.QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    window.backup_button.click()
    assert json.loads(target.read_text())["firmware"] == "0x0200"


def test_the_introduction_once_after_the_first_controller(make, tmp_path, qapp):
    window = make()
    window.show()                                       # the cable moves only while the page is on screen
    qapp.processEvents()
    assert window.stack.currentWidget() is window.connect_page and window.connect_page.view.timer.isActive()
    plug(tmp_path / "sys")
    window.refresh()
    qapp.processEvents()
    intro = window.intro_page
    assert window.stack.currentWidget() is intro and not window.connect_page.view.timer.isActive()
    assert (intro.title.text(), intro.counter.text()) == ("Your controller on the board", "1 of 3")
    assert not intro.back_button.isEnabled()
    intro.next_button.click()
    assert intro.title.text() == "Up-to-date firmware" and intro.view.lit_parts == {"usb"}
    intro.next_button.click()
    assert intro.title.text() == "Four profiles" and intro.next_button.text() == "Start"
    assert {"fn", "back"} <= intro.view.lit_parts and not intro.skip_button.isVisibleTo(intro)
    intro.next_button.click()
    assert window.stack.currentWidget() is window.main_page
    assert main_window.ControlSettings(main_window.INFO).get("intro_seen")
    window = make()                                     # a second start goes straight to the controller
    assert window.stack.currentWidget() is window.main_page
    window.intro_button.click()
    assert window.stack.currentWidget() is window.intro_page
    window.intro_page.skip_button.click()
    assert window.stack.currentWidget() is window.main_page


def test_the_introduction_of_a_dualsense_ends_with_its_battery(make, tmp_path):
    plug(tmp_path / "sys", product=0x0CE6)
    window = make()
    assert window.stack.currentWidget() is window.intro_page
    window.intro_page.go(2)
    assert window.intro_page.title.text() == "The battery" and not window.intro_page.view.edge


def test_a_controller_that_leaves_shows_connect_again(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert window.stack.currentWidget() is window.main_page
    unplug(tmp_path / "sys")
    window.refresh()
    assert window.stack.currentWidget() is window.connect_page


def test_the_main_page_waits_for_the_controller_after_an_update(make, tmp_path, qapp):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    window.latest_pill.click()
    wait(qapp, lambda: window.updating)
    unplug(tmp_path / "sys")                            # the controller restarts with its new firmware
    window.refresh()
    assert window.stack.currentWidget() is window.main_page and window.badge.text() == "No controller"


def test_a_chosen_profile_lights_what_it_sets(make, tmp_path):
    from conftest import DEFAULT_PROFILE, profile_reports
    third = bytearray(DEFAULT_PROFILE[2][2:56])
    third[8 + 14] = 0x10                                # the left back button sends Options
    third[28] = 2                                       # left stick Precise
    square = profile_reports(0x73, "Shooter", bytes(third))
    plug(tmp_path / "sys")
    window = make(device=FakeDevice(dict(zip((0x73, 0x74, 0x75), square))))
    assert window.view.lit_parts == set()
    window.cards[1].clicked.emit(window.cards[1].profile)
    assert window.view.lit_parts == {"fn", "back", "sticks"} and window.cards[1].chosen
    assert "Left back button → Options" in window.cards[1].details.text()
    window.cards[0].clicked.emit(window.cards[0].profile)
    assert window.view.lit_parts == {"fn"} and window.cards[0].chosen and not window.cards[1].chosen
    window.cards[0].clicked.emit(window.cards[0].profile)     # a second click lets go
    assert window.view.lit_parts == set()


def test_the_drawing_follows_the_controller_on_the_main_page(make, tmp_path):
    from usb_hdcontrol.inputs import Reading
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    [reader] = window.readers
    assert reader.path == tmp_path / "dev" / "hidraw2"
    reader.queue.append(Reading(frozenset({"l1", "back_left"}), (0.5, 0.0, 0.0, 0.0), (0.3, 0.0)))
    window._input_ready()
    assert window.view.pressed == {"l1", "back_left"} and window.view.triggers == (0.3, 0.0)
    window.show_intro()                                 # off the main page the drawing rests
    assert reader.closed and window.view.pressed == set()
    window.finish_intro()
    assert len(window.readers) == 2 and not window.readers[1].closed
    unplug(tmp_path / "sys")
    window.refresh()
    assert window.readers[1].closed and window.reader is None


def test_a_controller_that_leaves_while_read_stops_the_reading(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    def gone():
        raise OSError(19, "No such device")
    window.readers[0].read = gone
    window._input_ready()
    assert window.reader is None and window.readers[0].closed


def test_choose_a_light_bar_colour(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert window.lights == [] and window.view.light is None
    window.light_buttons[1].click()                     # red
    assert window.lights == [("hidraw2", "usb", (255, 32, 32))]
    assert main_window.ControlSettings(main_window.INFO).get("lightbar") == "#ff2020"
    assert window.view.light.name() == "#ff2020" and "keeps this color" in window.controller_text.text()
    assert window.light_name.text() == "Red"
    unplug(tmp_path / "sys")
    window.refresh()
    plug(tmp_path / "sys", instance=7)                  # set again when the controller connects
    window.refresh()
    assert window.lights[-1] == ("hidraw2", "usb", (255, 32, 32)) and len(window.lights) == 2


def test_a_light_bar_that_cannot_be_set_says_so(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make(light_error=PermissionError(13, "Permission denied"))
    window.choose_light("#000000")
    assert "could not be set: Permission denied" in window.controller_text.text()


def test_the_vibration_test_runs_each_motor_with_the_drawing_shaking(make, tmp_path, qapp, monkeypatch):
    from usb_hdcontrol import feedback
    monkeypatch.setattr(feedback, "VIBRATION_STEPS", ((0, "left", 100, 0), (30, "", 0, 0), (40, "right", 0, 100),
                                                      (70, "", 0, 0)))
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert window.vibrate_button.isEnabled()
    window.vibrate_button.click()
    [rumble] = window.rumbles
    assert rumble.path == tmp_path / "dev" / "input" / "event22" and not window.vibrate_button.isEnabled()
    sides = []
    end = time.monotonic() + 2
    while not rumble.closed and time.monotonic() < end:
        qapp.processEvents()
        sides.append(window.view.shake_side)
        time.sleep(0.005)
    assert rumble.closed and rumble.played == [(100, 0), (0, 100)]
    assert "left" in sides and "right" in sides and window.view.shake_side == ""
    assert window.vibrate_button.isEnabled()


def test_the_update_shows_data_flowing(make, tmp_path, qapp):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    seen_progress = []

    def slow(dev, data, progress):
        progress.total, progress.done = 100, 40
        time.sleep(0.3)
    window = make(update=slow)
    window.latest_pill.click()
    end = time.monotonic() + 3
    while window.updating and time.monotonic() < end:
        window.show_state()
        seen_progress.append(window.view.data_progress)
        qapp.processEvents()
        time.sleep(0.01)
    assert 0.4 in seen_progress and window.view.data_progress is None


def test_on_bluetooth_with_the_cable_in_offers_the_cable(make, tmp_path, monkeypatch):
    from conftest import plug_held_back
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys", bus=0x05)
    held = plug_held_back(tmp_path / "sys")
    asked = []

    def disconnect(address):
        asked.append(address)
        unplug(tmp_path / "sys")                    # Bluetooth lets go; the cable still has no driver
        return ""
    window = make(disconnect=disconnect)
    assert window.badge.text() == "On Bluetooth, not the cable" and window.cable_button.isVisibleTo(window)
    assert "only charges it" in window.firmware_text.text()
    window.cable_button.click()
    assert asked == ["aa:bb:cc:dd:ee:ff"]
    assert window.badge.text() == "Plug the cable in again"
    assert window.stack.currentWidget() is window.connect_page and "plug it in again" in window.connect_page.text.text()
    import shutil
    shutil.rmtree(held)                             # plugged in again: the kernel takes it
    plug(tmp_path / "sys", instance=9)
    window.refresh()
    assert window.connection_box.value.text() == "USB" and not window.cable_button.isVisibleTo(window)
    assert "Plug your DualSense" in window.connect_page.text.text()


def test_use_the_cable_that_fails_says_what_to_do(make, tmp_path, monkeypatch):
    from conftest import plug_held_back
    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys", bus=0x05)
    plug_held_back(tmp_path / "sys")
    window = make(disconnect=lambda address: "Bluetooth did not let go of the controller.")
    window.cable_button.click()
    assert "hold the PS button for 10 s" in warnings[-1]


def test_the_boxes_keep_their_width_from_usb_to_bluetooth(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    usb = [box.minimumWidth() for box in (window.controller_box, window.connection_box, window.installed_box,
                                          window.latest_pill)]
    unplug(tmp_path / "sys")
    plug(tmp_path / "sys", bus=0x05, instance=6)
    window.refresh()
    assert window.connection_box.value.text() == "Bluetooth"
    assert [box.minimumWidth() for box in (window.controller_box, window.connection_box, window.installed_box,
                                           window.latest_pill)] == usb
    assert len(set(usb)) == 1


def test_every_button_says_what_it_does(make, tmp_path):
    from PyQt6.QtWidgets import QAbstractButton
    plug(tmp_path / "sys")
    window = make()
    missing = [button.text() or button.styleSheet()[:40] for button in window.findChildren(QAbstractButton)
               if not button.toolTip()]
    assert missing == []
    assert all(card.toolTip() for card in window.cards)



def test_the_firmware_box_shows_the_kept_files_sha256_check(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert "SHA-256" not in window.firmware_text.text()          # nothing downloaded yet
    firmware.store(image(), tmp_path / "home")
    window.show_state()
    text = window.firmware_text.text()
    assert "FWUPDATE0044-0217.bin" in text and "not a file the app knows" in text
    assert firmware.sha256(image()) in text


def test_a_known_file_is_named_as_such(make, tmp_path, monkeypatch):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    monkeypatch.setitem(firmware.KNOWN, firmware.sha256(image()), firmware.Known(0x44, 0x0217, len(image())))
    firmware.store(image(), tmp_path / "home")
    window = make()
    assert "SHA-256 checked: it is the known file 0x0217" in window.firmware_text.text()


def test_the_profile_cards_and_colours_say_their_own_thing(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert window.cards[0].toolTip().startswith("Fn + Triangle: Default Profile. Click")
    assert window.cards[1].toolTip().startswith("Fn + Square: no profile yet.")
    tips = [button.toolTip() for button in window.light_buttons]
    assert len(set(tips)) == len(tips) and tips[0] == "Light bar blue." and "saves some battery" in tips[-1]


def test_the_info_sheet_shows_what_the_controller_reports(make, tmp_path, monkeypatch):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    rows = dict(window.info_rows(window.current()))
    assert rows["Model"] == "DualSense Edge" and rows["Installed firmware"].startswith("0x0200, built Jun 21 2024")
    assert rows["Battery"] == "100 %, full"
    assert not any("aa:bb" in value for value in rows.values())       # never the address
    opened = []
    monkeypatch.setattr(main_window.InfoDialog, "exec", lambda self: opened.append(self.text.text()))
    window.info_button.click()
    assert "CFI-ZCP1" in opened[0]


def test_turn_off_only_over_bluetooth(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert not window.off_button.isEnabled()                          # on the cable it stays on
    unplug(tmp_path / "sys")
    plug(tmp_path / "sys", bus=0x05, instance=6)
    asked = []
    window.disconnect = lambda address: asked.append(address) or ""
    window.refresh()
    assert window.off_button.isEnabled()
    window.off_button.click()
    assert asked == ["aa:bb:cc:dd:ee:ff"]


def test_the_top_boxes_share_the_width_and_the_colours_follow_the_drawing(make, tmp_path, qapp):
    from usb_hdcontrol.pages import Section
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    window.resize(1000, 720)
    window.show()
    for size in ((1000, 720), (1300, 800)):
        window.resize(*size)
        for _ in range(3):
            qapp.processEvents()
        boxes = {box.bar.text(): box.width() for box in window.findChildren(Section)}
        assert abs(boxes["Controller"] - boxes["Firmware"]) <= 1
        left, right = window.view.body_span()
        origin = window.view.mapTo(window, window.view.rect().topLeft()).x()
        first = window.light_buttons[0].mapTo(window, window.light_buttons[0].rect().topLeft()).x() - origin
        last = window.other_light.mapTo(window, window.other_light.rect().topRight()).x() - origin
        assert abs(first - left) <= 2 and abs(last - right) <= 2


class FakeEditor:
    """The profile editor, answered: *change* turns the settings it was opened with into those it returns."""
    opened: list = []
    change = staticmethod(lambda settings: settings)
    accept = True

    def __init__(self, slot, settings, creating, parent):
        FakeEditor.opened.append((slot, settings, creating))
        self.given = settings

    def exec(self):
        return main_window.QDialog.DialogCode.Accepted if FakeEditor.accept else main_window.QDialog.DialogCode.Rejected

    def settings(self):
        return FakeEditor.change(self.given)


@pytest.fixture
def editor(monkeypatch):
    FakeEditor.opened, FakeEditor.change, FakeEditor.accept = [], staticmethod(lambda settings: settings), True
    monkeypatch.setattr(main_window, "ProfileEditor", FakeEditor)
    monkeypatch.setattr(main_window.profiles.time, "sleep", lambda seconds: None)
    return FakeEditor


def test_the_cards_offer_create_edit_and_clear_but_not_on_the_default(make, tmp_path):
    from conftest import profile_reports
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    device = FakeDevice(dict(zip((0x76, 0x77, 0x78), profile_reports(0x76, "Racing"))))
    window = make(device=device)
    default, square, cross = window.cards[:3]
    assert not any(b.isVisibleTo(default) for b in (default.create_button, default.edit_button, default.clear_button))
    assert "the app does not change it" in default.toolTip()
    assert square.create_button.isVisibleTo(square) and not square.edit_button.isVisibleTo(square)
    assert cross.edit_button.isVisibleTo(cross) and cross.clear_button.isVisibleTo(cross)
    assert cross.edit_button.isEnabled()


def test_over_bluetooth_the_profiles_cannot_be_changed(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys", bus=0x05)
    window = make()
    square = window.cards[1]
    assert not square.create_button.isEnabled() and "USB cable" in square.create_button.toolTip()


def test_create_starts_from_the_default_backs_up_and_writes(make, tmp_path, editor):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    editor.change = staticmethod(
        lambda s: main_window.dataclasses.replace(s, name="Shooter", triggers=(0, 128, 0, 255)))
    window = make()
    window.cards[1].create_button.click()
    [(slot, given, creating)] = editor.opened
    assert slot == "Square" and creating and given.name == "New profile" and given.buttons == tuple(range(16))
    assert [r[0] for r in window.device.sent] == [0x60] * 3
    assert window.device.sent[1][28:44] != bytes(16)                    # a new profile gets its own ID
    square = window.cards[1]
    assert square.name.text() == "Shooter" and "0 to 50 %" in square.details.text()
    assert window.chosen_slot == "Square" and window.warnings == []
    [backup] = (tmp_path / "home" / "profiles").glob("profiles-*.json")
    assert json.loads(backup.read_text())["profiles"][1]["empty"] is True   # taken before the write


def test_edit_keeps_the_profiles_own_bytes(make, tmp_path, editor):
    from conftest import profile_reports
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    racing = profile_reports(0x76, "Racing")
    racing = (racing[0], racing[1][:28] + bytes(range(1, 17)) + racing[1][44:], racing[2])
    editor.change = staticmethod(lambda s: main_window.dataclasses.replace(s, name="Racing 2"))
    window = make(device=FakeDevice(dict(zip((0x76, 0x77, 0x78), racing))))
    window.cards[2].edit_button.click()
    assert not editor.opened[0][2] and editor.opened[0][1].name == "Racing"
    sent = window.device.sent
    assert [r[0] for r in sent] == [0x61] * 3 and sent[1][28:44] == bytes(range(1, 17))
    assert window.cards[2].name.text() == "Racing 2"


def test_a_cancelled_editor_writes_nothing(make, tmp_path, editor):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    editor.accept = False
    window = make()
    window.cards[3].create_button.click()
    assert window.device.sent == [] and not (tmp_path / "home" / "profiles").exists()


def test_clear_asks_backs_up_and_empties(make, tmp_path, editor):
    from conftest import profile_reports
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make(device=FakeDevice(dict(zip((0x79, 0x7A, 0x7B), profile_reports(0x79, "Old")))))
    window.cards[3].clear_button.click()
    assert "Remove Old from Fn + Circle?" in window.questions[-1]
    assert window.device.sent == [bytes([0x68, 4]) + bytes(62)]
    assert window.cards[3].name.text() == "Empty" and window.warnings == []
    assert list((tmp_path / "home" / "profiles").glob("profiles-*.json"))


def test_a_write_the_controller_refuses_says_so_with_the_backup(make, tmp_path, editor):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")

    class Deaf(FakeDevice):
        def set_feature(self, data):
            self.sent.append(bytes(data))
    window = make(device=Deaf())
    window.cards[1].create_button.click()
    assert "did not keep the profile in Fn + Square" in window.warnings[-1]
    assert "The profiles from before are saved in" in window.warnings[-1]
    assert window.cards[1].name.text() == "Empty"


def test_the_active_profile_is_marked_and_follows_fn(make, tmp_path):
    from usb_hdcontrol.inputs import Reading
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    [reader] = window.readers
    assert not any(card.active.isVisibleTo(card) for card in window.cards)
    reader.queue.append(Reading(profile="Triangle"))
    window._input_ready()
    assert [card.active.isVisibleTo(card) for card in window.cards] == [True, False, False, False]
    reader.queue.append(Reading(profile="Square"))                     # Fn + Square
    window._input_ready()
    assert [card.active.isVisibleTo(card) for card in window.cards] == [False, True, False, False]
    window.show_intro()                                                 # not read: not known
    window.finish_intro()
    assert not any(card.active.isVisibleTo(card) for card in window.cards)


def test_the_drawing_shows_the_player_lights(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys", players="01010")
    window = make()
    assert window.view.players == (False, True, False, True, False)


def test_the_idle_choice_is_saved_for_the_service(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    window = make()
    combo = window.idle_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["Never", "after 10 min", "after 30 min",
                                                                  "after 60 min"]
    assert combo.currentData() == 10                                    # the PS5's shortest, by default
    combo.setCurrentIndex(combo.findData(30))
    assert main_window.ControlSettings(main_window.INFO).get("idle_minutes") == 30
    from usb_hdcontrol import idle
    assert idle.minutes_setting()() == 30                               # what the service reads


def test_the_live_pills_in_the_header(make, tmp_path):
    from usb_hdcontrol.inputs import Reading
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys", bus=0x05)
    MONOTONIC[0] = 5000.0
    window = make()
    assert window.rate_pill.value.text() == "—"
    assert window.off_pill.value.text() == "—" and "not running" in window.off_pill.toolTip()
    [reader] = window.readers
    reader.queue += [Reading(profile="Square")] * 3
    for _ in range(3):
        window._input_ready()
    MONOTONIC[0] += 1.0
    window.show_state()                                 # a second's count starts here
    reader.queue += [Reading(profile="Square")] * 250
    for _ in range(250):
        window._input_ready()
    MONOTONIC[0] += 1.0
    window.show_state()
    assert window.rate_pill.value.text() == "250 Hz"
    (tmp_path / "idle.json").write_text(json.dumps({"last_used": {"hidraw2": MONOTONIC[0] - 180}}))
    window.show_state()
    assert window.off_pill.value.text() == "7 min"                  # 10 minutes, 3 used up
    (tmp_path / "idle.json").write_text(json.dumps({"last_used": {"hidraw2": MONOTONIC[0] - 570}}))
    window.show_state()
    assert window.off_pill.value.text() == "30 s"
    window.idle_combo.setCurrentIndex(window.idle_combo.findData(0))
    window.show_state()
    assert window.off_pill.value.text() == "Never"


def test_on_the_cable_the_off_pill_says_cable(make, tmp_path):
    main_window.ControlSettings(main_window.INFO).set("intro_seen", True)
    plug(tmp_path / "sys")
    window = make()
    assert window.off_pill.value.text() == "Cable"
