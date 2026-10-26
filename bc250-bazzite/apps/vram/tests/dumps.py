# SPDX-License-Identifier: GPL-3.0-or-later
"""CMOS bank 2 of the owner's two boards (BIOS P5.00, 6144 MB split), read on 10-10-2026. The memory block
(0x90-0xAB) is the same on both; most of the rest is noise that differs between them."""

BOARD_1 = """
FF 00 00 00 00 00 00 00 98 42 EE 7D FF 30 3F 00
FF FF FF FF FF FF FF F7 FF FF EF DD FF FB FF DF
FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF
FF EF FF FF FE FF FF 7F FF FF FF BF FF FF FF F7
00 00 01 02 56 90 F0 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
FF FF FF FF BF FF FF FF FF BF FF FF FF FF FF F7
24 41 42 4C 10 04 D6 06 18 34 1B 13 4E 00 1A 00
08 08 02 20 F7 26 D2 00 18 01 00 18 FF FF FF 7F
FF FF FF FF FF FF FB FF FF EE FF FF FF FF FF EF
FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF
FF FF FF FF FE FF FF FF FF FF FF FF FF FF FF FF
FF FF FF FF FF 7F EF FF FF FF FF FF 7B F7 FF FF
FF 7F AF FF FF DF FF FF FF FF FF B7 FE FF F7 FF
"""

BOARD_2 = """
FF 00 00 00 00 00 00 00 98 42 EE 7D FF 30 3F 00
FF FF EF FF FF FF FF FF FF FF FF FF FF FF FF FF
FF FF FF FF EF FF F7 FF FF F7 FF FF FF FF FF FF
BF FB FF FF FF FF FF FF FF FF FF FF FF FF FF FF
00 00 01 02 56 90 F0 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
FF EF FF FF BF FF FF FF FF FF FF FF BD FB FF FF
24 41 42 4C 10 04 D6 06 18 34 1B 13 4E 00 1A 00
08 08 02 20 F7 26 D2 00 18 01 00 18 FF FF FE FF
FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF
FF FF FF FF FF FF 7F FF FF FF FF FF FF FF FF FF
FF FF FF FF FF FF FF FF FF FF F7 FF FF FF FF FF
BF FF FB FB FF FF FF FF FF FF FF FF FF FF FF FF
FF FF DF FF FF BF F7 FF FF FD FF 7F FF FF FF EF
"""


def bank(text: str) -> bytearray:
    return bytearray(bytes.fromhex(text.replace("\n", " ")))


class FakePort:
    """I/O ports 0x72/0x73 over a 256-byte bank; records every write as (port, value)."""

    def __init__(self, data: bytearray, stuck: set[int] | None = None):
        self.data = data
        self.index = 0
        self.writes: list[tuple[int, int]] = []
        self.stuck = stuck or set()         # offsets that ignore writes, to simulate a write that does not stick
        self.closed = False

    def write(self, port: int, value: int) -> None:
        self.writes.append((port, value))
        if port == 0x72:
            self.index = value
        elif port == 0x73 and self.index not in self.stuck:
            self.data[self.index] = value

    def read(self, port: int) -> int:
        assert port == 0x73
        return self.data[self.index]

    def close(self) -> None:
        self.closed = True
