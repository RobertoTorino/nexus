# SPDX-License-Identifier: GPL-3.0-or-later
"""The V4L2 control ioctls against a fake kernel that has the controls the PS5 HD Camera reported on the owner's
board (23-10-2026), and applying the values the user chose."""

from __future__ import annotations

import ctypes
import errno

from usb_hdcam import controls

# (id, type, name, minimum, maximum, step, default, flags, menu) as v4l2-ctl listed them on the owner's board.
BOARD = [
    (0x980900, 1, "Brightness", 0, 8, 1, 4, 0, {}),
    (0x980901, 1, "Contrast", 0, 8, 1, 4, 0, {}),
    (0x980902, 1, "Saturation", 0, 8, 1, 4, 0, {}),
    (0x980903, 1, "Hue", 0, 11, 1, 0, 0, {}),
    (0x98090c, 2, "White Balance, Automatic", 0, 1, 1, 1, 0, {}),
    (0x980913, 1, "Gain", 0, 8, 1, 4, 0, {}),
    (0x980918, 3, "Power Line Frequency", 0, 2, 1, 1, 0, {0: "Disabled", 1: "50 Hz", 2: "60 Hz"}),
    (0x98091a, 1, "White Balance Temperature", 2800, 6500, 100, 4600, 0, {}),
    (0x98091b, 1, "Sharpness", 0, 8, 1, 4, 0, {}),
    (0x9a0901, 3, "Auto Exposure", 0, 3, 1, 2, 0, {0: "Auto Mode", 2: "Shutter Priority Mode"}),
    (0x9a0902, 1, "Exposure Time, Absolute", 1, 5000, 1, 1000, 0, {}),
]
AUTO_WB, WB_TEMPERATURE, AUTO_EXPOSURE, EXPOSURE = 0x98090c, 0x98091a, 0x9a0901, 0x9a0902


class FakeKernel:
    """A uvcvideo camera: its controls, values that start at the defaults, the white balance temperature inactive
    while the white balance is automatic, and the exposure time while the exposure is not manual (1)."""

    def __init__(self, refuse: set[int] = frozenset()):
        self.table = {row[0]: row for row in BOARD}
        self.values = {row[0]: row[6] for row in BOARD}
        self.sets = []
        self.refuse = refuse

    def flags(self, control_id: int) -> int:
        if control_id == WB_TEMPERATURE and self.values[AUTO_WB]:
            return controls.FLAG_INACTIVE
        if control_id == EXPOSURE and self.values[AUTO_EXPOSURE] != 1:
            return controls.FLAG_INACTIVE
        return 0

    def __call__(self, fd, request, argument):
        if request == controls.QUERYCTRL:
            wanted = argument.id & ~controls.NEXT_CTRL
            following = [i for i in sorted(self.table) if i > wanted] if argument.id & controls.NEXT_CTRL else \
                [wanted] if wanted in self.table else []
            if not following:
                raise OSError(errno.EINVAL, "no more")
            row = self.table[following[0]]
            argument.id, argument.type, argument.name = row[0], row[1], row[2].encode()
            argument.minimum, argument.maximum, argument.step, argument.default_value = row[3:7]
            argument.flags = self.flags(row[0])
        elif request == controls.QUERYMENU:
            menu = self.table[argument.id][8]
            if argument.index not in menu:
                raise OSError(errno.EINVAL, "gap")
            argument.name = menu[argument.index].encode()
        elif request == controls.G_CTRL:
            argument.value = self.values[argument.id]
        elif request == controls.S_CTRL:
            if argument.id in self.refuse:
                raise OSError(errno.EIO, "Input/output error")
            self.sets.append((argument.id, argument.value))
            self.values[argument.id] = argument.value


def open_fake(kernel):
    return controls.Camera("/dev/video1", ioctl=kernel, open_node=lambda path: -1)


def test_ioctl_numbers():
    assert (ctypes.sizeof(controls.QueryCtrl), ctypes.sizeof(controls.QueryMenu), ctypes.sizeof(controls.Ctrl)) == \
        (68, 44, 8)
    assert controls.QUERYCTRL == 0xC0445624 and controls.QUERYMENU == 0xC02C5625
    assert controls.G_CTRL == 0xC008561B and controls.S_CTRL == 0xC008561C


def test_list_as_on_the_board():
    listed = open_fake(FakeKernel()).list()
    assert [c.key for c in listed] == ["brightness", "contrast", "saturation", "hue", "white_balance_automatic", "gain",
                                       "power_line_frequency", "white_balance_temperature", "sharpness",
                                       "auto_exposure", "exposure_time_absolute"]
    by_key = {c.key: c for c in listed}
    assert by_key["auto_exposure"].menu == {0: "Auto Mode", 2: "Shutter Priority Mode"}     # 1 and 3: gaps
    assert by_key["brightness"].value == 4 and by_key["brightness"].active
    assert not by_key["white_balance_temperature"].active and not by_key["exposure_time_absolute"].active


def test_apply_sets_every_chosen_value_modes_first():
    kernel = FakeKernel()
    refused = controls.apply(open_fake(kernel), {"brightness": 7, "white_balance_automatic": 0,
                                                 "white_balance_temperature": 5200, "gain": 4, "unknown": 3})
    assert refused == []
    assert kernel.sets[0] == (AUTO_WB, 0)
    assert set(kernel.sets[1:]) == {(0x980900, 7), (WB_TEMPERATURE, 5200), (0x980913, 4)}  # gain read 4 already


def test_apply_names_what_the_camera_refused():
    assert controls.apply(open_fake(FakeKernel(refuse={0x980900})), {"brightness": 7}) == ["Brightness"]
