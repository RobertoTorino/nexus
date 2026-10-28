# SPDX-License-Identifier: GPL-3.0-or-later
"""What the device is, as Windows reports it: one PowerShell query of Windows' own inventory (CIM: the computer, the
processor, the graphics, the memory modules, the drives, the battery, Windows itself and the firmware; and for the
Hardware card the built-in panel, the network adapters, the Bluetooth adapter, audio, touch, the fingerprint reader,
cameras, sensors and USB; for the Connected card the USB hubs (a dock shows as one), the external screens, the network
adapters and drives on USB), read in the background and returned as JSON, so the app needs nothing installed for it.
Serial numbers, MAC addresses and other personal data are not asked for: of Bluetooth only the adapter itself is
listed (USB or PCI), never a paired device, which carries its owner's name.

Installed memory is what the modules hold; usable memory is what Windows has after the graphics took its share (the
Ally X: 24 GB installed, about 16 usable with the default graphics memory)."""

from __future__ import annotations

import ctypes
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from bc250_core.platform import NO_WINDOW, powershell_argv

QUERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$connections = @(Get-CimInstance -Namespace root\wmi WmiMonitorConnectionParams)
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
          model = $_.Model.Trim(); size = [int64]$_.Size; usb = $_.InterfaceType -eq 'USB' -or
          $_.PNPDeviceID -match '^USBSTOR' -or $_.MediaType -match 'External' } })
  battery = @(Get-CimInstance Win32_Battery | ForEach-Object { [pscustomobject]@{
          charge = $_.EstimatedChargeRemaining; status = $_.BatteryStatus } })
  firmware = (Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion
  panel = @(Get-CimInstance -Namespace root\wmi WmiMonitorBasicDisplayParams | ForEach-Object { $s = $_
          $c = $connections | Where-Object InstanceName -eq $s.InstanceName | Select-Object -First 1
          [pscustomobject]@{ width = $s.MaxHorizontalImageSize; height = $s.MaxVerticalImageSize
                             internal = ([int64]$c.VideoOutputTechnology -band 0x80000000) -ne 0 } })
  network = @(Get-NetAdapter -Physical | ForEach-Object { [pscustomobject]@{
          name = $_.InterfaceDescription; media = $_.PhysicalMediaType; driver = $_.DriverVersion
          up = $_.Status -eq 'Up'; usb = $_.PnPDeviceID -match '^USB' } })
  hubs = @(Get-PnpDevice -Class USB -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\VID_' -and
          $_.FriendlyName -match 'hub' } | ForEach-Object { [pscustomobject]@{
          name = $_.FriendlyName; id = ($_.InstanceId -split '\\')[1] } })
  screens = @(Get-CimInstance -Namespace root\wmi WmiMonitorID | ForEach-Object { $m = $_
          $c = $connections | Where-Object InstanceName -eq $m.InstanceName | Select-Object -First 1
          [pscustomobject]@{ name = -join [char[]]@($m.UserFriendlyName | Where-Object { $_ -ne 0 })
                             output = [int64]$c.VideoOutputTechnology } })
  bluetooth = @(Get-PnpDevice -Class Bluetooth -PresentOnly | Where-Object { $_.InstanceId -match '^(USB|PCI)\\' } |
          ForEach-Object { $_.FriendlyName })
  audio = @(Get-CimInstance Win32_SoundDevice | ForEach-Object { $_.Name })
  touch = @(Get-PnpDevice -PresentOnly | Where-Object { $_.Class -ne 'Biometric' -and
          $_.FriendlyName -match 'touch ?(panel|screen)' } | ForEach-Object { $_.FriendlyName })
  fingerprint = @(Get-PnpDevice -Class Biometric -PresentOnly | ForEach-Object { $_.FriendlyName })
  camera = @(Get-PnpDevice -Class Camera, Image -PresentOnly | ForEach-Object { $_.FriendlyName })
  sensors = @(Get-PnpDevice -Class Sensor -PresentOnly | ForEach-Object { $_.FriendlyName })
  usb = @(Get-CimInstance Win32_USBController | ForEach-Object { $_.Name })
} | ConvertTo-Json -Depth 3 -Compress
"""
TIMEOUT = 30                            # s: CIM answered in about three and a half seconds on the Ally
GB = 1024 ** 3
# Win32_Battery's BatteryStatus: what the battery is doing
CHARGING = {2: "plugged in", 3: "full", 6: "charging", 7: "charging", 8: "charging", 9: "charging"}
WIRELESS = "Native 802.11"              # Get-NetAdapter's PhysicalMediaType of a Wi-Fi adapter
INTERNAL = 0x80000000                   # WmiMonitorConnectionParams' VideoOutputTechnology: the built-in panel
OUTPUTS = {0: "VGA", 4: "DVI", 5: "HDMI", 10: "DisplayPort", 11: "DisplayPort", 15: "Miracast", 16: "a wired link"}
# The makers of the hub chips docks are built with, by their USB vendor id: the hub tells no dock's name
VENDORS = {"0BDA": "Realtek", "05E3": "Genesys Logic", "2109": "VIA Labs", "0451": "Texas Instruments",
           "1A40": "Terminus", "174C": "ASMedia", "1D5C": "Fresco Logic", "0424": "Microchip", "2188": "CalDigit",
           "17EF": "Lenovo", "413C": "Dell", "03F0": "HP", "0B05": "ASUS", "045E": "Microsoft", "05AC": "Apple",
           "8087": "Intel", "1A86": "QinHeng", "2537": "Norelsys", "0B95": "ASIX"}
SM_MAXIMUMTOUCHES = 95                  # GetSystemMetrics: how many touch points the touch screen takes

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
    disks: list[tuple[str, int]] = field(default_factory=list)          # model, bytes: the built-in drives
    external_disks: list[tuple[str, int]] = field(default_factory=list)  # on USB
    battery: tuple[int, str] | None = None                              # percent, what it is doing
    firmware: str = ""
    panel: tuple[int, int] | None = None                                # the built-in screen: cm wide, high
    wifi: list[tuple[str, str]] = field(default_factory=list)          # adapter, driver version
    network: list[tuple[str, bool]] = field(default_factory=list)      # the other built-in adapters: name, connected
    usb_network: list[tuple[str, bool]] = field(default_factory=list)  # on USB (a dock's Ethernet port)
    hubs: list[tuple[str, str]] = field(default_factory=list)          # maker, "USB 3" or "USB 2"
    screens: list[tuple[str, str]] = field(default_factory=list)       # the external screens: name, how connected
    bluetooth: list[str] = field(default_factory=list)
    audio: list[str] = field(default_factory=list)
    touch: list[str] = field(default_factory=list)
    touch_points: int = 0
    fingerprint: list[str] = field(default_factory=list)
    camera: list[str] = field(default_factory=list)
    sensors: list[str] = field(default_factory=list)
    usb: list[str] = field(default_factory=list)

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
            rows.append(("Battery", f"{self.battery[0]}%, {self.battery[1]}" if self.battery[1]
                         else f"{self.battery[0]}%"))
        return [(label, value) for label, value in rows if value]

    def hardware_rows(self) -> list[tuple[str, str]]:
        """What the Hardware card shows: the panel, touch and the rest of what is built in or plugged in."""
        panel = ""
        if self.panel:
            width, height = self.panel
            panel = f"about {round(math.hypot(width, height) / 2.54)} inches ({width} x {height} cm)"
        named = [name for name in self.touch if not name.startswith("HID-compliant")]
        touch = ", ".join(named or self.touch)          # the panel's name, not Windows' generic one beside it
        if self.touch_points:
            touch += (", " if touch else "") + f"{self.touch_points} touch points"
        rows = [("Panel", panel), ("Touch", touch),
                ("Wi-Fi", ", ".join(f"{name}, driver {driver}" if driver else name for name, driver in self.wifi)),
                ("Network", ", ".join(name + ("" if up else " (not connected)") for name, up in self.network)),
                ("Bluetooth", ", ".join(self.bluetooth)), ("Audio", ", ".join(self.audio)),
                ("Fingerprint", ", ".join(self.fingerprint)), ("Camera", ", ".join(self.camera)),
                ("Sensors", ", ".join(self.sensors)), ("USB", ", ".join(self.usb))]
        return [(label, value) for label, value in rows if value]

    def connected_rows(self) -> list[tuple[str, str]]:
        """What the Connected card shows: what is plugged in. A dock is a USB hub with its ports behind it, and
        Windows does not tell a dock from a hub: the hub's maker and the devices behind it are what shows."""
        makers: dict[str, list[str]] = {}
        for maker, speed in self.hubs:
            speeds = makers.setdefault(maker, [])
            if speed not in speeds:
                speeds.append(speed)
        rows = [("Dock or hub", ", ".join(f"{maker} USB hub ({', '.join(sorted(speeds, reverse=True))})"
                                          for maker, speeds in makers.items())),
                ("Screens", ", ".join(f"{name}, {output}" if output else name for name, output in self.screens)),
                ("Network", ", ".join(name + ("" if up else " (not connected)") for name, up in self.usb_network)),
                ("Drives", ", ".join(f"{size / 1e9:.0f} GB, {model}" for model, size in self.external_disks))]
        return [(label, value) for label, value in rows if value]

    def report(self) -> str:
        return "\n".join(f"{label}: {value}"
                         for label, value in self.rows() + self.hardware_rows() + self.connected_rows())


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
    for disk in _list(data.get("disks")):
        model = re.sub(r" (SCSI Disk Device|USB Device)$", "", (disk.get("model") or "").strip())
        if model:
            (device.external_disks if disk.get("usb") else device.disks).append((model, int(disk.get("size") or 0)))
    if batteries and batteries[0].get("charge") is not None:
        status = batteries[0].get("status")
        device.battery = (int(batteries[0]["charge"]), CHARGING.get(status, "on battery" if status == 1 else ""))
    panels = [p for p in _list(data.get("panel")) if p.get("internal") and p.get("width") and p.get("height")]
    if panels:
        device.panel = (int(panels[0]["width"]), int(panels[0]["height"]))
    for adapter in _list(data.get("network")):
        name = (adapter.get("name") or "").strip()
        if not name:
            continue
        if adapter.get("media") == WIRELESS:
            device.wifi.append((name, (adapter.get("driver") or "").strip()))
        else:
            (device.usb_network if adapter.get("usb") else device.network).append((re.sub(r" #\d+$", "", name), bool(adapter.get("up"))))   # "... Controller #2"
    for key in ("bluetooth", "audio", "touch", "fingerprint", "camera", "sensors", "usb"):
        setattr(device, key, names(data.get(key)))
    for hub in _list(data.get("hubs")):
        vendor = re.match(r"VID_([0-9A-Fa-f]{4})", str(hub.get("id") or ""))
        if vendor:
            maker = VENDORS.get(vendor.group(1).upper(), f"vendor {vendor.group(1).upper()}")
            device.hubs.append((maker, "USB 3" if "SuperSpeed" in str(hub.get("name") or "") else "USB 2"))
    for screen in _list(data.get("screens")):
        output = int(screen.get("output") or 0)
        if output & INTERNAL:
            continue                                    # the built-in panel: the Hardware card's
        device.screens.append(((screen.get("name") or "").strip() or "a screen", OUTPUTS.get(output, "")))
    return device


def names(value) -> list[str]:
    """Device names as Windows gives them, each once, without the "(Microsoft)" of the driver's maker."""
    found: list[str] = []
    for name in _list(value):
        name = re.sub(r"\s*\(Microsoft\)$", "", str(name or "").strip())
        if name and name not in found:
            found.append(name)
    return found


def touch_points() -> int:
    """How many touch points the touch screen takes (Windows' own count); 0 without one, or not on Windows."""
    if sys.platform != "win32":
        return 0
    return int(ctypes.windll.user32.GetSystemMetrics(SM_MAXIMUMTOUCHES))  # type: ignore[attr-defined]


def run_powershell(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"PowerShell ended with {result.returncode}")
    return result.stdout


def read(run: Run = run_powershell, touches: Callable[[], int] = touch_points) -> Device:
    """The device, read now (about three and a half seconds: call it off the window's thread)."""
    device = parse(run(powershell_argv(QUERY)))
    device.touch_points = touches()
    return device
