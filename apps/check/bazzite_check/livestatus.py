# SPDX-License-Identifier: GPL-3.0-or-later
"""Status-bar widget with live CPU/GPU load, the running game and the display refresh rate."""

from __future__ import annotations

import html

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

from . import plain_tooltip
from .monitor import LiveSample, Sampler

BASE_INTERVAL_MS = 2000
MAX_INTERVAL_MS = 8000
SLOW_SAMPLE_MS = 30.0


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}%"


def _rate(bits: float | None) -> str:
    if bits is None:
        return "—"
    if bits >= 1e9:
        return f"{bits / 1e9:.2f} Gbit/s"
    if bits >= 1e6:
        return f"{bits / 1e6:.1f} Mbit/s"
    return f"{bits / 1e3:.0f} kbit/s"


def _color(v: float | None) -> str:
    if v is None:
        return "#9aa0a6"
    return "#ef6c00" if v >= 90 else "#2e7d32" if v < 60 else "#1565c0"


class LiveStatus(QWidget):
    def __init__(self, sampler: Sampler | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.sampler = sampler or Sampler()
        self._visible = True
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 4, 0)
        row.setSpacing(12)
        self.game = QLabel()
        self.cpu = QLabel()
        self.gpu = QLabel()
        self.hz = QLabel()
        self.net = QLabel()
        self.enabled = QCheckBox("Live")
        self.enabled.setChecked(self.sampler.available)
        self.enabled.setEnabled(self.sampler.available)
        self.enabled.setToolTip("Live CPU/GPU load, network speed, running game and refresh rate (Linux only). "
                                "Paused while the window is minimized.")
        self.enabled.toggled.connect(self._apply_state)
        for w in (self.game, self.cpu, self.gpu, self.net, self.hz, self.enabled):
            row.addWidget(w)

        self.timer = QTimer(self)
        self.timer.setInterval(BASE_INTERVAL_MS)
        self.timer.timeout.connect(self.tick)
        self._show(LiveSample())
        self._apply_state()

    def set_window_visible(self, visible: bool) -> None:
        self._visible = visible
        self._apply_state()

    def _apply_state(self) -> None:
        run = self._visible and self.enabled.isChecked() and self.sampler.available
        for w in (self.cpu, self.gpu, self.net, self.game, self.hz):
            w.setVisible(self.enabled.isChecked())
        if run and not self.timer.isActive():
            self.tick()                 # first sample is a baseline; values appear on the next one
            self.timer.start()
        elif not run:
            self.timer.stop()

    def tick(self) -> None:
        s = self.sampler.sample()
        # Back off if sampling ever gets expensive (e.g. thousands of processes), recover when it is cheap.
        interval = self.timer.interval()
        if s.cost_ms > SLOW_SAMPLE_MS:
            self.timer.setInterval(min(MAX_INTERVAL_MS, interval * 2))
        elif s.cost_ms < SLOW_SAMPLE_MS / 3 and interval > BASE_INTERVAL_MS:
            self.timer.setInterval(BASE_INTERVAL_MS)
        self._show(s)

    def _show(self, s: LiveSample) -> None:
        self.cpu.setText(f"CPU <b style='color:{_color(s.cpu)}'>{_pct(s.cpu)}</b>")
        self.gpu.setText(f"GPU <b style='color:{_color(s.gpu)}'>{_pct(s.gpu)}</b>")
        src = {"sensor": "kernel load sensor (gpu_busy_percent)",
               "gpu_metrics": "gpu_metrics patched by the governor's fix-metrics",
               "fdinfo": "GPU engine time of this user's processes (/proc/*/fdinfo)"}.get(s.gpu_source, "not available")
        cost = (f"\nSampling every {self.timer.interval() / 1000:.0f} s took {s.cost_ms:.1f} ms"
                + (f" (process scan {s.scan_ms:.1f} ms)" if s.scan_ms else ""))
        self.cpu.setToolTip("Whole-system CPU load from /proc/stat" + cost)
        self.gpu.setToolTip(f"GPU load from the {src}" + cost)

        if s.net_ifaces:
            self.net.setText(f"↓ {_rate(s.net_down)}  ↑ {_rate(s.net_up)}")
            self.net.setToolTip(plain_tooltip(
                f"Network traffic right now over {', '.join(s.net_ifaces)} (download ↓, upload ↑), "
                "from the byte counters in /proc/net/dev."))
        else:
            self.net.setText("")
            self.net.setToolTip("")

        screen = self.window().screen() if self.window() else None
        hz = screen.refreshRate() if screen else 0
        self.hz.setText(f"{hz:.0f} Hz" if hz else "")
        self.hz.setToolTip(f"Refresh rate of the display this window is on ({screen.name() if screen else '?'})")

        g = s.game
        if g is None:
            self.game.setText("")
            self.game.setToolTip("")
            return
        parts = [f"CPU {_pct(g.cpu)}", f"GPU {_pct(g.gpu)}"]
        if g.fps is not None:
            parts.append(f"<b>{g.fps:.0f} FPS</b>")
        self.game.setText(f"🎮 <b>{html.escape(g.title)}</b>: " + " · ".join(parts))
        self.game.setToolTip(plain_tooltip(
            f"{g.title}" + (f" (Steam app {g.appid})" if g.appid else "")
            + "\nCPU: share of the whole CPU used by the game's processes."
            + "\nGPU: GPU engine time of the game's processes."
            + ("\nFPS: from MangoHud's live CSV log." if g.fps is not None
               else "\nFPS: enable MangoHud logging to see it here (see Help).")))
