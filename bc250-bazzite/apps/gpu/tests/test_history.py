# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
from datetime import datetime, timedelta

from gpu_governor.history import COLUMNS, History, Sample, default_csv_name


def test_ring_buffer_and_last(snapshot):
    history = History(5)
    start = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(8):
        history.add(Sample.from_snapshot(snapshot(clock=1000 + i), start + timedelta(seconds=2 * i)))
    assert len(history) == 5
    assert [s.clock for s in history.last(3)] == [1005, 1006, 1007]
    assert [s.clock for s in history.last(99)] == [1003, 1004, 1005, 1006, 1007]
    assert history.span() == (start + timedelta(seconds=6), start + timedelta(seconds=14))


def test_csv_export(tmp_path, snapshot):
    history = History(10)
    when = datetime(2026, 1, 1, 12, 0, 0)
    history.add(Sample.from_snapshot(snapshot(load=None, enabled=True), when))
    history.add(Sample.from_snapshot(snapshot(bus=False, temp=61.26), when + timedelta(seconds=2)))
    path = tmp_path / "out.csv"
    assert history.write_csv(path) == 2
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert list(rows[0]) == list(COLUMNS)
    assert rows[0]["load_percent"] == "" and rows[0]["performance_mode"] == "on" and rows[0]["range_max_mhz"] == "2000"
    assert rows[1]["performance_mode"] == "" and rows[1]["range_min_mhz"] == "" and rows[1]["temp_c"] == "61.3"
    assert rows[0]["time"] == "2026-01-01T12:00:00"


def test_default_csv_name():
    assert default_csv_name(datetime(2026, 10, 7, 5, 4, 3)) == "bc250-telemetry-20261007-050403.csv"


def test_overview_window_right_aligned(qapp, snapshot):
    from gpu_governor.pages import POLL_MS, OverviewPage
    page = OverviewPage()
    assert not page.export_button.isEnabled()
    for i in range(100):
        page.update(snapshot(load=None if i % 7 == 0 else 50.0, clock=1500 + i))
    assert page.export_button.isEnabled()
    points = page.series["clock"].points()
    window = 120 * 1000 // POLL_MS
    assert len(points) == window and points[-1].x() == window - 1 and points[-1].y() == 1599
    page.window.setCurrentIndex(1)              # 10 min: 300 slots, 100 samples at the right edge
    points = page.series["clock"].points()
    assert len(points) == 100 and points[0].x() == 200 and page.axis_x.max() == 299
    assert len(page.series["load"].points()) == 100 - len(range(0, 100, 7))


def test_csv_round_trip_and_summary(tmp_path, snapshot):
    from gpu_governor.history import read_csv, summarise
    history = History(10)
    when = datetime(2026, 1, 1, 12, 0, 0)
    history.add(Sample.from_snapshot(snapshot(load=40.0, clock=1200, temp=60.0, enabled=True), when))
    history.add(Sample.from_snapshot(snapshot(load=None, clock=1800, temp=70.0, bus=False), when + timedelta(seconds=2)))
    history.add(Sample.from_snapshot(snapshot(load=80.0, clock=None, temp=None), when + timedelta(seconds=4)))
    path = tmp_path / "out.csv"
    history.write_csv(path)
    back = read_csv(path)
    assert [s.clock for s in back] == [1200, 1800, None]
    assert [s.perf_enabled for s in back] == [True, None, False]
    assert back[0].time == when and back[2].load == 80.0
    summary = summarise(back)
    assert summary.seconds == 4 and summary.load_avg == 60.0 and summary.clock_max == 1800
    assert summary.temp_avg == 65.0 and summary.temp_max == 70.0
    assert summary.text().startswith("load 60 %, clock 1500 MHz (max 1800), 65 °C (max 70)")


def test_read_csv_rejects_foreign_files_and_skips_bad_rows(tmp_path):
    import pytest
    from gpu_governor.history import read_csv
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_csv(bad)
    partial = tmp_path / "partial.csv"
    partial.write_text("time,load_percent,clock_mhz,temp_c\nnot-a-time,1,2,3\n2026-01-01T12:00:00,,x,55\n",
                       encoding="utf-8")
    samples = read_csv(partial)
    assert len(samples) == 1 and samples[0].load is None and samples[0].clock is None and samples[0].temp == 55.0
    assert samples[0].power is None and samples[0].perf_enabled is None


def test_overview_reference_overlay(qapp, snapshot):
    from gpu_governor.pages import POLL_MS, OverviewPage
    page = OverviewPage()
    for i in range(50):
        page.update(snapshot(load=50.0, clock=1500))
    assert not page.clear_compare_button.isEnabled() and not page.ref_series["clock"].isVisible()
    when = datetime(2026, 1, 1, 12, 0, 0)
    ref = [Sample(when + timedelta(seconds=2 * i), 30.0, 1000 + i, 55.0, 60.0, True, None, None) for i in range(20)]
    page.set_reference(ref, "old.csv")
    window = 120 * 1000 // POLL_MS
    points = page.ref_series["clock"].points()
    assert page.ref_series["clock"].isVisible() and len(points) == 20
    assert points[-1].x() == window - 1 and points[-1].y() == 1019       # right-aligned like the live lines
    note = page.chart_note.text()
    assert "Reference old.csv (38 s): load 30 %, clock 1010 MHz (max 1019), 55 °C (max 55), 60 W." in note
    assert "Live window" in note and note.startswith("Current:")
    page.update(snapshot(load=50.0, clock=1500))                        # a new poll keeps the comparison
    assert "Reference old.csv" in page.chart_note.text()
    page.clear_compare_button.click()
    assert not page.reference and not page.ref_series["clock"].isVisible()
    assert "Reference" not in page.chart_note.text() and page.chart_note.text().startswith("Current:")
