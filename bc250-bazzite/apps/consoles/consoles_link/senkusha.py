# SPDX-License-Identifier: AGPL-3.0-only
"""The network test before the stream, Senkusha: a Takion connection of version 7
to UDP 9297, without crypto, that measures what the stream then asks for in its launch spec.

1. TAKIONPROTOCOLREQUEST (version 9) and its acknowledgement, then a BIG with empty fields and the console's BANG.
2. Round trip: echo on, ten pings (version 7 audio packets of 0x224 bytes with a random tag), each answered by the
   console with a pong carrying the same tag; echo off. The average is the round trip.
3. MTU in: the console sends a video packet of the size asked for; a binary search between 576 and 1454 bytes.
4. MTU out: the board sends pings of the size tried; the same search, starting at MTU in, then a final
   CLIENT_MTU_COMMAND. As in the reference, a search that does not start at 1454 ends at 1453 at most.

When it fails, the reference streams with 1454 bytes both ways and 1 ms (stream.MTU, stream.RTT_MS), and so does the
app."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable

from . import tkproto
from .stream import StreamError, _core

PORT = 9297
EXPECT_TIMEOUT = 5.0
PING_COUNT = 10
PONG_TIMEOUT = 1.0
PING_SIZE = 0x224
MTU_MIN, MTU_MAX = 576, 1454
MTU_RETRIES = 3
MTU_UDP_ADD = 0x1c                      # IPv4 and UDP headers: the MTU counts them, the packet does not
V7_HEADER = 0x12                        # a version 7 audio header
CHANNEL = 1
CHANNEL_SENKUSHA = 8
PING_CODEC = 0xff
PING_UNITS = 0x800
PADDING = b"BC-250"                     # filler of the large pings


class SenkushaError(StreamError):
    pass


@dataclass
class Measurement:
    mtu_in: int
    mtu_out: int
    rtt_us: int
    pongs: int = 0
    log: list[str] = field(default_factory=list)

    @property
    def rtt_ms(self) -> int:
        """As the launch spec gets it: whole milliseconds, rounded down (0 on a fast network, as in the reference)."""
        return self.rtt_us // 1000


class Senkusha:
    def __init__(self, host: str, port: int = PORT, timeout: float = EXPECT_TIMEOUT,
                 random: Callable[[int], bytes] = os.urandom, core=None):
        self.host, self.port, self.timeout, self.random = host, port, timeout, random
        self.core = core or _core()
        self.takion = None
        self.log: list[str] = []

    def note(self, text: str) -> None:
        self.log.append(text)

    # --- Events ---------------------------------------------------------------------------------------------

    def _wait(self, timeout: float, accept: Callable[[tuple], bool]) -> tuple | None:
        """The first event *accept* takes within *timeout*, or None; the others are dropped, as in the reference's
        state machine."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            event = self.takion.next_event(remaining)
            if event is None:
                return None
            if event[0] == "closed":
                raise SenkushaError(f"The network test's connection closed: {event[1]}.")
            if accept(event):
                return event
        return None

    def _message(self, timeout: float, accept: Callable[[tkproto.Message], bool]) -> tkproto.Message | None:
        found: list[tkproto.Message] = []

        def take(event: tuple) -> bool:
            if event[0] != "data" or event[1] != 0:
                return False
            try:
                message = tkproto.parse(event[3])
            except tkproto.ProtoError:
                return False
            if accept(message):
                found.append(message)
                return True
            return False
        return found[0] if self._wait(timeout, take) else None

    def _send_acked(self, data: bytes) -> None:
        seq_num = self.takion.send_data(data, channel=CHANNEL_SENKUSHA, flags=1)
        if not self._wait(self.timeout, lambda e: e[0] == "data_ack" and e[1] == seq_num):
            raise SenkushaError("The console did not acknowledge a network test command.")

    def _ping(self, unit_index: int, size: int, timeout: float, padded: bool = False) -> float | None:
        """One ping of *size* bytes (zeros after the tag, or the padding for the MTU test); the round trip in
        seconds, or None when no pong came."""
        tag = self.random(4)
        header = self.core.v7_av_header(codec=PING_CODEC, frame_index=0, unit_index=unit_index, units_total=PING_UNITS)
        packet = header + bytes(4) + tag
        rest = size - len(packet)
        packet += (PADDING * (rest // len(PADDING) + 1))[:rest] if padded else bytes(rest)
        start = time.monotonic()
        self.takion.send_raw(packet)

        def pong(event: tuple) -> bool:
            if event[0] != "av":
                return False
            av, data = event[1], event[2]
            return (not av["video"] and av["frame_index"] == 0 and av["unit_index"] == unit_index and len(data) >= 8
                    and data[4:8] == tag)
        return time.monotonic() - start if self._wait(timeout, pong) else None

    # --- The tests ------------------------------------------------------------------------------------------

    def rtt_test(self) -> tuple[int, int]:
        self._send_acked(tkproto.echo_command(True))
        times = [t for i in range(PING_COUNT) if (t := self._ping(i, PING_SIZE, PONG_TIMEOUT)) is not None]
        self._send_acked(tkproto.echo_command(False))
        if not times:
            raise SenkushaError("The console answered none of the network test's pings.")
        rtt_us = int(sum(times) / len(times) * 1_000_000)
        self.note(f"Round trip {rtt_us / 1000:.2f} ms ({len(times)} of {PING_COUNT} pings answered).")
        return rtt_us, len(times)

    def mtu_in_test(self, timeout: float) -> int:
        low, high, cur, request_id = MTU_MIN, MTU_MAX, MTU_MAX, 0
        while high - low > 1:
            success = False
            for _attempt in range(MTU_RETRIES):
                request_id += 1
                self.takion.send_data(tkproto.mtu_command(request_id, cur), channel=CHANNEL_SENKUSHA, flags=1)
                wanted = request_id
                if self._wait(timeout, lambda e: e[0] == "av" and e[1]["video"] and e[1]["frame_index"] == wanted):
                    success = True
                    break
            if success:
                low = cur
            else:
                high = cur
            cur = low + (high - low) // 2
        return low

    def mtu_out_test(self, mtu_in: int, timeout: float) -> int:
        low, high = MTU_MIN, MTU_MAX
        self.takion.send_data(tkproto.client_mtu_command(1, True, mtu_in, mtu_in), channel=CHANNEL_SENKUSHA, flags=1)
        if self._message(self.timeout, lambda m: tkproto.senkusha_client_mtu(m) == 1) is None:
            raise SenkushaError("The console did not answer the network test's client MTU command.")
        cur = mtu_in
        while high - low > 1:
            success = any(self._ping(attempt, cur - MTU_UDP_ADD, timeout, padded=True) is not None
                          for attempt in range(MTU_RETRIES))
            if success:
                low = cur
            else:
                high = cur
            cur = low + (high - low) // 2
        self._send_acked(tkproto.client_mtu_command(2, False, high, mtu_in))
        return low

    def run(self) -> Measurement:
        try:
            self.takion = self.core.Takion(self.host, self.port, 7, self.timeout, crypt=False)
        except TimeoutError as error:
            raise SenkushaError(f"The console did not answer on the network test port {self.port}: {error}.") \
                from error
        except OSError as error:
            raise SenkushaError(f"The network test connection to {self.host} failed: {error}.") from error
        try:
            self.takion.send_data(tkproto.protocol_request([9]), channel=CHANNEL, flags=1)
            if self._message(self.timeout, lambda m: tkproto.protocol_ack(m) is not None) is None:
                raise SenkushaError("The console did not answer the network test's protocol request.")
            self.takion.send_data(tkproto.senkusha_big(), channel=CHANNEL, flags=1)
            if self._message(self.timeout, lambda m: tkproto.bang(m) is not None) is None:
                raise SenkushaError("The console sent no BANG for the network test.")
            rtt_us, pongs = self.rtt_test()
            mtu_timeout = min(max(rtt_us * 5 / 1_000_000, 0.005), 0.5)      # the reference: 5 round trips, 5 to 500 ms
            mtu_in = self.mtu_in_test(mtu_timeout)
            mtu_out = self.mtu_out_test(mtu_in, mtu_timeout)
            self.note(f"Network test: MTU {mtu_in} in, {mtu_out} out.")
            try:
                self.takion.send_data(tkproto.disconnect(), channel=CHANNEL, flags=1)
            except OSError:
                pass
            return Measurement(mtu_in, mtu_out, rtt_us, pongs, self.log)
        finally:
            self.takion.close()
            self.takion = None

