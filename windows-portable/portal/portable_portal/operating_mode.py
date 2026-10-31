# SPDX-License-Identifier: GPL-3.0-or-later
"""The ROG Xbox Ally X's operating modes, as Armoury Crate SE's Command Center offers them (owner, 31-10-2026: in the
portal, only on the Ally X, every mode). A mode is three settings: ASUS's power plan and Windows' power mode, which
the user may set (here), and the three watt limits, which only an administrator may write: the helper
(helper/operating-mode.ps1, a scheduled task that runs as SYSTEM, installed with one administrator prompt), which
applies the whole mode the portal names, also again after every change of the power source. Command Center keeps its own record of the mode, so it may show another one after a change here; the mode
shown here is read back from the plan and the power mode. The values are the owner's measurements on the Ally X
(MIGRATION.md, 31-10-2026)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import NO_WINDOW

MODEL = "RC73XA"                # the ROG Xbox Ally X in Windows' product name ("ROG Xbox Ally X RC73XA_RC73XA")
BIOS_KEY = r"HARDWARE\DESCRIPTION\System\BIOS"
SUITE_FOLDER = "windows-portable-suite"
TASK = r"\Windows Portable Suite\Operating Mode"      # the helper's scheduled task (helper/install-helper.ps1)
HELPER = Path(__file__).resolve().parent / "helper"     # the helper's scripts as the portal ships them

BALANCED = "00000000-0000-0000-0000-000000000000"       # Windows' power mode: Balanced
EFFICIENCY = "961cc777-2547-4f9d-8174-7d86181b8a7a"     # Best power efficiency
PERFORMANCE = "ded574b5-45a0-4f42-8737-46345c09c238"    # Best performance

Watts = tuple[int, int, int]                            # sustained, slow, fast


@dataclass(frozen=True)
class Mode:
    letter: str                 # the header's marker
    name: str
    plan: str                   # the power plan's GUID
    overlay: str | None         # Windows' power mode; None: the player's own (Windows mode)
    charger: Watts
    battery: Watts


MODES = (
    Mode("S", "Silent", "64a64f24-65b9-4b56-befd-5ec1eaced9b3", EFFICIENCY, (13, 16, 20), (13, 16, 20)),
    Mode("P", "Performance", "27fa6203-3987-4dcc-918d-748559d549ec", BALANCED, (17, 21, 26), (17, 21, 26)),
    Mode("T", "Turbo", "6fecc5ae-f350-48a5-b669-b472cb895ccf", PERFORMANCE, (35, 44, 55), (25, 30, 36)),
    Mode("W", "Windows", "381b4222-f694-41f0-9685-ff5bb260df2e", None, (17, 21, 26), (17, 21, 26)),
)
BY_LETTER = {mode.letter: mode for mode in MODES}


def product_name() -> str:
    """Windows' product name for this device (the firmware's, as the BIOS reports it); "" off Windows."""
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, BIOS_KEY) as key:
            return str(winreg.QueryValueEx(key, "SystemProductName")[0])
    except OSError:
        return ""


def is_ally_x(product: Callable[[], str] = product_name) -> bool:
    return MODEL in product().upper()


class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> _GUID:
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), uuid.UUID(text).bytes_le, ctypes.sizeof(cls))
        return guid

    def text(self) -> str:
        return str(uuid.UUID(bytes_le=bytes(self)))


class PowerApi:
    """Windows' power API (powrprof): the active power plan and power mode, read and set as the user."""

    def __init__(self) -> None:
        self.api = ctypes.WinDLL("powrprof")

    def plan(self) -> str:
        active = ctypes.POINTER(_GUID)()
        if self.api.PowerGetActiveScheme(None, ctypes.byref(active)):
            return ""
        try:
            return active.contents.text()
        finally:
            ctypes.windll.kernel32.LocalFree(active)  # type: ignore[attr-defined]

    def overlay(self) -> str:
        guid = _GUID()
        return "" if self.api.PowerGetEffectiveOverlayScheme(ctypes.byref(guid)) else guid.text()

    def set_plan(self, plan: str) -> bool:
        return not self.api.PowerSetActiveScheme(None, ctypes.byref(_GUID.of(plan)))

    def set_overlay(self, overlay: str) -> bool:
        return not self.api.PowerSetActiveOverlayScheme(_GUID.of(overlay))


def active(api: PowerApi) -> Mode | None:
    """The mode the plan and the power mode make; None when they match none (another plan, or a power mode that is
    not the plan's)."""
    plan, overlay = api.plan().lower(), api.overlay().lower()
    for mode in MODES:
        if plan == mode.plan and (mode.overlay is None or overlay == mode.overlay):
            return mode
    return None


def apply(mode: Mode, api: PowerApi) -> bool:
    """Set *mode*'s plan and power mode (Windows mode: Windows' Balanced plan, the power mode left to the player).
    The watts are the helper's."""
    if not api.set_plan(mode.plan):
        return False
    return mode.overlay is None or api.set_overlay(mode.overlay)


def marker(api: PowerApi) -> str:
    """The header's marker: the active mode's letter, "" when none is active."""
    mode = active(api)
    return mode.letter if mode else ""


def watts_text(watts: Watts) -> str:
    """A mode's watts as its row shows them: "35 / 44 / 55 W" (sustained, slow, fast)."""
    return " / ".join(str(value) for value in watts) + " W"


def power_api(product: Callable[[], str] = product_name) -> PowerApi | None:
    """Windows' power API on the ROG Xbox Ally X, powrprof opened once; None on any other device (no marker, no
    Operating mode row)."""
    return PowerApi() if sys.platform == "win32" and is_ally_x(product) else None


@dataclass(frozen=True)
class Outcome:
    """The helper's last run, its operating-mode-result: the mode's letter, whether it was applied, and the watts
    written ("35 / 44 / 55 W") or why not."""
    letter: str
    ok: bool
    text: str


def parse_result(line: str) -> Outcome | None:
    """The helper's result line: "T ok charger 35 / 44 / 55 W" or "T failed <why>"; None for anything else."""
    parts = line.strip().split(" ", 2)
    if len(parts) < 3 or parts[1] not in ("ok", "failed"):
        return None
    if parts[1] == "failed":
        return Outcome(parts[0], False, parts[2])
    return Outcome(parts[0], True, parts[2].split(" ", 1)[1] if " " in parts[2] else parts[2])


class Helper:
    """The Operating Mode helper as the portal sees it: whether it is installed (its script in Program Files), the mode
    asked for (one letter in ProgramData, which users may write), the task started as the user, and its result."""

    def __init__(self, programs: Path | None = None, data: Path | None = None,
                 run: Callable[[list[str]], int] | None = None):
        self.programs = programs or Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / SUITE_FOLDER
        self.data = data or Path(os.environ.get("ProgramData", r"C:\ProgramData")) / SUITE_FOLDER
        self.run = run or (lambda argv: subprocess.run(argv, capture_output=True, creationflags=NO_WINDOW).returncode)

    @property
    def request_file(self) -> Path:
        return self.data / "operating-mode"

    @property
    def result_file(self) -> Path:
        return self.data / "operating-mode-result"

    def installed(self) -> bool:
        return (self.programs / "operating-mode.ps1").is_file() and self.request_file.is_file()

    def request(self, mode: Mode) -> str:
        """Ask the helper for *mode*: its letter in the request, then the task started; "" or why it was not."""
        try:
            self.request_file.write_text(mode.letter, encoding="ascii")
        except OSError as exc:
            return f"the request could not be written ({exc.strerror or exc})"
        try:
            status = self.run(["schtasks.exe", "/Run", "/TN", TASK])
        except OSError as exc:
            return f"the helper's task could not be started ({exc.strerror or exc})"
        return "" if status == 0 else f"the helper's task could not be started (schtasks: {status})"

    def result(self) -> tuple[float, Outcome | None]:
        """The time of the helper's last result (0: none) and what it says."""
        try:
            return self.result_file.stat().st_mtime, parse_result(self.result_file.read_text(encoding="utf-8-sig"))
        except OSError:
            return 0.0, None

    def install(self, remove: bool = False) -> str:
        """Start the helper's installer (or, *remove*, its copy in Program Files with --uninstall) as administrator,
        Windows' prompt first; "" once it started, or why not (the prompt declined)."""
        script = (self.programs if remove else HELPER) / "install-helper.ps1"
        args = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"' + (" --uninstall" if remove else "")
        shell = ctypes.windll.shell32  # type: ignore[attr-defined]
        code = shell.ShellExecuteW(None, "runas", "powershell.exe", args, None, 1)
        return "" if code > 32 else "administrator rights were not given" if code == 5 else f"Windows refused it ({code})"
