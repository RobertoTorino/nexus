# SPDX-License-Identifier: AGPL-3.0-or-later
"""The controller test window against a stand-in for SDL (fake_gamepad.py) and for the genuine check."""

from __future__ import annotations

import time

from consoles_link import gamepad, genuine
from consoles_link.controller_test import ControllerTest
from consoles_link.gamepad import PadInfo, Reading
from fake_gamepad import FakePad, FakeSdl


def _until(qapp, dialog, condition, timeout=2.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        qapp.processEvents()
        dialog.refresh()
        time.sleep(0.005)
    return True


def test_the_controller_test(qapp):
    pad = FakePad("PS4 Controller", Reading(buttons=frozenset({gamepad.SOUTH}), axes=(16384, 0, 0, -3277, 32767, 0),
                                              fingers={(0, 0): (0.25, 0.5)}))
    pad.info = PadInfo("PS4 Controller", 0x054C, 0x05C4, 0x2033, "/dev/hidraw3", "wireless", (1, 2), 1, True, True)
    sdl = FakeSdl({4: pad})
    checked = []

    def check(path):
        checked.append(path)
        return genuine.Result("DualShock 4 v1 (CUH-ZCT1)", [genuine.Check("Build date", True, "Built 15 May 2015.")],
                              0x05C4)
    dialog = ControllerTest(backend=sdl, check=check)
    try:
        assert _until(qapp, dialog, lambda: dialog.pad_box.count() == 1)
        assert dialog.pad_box.itemText(0) == "DualShock 4 v1 (CUH-ZCT1), wireless"
        assert dialog.info_label.text().startswith("DualShock 4 v1 (CUH-ZCT1): USB ID 054c:05c4")
        assert "054c:05c4" in dialog.info_label.text() and "battery on battery, 80 %" in dialog.info_label.text()
        assert dialog.genuine_label.text().startswith("Genuine DS4v1: it answers as a genuine DualShock 4")
        assert checked == ["/dev/hidraw3"]
        assert dialog.seen_label.text() == "1 of 16 buttons pressed at least once."
        assert dialog.left_label.text() == "Left  x +50%  y +0%" and dialog.l2_bar.value() == 255
        assert dialog.right_view.position == (0, -3277) and dialog.touch_view.fingers == [(0.25, 0.5)]
        with sdl.lock:
            pad.reading = Reading(buttons=frozenset({gamepad.NORTH}))
        assert _until(qapp, dialog, lambda: dialog.seen_label.text().startswith("2 of 16"))   # cross stays ticked
        dialog.left_motor.click()
        dialog.light_button.click()
        dialog.light_button.click()
        assert _until(qapp, dialog, lambda: len(sdl.outputs) == 3)
        assert sdl.outputs == [("rumble", "PS4 Controller", (0xFF00, 0, 1000)), ("led", "PS4 Controller", (255, 0, 0)),
                               ("led", "PS4 Controller", (0, 255, 0))]
        assert _until(qapp, dialog, lambda: dialog.status_label.text().startswith("Rumble sent (1 s)."))
        assert "Try another controller" in dialog.status_label.text()
        sdl.rumble_error = "That operation is not supported"
        dialog.right_motor.click()
        assert _until(qapp, dialog, lambda: "did not send" in dialog.status_label.text())
        assert dialog.status_label.text() == "SDL did not send the rumble: That operation is not supported."
        dialog.refresh()
        assert len(checked) == 1                        # checked once per controller
    finally:
        dialog.close()
    assert sdl.quit_called


def test_without_a_controller(qapp):
    dialog = ControllerTest(backend=FakeSdl(), check=lambda path: None)
    try:
        dialog.refresh()
        assert dialog.info_label.text().startswith("No controller found")
        assert not dialog.left_motor.isEnabled() and not dialog.light_button.isEnabled()
    finally:
        dialog.close()


def test_a_controller_that_is_not_sony(qapp):
    pad = FakePad("Xbox Wireless Controller")
    pad.info = PadInfo("Xbox Wireless Controller", 0x045E, 0x0B12, 0, "/dev/hidraw5", "cable", (), 0, True, False)
    sdl = FakeSdl({1: pad})
    dialog = ControllerTest(backend=sdl, check=genuine.check_device)
    try:
        assert _until(qapp, dialog, lambda: dialog.pad_box.count() == 1)
        assert "only checked for a Sony" in dialog.genuine_label.text()
        assert dialog.left_motor.isEnabled() and not dialog.light_button.isEnabled()
    finally:
        dialog.close()
