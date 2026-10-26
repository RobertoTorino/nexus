# SPDX-License-Identifier: GPL-3.0-or-later
"""Client for the governor's D-Bus service (com.cyanskillfish.Governor on the system bus).

Uses busctl, which every systemd system has, so the app needs no D-Bus Python binding. The governor's bus
policy lets every local user call the PerformanceMode interface and read/write its properties; only
TestMode is root-only, so that one call goes through pkexec. All changes are runtime only: the governor
forgets them at the next restart, config.toml is what persists.
"""

from __future__ import annotations

import subprocess


from .. import fmt
from .base import PerformanceState
from .process import run as _run

BUS_NAME = "com.cyanskillfish.Governor"
OBJECT_PATH = "/com/cyanskillfish/Governor"
PERF_IFACE = "com.cyanskillfish.Governor.PerformanceMode"
TEST_IFACE = "com.cyanskillfish.Governor.TestMode"
RANGE_IFACE = "com.cyanskillfish.Governor.Range"
RANGE_PATHS = {
    "current": f"{OBJECT_PATH}/Range/Current",
    "allowed": f"{OBJECT_PATH}/Range/Allowed",
    "initial": f"{OBJECT_PATH}/Range/Initial",
}


def _error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout).strip() or fmt(
        "busctl failed (%1)", str(result.returncode))


def _parse_values(output: str) -> list[str]:
    """busctl prints one `<signature> <value>` per property line; return the values."""
    values = []
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            values.append(parts[1])
    return values


class GovernorBus:
    """Thin busctl wrapper; every method returns rather than raises."""

    def available(self) -> tuple[bool, str]:
        result = _run(["busctl", "--system", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                       "org.freedesktop.DBus", "NameHasOwner", "s", BUS_NAME])
        if result.returncode != 0:
            return False, _error(result)
        if result.stdout.strip().endswith("true"):
            return True, ""
        return False, fmt("%1 is not on the system bus (governor stopped, or [dbus] enabled = false).",
            BUS_NAME)

    def _get_properties(self, path: str, iface: str, *names: str) -> list[str] | None:
        result = _run(["busctl", "--system", "get-property", BUS_NAME, path, iface, *names])
        if result.returncode != 0:
            return None
        values = _parse_values(result.stdout)
        return values if len(values) == len(names) else None

    def state(self) -> PerformanceState:
        ok, error = self.available()
        state = PerformanceState(available=ok, error=error)
        if not ok:
            return state
        perf = self._get_properties(OBJECT_PATH, PERF_IFACE, "Enabled", "LoadTargetMin", "LoadTargetMax",
                                    "TemperatureThrottling", "TemperatureRecovery")
        if perf is None:
            state.available = False
            state.error = "The governor answered on the bus, but its properties could not be read."
            return state
        state.enabled = perf[0] == "true"
        state.load_min, state.load_max = float(perf[1]), float(perf[2])
        state.temp_throttling, state.temp_recovery = int(perf[3]), int(perf[4])
        for kind, path in RANGE_PATHS.items():
            values = self._get_properties(path, RANGE_IFACE, "Min", "Max")
            if values:
                setattr(state, f"{kind}_min", int(values[0]))
                setattr(state, f"{kind}_max", int(values[1]))
        return state

    # ------------------------------------------------------------------ commands
    def _call(self, method: str, signature: str = "", *args: str) -> tuple[bool, str]:
        cmd = ["busctl", "--system", "call", BUS_NAME, OBJECT_PATH, PERF_IFACE, method]
        if signature:
            cmd += [signature, *args]
        result = _run(cmd, timeout=10)
        return result.returncode == 0, "" if result.returncode == 0 else _error(result)

    def set_enabled(self, enabled: bool) -> tuple[bool, str]:
        result = _run(["busctl", "--system", "set-property", BUS_NAME, OBJECT_PATH, PERF_IFACE, "Enabled", "b",
                       "true" if enabled else "false"], timeout=10)
        return result.returncode == 0, "" if result.returncode == 0 else _error(result)

    def set_fixed_frequency(self, mhz: int) -> tuple[bool, str]:
        """Performance mode pinned to one clock; must lie inside the allowed range."""
        return self._call("SetFixedFrequency", "u", str(int(mhz)))

    def set_range(self, min_mhz: int, max_mhz: int) -> tuple[bool, str]:
        """Runtime frequency range; 0 means no limit on that side. Leaves performance mode."""
        return self._call("SetRange", "uu", str(int(min_mhz)), str(int(max_mhz)))

    def set_load_target(self, lower: float, upper: float) -> tuple[bool, str]:
        return self._call("SetLoadTarget", "dd", f"{lower:.4f}", f"{upper:.4f}")

    def set_temperature_thresholds(self, throttling: int, recovery: int) -> tuple[bool, str]:
        """Recovery 0 means 'not set'."""
        return self._call("SetTemperatureThresholds", "uu", str(int(throttling)), str(int(recovery)))

    def set_test_mode(self, mhz: int, millivolts: int) -> tuple[bool, str]:
        """Pin frequency *and* voltage and stop the automatic adjustment (root-only interface, one pkexec
        prompt). The governor applies the pair as given, without looking at its safe points; the caller must
        check it. Any PerformanceMode call (Enabled, SetFixedFrequency, SetRange) ends test mode."""
        result = _run(["pkexec", "busctl", "--system", "call", BUS_NAME, OBJECT_PATH, TEST_IFACE, "SetTestMode",
                       "uu", str(int(mhz)), str(int(millivolts))], timeout=120)
        if result.returncode == 126:
            return False, "Authentication was canceled."
        return result.returncode == 0, "" if result.returncode == 0 else _error(result)
