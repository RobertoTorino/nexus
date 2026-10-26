# SPDX-License-Identifier: GPL-3.0-or-later
"""The script's --status output ("Name: value" lines), read into what the window shows."""

from __future__ import annotations

from dataclasses import dataclass, field

INSTALLED = "installed, "


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
    def directmesh(self) -> str:
        """What this version of the app builds: "v1.3.1, Mesa 26.2.1"."""
        return self.get("DirectMesh")

    @property
    def built(self) -> bool:
        return self.get("Build") not in ("", "none")

    @property
    def installed(self) -> bool:
        return self.get("Driver").startswith("installed")

    @property
    def driver(self) -> str:
        """The installed driver: "DirectMesh v1.3.1, Mesa 26.2.1, <built>"."""
        return self.get("Driver").removeprefix(INSTALLED) if self.installed else ""

    @property
    def tested(self) -> bool:
        """The test passed with the installed driver on the running kernel."""
        return self.get("Test").startswith("passed on this kernel")

    @property
    def test_failed(self) -> bool:
        return self.get("Test").startswith("failed")

    @property
    def launch_options(self) -> str:
        return self.get("Launch options")

    @property
    def build_outdated(self) -> bool:
        """The build is of another DirectMesh release than this version of the app builds (an app update brought a
        new one); the build still works, a new one brings the new release."""
        return self.built and bool(self.directmesh) and not self.get("Build").startswith(
            f"DirectMesh {self.directmesh},")

    @property
    def install_outdated(self) -> bool:
        """A newer build than the installed driver is waiting to be installed."""
        return self.installed and self.built and self.driver != self.get("Build")


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
        return "No BC-250", "bad", "This app is for the AMD BC-250 (GPU 1002:13fe or 1002:143f) only."
    if status.tested:
        return "Ready", "ok", "The test passed on this kernel: games with the launch options use the driver."
    if status.test_failed:
        return "Test failed", "bad", "Don't use the driver on this kernel."
    if status.installed:
        return "Test needed", "warn", "Run the test: games only use the driver after it passed on this kernel."
    if status.built:
        return "Not installed", "warn", "The driver is built; install it next."
    return "Not built", "warn", "Build the driver first."
