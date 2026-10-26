# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor

from bc250_core.theme import GREEN, ORANGE, RED
from usb_hdcontrol import battery


@pytest.mark.parametrize("capacity, lit", [(0, 0), (5, 1), (20, 1), (25, 2), (55, 3), (85, 5), (100, 5)])
def test_modules(capacity, lit):
    assert battery.modules(capacity) == lit


@pytest.mark.parametrize("capacity, status, color", [(80, "Discharging", GREEN), (20, "Discharging", ORANGE),
                                                      (10, "Discharging", RED), (10, "Charging", GREEN),
                                                      (100, "Full", GREEN)])
def test_colour(capacity, status, color):
    assert battery.colour(capacity, status) == color


def count(icon, colour: str) -> int:
    image = icon.grab().toImage()
    return sum(image.pixelColor(x, y) == QColor(colour) for x in range(image.width()) for y in range(image.height()))


def test_charging_fills_the_modules_one_after_another(qapp):
    icon = battery.BatteryIcon()
    icon.set_battery(45, "Charging")
    assert icon.timer.isActive() and icon.lit_modules() == 3
    seen = []
    for _ in range(4):
        icon._step()
        seen.append(icon.lit_modules())
    assert seen == [4, 5, 3, 4]                         # up to full, then from the level again
    assert "45 %, charging" in icon.toolTip()
    icon.set_battery(100, "Full")
    assert not icon.timer.isActive() and icon.lit_modules() == 5


def test_on_its_battery_the_level_stays(qapp):
    icon = battery.BatteryIcon()
    icon.set_battery(15, "Discharging")
    assert not icon.timer.isActive() and icon.lit_modules() == 1
    assert count(icon, ORANGE) > 0 and count(icon, GREEN) == 0


def test_no_controller_is_an_empty_outline(qapp):
    icon = battery.BatteryIcon()
    icon.set_battery(None, "")
    assert icon.lit_modules() == 0 and count(icon, GREEN) == 0 and "No controller" in icon.toolTip()
