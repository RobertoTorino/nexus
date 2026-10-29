# SPDX-License-Identifier: GPL-3.0-or-later
"""The temperatures (temps.py): the header's text, and Windows' answer read for real on Windows."""

from __future__ import annotations

import sys

import pytest

from portable_test import temps


@pytest.mark.parametrize("cpu, gpu, text", [(47, 45, "CPU 47° GPU 45°"), (None, 45, "GPU 45°"), (None, None, "")])
def test_the_header_text(cpu, gpu, text):
    assert temps.text(cpu, gpu) == text


def test_nothing_to_read_off_windows(monkeypatch):
    monkeypatch.setattr(temps.sys, "platform", "linux")
    assert temps.Temperatures().read() == (None, None)


@pytest.mark.skipif(sys.platform != "win32", reason="AMD's ADL and Windows' D3DKMT")
def test_windows_answers():
    sensors = temps.Temperatures()                  # a CI runner has no AMD driver and a software adapter: None
    try:
        for value in sensors.read():
            assert value is None or 10 <= value <= 110
    finally:
        sensors.close()


@pytest.mark.parametrize("watts, hertz, parts", [
    (18, 120, ["CPU 47° GPU 45°", "18 W", "120 Hz", "82%"]),
    (None, 60, ["CPU 47° GPU 45°", "", "60 Hz", "82%"]),         # no AMD driver: no power draw
    (None, None, ["CPU 47° GPU 45°", "", "", "82%"]),
])
def test_the_second_line_has_the_power_draw_and_the_refresh_rate(watts, hertz, parts):
    assert temps.status(47, 45, watts, hertz, "82%") == parts


def test_the_power_draw_is_adls_asic_power(monkeypatch):
    sensors = temps.Temperatures.__new__(temps.Temperatures)
    sensors._adl = None
    assert sensors.watts() is None                              # no AMD driver

    class Adl:
        def ADL2_New_QueryPMLogData_Get(self, context, adapter, data):
            data._obj.sensors[temps.ASIC_POWER] = temps._Sensor(1, 18)
            return 0
    sensors._adl, sensors._context, sensors._adapter = Adl(), None, 0
    assert temps.ASIC_POWER == 23 and sensors.watts() == 18
