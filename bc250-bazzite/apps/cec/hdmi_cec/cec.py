# SPDX-License-Identifier: GPL-3.0-or-later
"""The CEC adapters of this machine and the messages the app sends, through cec-ctl (v4l-utils, in Bazzite).

`cec-ctl -d /dev/cecN` with no message only prints the adapter's state; nothing goes on the bus. The messages are
the plain CEC ones: Image View On, Active Source, Standby, Give Device Power Status, a poll and the volume keys.
/dev/cec* belongs to the logged-in user (udev uaccess), so none of this needs root.

On the BC-250 the adapter is amdgpu's own (CEC tunnelled over the DisplayPort AUX channel): it exists only when the
DP-to-HDMI converter in the cable or adapter reports CEC tunnelling, and it reaches the TV only when that converter
also wires the CEC line."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CEC_CTL = "cec-ctl"
OSD_NAME = "BC-250"                     # the name the TV shows for the board, unless the user set another
NO_ADDRESS = "f.f.f.f"
TV = 0                                  # logical addresses
AUDIO_SYSTEM = 5
BROADCAST = 15

# CEC UI commands (CEC 1.4 table 27), as cec-ctl names them: what a remote's key press arrives as.
UI_COMMANDS = {
    0x00: "select", 0x01: "up", 0x02: "down", 0x03: "left", 0x04: "right", 0x05: "right-up", 0x06: "right-down",
    0x07: "left-up", 0x08: "left-down", 0x09: "device-root-menu", 0x0A: "device-setup-menu", 0x0B: "contents-menu",
    0x0C: "favorite-menu", 0x0D: "back", 0x10: "media-top-menu", 0x11: "media-context-sensitive-menu",
    0x1D: "number-entry-mode", 0x1E: "number-11", 0x1F: "number-12", 0x20: "number-0", 0x21: "number-1",
    0x22: "number-2", 0x23: "number-3", 0x24: "number-4", 0x25: "number-5", 0x26: "number-6", 0x27: "number-7",
    0x28: "number-8", 0x29: "number-9", 0x2A: "dot", 0x2B: "enter", 0x2C: "clear", 0x2F: "next-favorite",
    0x30: "channel-up", 0x31: "channel-down", 0x32: "previous-channel", 0x33: "sound-select", 0x34: "input-select",
    0x35: "display-information", 0x36: "help", 0x37: "page-up", 0x38: "page-down", 0x40: "power",
    0x41: "volume-up", 0x42: "volume-down", 0x43: "mute", 0x44: "play", 0x45: "stop", 0x46: "pause",
    0x47: "record", 0x48: "rewind", 0x49: "fast-forward", 0x4A: "eject", 0x4B: "skip-forward",
    0x4C: "skip-backward", 0x4D: "stop-record", 0x4E: "pause-record", 0x50: "angle", 0x51: "sub-picture",
    0x52: "video-on-demand", 0x53: "electronic-program-guide", 0x54: "timer-programming",
    0x55: "initial-configuration", 0x56: "select-broadcast-type", 0x57: "select-sound-presentation",
    0x58: "audio-description", 0x59: "internet", 0x5A: "3d-mode", 0x60: "play-function",
    0x61: "pause-play-function", 0x62: "record-function", 0x63: "pause-record-function", 0x64: "stop-function",
    0x65: "mute-function", 0x66: "restore-volume-function", 0x67: "tune-function", 0x68: "select-media-function",
    0x69: "select-av-input-function", 0x6A: "select-audio-input-function", 0x6B: "power-toggle-function",
    0x6C: "power-off-function", 0x6D: "power-on-function", 0x71: "f1-blue", 0x72: "f2-red", 0x73: "f3-green",
    0x74: "f4-yellow", 0x75: "f5", 0x76: "data",
}

_FIELD = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z ]*?)\s*:\s*(?P<value>.*?)\s*$")
_TOPOLOGY = re.compile(r"^\s*(?P<address>[0-9a-f]\.[0-9a-f]\.[0-9a-f]\.[0-9a-f]):\s*(?P<name>.+?)\s*$")
_TX_FAILED = re.compile(r"^\s*Tx, (?!OK)", re.M)
_POWER = re.compile(r"pwr-state:\s*(?P<state>[a-z][a-z -]*?)\s*\(0x", re.I)


@dataclass(frozen=True)
class Adapter:
    device: str                                     # /dev/cec0
    driver: str = ""                                # amdgpu
    name: str = ""                                  # the connector for a GPU adapter: DP-1
    physical_address: str = NO_ADDRESS              # from the display's EDID; f.f.f.f when none is seen
    logical_addresses: tuple[str, ...] = ()         # "4 (Playback Device 1)": empty until configured
    osd_name: str = ""
    connector: str = ""                             # "card 1, connector 87"
    capabilities: tuple[str, ...] = field(default=())

    @property
    def has_display(self) -> bool:
        return self.physical_address not in ("", NO_ADDRESS)

    @property
    def configured(self) -> bool:
        return bool(self.logical_addresses)


def devices(dev_root: Path = Path("/dev")) -> list[str]:
    """/dev/cec0, /dev/cec1, … in number order."""
    found = [p for p in dev_root.glob("cec*") if p.name[3:].isdigit()]
    return [str(p) for p in sorted(found, key=lambda p: int(p.name[3:]))]


def pick(adapters: list[Adapter]) -> Adapter | None:
    """The adapter to use when there are several (amdgpu's and a USB one, or one for each display output): the
    first that sees a display, else the first."""
    return next((a for a in adapters if a.has_display), adapters[0] if adapters else None)


def parse_info(device: str, text: str) -> Adapter:
    """The Driver Info block that cec-ctl prints for an adapter."""
    values: dict[str, str] = {}
    logical: list[str] = []
    capabilities: list[str] = []
    in_caps = False
    for line in text.splitlines():
        match = _FIELD.match(line)
        if match is None:
            if in_caps and line.strip():
                capabilities.append(line.strip())
            continue
        key, value = match["key"], match["value"]
        in_caps = key == "Capabilities"
        if key == "Logical Address":
            logical.append(value)
        else:
            values.setdefault(key, value)
    return Adapter(device=device, driver=values.get("Driver Name", ""), name=values.get("Adapter Name", ""),
                   physical_address=values.get("Physical Address", NO_ADDRESS),
                   logical_addresses=tuple(logical), osd_name=values.get("OSD Name", "").strip("'"),
                   connector=values.get("DRM Connector Info", ""), capabilities=tuple(capabilities))


def parse_topology(text: str) -> list[tuple[str, str]]:
    """The devices under "Topology:" in cec-ctl --show-topology: (physical address, what it is)."""
    _head, found, tail = text.partition("Topology:")
    if not found:
        return []
    return [(m["address"], m["name"]) for m in map(_TOPOLOGY.match, tail.splitlines()) if m]


def acked(text: str) -> bool:
    """Whether the other end took the message. cec-ctl exits 0 either way; it prints a "Tx, …" status line when the
    transmit failed ("Tx, Not Acknowledged (1), Max Retries" when no device answered), or when it went out but the
    reply did not come as asked ("Tx, OK, Rx, OK, Feature Abort": the device does not support the message)."""
    return "Sequence:" in text and _TX_FAILED.search(text) is None


def power_status(text: str) -> str:
    """The TV's answer to Give Device Power Status: "on", "standby", "to-on", …; "" without an answer."""
    match = _POWER.search(text)
    return match["state"].strip().lower() if match else ""


def ui_command_name(code: int) -> str:
    return UI_COMMANDS.get(code, f"0x{code:02x}")


# --- The messages, as cec-ctl arguments ---------------------------------------------------------------------------

def info(device: str) -> list[str]:
    return ["-d", device]


def needs_name(adapter: Adapter, name: str) -> bool:
    """Whether the app should (re)configure the adapter: it has no logical address, or another name than the one the
    TV should show (cec-ctl --playback without --osd-name leaves "Playback", and the TV then lists that)."""
    return not adapter.configured or adapter.osd_name != name


def configure(device: str, name: str = OSD_NAME) -> list[str]:
    """Claim a logical address as a playback device, as Bazzite's cec-control does, when nothing has yet."""
    return ["-d", device, "--playback", "--osd-name", name]


def set_osd_name(device: str, name: str) -> list[str]:
    """Tells the TV the board's name now (TVs otherwise ask when the cable is plugged in)."""
    return ["-d", device, "-s", "--to", str(TV), "--set-osd-name", f"name={name}"]


def topology(device: str) -> list[str]:
    return ["-d", device, "--show-topology"]


def poll(device: str, to: int = TV) -> list[str]:
    return ["-d", device, "-s", "--poll", "--to", str(to)]


def give_power_status(device: str, to: int = TV) -> list[str]:
    return ["-d", device, "-s", "--to", str(to), "--give-device-power-status"]


def image_view_on(device: str) -> list[str]:
    return ["-d", device, "-s", "--to", str(TV), "--image-view-on"]


def active_source(device: str, physical_address: str) -> list[str]:
    """Tells every device that this board is the source to show: the TV switches its input to it."""
    return ["-d", device, "-s", "--to", str(BROADCAST), "--active-source", f"phys-addr={physical_address}"]


def standby(device: str, to: int = TV) -> list[str]:
    return ["-d", device, "-s", "--to", str(to), "--standby"]


def key_press(device: str, to: int, ui_cmd: str) -> list[str]:
    return ["-d", device, "-s", "--to", str(to), "--user-control-pressed", f"ui-cmd={ui_cmd}"]


def key_release(device: str, to: int) -> list[str]:
    return ["-d", device, "-s", "--to", str(to), "--user-control-released"]


# --- The display at the other end --------------------------------------------------------------------------------

def edid_name(edid: bytes) -> str:
    """The monitor name descriptor (tag 0xFC) of an EDID base block: "Mi TV"; "" when there is none."""
    if len(edid) < 128:
        return ""
    for start in range(54, 126, 18):
        block = edid[start:start + 18]
        if block[:3] == b"\0\0\0" and block[3] == 0xFC:
            return block[5:18].split(b"\n", 1)[0].decode("ascii", "replace").strip()
    return ""


def display_name(adapter_name: str, sys_root: Path = Path("/sys")) -> str:
    """The name in the EDID of the display on the adapter's connector (amdgpu names the adapter after it)."""
    if not adapter_name:
        return ""
    for edid in sorted((sys_root / "class/drm").glob(f"card*-{adapter_name}/edid")):
        try:
            name = edid_name(edid.read_bytes())
        except OSError:
            continue
        if name:
            return name
    return ""
