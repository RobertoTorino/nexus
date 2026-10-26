# SPDX-License-Identifier: GPL-3.0-or-later
"""Alerts derived from the polled snapshot: a temperature the user picks, the governor's own throttling
threshold, and the governor service stopping on its own. Edge-triggered with hysteresis and a cooldown, so one
hot session gives one message, not one per poll."""

from __future__ import annotations

from dataclasses import dataclass, field


from . import fmt
from .pages import Snapshot

HYSTERESIS_C = 5.0          # re-arm a temperature alert this far below its threshold
COOLDOWN_S = 300.0          # at most one message per alert kind in this many seconds
MISSED_POLLS = 2            # the service must be seen running this often before "stopped" counts


@dataclass
class AlertSettings:
    temp_enabled: bool = True
    temp_c: int = 80
    throttle_enabled: bool = True
    service_enabled: bool = True


@dataclass
class AlertMonitor:
    settings: AlertSettings = field(default_factory=AlertSettings)
    _last_sent: dict[str, float] = field(default_factory=dict)
    _armed: dict[str, bool] = field(default_factory=lambda: {"temp": True, "throttle": True})
    _seen_running: int = 0

    def check(self, snap: Snapshot, now: float) -> list[tuple[str, str]]:
        """(title, text) messages to show for this poll."""
        out: list[tuple[str, str]] = []
        temp = snap.telemetry.temp_c
        if temp is not None:
            if self.settings.temp_enabled:
                out += self._temperature("temp", temp, float(self.settings.temp_c), now,
                                         "GPU temperature",
                                         fmt(("The GPU is at %1 °C (alert set at "
                                              "%2 °C)."),
                                             f"{temp:.0f}", str(self.settings.temp_c)))
            limit = snap.perf.temp_throttling if snap.perf.available else snap.saved.temp_throttling
            if self.settings.throttle_enabled and limit:
                out += self._temperature("throttle", temp, float(limit), now,
                                         "Governor throttling",
                                         fmt(("The GPU is at %1 °C, at or above the "
                                              "governor's throttling temperature of "
                                              "%2 °C; the maximum clock is being "
                                              "lowered."),
                                             f"{temp:.0f}", str(limit)))
        if snap.service.active:
            self._seen_running += 1
        else:
            if self.settings.service_enabled and self._seen_running >= MISSED_POLLS and self._due("service", now):
                state = ("failed"
                        if snap.service.sub_state == "failed"
                        else "stopped")
                out.append((fmt("Governor %1", state),
                           fmt(("The governor service has %1; the GPU runs at the "
                                "driver's default clocks. See the Service page."),
                               state)))
            self._seen_running = 0
        return out

    def _temperature(self, kind: str, temp: float, limit: float, now: float, title: str, text: str) -> list:
        if temp >= limit:
            if self._armed[kind] and self._due(kind, now):
                self._armed[kind] = False
                return [(title, text)]
        elif temp <= limit - HYSTERESIS_C:
            self._armed[kind] = True
        return []

    def _due(self, kind: str, now: float) -> bool:
        last = self._last_sent.get(kind)
        if last is not None and now - last < COOLDOWN_S:
            return False
        self._last_sent[kind] = now
        return True
