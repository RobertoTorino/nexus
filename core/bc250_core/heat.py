# SPDX-License-Identifier: GPL-3.0-or-later
"""The play mode's heat warning (the Windows Portable Suite's game managers; owner, 02-11-2026: the Ally got hot on
the outside during a game in Xenia, with a second screen attached): while the game runs, the CPU's and the GPU's
temperature are read every EVERY seconds (core's chip.py, as Windows Portable Test's header reads them). When the
hotter of the two stays above LIMIT for SUSTAIN seconds, a banner shows at the top of every screen for BANNER
seconds and the controller rumbles PULSES times; again at most every REPEAT seconds while it runs hot. The warning
never touches the game: the banner takes neither the focus nor a press, and the chip slows itself down at its own
limit (about 100 °C on the Ally's). When the game ends, the log says how hot it got and for how long (note()).

Windows has no sensor for how hot the case is on the outside; the chip's temperature is the closest there is.
Watch is the rule, without a clock or a sensor of its own; Guard reads, warns and keeps the banner up from the play
mode's loop (play.run), which has no Qt event loop of its own: Banner's tick() lets Qt draw. Qt is imported only
when the first banner shows."""

from __future__ import annotations

import sys
from collections.abc import Callable

LIMIT = 90                      # °C the hotter of the CPU and the GPU stays above before the warning
SUSTAIN = 30.0                  # s above LIMIT, read after read, before the first warning
REPEAT = 300.0                  # s at least between two warnings
EVERY = 2.0                     # s between two reads of the chip
BANNER = 8.0                    # s the banner shows
PULSES = (0.0, 0.35, 0.7)       # s after the warning: a short rumble each
PULSE_MS = 200                  # ms a rumble lasts
STRENGTH = 0.8                  # of 1: both of the controller's motors


def duration(seconds: float) -> str:
    """"45 s", "2 min 10 s", "1 h 5 min"."""
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s" if seconds else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def temperatures(cpu: int | None, gpu: int | None) -> str:
    """"CPU 93° GPU 88°", as Windows Portable Test's header writes them; "" with neither."""
    return " ".join(f"{name} {value}°" for name, value in (("CPU", cpu), ("GPU", gpu)) if value is not None)


def warning(cpu: int | None, gpu: int | None, limit: int = LIMIT, sustain: float = SUSTAIN) -> tuple[str, str]:
    """The banner's two lines."""
    return (f"Running hot: {temperatures(cpu, gpu)}",
            f"Above {limit}° for {duration(sustain)}. A pause, or a lower operating mode, lets it cool down.")


class Watch:
    """The rule: fed a read at a time, it says when to warn, and keeps the hottest reads and the time above the
    limit for note()."""

    def __init__(self, limit: int = LIMIT, sustain: float = SUSTAIN, repeat: float = REPEAT):
        self.limit, self.sustain, self.repeat = limit, sustain, repeat
        self.cpu: int | None = None                 # the hottest reads
        self.gpu: int | None = None
        self.above = 0.0                            # s above the limit in all, between two hot reads
        self.warnings = 0
        self._since: float | None = None            # the first of the hot reads in a row
        self._last: float | None = None             # the previous hot read
        self._warned: float | None = None

    def feed(self, now: float, cpu: int | None, gpu: int | None) -> bool:
        """A read at *now*; True when it is time to warn."""
        if cpu is not None:
            self.cpu = cpu if self.cpu is None else max(self.cpu, cpu)
        if gpu is not None:
            self.gpu = gpu if self.gpu is None else max(self.gpu, gpu)
        reads = [value for value in (cpu, gpu) if value is not None]
        if not reads or max(reads) <= self.limit:
            self._since = self._last = None
            return False
        if self._last is not None:
            self.above += now - self._last
        self._last = now
        self._since = now if self._since is None else self._since
        if now - self._since >= self.sustain and (self._warned is None or now - self._warned >= self.repeat):
            self._warned = now
            self.warnings += 1
            return True
        return False

    def note(self) -> str | None:
        """For the log when the game ends: how hot it got and for how long; None when nothing could be read."""
        hottest = temperatures(self.cpu, self.gpu)
        if not hottest:
            return None
        if not self.above:
            return f"Play: the hottest read {hottest}, never above {self.limit}° for long."
        warned = f"{self.warnings} warning{'s' if self.warnings != 1 else ''}"
        return f"Play: the hottest read {hottest}; above {self.limit}° for {duration(self.above)} in all, {warned}."


class Banner:
    """The warning at the top of every screen: in the suite's design, on top of the game, without taking the focus
    or a press (Windows' notifications are held back while a game runs full screen). show() puts it up for BANNER
    seconds; tick() lets Qt draw it and takes it down when its time is over."""

    def __init__(self, seconds: float = BANNER):
        from PyQt6.QtWidgets import QApplication

        from .theme import load_fonts
        self.app = QApplication.instance() or QApplication([sys.argv[0]])
        load_fonts()
        self.seconds = seconds
        self.windows: list = []
        self.until: float | None = None

    def show(self, now: float, title: str, line: str) -> None:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget

        from . import portable
        self.hide()
        for screen in self.app.screens():
            area = screen.availableGeometry()
            portable.scale((area.width(), area.height()))
            window = QWidget(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                             | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                             | Qt.WindowType.WindowTransparentForInput)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setScreen(screen)
            outer = QVBoxLayout(window)
            outer.setContentsMargins(0, 0, 0, 0)
            panel = QFrame()
            panel.setObjectName("heat")
            panel.setStyleSheet(f"#heat {{ background: {portable.SURFACE}; border: {portable.px(2)}px solid "
                                f"{portable.AMBER}; border-radius: {portable.px(portable.RADIUS)}px; }}")
            column = QVBoxLayout(panel)
            column.setContentsMargins(portable.px(20), portable.px(12), portable.px(20), portable.px(12))
            column.setSpacing(portable.px(2))
            column.addWidget(portable.text_label(title, 16, QFont.Weight.ExtraBold, color=portable.AMBER))
            column.addWidget(portable.text_label(line, portable.BODY, color=portable.TEXT))
            outer.addWidget(panel)
            window.adjustSize()
            window.move(area.x() + (area.width() - window.width()) // 2, area.y() + portable.px(24))
            window.show()
            window.raise_()
            self.windows.append(window)
        self.until = now + self.seconds
        self.app.processEvents()

    def tick(self, now: float) -> None:
        if self.until is not None and now >= self.until:
            self.hide()
        if self.windows:
            self.app.processEvents()

    def hide(self) -> None:
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.windows.clear()
        self.until = None
        self.app.processEvents()


class Guard:
    """The play mode's watch over the chip: tick() from its loop, with the controller reader (or None) for the
    rumble; close() when the game ends, then note(). A sensor or a banner that fails never stops the game: it is
    logged once, and the watch goes on without it."""

    def __init__(self, log: Callable[[str], None] = lambda line: None, sensors: Callable[[], object] | None = None,
                 banner: Callable[[], object] = Banner, watch: Watch | None = None, every: float = EVERY):
        self.log, self.every = log, every
        self.watch = watch or Watch()
        self._banner_factory = banner
        self.banner = None
        self.sensors = None
        try:
            if sensors is None:
                from .chip import Temperatures
                sensors = Temperatures
            self.sensors = sensors()
        except Exception as error:  # noqa: BLE001  (no reader: the game runs, without the warning)
            log(f"Play: the chip's temperatures cannot be read ({error}); no heat warning.")
        self._next: float | None = None
        self._pulses: list[float] = []

    def tick(self, now: float, pad: object | None = None) -> None:
        if self.sensors is not None and (self._next is None or now >= self._next):
            self._next = now + self.every if self._next is None else max(self._next + self.every, now)
            try:
                cpu, gpu = self.sensors.read()
            except Exception as error:  # noqa: BLE001
                self.log(f"Play: the chip's temperatures cannot be read ({error}); no heat warning.")
                self.sensors = None
            else:
                if self.watch.feed(now, cpu, gpu):
                    self._warn(now, cpu, gpu)
        while self._pulses and now >= self._pulses[0]:
            self._pulses.pop(0)
            rumble = getattr(pad, "rumble", None)
            if rumble is not None:
                rumble(STRENGTH, STRENGTH, PULSE_MS)
        if self.banner is not None:
            try:
                self.banner.tick(now)
            except Exception as error:  # noqa: BLE001
                self._banner_failed(error)

    def _warn(self, now: float, cpu: int | None, gpu: int | None) -> None:
        watch = self.watch
        self.log(f"Play: running hot, {temperatures(cpu, gpu)}, above {watch.limit}° for "
                 f"{duration(watch.sustain)}; warned on the screen and the controller.")
        self._pulses = [now + after for after in PULSES]
        if self._banner_factory is None:
            return
        try:
            if self.banner is None:
                self.banner = self._banner_factory()
            self.banner.show(now, *warning(cpu, gpu, watch.limit, watch.sustain))
        except Exception as error:  # noqa: BLE001
            self._banner_failed(error)

    def _banner_failed(self, error: Exception) -> None:
        self.log(f"Play: the heat banner cannot show ({error}); the controller still rumbles.")
        self.banner = self._banner_factory = None

    def close(self) -> None:
        for done in (self.banner and self.banner.hide, self.sensors and self.sensors.close):
            try:
                if done:
                    done()
            except Exception:  # noqa: BLE001  (closing never fails the play mode)
                pass

    def note(self) -> str | None:
        return self.watch.note()
