# SPDX-License-Identifier: GPL-3.0-or-later
"""The values from what Windows reports: the CPU's clock from the performance counters, the GPU's load from AMD's
driver or else Windows' own, the network of every adapter or of one, and a handheld that reports nothing."""

from __future__ import annotations

import sys

import pytest

from smart_screen import values
from smart_screen.values import Reading, Values

COUNTED = {"cpu_base": {"_Total": 2000.0}, "cpu_performance": {"_Total": 124.6},
           "gpu_3d": {"pid_1_eng_0_engtype_3D": 30.0, "pid_2_eng_0_engtype_3D": 12.5},
           "net_in": {"Wi-Fi adapter": 1000.0, "Ethernet adapter": 500.0},
           "net_out": {"Wi-Fi adapter": 10.0, "Ethernet adapter": 5.0},
           "disk_read": {"_Total": 2048.0}, "disk_write": {"_Total": 4096.0}}


def read(counted=COUNTED, adl_gpu=None, interface=None) -> Reading:
    return values.reading_from(counted, (47, 46), 12, adl_gpu, 7, (6, 16), (82, True), interface)


def test_every_value():
    r = read()
    assert (r.cpu_load, r.cpu_mhz, r.cpu_temp, r.gpu_temp, r.watts) == (7, 2492, 47, 46, 12)
    assert (r.ram, r.battery, r.disk) == ((6, 16), (82, True), (2048.0, 4096.0))
    assert r.net == (1500.0, 15.0)                                  # every adapter added up


def test_the_gpu_load_is_amds_or_else_windows_own():
    assert read(adl_gpu=3).gpu_load == 3
    assert read().gpu_load == 42.5
    assert read({**COUNTED, "gpu_3d": {"a": 80.0, "b": 70.0}}).gpu_load == 100.0


def test_one_adapter():
    assert read(interface="Ethernet adapter").net == (500.0, 5.0)
    assert read(interface="Gone adapter").net is None               # unplugged: no value rather than all of them


def test_nothing_reported():
    r = values.reading_from({}, (None, None), None, None, None, None, None)
    assert r == Reading()


class FakeCounters:
    def __init__(self):
        self.closed = False

    def values(self):
        return COUNTED

    def close(self):
        self.closed = True


class FakeTemps:
    def read(self):
        return 50, 51

    def watts(self):
        return 9

    def gpu_load(self):
        return None

    def close(self):
        pass


class FakeCpu:
    def read(self):
        return 3


def test_values_reads_and_lists_the_adapters():
    counters = FakeCounters()
    reader = Values(counters, FakeTemps(), FakeCpu(), lambda: (1, 2), lambda: None)
    assert reader.interfaces() == []
    first = reader.read()
    assert (first.cpu_temp, first.watts, first.cpu_load, first.ram, first.battery) == (50, 9, 3, (1, 2), None)
    assert reader.interfaces() == ["Ethernet adapter", "Wi-Fi adapter"]
    reader.interface = "Wi-Fi adapter"
    assert reader.read().net == (1000.0, 10.0)
    reader.close()
    assert counters.closed


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' performance counters and memory status")
def test_windows_answers():
    """The counters open by their English names on this Windows, and the memory is read."""
    counters = values.Counters()
    try:
        assert counters.values() is not None
    finally:
        counters.close()
    used, total = values.memory()
    assert 0 < used < total
