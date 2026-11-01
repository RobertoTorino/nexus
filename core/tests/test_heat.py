# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode's heat warning (heat.py): the rule (above the limit for half a minute, again at most every five
minutes), the banner and the rumble it gives, a sensor or a banner that fails, and the note when the game ends."""

from __future__ import annotations

from pathlib import Path

from bc250_core import heat, play, portable
from bc250_core.heat import Guard, Watch


def fed(watch: Watch, reads: dict[float, tuple[int | None, int | None]]) -> list[float]:
    """When *watch* warns, fed *reads* ({time: (cpu, gpu)}) in order."""
    return [now for now, (cpu, gpu) in sorted(reads.items()) if watch.feed(now, cpu, gpu)]


def every(start: float, end: float, cpu: int | None, gpu: int | None, step: float = 2.0) -> dict:
    reads, now = {}, start
    while now <= end:
        reads[now] = (cpu, gpu)
        now += step
    return reads


def test_above_the_limit_for_half_a_minute_warns_once_then_every_five_minutes():
    """The owner's limit (02-11-2026): above 90° for 30 s in a row, then at most every 5 minutes while it runs hot."""
    watch = Watch()
    assert (heat.LIMIT, heat.SUSTAIN, heat.REPEAT) == (90, 30.0, 300.0)
    assert fed(watch, every(0, 700, 91, 80)) == [30, 330, 630]
    assert watch.warnings == 3 and watch.above == 700 and (watch.cpu, watch.gpu) == (91, 80)


def test_a_short_spike_or_the_limit_itself_does_not_warn():
    watch = Watch()
    reads = {**every(0, 20, 95, 70), **every(22, 40, 75, 70), **every(42, 70, 95, 70), **every(72, 200, 90, 90)}
    assert fed(watch, reads) == []                     # 20 s, then 28 s above, then 90° on the dot
    assert watch.above == 48 and watch.cpu == 95


def test_the_gpu_counts_as_the_cpu_does_and_no_read_is_no_warning():
    assert fed(Watch(), every(0, 40, None, 93)) == [30]
    watch = Watch()
    assert fed(watch, every(0, 60, None, None)) == [] and watch.note() is None


def test_cooling_down_starts_the_half_minute_again_but_not_the_five_minutes():
    watch = Watch()
    reads = {**every(0, 40, 92, 80), **every(42, 100, 70, 60), **every(102, 400, 92, 80)}
    assert fed(watch, reads) == [30, 330]              # hot again from 102: 30 s held, but warned at 30


def test_the_note_when_the_game_ends():
    watch = Watch()
    fed(watch, every(0, 130, 94, 89))
    assert watch.note() == "Play: the hottest read CPU 94° GPU 89°; above 90° for 2 min 10 s in all, 1 warning."
    cool = Watch()
    fed(cool, every(0, 60, 72, 68))
    assert cool.note() == "Play: the hottest read CPU 72° GPU 68°, never above 90° for long."
    assert [heat.duration(s) for s in (45, 120, 130, 3600, 3900)] == ["45 s", "2 min", "2 min 10 s", "1 h",
                                                                         "1 h 5 min"]
    assert heat.warning(93, None) == ("Running hot: CPU 93°",
                                      "Above 90° for 30 s. A pause, or a lower operating mode, lets it cool down.")


class Sensors:
    def __init__(self, reads):
        self.reads, self.closed = reads, False        # a function of the time

    def read(self):
        return self.reads()

    def close(self):
        self.closed = True


class FakeBanner:
    def __init__(self):
        self.shown, self.ticks, self.hidden = [], 0, False

    def show(self, now, title, line):
        self.shown.append((now, title, line))

    def tick(self, now):
        self.ticks += 1

    def hide(self):
        self.hidden = True


class Motors:
    def __init__(self):
        self.pulses = []

    def rumble(self, low, high, ms):
        self.pulses.append((low, high, ms))


def guarded(reads, until: float, banner=None):
    """A Guard ticked every 50 ms up to *until*, as play.run ticks it."""
    lines, motors, clock = [], Motors(), {"now": 0.0}
    sensors = Sensors(lambda: reads(clock["now"]))
    made = banner or FakeBanner()
    guard = Guard(lines.append, sensors=lambda: sensors, banner=lambda: made)
    times, now = [], 0.0
    while now <= until:
        clock["now"] = now
        before = len(motors.pulses)
        guard.tick(now, motors)
        times += [round(now, 2)] * (len(motors.pulses) - before)
        now += play.POLL
    guard.close()
    return guard, lines, made, motors, times, sensors


def test_the_guard_warns_on_the_screen_and_the_controller():
    """A banner over the game and three short rumbles (owner, 02-11-2026); the chip read every 2 s."""
    guard, lines, banner, motors, times, sensors = guarded(lambda now: (96, 88), 40.5)
    assert len(banner.shown) == 1 and abs(banner.shown[0][0] - 30) <= play.POLL
    assert banner.shown[0][1:] == heat.warning(96, 88)
    assert motors.pulses == [(heat.STRENGTH, heat.STRENGTH, heat.PULSE_MS)] * 3
    assert all(abs(t - times[0] - after) <= play.POLL for t, after in zip(times, heat.PULSES))
    assert lines == ["Play: running hot, CPU 96° GPU 88°, above 90° for 30 s; warned on the screen and the "
                     "controller."]
    assert banner.ticks > 0 and banner.hidden and sensors.closed
    assert guard.note().endswith("above 90° for 40 s in all, 1 warning.")


def test_a_sensor_or_a_banner_that_fails_never_stops_the_game():
    def broken():
        raise OSError("atiadlxx.dll gone")
    guard, lines, *_ = guarded(lambda now: broken(), 10)
    assert lines == ["Play: the chip's temperatures cannot be read (atiadlxx.dll gone); no heat warning."]

    class NoScreen(FakeBanner):
        def show(self, now, title, line):
            raise RuntimeError("no screen")
    guard, lines, _, motors, *_ = guarded(lambda now: (97, 90), 40, banner=NoScreen())
    assert lines[-1] == "Play: the heat banner cannot show (no screen); the controller still rumbles."
    assert len(motors.pulses) == 3

    unread = Guard(sensors=lambda: broken())
    assert unread.sensors is None
    unread.tick(0.0, None)
    assert unread.note() is None


def test_the_banner_shows_on_every_screen_without_the_focus(qapp):
    """On top of the game, taking neither the focus nor a press, at the top of each screen; down after its time."""
    from PyQt6.QtCore import Qt
    portable.pin_scale((1280, 720))
    banner = heat.Banner(seconds=8.0)
    banner.show(100.0, *heat.warning(93, 88))
    assert len(banner.windows) == len(qapp.screens()) >= 1
    window = banner.windows[0]
    flags = window.windowFlags()
    for flag in (Qt.WindowType.WindowStaysOnTopHint, Qt.WindowType.WindowDoesNotAcceptFocus,
                 Qt.WindowType.WindowTransparentForInput, Qt.WindowType.FramelessWindowHint):
        assert flags & flag
    assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating) and window.isVisible()
    area = window.screen().availableGeometry()
    assert window.y() == area.y() + portable.px(24) and window.width() <= area.width()
    banner.tick(107.9)
    assert banner.windows
    banner.tick(108.0)
    assert banner.windows == [] and not window.isVisible()


def test_play_run_watches_the_chip_and_notes_it_when_the_game_ends():
    class Process:
        pid, returncode = 4242, None

        def poll(self):
            return self.returncode

    class NoPad:
        def events(self):
            return []

        def close(self):
            pass

    process, lines, clock = Process(), [], {"now": 0.0}

    def sleep(seconds):
        clock["now"] += seconds
        if clock["now"] >= 45:
            process.returncode = 0
    banner = FakeBanner()
    play.run(["emu.exe"], Path("."), log=lines.append, start=lambda c, d: process, pad=NoPad,
             clock=lambda: clock["now"], sleep=sleep,
             heat=lambda log: Guard(log, sensors=lambda: Sensors(lambda: (93, 85)), banner=lambda: banner))
    assert len(banner.shown) == 1 and banner.hidden
    assert lines[-2] == "Play: the emulator ended (exit code 0)."
    assert lines[-1].startswith("Play: the hottest read CPU 93° GPU 85°; above 90° for 4")
