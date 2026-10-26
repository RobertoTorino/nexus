# SPDX-License-Identifier: AGPL-3.0-or-later
"""stream_stats.py: the files kept, the processor's figures from a /proc made in a temp folder, the line per second
and the recorder."""

from __future__ import annotations

import datetime
import io
import threading
from pathlib import Path

from consoles_link import stream_stats


def fake_proc(root: Path, cpu: list[list[int]], threads: dict[int, tuple[str, int, int]], mhz=(3500.0, 1200.0)) -> Path:
    lines = [f"cpu{'' if i == 0 else i - 1} " + " ".join(map(str, ticks)) for i, ticks in enumerate(cpu)]
    root.mkdir(parents=True, exist_ok=True)
    (root / "stat").write_text("\n".join(lines) + "\nintr 1 2 3\n")
    (root / "cpuinfo").write_text("".join(f"processor\t: {i}\nmodel name\t: AMD BC-250\ncpu MHz\t\t: {m}\n\n"
                                          for i, m in enumerate(mhz)))
    for tid, (name, user, system) in threads.items():
        task = root / "42" / "task" / str(tid)
        task.mkdir(parents=True, exist_ok=True)
        fields = ["S"] + ["0"] * 10 + [str(user), str(system)] + ["0"] * 10
        (task / "stat").write_text(f"{tid} ({name}) " + " ".join(fields) + "\n")
    return root


def test_new_files_by_time_and_only_the_newest_kept(tmp_path):
    where = tmp_path / "streams"
    for day in range(1, 25):
        path = stream_stats.new_path(where, datetime.datetime(2026, 10, day, 12, 0, 0))
        path.write_text("x")
    kept = sorted(p.name for p in where.glob("stream-*.txt"))
    assert len(kept) == stream_stats.KEEP
    assert kept[0] == "stream-2026-10-05_12-00-00.txt" and kept[-1] == "stream-2026-10-24_12-00-00.txt"


def test_folder_follows_xdg_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert stream_stats.folder() == tmp_path / "bc250-console-link" / "streams"


def test_processor_figures(tmp_path):
    proc = fake_proc(tmp_path / "a", [[100, 0, 100, 700, 100], [50, 0, 50, 400, 0], [50, 0, 50, 300, 100]],
                     {42: ("python3", 10, 5), 43: ("Thread-2 (_run)", 3, 1)})
    times = stream_stats.cpu_times(proc)
    assert times["cpu"] == (200, 1000) and times["cpu1"] == (100, 500)      # idle and iowait are not busy
    assert stream_stats.thread_times(proc, 42) == {42: ("python3", 15), 43: ("Thread-2 (_run)", 4)}
    assert stream_stats.cpu_mhz(proc) == [3500.0, 1200.0] and stream_stats.cpu_model(proc) == "AMD BC-250"


def test_disk_figures_and_line(tmp_path):
    proc = fake_proc(tmp_path / "a", [[100, 0, 100, 700, 100]], {})
    (proc / "vmstat").write_text("nr_free_pages 5\npswpin 10\npswpout 4\n")
    (proc / "42").mkdir()
    (proc / "42" / "stat").write_text("42 (python3 (x)) S " + " ".join(["0"] * 8 + ["7"] + ["0"] * 30) + "\n")
    figures = stream_stats.disk_figures(proc, 42)
    assert figures == {"iowait": 100, "ticks": 1000, "pswpin": 10, "pswpout": 4, "majflt": 7}
    later = {"iowait": 150, "ticks": 1500, "pswpin": 30, "pswpout": 4, "majflt": 9}
    assert stream_stats.disk_line(figures, later) == "disk wait 10%, swapped 20 in 0 out, app read from disk 2 times"


def test_processor_line():
    before = {"cpu": (200, 1000), "cpu0": (100, 500), "cpu1": (100, 500)}
    after = {"cpu": (500, 1400), "cpu0": (290, 700), "cpu1": (210, 700)}
    threads_before = {42: ("python3", 15), 43: ("Thread-2", 4), 44: ("idle", 0)}
    threads_after = {42: ("python3", 45), 43: ("Thread-2", 64), 44: ("idle", 1)}
    text = stream_stats.cpu_line(before, after, threads_before, threads_after, {42: "MainThread"}, 1.0,
                                 [3500.0, 1200.0], 100)
    assert text == ("cpu 75% busiest core 95% app 91% (Thread-2 60%, MainThread 30%) clock 1200-3500 MHz")


def test_the_line_per_second():
    stream_before = {"frames": 100, "frame_bytes": 1_000_000, "decoded": 100, "decode_seconds": 0.5,
                     "frames_lost": 0, "fec_frames": 1, "audio_frames": 1000, "audio_lost": 0}
    stream_now = {"frames": 160, "frame_bytes": 2_250_000, "decoded": 159, "decode_seconds": 0.8,
                  "decode_max": 0.0121, "frame_gap_max": 0.034, "frames_lost": 1, "fec_frames": 3,
                  "audio_frames": 1100, "audio_lost": 2}
    window_before = {"shown": 10, "replaced": 1, "sound_silence_ms": 0.0, "sound_dropped_ms": 0.0}
    window = {"shown": 68, "replaced": 3, "age_max": 0.009, "age_sum": 0.29, "age_count": 58, "late_max": 0.041,
              "sound_buffered_ms": 12.0, "sound_silence_ms": 30.0, "sound_dropped_ms": 0.0, "muted": False}
    reader = {"polls": 450, "gap_max": 0.007}
    text = stream_stats.line(stream_now, stream_before, window, window_before, reader, {"polls": 200}, 1.0)
    assert text == ("in 60 frames 10.0 Mbit/s, longest gap 34 ms, lost 1, FEC 2 | decode 59 avg 5.0 max 12.1 ms | "
                    "sound in 100 frames, lost 2 | shown 58, skipped 2, age avg 5 max 9 ms | window late max 41 ms | "
                    "sound buffer 12 ms, gaps 30 ms, dropped 0 ms | controller 250 reads, longest gap 7 ms")
    assert stream_stats.line({}, {}, {}, {}, {}, {}, 1.0) == ""
    recovering = dict(stream_now, fec_failed=1, idr_requests=1, frames_skipped=4, missing_reference=0)
    assert "| recovery: FEC failed 1, key frames asked 1, skipped 4, no reference 0 |" in \
        stream_stats.line(recovering, stream_before, {}, {}, {}, {}, 1.0)


def test_recorder_writes_a_header_and_a_line_per_second(tmp_path):
    proc = fake_proc(tmp_path / "proc", [[1, 0, 1, 8, 0]], {42: ("python3", 1, 1)})
    out = io.StringIO()
    out.close = lambda: None
    counts = {"frames": 0}
    calls = threading.Event()

    def stream():
        counts["frames"] += 60
        if counts["frames"] > 120:
            calls.set()
        return {"frames": counts["frames"], "decode_max": 0.004}

    def broken():
        raise RuntimeError("the window is gone")

    recorder = stream_stats.Recorder(out, ["Console Link 1.0.0", "Console: PS4"], stream, broken, None,
                                     interval=0.01, proc=proc).start()
    assert calls.wait(2)
    recorder.stop()
    lines = out.getvalue().splitlines()
    assert lines[:2] == ["# Console Link 1.0.0", "# Console: PS4"]
    body = lines[2:]
    assert len(body) == recorder.lines >= 2
    assert all(" s | in 60 frames" in line and "decode 0 avg 0.0 max 4.0 ms" in line and "| cpu " in line
               and "| disk wait " in line for line in body[:2])
    assert "shown" not in body[0]                                       # a failing source leaves its part out
