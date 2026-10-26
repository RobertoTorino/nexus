# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from gpu_governor.safepoints_page import SafePointsPage, _interpolate


def test_parse_and_render(backend):
    points = backend.safe_points()
    assert [(p.frequency, p.voltage) for p in points] == [(1000, 700), (1500, 800), (2000, 900)]
    text = backend.render_safe_points(backend.read_config_text(), [(900, 700), (1800, 850)])
    assert text.count("[[safe-points]]") == 2
    backend.config_path.write_text(text, encoding="utf-8")
    assert [(p.frequency, p.voltage) for p in backend.safe_points()] == [(900, 700), (1800, 850)]
    assert backend.read_config().freq_max == 2000     # the rest of the file survives


def test_interpolate():
    curve = [(1000, 700), (2000, 900)]
    assert _interpolate(curve, 1500) == 800
    assert _interpolate(curve, 1000) == 700
    assert _interpolate([], 1500) is None


def test_add_to_table_sorted_and_replacing(qapp, backend):
    page = SafePointsPage(str(backend.config_path), backend.default_safe_points)
    page.load(backend.safe_points())
    page.test_freq.setValue(1750)
    page.test_volt.setValue(850)
    page._add_test_point()
    assert page.points() == [(1000, 700), (1500, 800), (1750, 850), (2000, 900)]
    page.test_volt.setValue(860)
    page._add_test_point()
    assert page.points()[2] == (1750, 860) and page.is_dirty()
