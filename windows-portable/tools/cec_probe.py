#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""HDMI-CEC probe: can this handheld reach the TV's CEC through its USB-C to HDMI adapter?

    python windows-portable/tools/cec_probe.py              # read only
    python windows-portable/tools/cec_probe.py --ping       # also asks the TV
    python windows-portable/tools/cec_probe.py --ping --listen

Windows has no CEC support of its own. A USB-C to HDMI adapter is a DisplayPort to HDMI converter, and one that
reports CEC tunneling (DisplayPort 1.3, DPCD 0x3000 to 0x303F, the registers Linux's drm_dp_cec drives) carries CEC
over the link's AUX channel. AMD's driver reaches that channel: atiadlxx.dll exports
ADL_Display_NativeAUXChannel_Access, which AMD's public SDK leaves out; its struct (AuxData) is read from the
driver's code.

For every connected display it shows the connector, the HDMI physical address from the EDID, the DPCD revision,
the branch device (the converter chip: OUI, id, hardware and firmware), the downstream port and the CEC tunneling
capability. It also says whether a Pulse-Eight USB-CEC adapter (USB VID 2548) was ever plugged in.

--ping, on an adapter that reports tunneling, writes: tunneling on, logical address Playback 1, then polls the TV
and asks its power status and its name, and puts the two registers it changed back as they were. Only queries: the
TV's state does not change. --listen then prints every message on the line for 60 s (with snooping on). An address
NACK on the poll means the TV did not answer: CEC off on the TV, or an adapter, cable or input without the CEC line.

AMD GPUs only, 64-bit Python 3, no packages."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import POINTER, byref, c_char, c_int, c_ubyte, c_void_p, sizeof

ADL_MAX_PATH = 256


class AdapterInfo(ctypes.Structure):
    _fields_ = [("iSize", c_int), ("iAdapterIndex", c_int), ("strUDID", c_char * ADL_MAX_PATH),
                ("iBusNumber", c_int), ("iDeviceNumber", c_int), ("iFunctionNumber", c_int), ("iVendorID", c_int),
                ("strAdapterName", c_char * ADL_MAX_PATH), ("strDisplayName", c_char * ADL_MAX_PATH),
                ("iPresent", c_int), ("iExist", c_int), ("strDriverPath", c_char * ADL_MAX_PATH),
                ("strDriverPathExt", c_char * ADL_MAX_PATH), ("strPNPString", c_char * ADL_MAX_PATH),
                ("iOSDisplayIndex", c_int)]


class DisplayInfo(ctypes.Structure):
    _fields_ = [("iDisplayLogicalIndex", c_int), ("iDisplayPhysicalIndex", c_int),
                ("iDisplayLogicalAdapterIndex", c_int), ("iDisplayPhysicalAdapterIndex", c_int),
                ("iDisplayControllerIndex", c_int), ("strDisplayName", c_char * ADL_MAX_PATH),
                ("strDisplayManufacturerName", c_char * ADL_MAX_PATH), ("iDisplayType", c_int),
                ("iDisplayOutputType", c_int), ("iDisplayConnector", c_int), ("iDisplayInfoMask", c_int),
                ("iDisplayInfoValue", c_int)]


class AuxData(ctypes.Structure):
    # Not in AMD's public SDK; from the driver's code (atiadlxx.dll checks iSize == 0x24, copies back iStatus and,
    # after a read, iDataSize and cData). iCommand: AUX_READ, AUX_WRITE, 2 and 3 the same over I2C.
    _fields_ = [("iSize", c_int), ("iStatus", c_int), ("iCommand", c_int), ("iAddress", c_int),
                ("iDataSize", c_int), ("cData", c_ubyte * 16)]


class EdidData(ctypes.Structure):
    _fields_ = [("iSize", c_int), ("iFlag", c_int), ("iEDIDSize", c_int), ("iBlockIndex", c_int),
                ("cEDIDData", c_ubyte * 256), ("iReserved", c_int * 4)]


AUX_READ, AUX_WRITE = 0, 1
DISPLAY_CONNECTED = 0x01
CONNECTORS = {10: "HDMI", 15: "DisplayPort", 16: "eDP (internal)", 18: "USB-C"}
PORT_TYPES = {0: "DisplayPort", 1: "VGA", 2: "DVI", 3: "HDMI", 4: "other (no EDID)", 5: "DP++"}

# The DPCD registers, as Linux's drm_dp.h names them.
DPCD_REV, DOWNSTREAM_PORT, BRANCH_OUI = 0x0000, 0x0080, 0x0500
CEC_CAPABILITY, CEC_CONTROL, CEC_RX_INFO, CEC_TX_INFO, CEC_IRQ = 0x3000, 0x3001, 0x3002, 0x3003, 0x3004
CEC_LA_MASK, CEC_RX_BUFFER, CEC_TX_BUFFER = 0x300E, 0x3010, 0x3020
CEC_CAPABLE, CEC_SNOOPING, CEC_MULTIPLE_LA = 0x01, 0x02, 0x04
CEC_ENABLE, CEC_SNOOPING_ENABLE = 0x01, 0x02
IRQ_RX_VALID, IRQ_TX_SENT, IRQ_TX_LINE, IRQ_TX_ADDR_NACK, IRQ_TX_DATA_NACK = 0x01, 0x10, 0x20, 0x40, 0x80
TX_SEND, TX_RETRIES = 0x80, 2

TV, PLAYBACK_1, UNREGISTERED = 0, 4, 15
GIVE_POWER_STATUS, REPORT_POWER_STATUS, GIVE_OSD_NAME, SET_OSD_NAME = 0x8F, 0x90, 0x46, 0x47
POWER = {0: "on", 1: "standby", 2: "going on", 3: "going to standby"}
PULSE_EIGHT_VID = "VID_2548"


class Link:
    """One display's AUX channel through AMD's driver: DPCD reads and writes of up to 16 bytes."""

    def __init__(self, adl, adapter: int, display: int):
        self.adl, self.adapter, self.display = adl, adapter, display

    def _access(self, command: int, address: int, data: bytes | int) -> AuxData:
        size = data if isinstance(data, int) else len(data)
        d = AuxData(iSize=sizeof(AuxData), iCommand=command, iAddress=address, iDataSize=size)
        if not isinstance(data, int):
            d.cData[:size] = list(data)
        rc = self.adl.ADL_Display_NativeAUXChannel_Access(self.adapter, self.display, byref(d))
        if rc != 0:
            raise OSError(f"AUX {'read' if command == AUX_READ else 'write'} {address:#06x} failed:"
                          f" ADL {rc}, AUX status {d.iStatus}")
        return d

    def read(self, address: int, size: int) -> bytes:
        d = self._access(AUX_READ, address, size)
        if d.iDataSize != size:
            raise OSError(f"AUX read {address:#06x} gave {d.iDataSize} of {size} bytes")
        return bytes(d.cData[:size])

    def write(self, address: int, data: bytes) -> None:
        self._access(AUX_WRITE, address, data)


def physical_address(edid: bytes) -> str:
    """What the EDID's first CEA extension says of the HDMI physical address the TV gave this input."""
    block = edid[128:256]
    if len(block) < 128 or block[0] != 0x02:
        return "no CEA extension: not an HDMI sink"
    end, pos = block[2], 4
    while pos < min(end, 127):
        tag, length = block[pos] >> 5, block[pos] & 31
        if tag == 3 and block[pos + 1:pos + 4] == b"\x03\x0c\x00":       # HDMI's vendor block, OUI 00-0C-03
            a, b = block[pos + 4], block[pos + 5]
            return f"HDMI sink, physical address {a >> 4}.{a & 15}.{b >> 4}.{b & 15}"
        pos += length + 1
    return "CEA extension without an HDMI block (DVI or DP sink)"


def describe(link) -> int:
    """Prints the link's DPCD and returns its CEC tunneling capability (0 when it has none)."""
    rev = link.read(DPCD_REV, 16)
    print(f"   DPCD revision: {rev[0] >> 4}.{rev[0] & 15}")
    if rev[5] & 1:
        port = link.read(DOWNSTREAM_PORT, 4)
        print(f"   downstream port: {PORT_TYPES.get(port[0] & 7, port[0] & 7)} (raw {port.hex(' ')})")
    else:
        print("   downstream port: none reported (a plain DP sink or a passive cable)")
    branch = link.read(BRANCH_OUI, 12)
    ident = branch[3:9].rstrip(b"\0").decode(errors="replace")
    print(f"   branch device: OUI {branch[0:3].hex('-').upper()}, id '{ident}', hw {branch[9]:#04x},"
          f" fw {branch[10]}.{branch[11]}")
    cap, control = link.read(CEC_CAPABILITY, 2)
    print(f"   CEC tunneling capability (0x3000): {cap:#04x}"
          f" -> {'CAPABLE' if cap & CEC_CAPABLE else 'not capable'}"
          f"{', snooping' if cap & CEC_SNOOPING else ''}"
          f"{', multiple logical addresses' if cap & CEC_MULTIPLE_LA else ''}; control (0x3001): {control:#04x}")
    return cap if cap & CEC_CAPABLE else 0


def ping(link, listen: float = 0, clock=time.monotonic, sleep=time.sleep) -> dict:
    """Tunneling on as Playback 1, the poll and the two questions to the TV, the replies, then (listen) every message
    on the line; 0x3001 and 0x300E are put back as they were, also after an error. Returns what the TV said."""
    result = {"poll": None, "power": None, "name": None, "heard": []}

    def clear_irq():
        flags = link.read(CEC_IRQ, 1)[0]
        if flags:
            link.write(CEC_IRQ, bytes([flags]))

    def send(message: bytes) -> str:
        clear_irq()
        link.write(CEC_TX_BUFFER, message)
        link.write(CEC_TX_INFO, bytes([(len(message) - 1) | (TX_RETRIES << 4) | TX_SEND]))
        deadline = clock() + 2
        while clock() < deadline:
            flags = link.read(CEC_IRQ, 1)[0]
            done = flags & (IRQ_TX_SENT | IRQ_TX_LINE | IRQ_TX_ADDR_NACK | IRQ_TX_DATA_NACK)
            if done:
                link.write(CEC_IRQ, bytes([done]))
                if flags & IRQ_TX_SENT:
                    return "acked"
                return "line error" if flags & IRQ_TX_LINE else f"not acked (flags {flags:#04x})"
            sleep(0.02)
        return "no answer from the adapter (timeout)"

    def receive(opcode: int | None, seconds: float = 2.0) -> bytes | None:
        deadline = clock() + seconds
        while clock() < deadline:
            if link.read(CEC_IRQ, 1)[0] & IRQ_RX_VALID:
                length = (link.read(CEC_RX_INFO, 1)[0] & 0x0F) + 1
                message = link.read(CEC_RX_BUFFER, length)
                link.write(CEC_IRQ, bytes([IRQ_RX_VALID]))
                print(f"   <- {message.hex(' ')}")
                result["heard"].append(message)
                if opcode is not None and len(message) > 1 and message[1] == opcode:
                    return message
            sleep(0.02)
        return None

    print("\n   -- ping (writes 0x3001 and 0x300E, puts both back) --")
    control, mask = link.read(CEC_CONTROL, 1), link.read(CEC_LA_MASK, 2)
    header = (PLAYBACK_1 << 4) | TV
    try:
        link.write(CEC_CONTROL, bytes([CEC_ENABLE]))
        la_mask = (1 << PLAYBACK_1) | (1 << UNREGISTERED)                 # as Linux does: 15 always
        link.write(CEC_LA_MASK, bytes([la_mask & 0xFF, la_mask >> 8]))
        result["poll"] = send(bytes([header]))
        print(f"   poll the TV ({header:02x}): {result['poll']}")
        print(f"   Give Device Power Status ({header:02x} 8f): {send(bytes([header, GIVE_POWER_STATUS]))}")
        reply = receive(REPORT_POWER_STATUS)
        if reply and len(reply) > 2:
            result["power"] = POWER.get(reply[2], str(reply[2]))
        print(f"   TV power: {result['power'] or 'no reply'}")
        print(f"   Give OSD Name ({header:02x} 46): {send(bytes([header, GIVE_OSD_NAME]))}")
        reply = receive(SET_OSD_NAME)
        if reply:
            result["name"] = reply[2:].decode(errors="replace")
        print(f"   TV name: {result['name'] or 'no reply'}")
        if listen:
            link.write(CEC_CONTROL, bytes([CEC_ENABLE | CEC_SNOOPING_ENABLE]))
            print(f"   listening {listen:g} s: switch the TV's input away and back, or press its remote's keys",
                  flush=True)
            receive(None, listen)
    except OSError as exc:
        print(f"   {exc}")
    finally:
        link.write(CEC_LA_MASK, mask)
        link.write(CEC_CONTROL, control)
        print(f"   restored: control {control[0]:#04x}, logical address mask {mask.hex(' ')}")
    return result


def pulse_eight() -> list[str]:
    """The Pulse-Eight USB devices Windows has seen on this machine."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\USB") as key:
            names = [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]
    except OSError:
        return []
    return [n for n in names if n.upper().startswith(PULSE_EIGHT_VID)]


_buffers = []


@ctypes.CFUNCTYPE(c_void_p, c_int)
def _malloc(size):
    buf = ctypes.create_string_buffer(size)
    _buffers.append(buf)
    return ctypes.addressof(buf)


def main(argv: list[str]) -> int:
    try:
        adl = ctypes.CDLL("atiadlxx.dll")
    except OSError as exc:
        print(f"No AMD display library: {exc}")
        return 1
    if adl.ADL_Main_Control_Create(_malloc, 1) != 0:
        print("ADL_Main_Control_Create failed")
        return 1
    count = c_int()
    adl.ADL_Adapter_NumberOfAdapters_Get(byref(count))
    infos = (AdapterInfo * count.value)()
    for a in infos:
        a.iSize = sizeof(AdapterInfo)
    adl.ADL_Adapter_AdapterInfo_Get(infos, sizeof(infos))
    seen = set()
    for a in infos:
        if not a.iPresent or a.iAdapterIndex in seen:
            continue
        n, displays = c_int(), POINTER(DisplayInfo)()
        if adl.ADL_Display_DisplayInfo_Get(a.iAdapterIndex, byref(n), byref(displays), 0) != 0:
            continue
        for i in range(n.value):
            d = displays[i]
            if not d.iDisplayInfoValue & DISPLAY_CONNECTED or d.iDisplayLogicalAdapterIndex != a.iAdapterIndex:
                continue
            seen.add(a.iAdapterIndex)
            index = d.iDisplayLogicalIndex
            print(f"\n== {d.strDisplayName.decode(errors='replace')} on {a.strAdapterName.decode(errors='replace')}"
                  f" ({a.strDisplayName.decode(errors='replace')}), adapter {a.iAdapterIndex}, display {index}")
            print(f"   connector: {CONNECTORS.get(d.iDisplayConnector, d.iDisplayConnector)}")
            print(f"   EDID: {physical_address(edid(adl, a.iAdapterIndex, index))}")
            link = Link(adl, a.iAdapterIndex, index)
            try:
                cap = describe(link)
            except OSError as exc:
                print(f"   DPCD: {exc}")
                continue
            if "--ping" in argv and cap:
                ping(link, listen=60 if "--listen" in argv else 0)
    found = pulse_eight()
    print(f"\nPulse-Eight USB-CEC adapter: {', '.join(found) if found else 'never seen on this machine'}")
    return 0


def edid(adl, adapter: int, display: int) -> bytes:
    """The EDID's first two blocks, as far as the driver gives them."""
    data = b""
    for index in (0, 1):
        e = EdidData(iSize=sizeof(EdidData), iBlockIndex=index)
        if adl.ADL_Display_EdidData_Get(adapter, display, byref(e)) != 0:
            break
        block = bytes(e.cEDIDData[:max(e.iEDIDSize, 128)])
        if index == 0 and len(block) >= 256:
            return block[:256]
        data += block[:128]
        if index == 0 and (len(data) < 127 or not data[126]):
            break
    return data


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
