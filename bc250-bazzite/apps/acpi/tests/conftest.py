# SPDX-License-Identifier: MIT
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, and a fake board for
bc250-acpi-override.sh: a folder that stands in for / (BC250_ACPI_ROOT) plus stub commands (id, ujust, lspci,
journalctl) first on PATH. Nothing here touches /boot, GRUB or sudo."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP = Path(__file__).resolve().parent.parent
SCRIPT = APP / "bc250-acpi-override.sh"
GRUB_LINE = 'GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"'
BC250_GPU = "03:00.0 0300: 1002:13fe"

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="runs the bash script with stub commands")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path):
    """QSettings in tmp_path, as .ini files (on Windows the default would be the registry)."""
    from PyQt6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"


@dataclass
class Board:
    root: Path
    bin: Path
    env: dict

    @property
    def cpio(self) -> Path:
        return self.root / "boot" / "acpi_override.cpio"

    @property
    def grub(self) -> Path:
        return self.root / "etc" / "default" / "grub"

    @property
    def grub_runs(self) -> int:
        log = self.root / "ujust.log"
        return len(log.read_text().splitlines()) if log.is_file() else 0

    def run(self, *args: str, uid: int = 0) -> subprocess.CompletedProcess:
        env = {**self.env, "FAKE_UID": str(uid)}
        return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)


def _stub(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def board(tmp_path) -> Board:
    """A stock BC-250 without the override: GPU present, stock BIOS, no frequency steps."""
    root, stubs = tmp_path / "root", tmp_path / "bin"
    for d in ("boot", "etc/default", "sys/class/dmi/id", "sys/devices/system/cpu/cpu0/cpuidle/state0", stubs):
        (root / d if isinstance(d, str) else d).mkdir(parents=True, exist_ok=True)
    (root / "etc/default/grub").write_text('GRUB_TIMEOUT=5\nGRUB_CMDLINE_LINUX="rhgb quiet"\n')
    (root / "sys/class/dmi/id/bios_version").write_text("5.00\n")
    (root / "sys/devices/system/cpu/cpu0/cpuidle/state0/name").write_text("POLL\n")
    _stub(stubs, "id", '[ "$1" = -u ] && { echo "$FAKE_UID"; exit 0; }; exec /usr/bin/id "$@"')
    _stub(stubs, "ujust", 'echo "$*" >> "$BC250_ACPI_ROOT/ujust.log"')
    _stub(stubs, "lspci", 'printf "%s\\n" "$FAKE_LSPCI"')
    _stub(stubs, "journalctl", 'printf "%s\\n" "$FAKE_KLOG"')
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "BC250_ACPI_ROOT": str(root),
           "FAKE_LSPCI": BC250_GPU, "FAKE_KLOG": ""}
    return Board(root, stubs, env)


def give_override_cpu(board: Board) -> None:
    """What the CPU looks like with the override loaded: 8 frequency steps and C1/C2."""
    cpu0 = board.root / "sys/devices/system/cpu/cpu0"
    (cpu0 / "cpufreq").mkdir(exist_ok=True)
    steps = " ".join(str(khz) for khz in (3200000, 2800000, 2400000, 2000000, 1600000, 1400000, 1000000, 800000))
    (cpu0 / "cpufreq/scaling_available_frequencies").write_text(steps + " \n")
    for i, name in ((1, "C1"), (2, "C2")):
        (cpu0 / f"cpuidle/state{i}").mkdir(exist_ok=True)
        (cpu0 / f"cpuidle/state{i}/name").write_text(name + "\n")
