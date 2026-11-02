# SPDX-License-Identifier: GPL-3.0-or-later
"""The handheld's live values for the screen, as Windows reports them, without an administrator and in any Windows
language. The BC250 suite's USB IPS3.5 reads the board's /proc and /sys (core's sensors.py, Linux only); here:

* the CPU's and GPU's temperature, the chip's power and the GPU's load from core's chip.py (AMD's driver library, as
  Windows Portable Test's header reads them), the CPU's load from Windows' own times (chip.CpuLoad);
* the CPU's clock, the GPU's load without AMD's driver, the network and the disks from Windows' performance counters
  (PDH, by their English names, PdhAddEnglishCounterW, so a Dutch or German Windows reads the same), the rate
  Windows works out between two reads;
* the memory from GlobalMemoryStatusEx, the battery from core's power.py.

Every value is None where Windows has none, so the tile shows "—" instead of failing on a handheld without it. A read
takes a few milliseconds."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from dataclasses import dataclass

from bc250_core import chip, power

# The counters, by their English names (any Windows language)
NET_IN = r"\Network Interface(*)\Bytes Received/sec"
NET_OUT = r"\Network Interface(*)\Bytes Sent/sec"
DISK_READ = r"\PhysicalDisk(_Total)\Disk Read Bytes/sec"
DISK_WRITE = r"\PhysicalDisk(_Total)\Disk Write Bytes/sec"
GPU_3D = r"\GPU Engine(*engtype_3D)\Utilization Percentage"      # Task Manager's GPU 3D, every process's together
CPU_BASE = r"\Processor Information(_Total)\Processor Frequency"  # MHz, the base clock
CPU_PERFORMANCE = r"\Processor Information(_Total)\% Processor Performance"   # of the base: Task Manager's Speed
COUNTERS = {"net_in": NET_IN, "net_out": NET_OUT, "disk_read": DISK_READ, "disk_write": DISK_WRITE,
            "gpu_3d": GPU_3D, "cpu_base": CPU_BASE, "cpu_performance": CPU_PERFORMANCE}
PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2


@dataclass(frozen=True)
class Reading:
    cpu_load: float | None = None           # percent, over the time since the previous reading
    cpu_mhz: int | None = None              # the CPU's clock now, as Task Manager's Speed
    cpu_temp: float | None = None           # °C
    gpu_load: float | None = None           # percent
    gpu_temp: float | None = None           # °C
    watts: int | None = None                # the whole chip's power (AMD's driver)
    ram: tuple[int, int] | None = None      # used, total bytes
    battery: tuple[int, bool] | None = None     # percent, the charger in (core's power.battery)
    net: tuple[float, float] | None = None  # download, upload bytes/s since the previous reading
    disk: tuple[float, float] | None = None     # read, write bytes/s since the previous reading


class _Item(ctypes.Structure):          # PDH_FMT_COUNTERVALUE_ITEM_W with its PDH_FMT_COUNTERVALUE (a double)
    _fields_ = [("name", ctypes.c_wchar_p), ("status", ctypes.c_uint32), ("pad", ctypes.c_uint32),
                ("value", ctypes.c_double)]


class Counters:
    """Windows' performance counters, opened once: values() gives each counter's instances and values since the
    read before (the first read gives none: a rate needs two)."""

    def __init__(self, paths: dict[str, str] = COUNTERS):
        self._pdh = None
        self._query = ctypes.c_void_p()
        self._counters: dict[str, ctypes.c_void_p] = {}
        if sys.platform != "win32":
            return
        try:
            pdh = ctypes.WinDLL("pdh")
        except OSError:
            return
        if pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)):
            return
        pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                                     ctypes.POINTER(ctypes.c_uint32),
                                                     ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
        for key, path in paths.items():
            counter = ctypes.c_void_p()
            if not pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(counter)):
                self._counters[key] = counter
        self._pdh = pdh
        pdh.PdhCollectQueryData(self._query)

    def values(self) -> dict[str, dict[str, float]]:
        """{counter: {instance: value}}, a counter without a valid value left out."""
        if self._pdh is None or self._pdh.PdhCollectQueryData(self._query):
            return {}
        found = {}
        for key, counter in self._counters.items():
            size, count = ctypes.c_uint32(0), ctypes.c_uint32(0)
            status = self._pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, ctypes.byref(size),
                                                             ctypes.byref(count), None)
            if status & 0xFFFFFFFF != PDH_MORE_DATA or not size.value:
                continue
            buffer = ctypes.create_string_buffer(size.value)
            if self._pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, ctypes.byref(size),
                                                      ctypes.byref(count), buffer):
                continue
            items = ctypes.cast(buffer, ctypes.POINTER(_Item))
            found[key] = {items[n].name: items[n].value for n in range(count.value) if items[n].status in (0, 1)}
        return found

    def close(self) -> None:
        if self._pdh is not None:
            self._pdh.PdhCloseQuery(self._query)
            self._pdh = None


class _Memory(ctypes.Structure):        # MEMORYSTATUSEX
    _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32), ("total", ctypes.c_uint64),
                ("available", ctypes.c_uint64), ("total_page", ctypes.c_uint64), ("available_page", ctypes.c_uint64),
                ("total_virtual", ctypes.c_uint64), ("available_virtual", ctypes.c_uint64),
                ("available_extended", ctypes.c_uint64)]


def memory() -> tuple[int, int] | None:
    """The memory in use and Windows' usable memory (what the graphics left), in bytes; None off Windows."""
    if sys.platform != "win32":
        return None
    status = _Memory(length=ctypes.sizeof(_Memory))
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None
    return status.total - status.available, status.total


def _pair(values: dict[str, dict[str, float]], first: str, second: str,
          only: str | None = None) -> tuple[float, float] | None:
    """Two counters added up over their instances (only *only*'s, when given); None when either is missing."""
    if first not in values or second not in values:
        return None
    if only is not None:
        if only not in values[first] or only not in values[second]:
            return None
        return values[first][only], values[second][only]
    return sum(values[first].values()), sum(values[second].values())


def reading_from(values: dict[str, dict[str, float]], temps: tuple[int | None, int | None], watts: int | None,
                 adl_gpu_load: int | None, cpu_load: int | None, ram: tuple[int, int] | None,
                 battery: tuple[int, bool] | None, interface: str | None = None) -> Reading:
    """A Reading from what was read; *interface* the network adapter the Network tile measures (None: all)."""
    base, performance = values.get("cpu_base", {}), values.get("cpu_performance", {})
    mhz = None
    if base and performance:
        mhz = round(next(iter(base.values())) * next(iter(performance.values())) / 100) or None
    gpu = adl_gpu_load
    if gpu is None and "gpu_3d" in values:
        gpu = max(0.0, min(100.0, sum(values["gpu_3d"].values())))
    return Reading(cpu_load=cpu_load, cpu_mhz=mhz, cpu_temp=temps[0], gpu_load=gpu, gpu_temp=temps[1], watts=watts,
                   ram=ram, battery=battery, net=_pair(values, "net_in", "net_out", interface),
                   disk=_pair(values, "disk_read", "disk_write"))


class Values:
    """The readers, opened once; read() every second. *interface*: the adapter the Network tile measures, by the
    name Windows' counters give it (its description: "Intel(R) Wi-Fi 6E AX211"), None for all of them."""

    def __init__(self, counters: Counters | None = None, temperatures: chip.Temperatures | None = None,
                 cpu: chip.CpuLoad | None = None, ram: Callable[[], tuple[int, int] | None] = memory,
                 battery: Callable[[], tuple[int, bool] | None] = power.battery):
        self.counters = counters or Counters()
        self.temperatures = temperatures or chip.Temperatures()
        self.cpu = cpu or chip.CpuLoad()
        self._ram, self._battery = ram, battery
        self.interface: str | None = None
        self._interfaces: list[str] = []

    def interfaces(self) -> list[str]:
        """The network adapters seen at the last read, as Windows' counters name them."""
        return list(self._interfaces)

    def read(self) -> Reading:
        values = self.counters.values()
        if "net_in" in values:
            self._interfaces = sorted(values["net_in"])
        return reading_from(values, self.temperatures.read(), self.temperatures.watts(),
                            self.temperatures.gpu_load(), self.cpu.read(), self._ram(), self._battery(),
                            self.interface)

    def close(self) -> None:
        self.counters.close()
        self.temperatures.close()
