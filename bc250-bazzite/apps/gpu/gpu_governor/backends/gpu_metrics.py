# SPDX-License-Identifier: GPL-3.0-or-later
"""Structured reader for the amdgpu `gpu_metrics` sysfs table (format 2.x, used by Cyan Skillfish APUs).

Layout of `struct gpu_metrics_v2_1` / `v2_2` from the kernel's kgd_pp_interface.h. Everything is
little-endian; 0xFFFF marks a field the firmware does not report. The governor's fix-metrics writes its
own load into `average_gfx_activity` (byte 28), which is why this table is the one trustworthy load
source on a BC-250.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

UNSUPPORTED = 0xFFFF
USAGE_OFFSET = 0x1C                 # average_gfx_activity, the field the governor patches
# average_gfx_activity is in hundredths of a percent, as on other AMD APUs: the governor writes 0..10000 (10000 under
# full load on the board), and the unpatched 0xFFFF is what MangoHud shows as "655%".
ACTIVITY_SCALE = 100
# cyan_skillfish_ppt.c copies the SMU's power readings into the table unconverted: 24.8 fixed-point watts,
# which is why amdgpu's hwmon code shifts them right by 8 before use. Raw 4000..8000 is 15..31 W.
POWER_FRACTION_BITS = 8

_HEADER = struct.Struct("<HBB")     # structure_size, format_revision, content_revision
# Body of v2.1/v2.2 after the 4-byte header, up to and including fan_pwm (byte 112..114).
_BODY_V2 = struct.Struct("<" + "HH" + "8H" + "2H" + "HH" + "Q" + "HHHH" + "8H" + "6H" + "6H" + "8H" + "2H" + "I" + "H")
_BODY_V2_SIZE = _HEADER.size + _BODY_V2.size     # 114


@dataclass(slots=True)
class GpuMetrics:
    format_revision: int
    content_revision: int
    structure_size: int
    temperature_gfx: int | None         # °C
    temperature_soc: int | None
    temperature_core: list[int | None]  # per CPU core
    temperature_l3: list[int | None]
    gfx_activity: int | None            # %
    mm_activity: int | None             # % (UVD/VCN)
    system_clock_counter: int           # ns, driver timestamp
    socket_power: int | None            # W
    cpu_power: int | None
    soc_power: int | None
    gfx_power: int | None
    core_power: list[int | None]
    average_gfxclk: int | None          # MHz
    average_socclk: int | None
    average_uclk: int | None
    average_fclk: int | None
    average_vclk: int | None
    average_dclk: int | None
    current_gfxclk: int | None
    current_socclk: int | None
    current_uclk: int | None
    current_fclk: int | None
    current_vclk: int | None
    current_dclk: int | None
    current_coreclk: list[int | None]
    current_l3clk: list[int | None]
    throttle_status: int
    fan_pwm: int | None
    indep_throttle_status: int | None = field(default=None)     # v2.2 and later

    @property
    def version(self) -> str:
        return f"{self.format_revision}.{self.content_revision}"

    @property
    def socket_power_w(self) -> float | None:
        return power_watts(self.socket_power)

    @property
    def gfx_power_w(self) -> float | None:
        return power_watts(self.gfx_power)

    @property
    def soc_power_w(self) -> float | None:
        return power_watts(self.soc_power)

    @property
    def cpu_power_w(self) -> float | None:
        return power_watts(self.cpu_power)

    def gfx_activity_valid(self) -> bool:
        """The unpatched BC-250 table carries the 655% bug (0xFFFF), so only 0..100 % counts as a reading."""
        return self.gfx_activity is not None and 0 <= self.gfx_activity <= 100 * ACTIVITY_SCALE

    @property
    def gfx_activity_percent(self) -> float | None:
        """average_gfx_activity in percent; None when it is not a valid reading."""
        return self.gfx_activity / ACTIVITY_SCALE if self.gfx_activity_valid() else None


def power_watts(raw: int | None) -> float | None:
    """Cyan Skillfish power field (24.8 fixed point) in watts."""
    return None if raw is None else raw / (1 << POWER_FRACTION_BITS)


def _opt(value: int) -> int | None:
    return None if value == UNSUPPORTED else value


def parse_gpu_metrics(raw: bytes) -> GpuMetrics | None:
    """Parse a raw gpu_metrics blob; None when it is not a v2.1+ table or too short."""
    if len(raw) < _BODY_V2_SIZE:
        return None
    size, fmt, content = _HEADER.unpack_from(raw, 0)
    if fmt != 2 or content < 1:
        return None
    v = list(_BODY_V2.unpack_from(raw, _HEADER.size))
    pos = 0

    def take(n: int) -> list[int]:
        nonlocal pos
        chunk = v[pos:pos + n]
        pos += n
        return chunk

    temperature_gfx, temperature_soc = take(2)
    temperature_core = take(8)
    temperature_l3 = take(2)
    gfx_activity, mm_activity = take(2)
    (system_clock_counter,) = take(1)
    socket_power, cpu_power, soc_power, gfx_power = take(4)
    core_power = take(8)
    avg = take(6)
    cur = take(6)
    current_coreclk = take(8)
    current_l3clk = take(2)
    (throttle_status,) = take(1)
    (fan_pwm,) = take(1)

    indep = None
    if content >= 2 and len(raw) >= 128:
        (indep,) = struct.unpack_from("<Q", raw, 120)

    return GpuMetrics(
        format_revision=fmt, content_revision=content, structure_size=size,
        temperature_gfx=_opt(temperature_gfx), temperature_soc=_opt(temperature_soc),
        temperature_core=[_opt(x) for x in temperature_core], temperature_l3=[_opt(x) for x in temperature_l3],
        gfx_activity=_opt(gfx_activity), mm_activity=_opt(mm_activity),
        system_clock_counter=system_clock_counter,
        socket_power=_opt(socket_power), cpu_power=_opt(cpu_power), soc_power=_opt(soc_power),
        gfx_power=_opt(gfx_power), core_power=[_opt(x) for x in core_power],
        average_gfxclk=_opt(avg[0]), average_socclk=_opt(avg[1]), average_uclk=_opt(avg[2]),
        average_fclk=_opt(avg[3]), average_vclk=_opt(avg[4]), average_dclk=_opt(avg[5]),
        current_gfxclk=_opt(cur[0]), current_socclk=_opt(cur[1]), current_uclk=_opt(cur[2]),
        current_fclk=_opt(cur[3]), current_vclk=_opt(cur[4]), current_dclk=_opt(cur[5]),
        current_coreclk=[_opt(x) for x in current_coreclk], current_l3clk=[_opt(x) for x in current_l3clk],
        throttle_status=throttle_status, fan_pwm=_opt(fan_pwm), indep_throttle_status=indep,
    )
