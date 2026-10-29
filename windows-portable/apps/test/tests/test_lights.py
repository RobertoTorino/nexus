# SPDX-License-Identifier: GPL-3.0-or-later
"""The stick lights (lights.py) with a LampArray stood in for: the Ally's four lamps, a color on all or on one
stick's two, and let go on close."""

from __future__ import annotations

from portable_test import lights


class FakeArray:
    """A LampArray as pywinrt gives it: the Ally's controller, four lamps."""

    def __init__(self, lamps=4, enabled=True, available=True):
        self.lamp_count, self.is_enabled, self.is_available = lamps, enabled, available
        self.colors = [None] * lamps

    def set_color(self, color):
        self.colors = [color] * self.lamp_count

    def set_color_for_index(self, index, color):
        self.colors[index] = color


def make(array=None):
    array = array if array is not None else FakeArray()
    return lights.Lights(find=lambda: [("RTG789", array)], color=lambda rgb: rgb), array


def test_a_color_on_both_sticks_and_on_one():
    lamps, array = make()
    found = lamps.open()
    assert found == lights.Found("RTG789", 4, True, True) and "4 lamps" in found.text()
    assert lamps.show(lights.COLORS["Red"]) and array.colors == [(255, 0, 0)] * 4
    assert lamps.show(lights.COLORS["White"], lights.LEFT)
    assert array.colors == [(255, 255, 255), (255, 255, 255), (0, 0, 0), (0, 0, 0)]
    assert lamps.show(lights.COLORS["White"], lights.RIGHT)
    assert array.colors == [(0, 0, 0), (0, 0, 0), (255, 255, 255), (255, 255, 255)]
    lamps.close()
    assert lamps.array is None and not lamps.show(lights.OFF)       # let go: Windows gives the lights back


def test_none_found_and_the_window_not_in_front():
    assert lights.Lights(find=lambda: []).open() is None
    lamps, _ = make(FakeArray(available=False))
    assert "only while its window is in front" in lamps.open().text()
