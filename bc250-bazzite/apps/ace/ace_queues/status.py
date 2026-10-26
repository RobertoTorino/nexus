# SPDX-License-Identifier: GPL-3.0-or-later
"""The script's --status output ("Name: value" lines), read into what the window shows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_MESA = re.compile(r"Mesa (\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class Status:
    fields: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        return self.fields.get(name, "")

    @property
    def is_bc250(self) -> bool:
        return self.get("Board").startswith("BC-250")

    @property
    def system_mesa(self) -> str:
        return self.get("System Mesa")

    @property
    def built(self) -> bool:
        return self.get("Build") not in ("", "none")

    @property
    def build_mesa(self) -> str:
        found = _MESA.search(self.get("Build"))
        return found.group(1) if found else ""

    @property
    def installed(self) -> bool:
        return self.get("Driver").startswith("installed")

    @property
    def driver_mesa(self) -> str:
        found = _MESA.search(self.get("Driver"))
        return found.group(1) if found else ""

    @property
    def tested(self) -> bool:
        """The test passed with the installed driver on the running kernel."""
        return self.get("Test").startswith("passed on this kernel")

    @property
    def test_failed(self) -> bool:
        return self.get("Test").startswith("failed")

    @property
    def all_apps(self) -> bool:
        return self.get("All apps") == "on"

    @property
    def launch_options(self) -> str:
        return self.get("Launch options")

    @property
    def build_outdated(self) -> bool:
        """The system's Mesa moved on since the build (the build still works; a new one keeps up with it)."""
        known = self.system_mesa not in ("", "unknown")
        return self.built and known and self.build_mesa != self.system_mesa

    @property
    def install_outdated(self) -> bool:
        """A newer build than the installed driver is waiting to be installed."""
        return self.installed and self.built and self.driver_mesa != self.build_mesa


def parse(text: str) -> Status:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        name, sep, value = line.partition(": ")
        if sep and name and name not in fields:
            fields[name] = value.strip()
    return Status(fields)


def verdict(status: Status) -> tuple[str, str, str]:
    """(text, kind, tooltip) of the status next to the title (StatusText)."""
    if not status.fields:
        return "Unknown", "neutral", "The status could not be read."
    if not status.is_bc250:
        return "No BC-250", "bad", "This app is for the AMD BC-250 (GPU 1002:13fe) only."
    if status.all_apps:
        return "On for all apps", "info", "Every app uses the patched driver (Flatpak apps keep their own)."
    if status.tested:
        return "Ready", "ok", "The test passed on this kernel: games with the launch options use the patched driver."
    if status.test_failed:
        return "Test failed", "bad", "Don't use the driver on this kernel."
    if status.installed:
        return "Test needed", "warn", "Run the test: games only use the driver after it passed on this kernel."
    if status.built:
        return "Not installed", "warn", "The driver is built; install it next."
    return "Not built", "warn", "Build the driver first."
