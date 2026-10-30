# SPDX-License-Identifier: GPL-3.0-or-later
"""The chip's live values (chip.py): the CPU load from Windows' system times, the GPU load from ADL's activity
sensor, the text for a header, and Windows' answer read for real on Windows."""

from __future__ import annotations

import sys

import pytest

from bc250_core import chip


def test_the_cpu_load_is_the_busy_part_since_the_last_read():
    times = iter([(1000, 1000), (1300, 1700), (1300, 1700), None])
    load = chip.CpuLoad(times=lambda: next(times))
    assert load.read() == 70                                   # 300 idle, 700 busy
    assert load.read() is None                                 # no time passed
    assert load.read() is None                                 # Windows did not answer


def test_the_gpu_load_is_adls_activity_and_zero_counts():
    sensors = chip.Temperatures.__new__(chip.Temperatures)
    sensors._adl = None
    assert sensors.gpu_load() is None                          # no AMD driver

    class Adl:
        value = 0

        def ADL2_New_QueryPMLogData_Get(self, context, adapter, data):
            data._obj.sensors[chip.ACTIVITY_GFX] = chip._Sensor(1, self.value)
            return 0
    sensors._adl, sensors._context, sensors._adapter = Adl(), None, 0
    assert chip.ACTIVITY_GFX == 19 and sensors.gpu_load() == 0
    sensors._adl.value = 37
    assert sensors.gpu_load() == 37


@pytest.mark.parametrize("values, parts", [
    ((12, 48, 7, 47), ["CPU 12% 48°", "GPU 7% 47°"]),
    ((12, None, None, 47), ["CPU 12%", "GPU 47°"]),            # no AMD driver: the GPU's temperature from D3DKMT
    ((None, None, None, None), []),
])
def test_the_header_parts(values, parts):
    assert chip.parts(*values) == parts


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' GetSystemTimes, AMD's ADL")
def test_windows_answers():
    load, sensors = chip.CpuLoad(), chip.Temperatures()        # a CI runner has no AMD driver: None
    try:
        assert chip.system_times() is not None
        value = load.read()
        assert value is None or 0 <= value <= 100
        gpu = sensors.gpu_load()
        assert gpu is None or 0 <= gpu <= 100
    finally:
        sensors.close()
