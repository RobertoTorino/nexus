# SPDX-License-Identifier: GPL-3.0-or-later
"""average_gfx_activity of the governor's patched gpu_metrics table is in hundredths of a percent."""

from __future__ import annotations

import pytest

from gpu_governor.backends.gpu_metrics import USAGE_OFFSET, parse_gpu_metrics


def table(gfx_activity: int) -> bytes:
    """A 128-byte gpu_metrics v2.2 table with *gfx_activity* at byte 28."""
    raw = bytearray(128)
    raw[0:4] = (128).to_bytes(2, "little") + bytes([2, 2])
    raw[USAGE_OFFSET:USAGE_OFFSET + 2] = gfx_activity.to_bytes(2, "little")
    return bytes(raw)


@pytest.mark.parametrize("raw, percent", [(0, 0.0), (156, 1.56), (7656, 76.56), (10000, 100.0)])
def test_activity_in_hundredths_of_a_percent(raw, percent):
    m = parse_gpu_metrics(table(raw))
    assert m.gfx_activity_valid() and m.gfx_activity_percent == percent


@pytest.mark.parametrize("raw", [10001, 0xFFFF - 1])
def test_out_of_range_is_invalid(raw):
    m = parse_gpu_metrics(table(raw))
    assert not m.gfx_activity_valid() and m.gfx_activity_percent is None


def test_unpatched_table_is_unsupported():
    m = parse_gpu_metrics(table(0xFFFF))             # the "655%" of MangoHud
    assert m.gfx_activity is None and m.gfx_activity_percent is None and not m.gfx_activity_valid()
