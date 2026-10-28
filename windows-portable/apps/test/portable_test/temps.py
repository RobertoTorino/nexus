# SPDX-License-Identifier: GPL-3.0-or-later
"""The CPU and GPU temperatures for the header's status line, live (owner, 28-10-2026). Read without administrator
rights and in any Windows language: AMD's driver library (ADL, atiadlxx.dll, its PMLog sensors TEMPERATURE_CPU and
TEMPERATURE_GFX) on an AMD handheld; else the GPU's temperature as Task Manager reads it (D3DKMT, the adapter's
performance data) and no CPU temperature, rather than an ACPI thermal zone that is no CPU sensor (on the Ally the
THRM zone read about 10 °C above the CPU under load, 28-10-2026). A read takes a few milliseconds."""

from __future__ import annotations

import ctypes
import sys

# ADL: ADL_PMLOG_SENSORS (adl_defines.h), the sensors this reads; whole °C
TEMPERATURE_GFX, TEMPERATURE_CPU = 28, 32
SENSORS = 256                           # ADL_PMLOG_MAX_SENSORS
# D3DKMT: KMTQAITYPE_ADAPTERTYPE and _ADAPTERPERFDATA; the adapter type's SoftwareDevice bit (Microsoft Basic Render)
ADAPTER_TYPE, ADAPTER_PERFDATA = 15, 62
SOFTWARE = 0x4


class _AdapterInfo(ctypes.Structure):           # ADL's AdapterInfo (Windows)
    _fields_ = [("size", ctypes.c_int), ("index", ctypes.c_int), ("udid", ctypes.c_char * 256),
                ("bus", ctypes.c_int), ("device", ctypes.c_int), ("function", ctypes.c_int), ("vendor", ctypes.c_int),
                ("name", ctypes.c_char * 256), ("display", ctypes.c_char * 256), ("present", ctypes.c_int),
                ("exist", ctypes.c_int), ("driver_path", ctypes.c_char * 256),
                ("driver_path_ext", ctypes.c_char * 256), ("pnp", ctypes.c_char * 256),
                ("os_display_index", ctypes.c_int)]


class _Sensor(ctypes.Structure):
    _fields_ = [("supported", ctypes.c_int), ("value", ctypes.c_int)]


class _PMLog(ctypes.Structure):                 # ADLPMLogDataOutput
    _fields_ = [("size", ctypes.c_int), ("sensors", _Sensor * SENSORS)]


class _Luid(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_long)]


class _KmtAdapter(ctypes.Structure):            # D3DKMT_ADAPTERINFO
    _fields_ = [("handle", ctypes.c_uint32), ("luid", _Luid), ("sources", ctypes.c_ulong),
                ("precise", ctypes.c_int)]


class _Enum2(ctypes.Structure):                 # D3DKMT_ENUMADAPTERS2
    _fields_ = [("count", ctypes.c_ulong), ("adapters", ctypes.POINTER(_KmtAdapter))]


class _Query(ctypes.Structure):                 # D3DKMT_QUERYADAPTERINFO
    _fields_ = [("handle", ctypes.c_uint32), ("type", ctypes.c_int), ("data", ctypes.c_void_p),
                ("size", ctypes.c_uint32)]


class _PerfData(ctypes.Structure):              # D3DKMT_ADAPTER_PERFDATA: temperature in tenths of °C
    _fields_ = [("index", ctypes.c_uint32), ("memory_frequency", ctypes.c_uint64),
                ("max_memory_frequency", ctypes.c_uint64), ("max_memory_frequency_oc", ctypes.c_uint64),
                ("memory_bandwidth", ctypes.c_uint64), ("pcie_bandwidth", ctypes.c_uint64),
                ("fan", ctypes.c_ulong), ("power", ctypes.c_ulong), ("temperature", ctypes.c_ulong),
                ("override", ctypes.c_ubyte)]


_ALLOC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)


class Temperatures:
    """Opens ADL once (it stays open while the app runs) and reads both temperatures on read()."""

    def __init__(self):
        self._buffers: list = []                    # what ADL allocated through the callback: kept alive
        self._alloc = _ALLOC(self._allocate)
        self._adl = None
        self._context = ctypes.c_void_p()
        self._adapter = -1
        if sys.platform == "win32":
            self._open_adl()

    def _allocate(self, size: int) -> int:
        buffer = ctypes.create_string_buffer(size)
        self._buffers.append(buffer)
        return ctypes.addressof(buffer)

    def _open_adl(self) -> None:
        try:
            adl = ctypes.CDLL("atiadlxx.dll")
        except OSError:
            return                                  # no AMD driver
        if adl.ADL2_Main_Control_Create(self._alloc, 1, ctypes.byref(self._context)):
            return
        count = ctypes.c_int()
        adl.ADL2_Adapter_NumberOfAdapters_Get(self._context, ctypes.byref(count))
        if count.value > 0:
            infos = (_AdapterInfo * count.value)()
            adl.ADL2_Adapter_AdapterInfo_Get(self._context, ctypes.byref(infos), ctypes.sizeof(infos))
            for info in infos:
                active = ctypes.c_int()
                adl.ADL2_Adapter_Active_Get(self._context, info.index, ctypes.byref(active))
                if active.value:
                    self._adapter = info.index
                    break
        if self._adapter < 0:
            adl.ADL2_Main_Control_Destroy(self._context)
            return
        self._adl = adl

    def read(self) -> tuple[int | None, int | None]:
        """The CPU's and the GPU's temperature in °C; None where there is none to read."""
        cpu = gpu = None
        if self._adl is not None:
            data = _PMLog()
            if not self._adl.ADL2_New_QueryPMLogData_Get(self._context, self._adapter, ctypes.byref(data)):
                cpu = _sensor(data, TEMPERATURE_CPU)
                gpu = _sensor(data, TEMPERATURE_GFX)
        if gpu is None and sys.platform == "win32":
            gpu = kmt_temperature()
        return cpu, gpu

    def close(self) -> None:
        if self._adl is not None:
            self._adl.ADL2_Main_Control_Destroy(self._context)
            self._adl = None


def _sensor(data: _PMLog, index: int) -> int | None:
    sensor = data.sensors[index]
    return sensor.value if sensor.supported and sensor.value > 0 else None


def kmt_temperature() -> int | None:
    """The warmest hardware graphics adapter's temperature as Task Manager reads it; None when no driver says."""
    gdi = ctypes.WinDLL("gdi32")
    found = _Enum2()
    if gdi.D3DKMTEnumAdapters2(ctypes.byref(found)) or not found.count:
        return None
    adapters = (_KmtAdapter * found.count)()
    found.adapters = adapters
    if gdi.D3DKMTEnumAdapters2(ctypes.byref(found)):
        return None
    warmest = None
    for adapter in adapters[:found.count]:
        kind, perf = ctypes.c_uint32(), _PerfData()
        query = _Query(adapter.handle, ADAPTER_TYPE, ctypes.cast(ctypes.byref(kind), ctypes.c_void_p),
                       ctypes.sizeof(kind))
        if not gdi.D3DKMTQueryAdapterInfo(ctypes.byref(query)) and not kind.value & SOFTWARE:
            query = _Query(adapter.handle, ADAPTER_PERFDATA, ctypes.cast(ctypes.byref(perf), ctypes.c_void_p),
                           ctypes.sizeof(perf))
            if not gdi.D3DKMTQueryAdapterInfo(ctypes.byref(query)) and perf.temperature:
                warmest = max(warmest or 0, round(perf.temperature / 10))
        gdi.D3DKMTCloseAdapter(ctypes.byref(ctypes.c_uint32(adapter.handle)))
    return warmest


def text(cpu: int | None, gpu: int | None) -> str:
    """For the header: "CPU 47° GPU 45°" (owner, 28-10-2026); "" with neither."""
    return " ".join(f"{name} {value}°" for name, value in (("CPU", cpu), ("GPU", gpu)) if value is not None)
