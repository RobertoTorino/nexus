# SPDX-License-Identifier: GPL-3.0-or-later
"""The stick lights (owner, 29-10-2026: "the joysticks have LED backlight"), through Windows' Dynamic Lighting
(Windows.Devices.Lights: a LampArray). The Ally's controller (0B05:1B4C) is one LampArray of four lamps: 0 and 1 the
left stick's ring, 2 and 3 the right's. Windows lets an app set them only while its window is in front, and gives
them back to their own app (Armoury Crate) when the window closes or another one comes in front. Nothing is set
before a pill of the test is pressed."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

LEFT, RIGHT = (0, 1), (2, 3)                    # the lamps of each stick's ring
COLORS = {"Red": (255, 0, 0), "Green": (0, 255, 0), "Blue": (0, 0, 255), "White": (255, 255, 255)}
OFF = (0, 0, 0)
SETTINGS = "Settings > Personalization > Dynamic Lighting"


@dataclass
class Found:
    name: str
    lamps: int
    enabled: bool               # Dynamic Lighting on for the device
    available: bool             # this app may set it now (its window in front)

    def text(self) -> str:
        return (f"{self.name}: {self.lamps} lamps. Dynamic Lighting {'on' if self.enabled else 'off'} for it"
                f"{'' if self.available else '; Windows lets the app set it only while its window is in front'}.")


def find_lamp_arrays() -> list[tuple[str, object]]:
    """Every LampArray Windows knows, with its device's name; none off Windows or without pywinrt."""
    if sys.platform != "win32":
        return []
    try:
        import asyncio

        from winrt.windows.devices.enumeration import DeviceInformation
        from winrt.windows.devices.lights import LampArray
    except ImportError:
        return []

    async def find() -> list[tuple[str, object]]:
        found = []
        for info in await DeviceInformation.find_all_async_aqs_filter(LampArray.get_device_selector()):
            array = await LampArray.from_id_async(info.id)
            if array is not None:
                found.append((info.name, array))
        return found

    try:
        return asyncio.run(find())
    except OSError:
        return []


def winrt_color(rgb: tuple[int, int, int]):
    from winrt.windows.ui import Color
    return Color(255, *rgb)


class Lights:
    """The first LampArray, opened on open() and let go on close(); show() sets a color on all lamps or on some
    (the others off). *find* and *color* stand in for Windows in the tests."""

    def __init__(self, find: Callable[[], list[tuple[str, object]]] = find_lamp_arrays,
                 color: Callable[[tuple[int, int, int]], object] = winrt_color):
        self._find, self._color = find, color
        self.name, self.array = "", None

    def open(self) -> Found | None:
        arrays = self._find()
        if not arrays:
            return None
        self.name, self.array = arrays[0]
        return self.found()

    def found(self) -> Found | None:
        if self.array is None:
            return None
        return Found(self.name, self.array.lamp_count, bool(self.array.is_enabled), bool(self.array.is_available))

    def show(self, rgb: tuple[int, int, int], lamps: tuple[int, ...] | None = None) -> bool:
        """*rgb* on *lamps* (every lamp when None), the others off; False when there is no LampArray."""
        if self.array is None:
            return False
        if lamps is None:
            self.array.set_color(self._color(rgb))
            return True
        self.array.set_color(self._color(OFF))
        for index in lamps:
            if index < self.array.lamp_count:
                self.array.set_color_for_index(index, self._color(rgb))
        return True

    def close(self) -> None:
        """Lets the LampArray go: Windows gives the lights back to their own app."""
        self.name, self.array = "", None
