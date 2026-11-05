# SPDX-License-Identifier: GPL-3.0-or-later
"""The header's status line (owner, 05-11-2026): the CPU's and the GPU's load and temperature, the date and time."""

from __future__ import annotations

import datetime
import zoneinfo

from bc250_portal import status

AMSTERDAM = zoneinfo.ZoneInfo("Europe/Amsterdam")


def write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def board(tmp_path, busy: str | None = "37"):
    """A BC-250 as sysfs and /proc show it: k10temp, the GPU's amdgpu sensor beside a mainboard chip and an NVMe."""
    sys_root, proc = tmp_path / "sys", tmp_path / "proc"
    write(sys_root / "class/hwmon/hwmon0/name", "nvme")
    write(sys_root / "class/hwmon/hwmon0/temp1_input", "46850")
    write(sys_root / "class/hwmon/hwmon2/name", "nct6686")
    write(sys_root / "class/hwmon/hwmon2/temp1_input", "41000")
    write(sys_root / "class/hwmon/hwmon4/name", "k10temp")
    write(sys_root / "class/hwmon/hwmon4/temp1_input", "54875")
    write(sys_root / "class/hwmon/hwmon4/temp1_label", "Tctl")
    device = sys_root / "class/drm/card1/device"
    write(device / "pp_dpm_sclk", "0: 1000Mhz\n1: 1500Mhz *\n2: 2000Mhz\n")
    write(device / "hwmon/hwmon3/name", "amdgpu")
    write(device / "hwmon/hwmon3/temp1_input", "61000")
    write(device / "hwmon/hwmon3/temp1_label", "edge")
    if busy is not None:
        write(device / "gpu_busy_percent", busy)
    write(proc / "stat", "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 1 2 3 4\n")
    write(proc / "self/mountinfo", "")
    return sys_root, proc


THURSDAY = datetime.datetime(2026, 11, 5, 19, 44, tzinfo=AMSTERDAM)


def test_the_clock_reads_as_the_owner_wrote_it():
    assert status.clock_text(THURSDAY) == "Thursday 11/5/26 | 07:44 PM CET"
    assert status.clock_text(datetime.datetime(2026, 7, 2, 9, 5, tzinfo=AMSTERDAM)) == "Thursday 7/2/26 | 09:05 AM CEST"


def test_the_line_has_the_load_from_the_second_sample(tmp_path):
    sys_root, proc = board(tmp_path)
    reader = status.Status(sys_root, proc)
    assert reader.line(THURSDAY) == "CPU 55°C | GPU 37% 61°C | Thursday 11/5/26 | 07:44 PM CET"   # no load yet
    write(proc / "stat", "cpu  130 0 130 840 0 0 0 0 0 0\n")       # 60 busy of 100
    assert reader.line(THURSDAY) == "CPU 60% 55°C | GPU 37% 61°C | Thursday 11/5/26 | 07:44 PM CET"


def test_the_gpu_load_from_the_engine_time_without_a_load_sensor(tmp_path):
    """A stock Cyan Skillfish kernel has no gpu_busy_percent: the engine time of this user's GPU clients counts."""
    sys_root, proc = board(tmp_path, busy=None)
    now = [100.0]
    fdinfo = proc / "4242/fdinfo/7"
    write(fdinfo, "drm-driver:\tamdgpu\ndrm-client-id:\t9\ndrm-engine-gfx:\t1000000000 ns\n"
                  "drm-engine-compute:\t0 ns\n")
    write(proc / "17/fdinfo/3", "pos: 0\nflags: 02\n")             # not the GPU
    reader = status.Status(sys_root, proc, clock=lambda: now[0])
    assert reader.gpu_load() is None and reader._fds == [("4242", "7")]
    now[0] += 2
    write(fdinfo, "drm-driver:\tamdgpu\ndrm-client-id:\t9\ndrm-engine-gfx:\t1500000000 ns\n"
                  "drm-engine-compute:\t200000000 ns\n")
    assert reader.gpu_load() == 25.0                                # 0.5 s of gfx in 2 s


def test_the_patched_gpu_metrics_count_only_when_mounted(tmp_path):
    import struct
    sys_root, proc = board(tmp_path, busy=None)
    raw = bytearray(64)
    raw[0:4] = bytes([64, 0, 2, 2])
    struct.pack_into("<H", raw, 28, 42)
    (sys_root / "class/drm/card1/device/gpu_metrics").write_bytes(bytes(raw))
    reader = status.Status(sys_root, proc)
    assert reader._sensor() is None                                 # a stock kernel's copy: not read
    write(proc / "self/mountinfo", "1 2 0:3 / /sys/.../gpu_metrics rw - tmpfs\n")
    assert reader._sensor() == 42.0


def test_what_the_system_does_not_report_is_left_out(tmp_path):
    reader = status.Status(tmp_path / "sys", tmp_path / "proc")
    assert reader.line(THURSDAY) == "Thursday 11/5/26 | 07:44 PM CET"
