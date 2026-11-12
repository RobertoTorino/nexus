# SPDX-License-Identifier: GPL-3.0-or-later
"""What the window reads, as you, without a password: the adapter and whether it is on, the devices Bluetooth knows
(paired, connected, or heard in a search), the system part's two services and what the search after this boot did
(its journal; readable for the wheel group, as the board's user is)."""

from __future__ import annotations

import datetime
import json
import subprocess
from dataclasses import dataclass
from typing import Callable

from .boot import BATTERY_UNIT, PAIR_UNIT, devices, info_field

SCAN_S = 10                             # how long the window's search for nearby devices runs
LOG_LINES = 40

Runner = Callable[[list[str], float], tuple[int, str]]


def run(argv: list[str], timeout: float = 15) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError as exc:
        return 127, str(exc)
    return done.returncode, done.stdout


@dataclass(frozen=True)
class Adapter:
    present: bool
    powered: bool = False
    blocked: bool = False               # switched off with the rfkill switch (Plasma's Bluetooth off, airplane mode)


@dataclass(frozen=True)
class Device:
    address: str
    name: str
    paired: bool = False
    connected: bool = False


def adapter(run: Runner = run) -> Adapter:
    code, out = run(["bluetoothctl", "show"], 15)
    if code != 0 or not (out.startswith("Controller") or "\nController" in out):
        return Adapter(False)
    return Adapter(True, info_field(out, "Powered") == "yes", info_field(out, "PowerState") == "off-blocked")


def known(run: Runner = run) -> list[Device]:
    """The devices Bluetooth knows, paired ones first, each name once (the first, a connected one before others)."""
    def listed(*which: str) -> set[str]:
        return {address for address, _name in devices(run(["bluetoothctl", "devices", *which], 15)[1])}
    paired, connected = listed("Paired"), listed("Connected")
    found: dict[str, Device] = {}
    for address, name in devices(run(["bluetoothctl", "devices"], 15)[1]):
        if name.replace("-", ":") == address:
            continue                    # no name heard yet: shown by its address only, nothing to match
        device = Device(address, name, address in paired, address in connected)
        if name not in found or (device.connected and not found[name].connected):
            found[name] = device
    return sorted(found.values(), key=lambda d: (not d.paired, d.name.casefold()))


def scan(run: Runner = run, seconds: int = SCAN_S) -> list[Device]:
    """Searches for nearby devices for *seconds* (one in pairing mode answers), then what Bluetooth knows."""
    run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], seconds + 10)
    return known(run)


def unit_state(unit: str, run: Runner = run) -> str:
    """systemctl is-active: active, inactive (the search ended), failed, …"""
    return run(["systemctl", "is-active", unit], 15)[1].strip() or "unknown"


def last_search(run: Runner = run) -> list[str]:
    """What the search after this boot said, its newest lines with their time ("23:51:35 search ended; …"); [] when
    it did not run in this boot. Read as JSON: the journal's own lines carry the host name, which is not shown."""
    code, out = run(["journalctl", "-b", "-u", PAIR_UNIT, "-o", "json", "--no-pager", "-n", str(LOG_LINES)], 15)
    if code != 0:
        return []
    lines = []
    for raw in out.splitlines():
        try:
            entry = json.loads(raw)
            when = datetime.datetime.fromtimestamp(int(entry["__REALTIME_TIMESTAMP"]) / 1e6)
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
        message = entry.get("MESSAGE")
        if isinstance(message, list):           # a message that is not valid UTF-8 comes as its bytes
            message = bytes(message).decode("utf-8", "replace")
        if isinstance(message, str) and message.strip():
            lines.append(f"{when:%H:%M:%S} {message}")
    return lines


__all__ = ["Adapter", "BATTERY_UNIT", "Device", "PAIR_UNIT", "adapter", "known", "last_search", "scan", "unit_state"]
