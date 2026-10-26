# SPDX-License-Identifier: GPL-3.0-or-later
"""What the device is, as Windows reports it: one PowerShell query of Windows' own inventory (CIM: the computer, the
processor, the graphics, the memory modules, the drives, the battery, Windows itself and the firmware), read in the
background and returned as JSON, so the app needs nothing installed for it. Serial numbers and other personal data
are not asked for.

Installed memory is what the modules hold; usable memory is what Windows has after the graphics took its share (the
Ally X: 24 GB installed, about 16 usable with the default graphics memory)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from bc250_core.platform import NO_WINDOW, powershell_argv

QUERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
  maker = $cs.Manufacturer; model = $cs.Model; family = $cs.SystemFamily
  usable = [int64]$cs.TotalPhysicalMemory
  installed = [int64](Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum
  windows = $os.Caption; version = $os.Version; build = $os.BuildNumber
  cpu = @(Get-CimInstance Win32_Processor | ForEach-Object { [pscustomobject]@{
          name = $_.Name.Trim(); cores = $_.NumberOfCores; threads = $_.NumberOfLogicalProcessors } })
  gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { [pscustomobject]@{
          name = $_.Name; driver = $_.DriverVersion } })
  disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { [pscustomobject]@{
          model = $_.Model.Trim(); size = [int64]$_.Size } })
  battery = @(Get-CimInstance Win32_Battery | ForEach-Object { [pscustomobject]@{
          charge = $_.EstimatedChargeRemaining; status = $_.BatteryStatus } })
  firmware = (Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion
} | ConvertTo-Json -Depth 3 -Compress
"""
TIMEOUT = 30                            # s: CIM answered in about two seconds on the Ally
GB = 1024 ** 3
# Win32_Battery's BatteryStatus: what the battery is doing
CHARGING = {2: "plugged in", 3: "full", 6: "charging", 7: "charging", 8: "charging", 9: "charging"}

Run = Callable[[list[str]], str]


@dataclass
class Device:
    maker: str = ""
    model: str = ""
    family: str = ""
    windows: str = ""
    build: str = ""
    processor: str = ""
    cores: int = 0
    threads: int = 0
    graphics: list[tuple[str, str]] = field(default_factory=list)      # name, driver version
    installed: int = 0                                                  # bytes
    usable: int = 0
    disks: list[tuple[str, int]] = field(default_factory=list)          # model, bytes
    battery: tuple[int, str] | None = None                              # percent, what it is doing
    firmware: str = ""

    @property
    def name(self) -> str:
        """The device's name: the family Windows gives (ROG Xbox Ally X), else the maker and model."""
        return self.family or " ".join(part for part in (self.maker, self.model) if part)

    def rows(self) -> list[tuple[str, str]]:
        """What the Device card shows, a label and a value each."""
        windows = self.windows.removeprefix("Microsoft ")             # Windows 11 Home
        memory = f"{self.installed / GB:.0f} GB" if self.installed else ""
        if self.usable:
            memory += (", " if memory else "") + f"{self.usable / GB:.1f} GB usable"
        rows = [("Device", self.name), ("Processor", self.processor),
                ("Cores", f"{self.cores} cores, {self.threads} threads" if self.cores else ""),
                ("Graphics", ", ".join(name for name, _ in self.graphics)),
                ("Driver", ", ".join(driver for _, driver in self.graphics if driver)),
                ("Memory", memory),
                ("Storage", ", ".join(f"{size / 1e9:.0f} GB, {model}" for model, size in self.disks)),
                ("System", f"{windows}, build {self.build}" if self.build else windows),
                ("Firmware", self.firmware)]
        if self.battery is not None:
            rows.append(("Battery", f"{self.battery[0]} %, {self.battery[1]}" if self.battery[1]
                         else f"{self.battery[0]} %"))
        return [(label, value) for label, value in rows if value]

    def report(self) -> str:
        return "\n".join(f"{label}: {value}" for label, value in self.rows())


def _list(value) -> list:
    """ConvertTo-Json gives one object without a list around it."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse(text: str) -> Device:
    """The Device from the query's JSON; missing parts stay empty."""
    data = json.loads(text)
    cpus = _list(data.get("cpu"))
    batteries = _list(data.get("battery"))
    device = Device(maker=(data.get("maker") or "").strip(), model=(data.get("model") or "").strip(),
                    family=(data.get("family") or "").strip(), windows=(data.get("windows") or "").strip(),
                    build=str(data.get("build") or ""), installed=int(data.get("installed") or 0),
                    usable=int(data.get("usable") or 0), firmware=(data.get("firmware") or "").strip())
    if cpus:
        device.processor = cpus[0].get("name") or ""
        device.cores = sum(int(cpu.get("cores") or 0) for cpu in cpus)
        device.threads = sum(int(cpu.get("threads") or 0) for cpu in cpus)
    device.graphics = [((gpu.get("name") or "").strip(), (gpu.get("driver") or "").strip())
                       for gpu in _list(data.get("gpu")) if gpu.get("name")]
    device.disks = [((disk.get("model") or "").strip(), int(disk.get("size") or 0))
                    for disk in _list(data.get("disks")) if disk.get("model")]
    if batteries and batteries[0].get("charge") is not None:
        status = batteries[0].get("status")
        device.battery = (int(batteries[0]["charge"]), CHARGING.get(status, "on battery" if status == 1 else ""))
    return device


def run_powershell(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"PowerShell ended with {result.returncode}")
    return result.stdout


def read(run: Run = run_powershell) -> Device:
    """The device, read now (about two seconds: call it off the window's thread)."""
    return parse(run(powershell_argv(QUERY)))
