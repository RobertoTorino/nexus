# SPDX-License-Identifier: GPL-3.0-or-later
"""What the device is, as Windows reports it: one PowerShell query of Windows' own inventory (CIM: the computer, the
processor, the graphics, the memory modules, the drives, the battery, Windows itself and the firmware; and for the
Hardware card the built-in panel, the network adapters, the Bluetooth adapter, audio, touch, the controller, the
fingerprint reader, cameras, sensors, USB and the built-in devices Device Manager marks with a problem; for the
Connected card every USB device plugged in, the external screens, the network adapters and drives on USB), read in the
background and returned as JSON, so the app needs nothing installed for it. Serial numbers, MAC addresses and other
personal data are not asked for: of Bluetooth only the adapter itself is listed (USB or PCI), never a paired device,
which carries its owner's name.

What is plugged in is what Windows keeps outside the computer's own container (DEVPKEY_Device_ContainerId, as
Settings' Devices page groups them): each plugged-in device has a container of its own, and a dock's hubs share one.
The devices are numbered in the query and point to their parent by that number, so their instance IDs (which carry a
device's serial number) never leave it. A dock tells Windows only the maker of its hub chip, never its own brand (the
owner's JSAUX dock, 02-11-2026: two Realtek hubs, USB2.1 Hub and USB3.2 Hub, and a Realtek network chip behind them),
and an adapter shows by its chip (the owner's Ugreen adapter: ASIX AX88179).

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
$usb = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -match '^USB\\VID_')
$keys = @{}
$asked = [string[]]('DEVPKEY_Device_Parent', 'DEVPKEY_Device_ContainerId', 'DEVPKEY_Device_InLocalMachineContainer',
                    'DEVPKEY_Device_BusReportedDeviceDesc')
foreach ($d in $usb) {          # one call per device: Get-PnpDeviceProperty for several mixes up whose value is whose
  (Invoke-CimMethod -InputObject $d -MethodName GetDeviceProperties -Arguments @{ devicePropertyKeys = $asked }
  ).deviceProperties | ForEach-Object { $keys["$($d.InstanceId)|$($_.KeyName)".ToUpper()] = $_.Data } }
function Key($id, $name) { $keys["$id|DEVPKEY_Device_$name".ToUpper()] }
$at = @{}
for ($i = 0; $i -lt $usb.Count; $i++) { $at[$usb[$i].InstanceId.ToUpper()] = $i }
function At($id) { if ($id -and $at.ContainsKey("$id".ToUpper())) { $at["$id".ToUpper()] } else { -1 } }
$boxes = @{}
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
          up = $_.Status -eq 'Up'; status = [string]$_.Status; speed = [int64]$_.ReceiveLinkSpeed
          usb = $_.PnPDeviceID -match '^USB'; device = At $_.PnPDeviceID } })
  plugged = @(for ($i = 0; $i -lt $usb.Count; $i++) { $d = $usb[$i]; $box = [string](Key $d.InstanceId ContainerId)
          if (-not $boxes.ContainsKey($box)) { $boxes[$box] = $boxes.Count }
          [pscustomobject]@{ id = ($d.InstanceId -split '\\')[1]; class = $d.Class; name = $d.FriendlyName
                             service = $d.Service; own = Key $d.InstanceId BusReportedDeviceDesc
                             parent = At (Key $d.InstanceId Parent); box = $boxes[$box]
                             local = (Key $d.InstanceId InLocalMachineContainer) -eq $true
                             problem = [int]$d.ConfigManagerErrorCode } })
  problems = @(Get-PnpDevice -PresentOnly | Where-Object { [int]$_.ConfigManagerErrorCode -ne 0 -and
          $_.InstanceId -match '^(PCI|ACPI|HDAUDIO|DISPLAY|SCSI)\\' } | ForEach-Object { [pscustomobject]@{
          name = $_.FriendlyName; problem = [int]$_.ConfigManagerErrorCode } })
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
TIMEOUT = 30                            # s: CIM answered in about five seconds on the Ally, docked (02-11-2026)
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
WIRED = "802.3"                         # Get-NetAdapter's PhysicalMediaType of an Ethernet adapter
# The devices this suite's apps work with, by their USB ID: their own names say nothing ("USB Boot", "UsbMonitor")
KNOWN = {"VID_05A9&PID_0580": "PlayStation camera without its firmware",     # its boot loader: USB HD Cam loads it
         "VID_05A9&PID_058C": "PS5 HD Camera", "VID_1A86&PID_5722": "Turzx USB screen"}
# Device Manager's problem codes (CM_PROB_*), as its yellow mark says them
PROBLEMS = {1: "not configured", 10: "cannot start", 22: "disabled", 28: "no driver", 31: "the driver did not load",
            43: "stopped after an error"}
# Names Windows gives any device of a kind: the device's own name, or its maker, says more
# (Windows' English names; in another language the name stays as Windows gives it)
GENERIC = re.compile(r"^(USB (Composite|Input|Mass Storage|Serial) Device|Generic .*Hub|HID-compliant"
                     r"|USB Attached SCSI)", re.IGNORECASE)
STORAGE = {"USBSTOR", "UASPSTOR"}       # the drivers of a USB drive: the Drives row has it
PAD = re.compile(r"game ?pad|controller", re.IGNORECASE)

Run = Callable[[list[str]], str]


@dataclass
class Adapter:
    """A network adapter that is not Wi-Fi."""

    name: str
    status: str = ""                    # Get-NetAdapter's Status: Up, Disconnected, Disabled
    speed: int = 0                      # bit/s, while it is up
    media: str = WIRED
    device: int = -1                    # its USB device in Device.plugged, -1 when it is not on USB

    @property
    def state(self) -> str:
        if self.status == "Up":
            return f"connected, {rate(self.speed)}" if self.speed else "connected"
        if self.status == "Disabled":
            return "disabled"
        return "no cable" if self.media == WIRED else "not connected"


@dataclass
class Plugged:
    """A USB device as Windows lists it: a device of its own or one part (an interface) of one."""

    id: str                             # VID_0BDA&PID_8153, without the instance's serial number
    kind: str = ""                      # Windows' class: Net, Camera, Ports, USB ...
    service: str = ""                   # its driver: USBHUB3 for a hub, in any Windows language
    name: str = ""                      # Windows' name for it
    own: str = ""                       # the name the device gives itself (BusReportedDeviceDesc)
    parent: int = -1                    # the device it is plugged into, in Device.plugged
    box: int = 0                        # its container: the parts of one device, or of one dock, share it
    local: bool = False                 # built in: the computer's own container
    problem: int = 0                    # Device Manager's problem code, 0 without one

    @property
    def hub(self) -> bool:
        return self.service.upper().startswith("USBHUB")


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
    network: list[Adapter] = field(default_factory=list)               # the other built-in adapters
    usb_network: list[Adapter] = field(default_factory=list)           # on USB (a dock's Ethernet port)
    plugged: list[Plugged] = field(default_factory=list)               # every USB device, built in or plugged in
    problems: list[tuple[str, int]] = field(default_factory=list)      # other built-in devices: name, problem code
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
        """The device's name: the family Windows gives (ROG XBOX Ally X), else the maker and model."""
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
        pads = names([part.name for part in self.plugged if part.local and PAD.search(part.name)])
        problems = [(part.name or part.own, part.problem) for part in self.plugged if part.local and part.problem]
        rows = [("Panel", panel), ("Touch", touch), ("Controller", ", ".join(pads)),
                ("Wi-Fi", ", ".join(f"{name}, driver {driver}" if driver else name for name, driver in self.wifi)),
                ("Network", ", ".join(f"{adapter.name} ({adapter.state})" for adapter in self.network)),
                ("Bluetooth", ", ".join(self.bluetooth)), ("Audio", ", ".join(self.audio)),
                ("Fingerprint", ", ".join(self.fingerprint)), ("Camera", ", ".join(self.camera)),
                ("Sensors", ", ".join(self.sensors)), ("USB", ", ".join(self.usb)),
                ("Problems", ", ".join(f"{name or 'a device without a name'} ({problem_text(code)})"
                                       for name, code in problems + self.problems))]
        return [(label, value) for label, value in rows if value]

    def connected_rows(self) -> list[tuple[str, str]]:
        """What the Connected card shows: what is plugged in. A dock is a USB hub with its ports behind it, and
        Windows does not tell a dock from a hub: the hub's chip and the devices behind it are what shows."""
        hubs: dict[int, list[Plugged]] = {}
        devices: dict[int, list[int]] = {}
        for index, part in enumerate(self.plugged):
            if not part.local:
                if part.hub:
                    hubs.setdefault(part.box, []).append(part)
                else:
                    devices.setdefault(part.box, []).append(index)
        shown = []
        for indexes in devices.values():
            parts = [self.plugged[index] for index in indexes]
            if any(part.kind in ("Net", "DiskDrive", "SCSIAdapter") or part.service.upper() in STORAGE
                   for part in parts):
                continue                                # the Network and Drives rows have it
            notes = [problem_text(next((part.problem for part in parts if part.problem), 0))]
            notes.append("via the hub" if any(self.behind_hub(index) for index in indexes) else "")
            notes = [note for note in notes if note]
            shown.append(device_name(parts) + (f" ({', '.join(notes)})" if notes else ""))
        network = [f"{adapter.name} ({adapter.state}" + (", via the hub)" if self.behind_hub(adapter.device) else ")")
                   for adapter in self.usb_network]
        rows = [("Dock or hub", ", ".join(hub_text(parts) for parts in hubs.values())),
                ("Devices", ", ".join(shown)),
                ("Screens", ", ".join(f"{name}, {output}" if output else name for name, output in self.screens)),
                ("Network", ", ".join(network)),
                ("Drives", ", ".join(f"{size / 1e9:.0f} GB, {model}" for model, size in self.external_disks))]
        return [(label, value) for label, value in rows if value]

    def behind_hub(self, index: int) -> bool:
        """Whether the USB device *index* is plugged into a hub that is plugged in (a dock's), not into the
        handheld's own port."""
        seen: set[int] = set()
        index = self.plugged[index].parent if 0 <= index < len(self.plugged) else -1
        while 0 <= index < len(self.plugged) and index not in seen:
            seen.add(index)
            part = self.plugged[index]
            if part.hub and not part.local:
                return True
            index = part.parent
        return False

    def report(self) -> str:
        return "\n".join(f"{label}: {value}"
                         for label, value in self.rows() + self.hardware_rows() + self.connected_rows())


def rate(bits: int) -> str:
    """A link's speed: 1 Gbps, 2.5 Gbps, 100 Mbps."""
    if bits >= 1_000_000_000:
        return f"{bits / 1e9:g} Gbps"
    return f"{bits / 1e6:g} Mbps"


def problem_text(code: int) -> str:
    """Device Manager's problem, in words; "" without one."""
    return "" if not code else PROBLEMS.get(code, f"problem code {code}")


def maker(usb_id: str) -> str:
    """The maker of a USB device by its vendor ID (VID_0BDA&PID_5411: Realtek)."""
    vendor = re.match(r"VID_([0-9A-F]{4})", usb_id.upper())
    if not vendor:
        return "an unknown maker"
    return VENDORS.get(vendor.group(1), f"vendor {vendor.group(1)}")


def hub_text(parts: list[Plugged]) -> str:
    """A dock or hub as Windows sees it: the maker of its hub chip and its speeds, "Realtek hub chip (USB 3, USB 2)".
    The dock's own brand is not reported."""
    makers = names([maker(part.id) for part in parts])
    speeds = sorted({"USB 3" if "SuperSpeed" in part.name or part.own.upper().startswith("USB3") else "USB 2"
                     for part in parts}, reverse=True)
    return f"{' and '.join(makers)} hub chip ({', '.join(speeds)})"


def device_name(parts: list[Plugged]) -> str:
    """The best name of a device from its parts: a device this suite knows, a name that is more than its kind (USB
    Composite Device), the name the device gives itself, else its maker."""
    for part in parts:
        if part.id in KNOWN:
            return KNOWN[part.id]
    for part in sorted(parts, key=lambda part: part.kind in ("USB", "HIDClass", "")):
        if part.name and not GENERIC.match(part.name):
            return part.name
    for part in parts:
        if part.own and not GENERIC.match(part.own):
            return part.own
    return f"a USB device by {maker(parts[0].id)}"


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
            found = Adapter(re.sub(r" #\d+$", "", name),                         # "... Controller #2"
                            status=adapter.get("status") or ("Up" if adapter.get("up") else "Disconnected"),
                            speed=int(adapter.get("speed") or 0), media=adapter.get("media") or "",
                            device=_index(adapter.get("device")))
            (device.usb_network if adapter.get("usb") else device.network).append(found)
    for key in ("bluetooth", "audio", "touch", "fingerprint", "camera", "sensors", "usb"):
        setattr(device, key, names(data.get(key)))
    device.plugged = [Plugged(str(part.get("id") or "").upper(), kind=part.get("class") or "",
                              service=part.get("service") or "", name=(part.get("name") or "").strip(),
                              own=(part.get("own") or "").strip(),
                              parent=_index(part.get("parent")), box=int(part.get("box") or 0),
                              local=bool(part.get("local")), problem=int(part.get("problem") or 0))
                      for part in _list(data.get("plugged"))]
    device.problems = [((part.get("name") or "").strip(), int(part.get("problem") or 0))
                       for part in _list(data.get("problems")) if part.get("problem")]
    for screen in _list(data.get("screens")):
        output = int(screen.get("output") or 0)
        if output & INTERNAL:
            continue                                    # the built-in panel: the Hardware card's
        device.screens.append(((screen.get("name") or "").strip() or "a screen", OUTPUTS.get(output, "")))
    return device


def _index(value) -> int:
    """A device's number in the query's list; -1 for none."""
    return -1 if value is None else int(value)


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
    """The device, read now (about five seconds: call it off the window's thread)."""
    device = parse(run(powershell_argv(QUERY)))
    device.touch_points = touches()
    return device
