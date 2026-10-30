# SPDX-License-Identifier: GPL-3.0-or-later
"""The CPU and GPU temperatures for the header's status line, live (owner, 28-10-2026), and the power the chip
draws (owner, 29-10-2026: ADL's ASIC_POWER, whole watts; none without AMD's driver): read by core's chip.py (moved
there 30-10-2026, for the portal's header too); the header's text here."""

from __future__ import annotations

import sys  # noqa: F401  (the tests set sys.platform through it)

from bc250_core.chip import ASIC_POWER, Temperatures, _Sensor, kmt_temperature  # noqa: F401


def text(cpu: int | None, gpu: int | None) -> str:
    """For the header: "CPU 47° GPU 45°" (owner, 28-10-2026); "" with neither."""
    return " ".join(f"{name} {value}°" for name, value in (("CPU", cpu), ("GPU", gpu)) if value is not None)


def status(cpu: int | None, gpu: int | None, watts: int | None, hertz: int | None, battery: str) -> list[str]:
    """The header's second line (owner, 29-10-2026: "power, display Hz"): "CPU 47° GPU 45°", "18 W", "120 Hz" and
    the battery, each left out when there is none."""
    return [text(cpu, gpu), f"{watts} W" if watts else "", f"{hertz} Hz" if hertz else "", battery]
