# SPDX-License-Identifier: GPL-3.0-or-later
"""The network, measured on A: the Wi-Fi link (band, channel, standard, signal, rates), a wired link (an Ethernet
adapter on USB or a dock's port, and its speed), the power plan's Wi-Fi setting on mains and on battery, what else is
downloading, and a timed download of this app's newest release from GitHub over each connected adapter in turn, so a
slow moment can be compared with a fast one and Wi-Fi with the cable (the owner's Ally, 28-10-2026: the portal's
update came in at 0.8 MB/s where curl had 69 MB/s an hour later).

Each download goes out from its adapter's IPv4 address, which makes Windows send it over that adapter. The address is
only used for that: it is never shown, logged or saved.

The link and the power setting come from Windows' own APIs (wlanapi, powrprof) rather than netsh and powercfg, whose
labels are in Windows' language. The network's name and its access point's address are never read out: the access
point is only matched in Windows' list to find the frequency it is on."""

from __future__ import annotations

import ctypes
import functools
import http.client
import json
import subprocess
import sys
import time
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from bc250_core.appinfo import SUITE_REPO_URL
from bc250_core.platform import powershell_argv
from bc250_core.updates import latest_release, repo_slug

from .device import names, rate, run_powershell

# What else is downloading: the bytes every connected adapter received in SAMPLE seconds, Delivery Optimization's
# downloads (Windows Update, the Microsoft Store and the XBOX app's games) and the programs that download on their own;
# and the adapters that reach the internet (a default gateway), Windows' first choice first
QUERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$names = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object Name)
function Received { [int64](Get-NetAdapterStatistics -Name $names | Measure-Object -Property ReceivedBytes -Sum).Sum }
$before = Received
$clock = [Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Milliseconds SAMPLE_MS
$after = Received
[pscustomobject]@{
  received = $after - $before; seconds = $clock.Elapsed.TotalSeconds
  delivery = @(Get-DeliveryOptimizationStatus | Where-Object Status -eq 'Downloading').Count
  running = @(Get-Process -Name PROCESSES | ForEach-Object Name | Sort-Object -Unique)
  adapters = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
          Sort-Object { $_.NetIPv4Interface.InterfaceMetric } | ForEach-Object { [pscustomobject]@{
          name = $_.InterfaceDescription; media = [string]$_.NetAdapter.PhysicalMediaType
          speed = [int64]$_.NetAdapter.ReceiveLinkSpeed; source = @($_.IPv4Address)[0].IPAddress } })
} | ConvertTo-Json -Compress
"""
SAMPLE = 2.0                            # s: what the adapters receive before the download
DOWNLOAD_SECONDS = 10                   # the timed download stops after this, or at the end of the file
TAG_PREFIX = "wp-test-v"                # this app's releases: about 50 MB, from GitHub as the portal downloads them
USER_AGENT = "windows-portable-test"
MB = 1_000_000                          # MB as the portal shows a download
# The programs that download on their own, by their process name
DOWNLOADERS = {"steam": "Steam", "XBOXPcApp": "XBOX app", "EpicGamesLauncher": "Epic Games Launcher",
               "GalaxyClient": "GOG Galaxy", "Battle.net": "Battle.net", "EADesktop": "EA app",
               "upc": "Ubisoft Connect", "MoUsoCoreWorker": "Windows Update"}
# DOT11_PHY_TYPE: the Wi-Fi standard of the link
STANDARDS = {4: "802.11a", 5: "802.11b", 6: "802.11g", 7: "Wi-Fi 4 (802.11n)", 8: "Wi-Fi 5 (802.11ac)",
             10: "Wi-Fi 6 (802.11ax)", 11: "Wi-Fi 7 (802.11be)"}
# The power plan's Wireless Adapter Settings, Power Saving Mode, and its four values
WIRELESS_SUBGROUP = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"
POWER_SAVING_MODE = "12bbebe6-58d6-4636-95bb-3217ef867c1a"
POWER_SAVING = {0: "Maximum Performance", 1: "Low Power Saving", 2: "Medium Power Saving", 3: "Maximum Power Saving"}
WIRELESS = "Native 802.11"              # Get-NetAdapter's PhysicalMediaType of a Wi-Fi adapter


@dataclass
class Link:
    """The Wi-Fi connection as the adapter reports it."""

    frequency: int = 0                  # MHz, 0 when Windows did not list the access point
    channel: int = 0
    standard: int = 0                   # DOT11_PHY_TYPE
    signal: int = 0                     # percent
    rssi: int = 0                       # dBm, 0 when unknown
    receive: int = 0                    # Mbps
    transmit: int = 0

    @property
    def band(self) -> str:
        if not self.frequency:
            return ""
        return "2.4 GHz" if self.frequency < 3000 else "5 GHz" if self.frequency < 5925 else "6 GHz"


@dataclass
class Adapter:
    """An adapter that reaches the internet."""

    name: str
    media: str = ""                                     # Get-NetAdapter's PhysicalMediaType
    speed: int = 0                                      # bit/s
    source: str = field(default="", repr=False)         # its IPv4 address: the download's, never shown

    @property
    def kind(self) -> str:
        return "Wi-Fi" if self.media == WIRELESS else "wired"


@dataclass
class Download:
    """One timed download; *kind* is the adapter's (Wi-Fi, wired), "" when Windows chose it."""

    kind: str = ""
    downloaded: int = 0                                 # bytes
    seconds: float = 0.0
    error: str = ""                                     # why it failed

    @property
    def speed(self) -> float:
        """MB/s."""
        return self.downloaded / MB / self.seconds if self.seconds else 0.0

    def text(self) -> str:
        if self.error:
            return f"failed: {self.error}"
        return f"{self.speed:.1f} MB/s ({self.downloaded / MB:.1f} MB in {self.seconds:.1f} s)" if self.seconds else ""


@dataclass
class Network:
    power: str = ""                                     # "mains, 100%" or "battery, 82%" (power_text)
    adapter: str = ""                                   # the Wi-Fi adapter, "" without one
    link: Link | None = None                            # None: no Wi-Fi connection
    plan: str = ""                                      # the power plan's name
    wifi_power: tuple[int, int] | None = None           # Power Saving Mode on mains, on battery
    other: float | None = None                          # MB/s the adapters received before the download
    delivery: int = 0                                   # Delivery Optimization's downloads
    running: list[str] = field(default_factory=list)    # the programs that download on their own
    adapters: list[Adapter] = field(default_factory=list)    # the ones that reach the internet, Windows' first first
    downloads: list[Download] = field(default_factory=list)  # one per adapter

    def rows(self) -> list[tuple[str, str]]:
        """What the Network card shows, a label and a value each."""
        link = self.link
        if link is None:
            wifi = "not connected" if self.adapter else "no Wi-Fi adapter"
            rows = [("Wi-Fi", wifi)]
        else:
            where = ", ".join(part for part in (link.band, f"channel {link.channel}" if link.channel else "") if part)
            signal = f"{link.signal}%" + (f", {link.rssi} dBm" if link.rssi else "")
            rows = [("Wi-Fi", where), ("Standard", STANDARDS.get(link.standard, "")), ("Signal", signal),
                    ("Rate", f"{link.receive} Mbps down, {link.transmit} up")]
        rows.append(("Wired", ", ".join(f"{adapter.name}, {rate(adapter.speed)}" if adapter.speed else adapter.name
                                        for adapter in self.adapters if adapter.kind == "wired")))
        rows.append(("Power", ", ".join(part for part in (self.power, f"{self.plan} plan" if self.plan else "")
                                        if part)))
        if self.wifi_power is not None:
            mains, battery = (POWER_SAVING.get(value, str(value)) for value in self.wifi_power)
            rows += [("Wi-Fi on mains", mains), ("Wi-Fi on battery", battery)]
        if self.other is not None:
            rows.append(("Other traffic", f"{self.other:.2f} MB/s before the download"))
        busy = ([f"Delivery Optimization ({self.delivery} download{'s' if self.delivery != 1 else ''})"]
                if self.delivery else []) + self.running
        rows.append(("Also running", ", ".join(busy) or "nothing that downloads"))
        kinds = [download.kind for download in self.downloads]
        for n, download in enumerate(self.downloads):
            label = f"Download, {download.kind}" if download.kind else "Download"
            if kinds.count(download.kind) > 1:
                label += f" {kinds[:n + 1].count(download.kind)}"                   # two wired adapters
            rows.append((label, download.text()))
        return [(label, value) for label, value in rows if value]

    @property
    def error(self) -> str:
        """Why the downloads failed, "" when one of them worked."""
        if any(not download.error for download in self.downloads):
            return ""
        return "; ".join(names([download.error for download in self.downloads]))


def power_text(state: tuple[int, bool] | None) -> str:
    """Mains or battery for the Power row, from power.battery(): "battery, 82%"; "" without a battery."""
    if state is None:
        return ""
    percent, plugged = state
    return f"{'mains' if plugged else 'battery'}, {percent}%"


def parse_traffic(text: str, network: Network) -> None:
    """The query's JSON into *network*: the other traffic, Delivery Optimization, the programs running and the
    adapters that reach the internet."""
    data = json.loads(text)
    seconds = float(data.get("seconds") or 0)
    if seconds > 0:
        network.other = max(0, int(data.get("received") or 0)) / MB / seconds
    network.delivery = int(data.get("delivery") or 0)
    running = data.get("running") or []
    names = {name.lower(): shown for name, shown in DOWNLOADERS.items()}
    network.running = [names[name.lower()] for name in (running if isinstance(running, list) else [running])
                       if str(name).lower() in names]
    adapters = data.get("adapters") or []
    network.adapters = [Adapter((adapter.get("name") or "").strip(), media=adapter.get("media") or "",
                                speed=int(adapter.get("speed") or 0), source=adapter.get("source") or "")
                        for adapter in (adapters if isinstance(adapters, list) else [adapters])
                        if adapter.get("source")]


def traffic_query() -> str:
    return QUERY.replace("SAMPLE_MS", str(round(SAMPLE * 1000))).replace("PROCESSES", ", ".join(DOWNLOADERS))


# Windows' Native Wi-Fi API (wlanapi) and power API (powrprof), through ctypes

class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> _GUID:
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), uuid.UUID(text).bytes_le, ctypes.sizeof(cls))
        return guid


class _Interface(ctypes.Structure):           # WLAN_INTERFACE_INFO
    _fields_ = [("guid", _GUID), ("description", ctypes.c_wchar * 256), ("state", ctypes.c_int)]


class _Interfaces(ctypes.Structure):          # WLAN_INTERFACE_INFO_LIST
    _fields_ = [("count", ctypes.c_ulong), ("index", ctypes.c_ulong), ("items", _Interface * 1)]


class _SSID(ctypes.Structure):                # DOT11_SSID
    _fields_ = [("length", ctypes.c_ulong), ("ssid", ctypes.c_ubyte * 32)]


class _Association(ctypes.Structure):         # WLAN_ASSOCIATION_ATTRIBUTES
    _fields_ = [("ssid", _SSID), ("bss_type", ctypes.c_int), ("bssid", ctypes.c_ubyte * 6),
                ("phy_type", ctypes.c_int), ("phy_index", ctypes.c_ulong), ("quality", ctypes.c_ulong),
                ("receive", ctypes.c_ulong), ("transmit", ctypes.c_ulong)]


class _Connection(ctypes.Structure):          # WLAN_CONNECTION_ATTRIBUTES
    _fields_ = [("state", ctypes.c_int), ("mode", ctypes.c_int), ("profile", ctypes.c_wchar * 256),
                ("association", _Association), ("security_enabled", ctypes.c_int), ("onex", ctypes.c_int),
                ("auth", ctypes.c_int), ("cipher", ctypes.c_int)]


class _Bss(ctypes.Structure):                 # WLAN_BSS_ENTRY
    _fields_ = [("ssid", _SSID), ("phy_id", ctypes.c_ulong), ("bssid", ctypes.c_ubyte * 6),
                ("bss_type", ctypes.c_int), ("phy_type", ctypes.c_int), ("rssi", ctypes.c_long),
                ("quality", ctypes.c_ulong), ("in_domain", ctypes.c_ubyte), ("beacon", ctypes.c_ushort),
                ("timestamp", ctypes.c_ulonglong), ("host_timestamp", ctypes.c_ulonglong),
                ("capability", ctypes.c_ushort), ("frequency", ctypes.c_ulong), ("rates", ctypes.c_ulong),
                ("rate_set", ctypes.c_ushort * 126), ("ie_offset", ctypes.c_ulong), ("ie_size", ctypes.c_ulong)]


class _BssList(ctypes.Structure):             # WLAN_BSS_LIST
    _fields_ = [("size", ctypes.c_ulong), ("count", ctypes.c_ulong), ("items", _Bss * 1)]


CONNECTED = 1                       # WLAN_INTERFACE_STATE: wlan_interface_state_connected
CURRENT_CONNECTION, CHANNEL = 7, 8  # WLAN_INTF_OPCODE


def _items(head, kind, count: int):
    """The variable-length array at the end of a wlanapi list."""
    return ctypes.cast(ctypes.addressof(head), ctypes.POINTER(kind * count)).contents if count else []


def wifi() -> tuple[str, Link | None]:
    """The Wi-Fi adapter and its link; ("", None) without an adapter, or not on Windows."""
    if sys.platform != "win32":
        return "", None
    api = ctypes.WinDLL("wlanapi")
    handle, version = ctypes.c_void_p(), ctypes.c_ulong()
    if api.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        return "", None                 # no WLAN service: no Wi-Fi adapter
    found: tuple[str, Link | None] = ("", None)
    try:
        interfaces = ctypes.POINTER(_Interfaces)()
        if api.WlanEnumInterfaces(handle, None, ctypes.byref(interfaces)):
            return found
        try:
            for interface in _items(interfaces.contents.items, _Interface, interfaces.contents.count):
                found = (interface.description, None)
                if interface.state == CONNECTED:
                    return interface.description, _link(api, handle, interface.guid)
        finally:
            api.WlanFreeMemory(interfaces)
    finally:
        api.WlanCloseHandle(handle, None)
    return found


def _link(api, handle, guid: _GUID) -> Link | None:
    size, data = ctypes.c_ulong(), ctypes.c_void_p()
    if api.WlanQueryInterface(handle, ctypes.byref(guid), CURRENT_CONNECTION, None, ctypes.byref(size),
                              ctypes.byref(data), None):
        return None
    try:
        connection = ctypes.cast(data, ctypes.POINTER(_Connection)).contents
        association = connection.association
        link = Link(standard=association.phy_type, signal=association.quality,
                    receive=association.receive // 1000, transmit=association.transmit // 1000)   # kbps
        bss = ctypes.POINTER(_BssList)()
        if not api.WlanGetNetworkBssList(handle, ctypes.byref(guid), ctypes.byref(association.ssid),
                                         association.bss_type, connection.security_enabled, None, ctypes.byref(bss)):
            try:
                for entry in _items(bss.contents.items, _Bss, bss.contents.count):
                    if bytes(entry.bssid) == bytes(association.bssid):          # the access point it is on
                        link.frequency, link.rssi = entry.frequency // 1000, entry.rssi     # kHz
                        break
            finally:
                api.WlanFreeMemory(bss)
    finally:
        api.WlanFreeMemory(data)
    channel = ctypes.c_void_p()
    if not api.WlanQueryInterface(handle, ctypes.byref(guid), CHANNEL, None, ctypes.byref(size),
                                  ctypes.byref(channel), None):
        link.channel = ctypes.cast(channel, ctypes.POINTER(ctypes.c_ulong)).contents.value
        api.WlanFreeMemory(channel)
    return link


def wifi_power() -> tuple[str, tuple[int, int] | None]:
    """The active power plan's name and its Wi-Fi Power Saving Mode on mains and on battery; ("", None) when the
    plan has no such setting, or not on Windows."""
    if sys.platform != "win32":
        return "", None
    api = ctypes.WinDLL("powrprof")
    active = ctypes.POINTER(_GUID)()
    if api.PowerGetActiveScheme(None, ctypes.byref(active)):
        return "", None
    try:
        subgroup, setting = _GUID.of(WIRELESS_SUBGROUP), _GUID.of(POWER_SAVING_MODE)
        mains, battery = ctypes.c_ulong(), ctypes.c_ulong()
        if (api.PowerReadACValueIndex(None, active, ctypes.byref(subgroup), ctypes.byref(setting), ctypes.byref(mains))
                or api.PowerReadDCValueIndex(None, active, ctypes.byref(subgroup), ctypes.byref(setting),
                                             ctypes.byref(battery))):
            return "", None
        name, size = ctypes.create_unicode_buffer(256), ctypes.c_ulong(512)
        if api.PowerReadFriendlyName(None, active, None, None, name, ctypes.byref(size)):
            name.value = ""
        return name.value, (mains.value, battery.value)
    finally:
        ctypes.windll.kernel32.LocalFree(active)  # type: ignore[attr-defined]


def release_url() -> str:
    """The zip of this app's newest release on GitHub."""
    release = latest_release(repo_slug(SUITE_REPO_URL), TAG_PREFIX, user_agent=USER_AGENT)
    if release.error or not release.asset_url:
        raise OSError(release.error or "the release has no zip")
    return release.asset_url


class _Through(urllib.request.HTTPSHandler):
    """HTTPS from one address of the device: Windows sends it over the adapter that has the address."""

    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def https_open(self, req):
        return self.do_open(functools.partial(http.client.HTTPSConnection, source_address=(self.source, 0)), req,
                            context=self._context)


def timed_download(url: str, source: str = "", seconds: float = DOWNLOAD_SECONDS,
                   clock: Callable[[], float] = time.perf_counter) -> tuple[int, float]:
    """The bytes *url* gave in at most *seconds*, and the seconds it took from the request on, over the adapter with
    the address *source* ("": the one Windows chooses). Nothing is kept."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start, got = clock(), 0
    opened = urllib.request.build_opener(_Through(source)).open if source else urllib.request.urlopen
    with opened(request, timeout=30) as response:
        while chunk := response.read(1 << 16):
            got += len(chunk)
            if clock() - start >= seconds:
                break
    return got, clock() - start


def measure(power: str, *, link: Callable[[], tuple[str, Link | None]] = wifi,
            plan: Callable[[], tuple[str, tuple[int, int] | None]] = wifi_power,
            run: Callable[[list[str]], str] = run_powershell, url: Callable[[], str] = release_url,
            download: Callable[[str, str], tuple[int, float]] = timed_download,
            say: Callable[[str], None] = lambda text: None) -> Network:
    """The network, measured now (a few seconds, plus ten at most for each adapter's download: call it off the
    window's thread). *say* tells what it is doing."""
    network = Network(power=power)
    say("Reading the Wi-Fi link ...")
    network.adapter, network.link = link()
    network.plan, network.wifi_power = plan()
    say(f"Measuring what else the network receives for {SAMPLE:.0f} seconds ...")
    try:
        parse_traffic(run(powershell_argv(traffic_query())), network)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        pass                            # the rows leave it out
    try:
        address = url()
    except OSError as error:
        network.downloads = [Download(error=reason(error))]
        return network
    # Each adapter in turn; without the list (the query failed), the one Windows chooses
    for adapter in network.adapters or [Adapter("")]:
        found = Download(adapter.kind if adapter.source else "")
        over = f" over {adapter.kind}" if adapter.source else ""
        say(f"Downloading{over} for up to {DOWNLOAD_SECONDS} seconds ...")
        try:
            found.downloaded, found.seconds = download(address, adapter.source)
        except OSError as error:
            found.error = reason(error)
        network.downloads.append(found)
    return network


def reason(error: OSError) -> str:
    """Why a download failed: urllib's reason, else the error."""
    return str(getattr(error, "reason", "") or error) or type(error).__name__
