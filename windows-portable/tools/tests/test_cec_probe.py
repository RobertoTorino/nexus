# SPDX-License-Identifier: GPL-3.0-or-later
"""The HDMI-CEC probe (cec_probe.py) with the adapter stood in for: the DPCD it describes, the HDMI physical address
from an EDID, the ping against a TV that answers and one that does not, and the two registers it changes put back,
also after an error. AMD's driver itself is only on the handheld."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cec_probe as cp  # noqa: E402


class Adapter:
    """A DPCD with CEC tunneling: a sent message ends with the TV's ack or an address NACK, and a question the TV
    answers puts its reply in the receive buffer. 0x3004 clears the bits written to it, as the hardware does."""

    def __init__(self, tv: bool = True, fail_at: int | None = None):
        self.dpcd = bytearray(0x3100)
        self.dpcd[0x0000], self.dpcd[0x0005] = 0x12, 0x01
        self.dpcd[0x0080:0x0084] = bytes([0x0B, 0xF0, 0x02, 0x11])
        self.dpcd[0x0500:0x050C] = bytes([0x00, 0x1C, 0xF8]) + b"176GB0" + bytes([0x00, 199, 118])
        self.dpcd[0x3000] = 0x07
        self.dpcd[0x300E:0x3010] = bytes([0x00, 0x80])
        self.tv, self.fail_at, self.sent, self.writes = tv, fail_at, [], []

    def read(self, address, size):
        return bytes(self.dpcd[address:address + size])

    def write(self, address, data):
        self.writes.append((address, bytes(data)))
        if address == self.fail_at:
            raise OSError(f"AUX write {address:#06x} failed: ADL -1, AUX status 0")
        if address == cp.CEC_IRQ:
            self.dpcd[address] &= ~data[0] & 0xFF
            return
        self.dpcd[address:address + len(data)] = data
        if address == cp.CEC_TX_INFO and data[0] & cp.TX_SEND:
            message = bytes(self.dpcd[cp.CEC_TX_BUFFER:cp.CEC_TX_BUFFER + (data[0] & 0x0F) + 1])
            self.sent.append(message)
            if not self.tv:
                self.dpcd[cp.CEC_IRQ] |= cp.IRQ_TX_ADDR_NACK
                return
            self.dpcd[cp.CEC_IRQ] |= cp.IRQ_TX_SENT
            reply = {cp.GIVE_POWER_STATUS: bytes([0x04, cp.REPORT_POWER_STATUS, 0x00]),
                     cp.GIVE_OSD_NAME: bytes([0x04, cp.SET_OSD_NAME]) + b"Mi TV"}.get(message[1:2] and message[1])
            if reply:
                self.dpcd[cp.CEC_RX_BUFFER:cp.CEC_RX_BUFFER + len(reply)] = reply
                self.dpcd[cp.CEC_RX_INFO] = len(reply) - 1
                self.dpcd[cp.CEC_IRQ] |= cp.IRQ_RX_VALID


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def ping(adapter, **kw):
    clock = Clock()
    return cp.ping(adapter, clock=clock, sleep=clock.sleep, **kw)


def test_describe_reads_the_branch_device_and_the_capability(capsys):
    assert cp.describe(Adapter()) == 0x07
    out = capsys.readouterr().out
    assert "DPCD revision: 1.2" in out
    assert "downstream port: HDMI" in out
    assert "OUI 00-1C-F8, id '176GB0', hw 0x00, fw 199.118" in out
    assert "CAPABLE, snooping, multiple logical addresses" in out


def test_describe_without_tunneling_returns_nothing():
    adapter = Adapter()
    adapter.dpcd[0x3000] = 0x00
    assert cp.describe(adapter) == 0


def test_physical_address_from_the_hdmi_block():
    block = bytearray(128)
    block[0:4] = bytes([0x02, 0x03, 4 + 8, 0x00])
    block[4:12] = bytes([(3 << 5) | 7, 0x03, 0x0C, 0x00, 0x30, 0x00, 0x00, 0x00])
    assert cp.physical_address(bytes(128) + bytes(block)) == "HDMI sink, physical address 3.0.0.0"
    assert cp.physical_address(bytes(128)) == "no CEA extension: not an HDMI sink"
    block[5] = 0x00
    assert "without an HDMI block" in cp.physical_address(bytes(128) + bytes(block))


def test_ping_a_tv_that_answers():
    adapter = Adapter()
    result = ping(adapter)
    assert result["poll"] == "acked"
    assert result["power"] == "on"
    assert result["name"] == "Mi TV"
    assert adapter.sent == [b"\x40", b"\x40\x8f", b"\x40\x46"]
    assert (cp.CEC_LA_MASK, bytes([0x10, 0x80])) in adapter.writes      # Playback 1 and 15, as Linux does


def test_ping_a_tv_that_does_not_answer():
    result = ping(Adapter(tv=False))
    assert result["poll"] == "not acked (flags 0x40)"
    assert result["power"] is None and result["name"] is None


def test_ping_puts_the_registers_back():
    adapter = Adapter()
    ping(adapter, listen=1)
    assert adapter.read(cp.CEC_CONTROL, 1) == b"\x00"
    assert adapter.read(cp.CEC_LA_MASK, 2) == b"\x00\x80"
    assert (cp.CEC_CONTROL, bytes([cp.CEC_ENABLE | cp.CEC_SNOOPING_ENABLE])) in adapter.writes


def test_ping_puts_the_registers_back_after_an_error(capsys):
    adapter = Adapter(fail_at=cp.CEC_TX_INFO)
    result = ping(adapter)
    assert result["poll"] is None
    assert "AUX write 0x3003 failed" in capsys.readouterr().out
    assert adapter.writes[-2:] == [(cp.CEC_LA_MASK, b"\x00\x80"), (cp.CEC_CONTROL, b"\x00")]
