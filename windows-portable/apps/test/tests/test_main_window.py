# SPDX-License-Identifier: GPL-3.0-or-later
"""The window (main_window.py): the device read on A in the background and shown, read again, the report saved, a failed
read, the network measured, the controller test that has every button until B is held, and B closing the app."""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

from bc250_core import portable
from bc250_core.gamepad import Gamepad
from portable_test import device, lights, network
from portable_test.main_window import MainWindow


class FakePad:
    def __init__(self):
        self.queue = []

    def events(self):
        found, self.queue = self.queue, []
        return found

    def close(self):
        pass

    def names(self):
        return ["ASUSTeK Computer Inc."]


class FakeBack(QObject):
    """Stands in for the ASUS channel of the back buttons (back_buttons.Reader)."""

    changed = pyqtSignal(bool)

    def __init__(self, available: bool):
        super().__init__()
        self.available = available

    def start(self) -> bool:
        return self.available

    def stop(self) -> None:
        pass


def wait_for(qapp, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def make(qapp, tmp_path, ally_json):
    windows = []

    def make(read=None, pad=None, measure=None, back=None, lamps=None):
        pad = pad or FakePad()
        window = MainWindow(gamepad=Gamepad(source_factory=lambda: pad), read=read or (lambda: device.parse(ally_json)),
                            measure=measure or measured, battery=lambda: (82, False), reports=tmp_path / "reports",
                            temperatures=lambda: (47, 45), watts=lambda: 18, hertz=lambda: 120,
                            back_reader=back or FakeBack(True),
                            lamps=lamps or lights.Lights(find=lambda: []))     # never the real lights
        portable.scale((1280, 720))
        window.resize(1280, 720)
        window.show()
        window.activateWindow()                     # a card gets its focus events in the active window only
        qapp.processEvents()
        window.start()
        windows.append(window)
        return window, pad
    yield make
    for window in windows:
        window.close()


def measured(power, say):
    say("Downloading for up to 10 seconds ...")
    return network.Network(power=power, adapter="MediaTek", link=network.Link(5280, 56, 10, 85, -54, 2402, 2402),
                           downloaded=4_521_984, seconds=10.05)


def values(window, pane=None) -> dict[str, str]:
    grid = (pane or window.device_pane).grid
    cells = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    return dict(zip(cells[0::2], cells[1::2]))


def read(window, qapp) -> bool:
    window.device_pane.read_pill.click()
    return wait_for(qapp, lambda: window.device is not None)


def test_nothing_is_read_before_a(make, qapp, ally_json, monkeypatch):
    calls = []
    window, _ = make(read=lambda: calls.append(True) or device.parse(ally_json))
    qapp.processEvents()
    assert calls == [] and window.device is None and window.device_pane.read_pill.label.text() == "Read"
    assert window.device_pane.status.text() == ""              # the pill says it (owner, 29-10-2026: not twice)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")                                  # A on the Device card
    assert wait_for(qapp, lambda: calls == [True])


def test_the_device_is_read_and_shown(make, qapp):
    window, _ = make()
    assert read(window, qapp)
    assert window.device_pane.read_pill.label.text() == "Read again"
    shown = values(window)
    assert shown["Device"] == "ROG Xbox Ally X" and shown["Memory"] == "24 GB, 15.6 GB usable"
    assert "Screen" in shown and "% scaling, " in shown["Screen"]
    assert list(shown).index("Screen") == list(shown).index("Memory") - 1
    assert re.fullmatch(r"\w+day \d\d/\d\d/\d{4}  \|  \d\d:\d\d", window.header.status.text())
    assert window.header.second.text() == "CPU 47° GPU 45°  |  18 W  |  120 Hz  |  82%"   # under it (owner, 29-10-2026)
    assert window.header.icon is None                       # the screen is too small for it (owner, 27-10-2026)
    assert [text for _, text in window.legend.items] == ["Save report", "Close"]


def test_read_again_and_a_failed_read(make, qapp, ally_json):
    answers = [lambda: device.parse(ally_json), lambda: (_ for _ in ()).throw(RuntimeError("CIM is not running"))]
    window, _ = make(read=lambda: answers.pop(0)())
    assert read(window, qapp) and wait_for(qapp, lambda: window.device_pane.read_pill.label.text() == "Read again")
    window.device_pane.read_pill.click()
    assert wait_for(qapp, lambda: "did not answer" in window.device_pane.status.text())
    assert "CIM is not running" in window.device_pane.status.text() and window.device is not None


def test_x_saves_the_report(make, qapp, tmp_path, monkeypatch):
    window, _ = make()
    assert read(window, qapp)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("x")
    saved = list((tmp_path / "reports").glob("device-*.txt"))
    assert len(saved) == 1 and "Device: ROG Xbox Ally X" in saved[0].read_text(encoding="utf-8")
    assert str(saved[0]) in window.device_pane.status.text()


def test_the_controller_test_has_every_button_until_b_is_held(make, qapp, monkeypatch):
    window, pad = make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.controller_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.controller_pane
    window.on_action("accept")
    assert window.testing and window.legend.items == [("B", "Hold to finish")]
    pad.queue += [("button", "b", True), ("button", "b", False), ("button", "dpad_down", True),
                  ("button", "dpad_down", False), ("button", "x", True)]
    window.gamepad.poll()
    assert closed == [] and window.controller_card.hasFocus()                # B and the d-pad were the test's
    assert set(window.controller_pane.seen()) == {"b", "dpad_down", "x"}
    window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not window.testing and closed == []                                # Escape ended the test only
    window.on_action("back")
    assert closed == [True]                                                   # now B closes the app


def test_the_cards_show_their_panes(make, qapp):
    window, _ = make()
    window.controller_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.controller_pane
    assert window.legend.items == [("A", "Start the test"), ("Y", "Stick lights"), ("B", "Close")]
    window.device_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.device_pane


def test_a_long_value_wraps_and_leaves_the_cards_their_width(make, qapp):
    window, _ = make()
    assert read(window, qapp)
    width = window.device_card.width()
    window.device_pane.show_rows([("Graphics", "AMD Radeon 890M Graphics " * 12)])
    qapp.processEvents()
    assert window.device_card.width() == width
    assert window.device_pane.geometry().right() < window.width()


def test_the_version_is_the_apps():
    from portable_test import __version__
    assert __version__ == (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()


def test_one_read_fills_the_device_hardware_and_connected_cards(make, qapp, monkeypatch):
    import json

    from conftest import DOCKED
    window, _ = make(read=lambda: device.parse(json.dumps(DOCKED)))
    assert read(window, qapp)
    window.hardware_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.hardware_pane
    assert window.legend.items == [("X", "Save report"), ("B", "Close")]
    hardware = window.hardware_pane.grid
    assert [hardware.itemAt(i).widget().text() for i in range(0, hardware.count(), 2)][:2] == ["Panel", "Touch"]
    window.connected_card.setFocus()
    qapp.processEvents()
    connected = window.connected_pane.grid
    assert connected.itemAt(1).widget().text() == "Realtek USB hub (USB 3, USB 2)"
    assert all(p.read_pill.label.text() == "Read again" for p in window.info_panes)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    saved = window.save_report().read_text(encoding="utf-8")
    assert "\nDevice\nDevice: ROG Xbox Ally X\n" in saved and "\nHardware\nPanel: about 7 inches" in saved
    assert "\nConnected\nDock or hub: Realtek USB hub (USB 3, USB 2)\n" in saved
    assert str(window.reports) in window.connected_pane.status.text()      # every card says where it went


def test_nothing_plugged_in_says_so(make, qapp):
    window, _ = make()
    assert read(window, qapp)
    assert window.connected_pane.grid.count() == 0 and window.connected_pane.status.text() == "Nothing is plugged in."


def test_the_header_has_the_date():
    import datetime

    from bc250_core.portable import status_clock
    assert status_clock(datetime.datetime(2026, 10, 28, 17, 4)) == ["Wednesday 28/10/2026", "17:04"]


def test_the_network_is_measured_on_a_and_saved_with_x(make, qapp, monkeypatch):
    said = []
    window, _ = make(measure=lambda power, say: said.append(power) or measured(power, say))
    window.network_card.setFocus()
    qapp.processEvents()
    assert window.panes.currentWidget() is window.network_pane
    assert window.legend.items == [("X", "Save report"), ("B", "Close")]
    assert said == [] and window.network_pane.status.text() == ""
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.on_action("accept")
    assert wait_for(qapp, lambda: window.network is not None)
    qapp.processEvents()
    assert said == ["battery, 82%"] and window.network_pane.read_pill.label.text() == "Test again"
    shown = values(window, window.network_pane)
    assert shown["Wi-Fi"] == "5 GHz, channel 56" and shown["Download"] == "0.4 MB/s (4.5 MB in 10.1 s)"
    assert window.device is None and window.device_pane.grid.count() == 0       # the device was not read
    saved = window.save_report().read_text(encoding="utf-8")
    assert "\nNetwork\nWi-Fi: 5 GHz, channel 56\n" in saved and "\nDevice\n" not in saved
    assert str(window.reports) in window.network_pane.status.text()
    assert read(window, qapp)
    saved = window.save_report().read_text(encoding="utf-8")
    assert saved.index("\nDevice\n") < saved.index("\nNetwork\n")                  # the network's section last


def test_a_failed_download_and_a_failed_measurement(make, qapp):
    def failed(power, say):
        return network.Network(power=power, error="timed out")
    window, _ = make(measure=failed)
    window.network_pane.read_pill.click()
    assert wait_for(qapp, lambda: window.network is not None)
    assert window.network_pane.status.text() == "The download failed: timed out"
    window, _ = make(measure=lambda power, say: (_ for _ in ()).throw(OSError("wlanapi is missing")))
    window.network_pane.read_pill.click()
    assert wait_for(qapp, lambda: "not measured" in window.network_pane.status.text())
    assert window.network_pane.read_pill.isEnabled() and window.device_pane.status.text() == ""


def test_the_window_fits_the_allys_screen(make, qapp):
    # The legend was cut off at the bottom on the Ally (owner, 28-10-2026): the window asked for 740 of 720 px.
    window, _ = make()
    assert window.minimumSizeHint().height() <= 720 and window.height() == 720


def test_the_back_buttons_light_one_chip(make, qapp):
    # M1 and M2 come through the ASUS channel as one code (owner's Ally X, 28-10-2026): one M1/M2 chip.
    back = FakeBack(True)
    window, _ = make(back=back)
    pane = window.controller_pane
    assert pane.chips["m1m2"].isVisibleTo(pane) and pane.count.text() == "0 of 16 buttons answered"
    window.start_test()
    back.changed.emit(True)
    assert pane.chips["m1m2"].held
    back.changed.emit(False)
    assert pane.seen() == ["m1m2"] and pane.count.text() == "1 of 16 buttons answered"
    assert "cannot tell them apart" in pane.back_buttons.info


def test_without_the_asus_channel_there_is_no_back_buttons_chip(make, qapp):
    window, _ = make(back=FakeBack(False))
    pane = window.controller_pane
    assert not pane.chips["m1m2"].isVisibleTo(pane) and pane.count.text() == "0 of 15 buttons answered"
    assert "reports none" in pane.back_buttons.info


def test_the_window_fits_a_smaller_screen(qapp, ally_json):
    # It adapts to the screen it is on (owner, 28-10-2026): a 1080p screen at 175 % is 1097 x 617.
    portable.pin_scale((1097, 617))
    try:
        window = MainWindow(gamepad=Gamepad(source_factory=FakePad), read=lambda: device.parse(ally_json),
                            measure=measured, battery=lambda: (82, False), temperatures=lambda: (47, 45),
                            back_reader=FakeBack(True))
        window.resize(1097, 617)
        window.show()
        qapp.processEvents()
        assert window.minimumSizeHint().height() <= 617 and window.height() == 617
        window.close()
    finally:
        portable.pin_scale((1280, 720))


def test_read_while_a_read_runs_says_so(make, qapp, ally_json):
    """Read and Test are never grayed out (owner, 29-10-2026): pressed again while they run, the pane says so."""
    gate = threading.Event()
    window, _ = make(read=lambda: gate.wait(10) and device.parse(ally_json),
                     measure=lambda power, say: gate.wait(10) and network.Network(power=power, error="timed out"))
    window.device_pane.read_pill.click()
    window.device_pane.read_pill.click()
    assert window.device_pane.read_pill.isEnabled()
    assert window.device_pane.status.text() == "Reading ... Windows is still answering the read before."
    window.network_pane.read_pill.click()
    window.network_pane.read_pill.click()
    assert window.network_pane.read_pill.isEnabled()
    assert window.network_pane.status.text() == "Measuring ... the test before is still running."
    gate.set()
    assert wait_for(qapp, lambda: window.device is not None and window.network is not None)


def test_the_stick_lights_test_is_a_popup(make, qapp, monkeypatch):
    """Short of space on the Controller pane, Y in its legend opens the LED test over the window (owner, 29-10-2026:
    the icon for it was hard to reach): the colors as pills, the d-pad between them, A presses, B closes and gives
    the lights back."""
    from test_lights import FakeArray
    array = FakeArray()
    lamps = lights.Lights(find=lambda: [("RTG789", array)], color=lambda rgb: rgb)
    window, _ = make(lamps=lamps)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.controller_card.setFocus()
    qapp.processEvents()
    assert ("Y", "Stick lights") in window.legend.items
    window.on_action("y")
    popup = window.popup
    panel = popup.content
    assert popup is not None and list(panel.pills) == ["Red", "Green", "Blue", "White", "Left only", "Right only", "Off"]
    assert panel.pills["Red"].hasFocus() and "4 lamps" in panel.report.text()
    window.on_action("accept")                                      # A on Red
    assert array.colors == [(255, 0, 0)] * 4 and panel.status.text() == "Red on both sticks."
    window.on_action("right")
    assert panel.pills["Green"].hasFocus()
    for _ in range(6):                                              # the focus stays inside the popup
        window.on_action("down")
    assert window.focusWidget() in popup.pills()
    panel.pills["Left only"].setFocus()
    window.on_action("accept")
    assert array.colors[:2] == [(255, 255, 255)] * 2 and array.colors[2:] == [(0, 0, 0)] * 2
    assert panel.status.text() == "White on the left stick."
    window.on_action("back")                                        # B: closed, the lights given back
    assert window.popup is None and lamps.array is None and window.controller_card.hasFocus()
    window.device_card.setFocus()
    qapp.processEvents()
    window.on_action("y")                                           # Y is the Controller card's alone
    assert window.popup is None


def test_no_lights_says_how_to_switch_them_on(make, qapp, monkeypatch):
    window, _ = make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.controller_card.setFocus()
    qapp.processEvents()
    window.legend.entries["Y"].pressed.emit()                       # a tap on Y Stick lights
    panel = window.popup.content
    assert panel.pills == {} and "Settings > Personalization > Dynamic Lighting" in panel.report.text()
    assert window.popup.close_pill.hasFocus()
    window.on_action("accept")                                      # A on Close
    assert window.popup is None


def test_the_lights_are_off_limits_during_the_button_test(make, qapp, monkeypatch):
    window, _ = make()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.start_test()
    assert window.legend.items == [("B", "Hold to finish")] and window.controller_pane.back_buttons.isHidden()
    window.on_action("y")
    window.show_lights()
    assert window.popup is None
    window.controller_pane.finish()
    assert not window.controller_pane.back_buttons.isHidden() and ("Y", "Stick lights") in window.legend.items
