# SPDX-License-Identifier: GPL-3.0-or-later
"""The battery for the header's status line: Windows' GetSystemPowerStatus, which answers at once (the Device
card's CIM query takes seconds). None where there is no battery, or not on Windows."""

from __future__ import annotations

import ctypes
import sys


class _Status(ctypes.Structure):
    _fields_ = [("ac_line", ctypes.c_ubyte), ("flags", ctypes.c_ubyte), ("percent", ctypes.c_ubyte),
                ("saver", ctypes.c_ubyte), ("seconds_left", ctypes.c_ulong), ("seconds_full", ctypes.c_ulong)]


NO_BATTERY = 128                # BatteryFlag: no system battery
UNKNOWN = 255                   # BatteryLifePercent: unknown


def battery() -> tuple[int, bool] | None:
    """The charge in percent and whether the charger is in; None without a battery or its percentage."""
    if sys.platform != "win32":
        return None
    status = _Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None
    return from_status(status.ac_line, status.flags, status.percent)


def from_status(ac_line: int, flags: int, percent: int) -> tuple[int, bool] | None:
    if flags & NO_BATTERY or percent == UNKNOWN:
        return None
    return percent, ac_line == 1


def text(state: tuple[int, bool] | None) -> str:
    """"82 %" on battery, "100 % charging" on the charger, "" without a battery."""
    if state is None:
        return ""
    percent, plugged = state
    return f"{percent} % charging" if plugged and percent < 100 else f"{percent} %"
