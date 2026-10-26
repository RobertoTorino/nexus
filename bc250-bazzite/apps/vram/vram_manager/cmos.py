# SPDX-License-Identifier: GPL-3.0-or-later
"""The BC-250's memory configuration block in CMOS, and the root helper that reads and writes it.

The firmware keeps the memory settings in CMOS bank 2 (index port 0x72, data port 0x73), offsets 0x90-0xAB:

    0x90  signature  u32   "$ABL" (0x4C424124) as the firmware writes it, 0x42435041 as a Linux tool writes it
    0x94  checksum   u16   16-bit sum of the bytes 0x96-0xAB
    0x96  ClockSpeed u16   then the memory timings (u8 or u16, see FIELDS)
    0xAA  UMA_SIZE   u16   the VRAM split in MB, in 16 MB steps

The layout is the one of fanoush/bc250_memcfg (MIT), confirmed on two boards with BIOS P5.00. A write goes like
that tool's: the whole block, from 0x90 upwards, with the Linux tool signature and a new checksum. Unlike it, this
module only writes a block it can trust (a known signature, a matching checksum, every timing in range), changes
UMA_SIZE and nothing else, and reads the block back.

Run as root (through pkexec) with the system Python, standard library only:

    python3 -I cmos.py --read           the block, decoded, and the whole of bank 2, as JSON
    python3 -I cmos.py --set-uma 6144   change UMA_SIZE; JSON with the block before and after

Takes effect at the next boot. Nothing outside 0x90-0xAB is ever written."""

from __future__ import annotations

import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

INDEX_PORT, DATA_PORT = 0x72, 0x73
BANK_SIZE = 0x100
BLOCK_START, BLOCK_SIZE = 0x90, 28
CHECKSUM_FROM = 6                       # the checksum covers the block from 0x96 on

SIG_LINUX_TOOL = 0x42435041
SIG_ABL = 0x4C424124
SIGNATURES = {SIG_LINUX_TOOL: "LINUX_TOOL", SIG_ABL: "ABL", 0x42534D43: "CMOS_BAD", 0x46544457: "WATCH_DOG_TIMER_FIRED",
              0x454B4843: "CHECKSUM_ERROR", 0x45474953: "SIGNATURE_ERROR"}
TRUSTED = (SIG_ABL, SIG_LINUX_TOOL)

# name, offset in the block, size, allowed range (from bc250_memcfg's table; None: any value)
FIELDS = (
    ("ClockSpeed", 0x06, 2, (0x01C2, 0x06D6)),
    ("tCL", 0x08, 1, (0x08, 0x21)),
    ("tRAS", 0x09, 1, (0x15, 0x3A)),
    ("tRCDRD", 0x0A, 1, (0x08, 0x1B)),
    ("tRCDWR", 0x0B, 1, (0x08, 0x1B)),
    ("tRCAb", 0x0C, 1, (0x28, 0x5A)),
    ("tRCPb", 0x0D, 1, (0x00, 0x0B)),
    ("tRPAb", 0x0E, 1, (0x08, 0x1B)),
    ("tRPPb", 0x0F, 1, (0x00, 0x0B)),
    ("tRRDS", 0x10, 1, (0x04, 0x0C)),
    ("tRRDL", 0x11, 1, (0x04, 0x0C)),
    ("tRTP", 0x12, 1, (0x00, 0x0E)),
    ("tFAW", 0x13, 1, (0x04, 0x22)),
    ("tREF", 0x14, 2, None),
    ("RFCPb", 0x16, 2, None),
    ("tRFC", 0x18, 2, None),
)
UMA_OFFSET = 0x1A

# The splits this app writes. bc250_memcfg takes 256-16383; above 10 GB the system keeps less than 6 GB of RAM.
UMA_MIN, UMA_MAX, UMA_STEP = 512, 10240, 16

BOARD_NAME = "AMD BC-250"


class CmosError(Exception):
    pass


@dataclass(frozen=True)
class Block:
    raw: bytes

    @property
    def signature(self) -> int:
        return struct.unpack_from("<I", self.raw, 0)[0]

    @property
    def signature_name(self) -> str:
        return SIGNATURES.get(self.signature, "UNKNOWN")

    @property
    def checksum(self) -> int:
        return struct.unpack_from("<H", self.raw, 4)[0]

    @property
    def computed_checksum(self) -> int:
        return checksum(self.raw)

    @property
    def uma_mb(self) -> int:
        return struct.unpack_from("<H", self.raw, UMA_OFFSET)[0]

    def fields(self) -> dict[str, int]:
        out = {}
        for name, offset, size, _ in FIELDS:
            out[name] = self.raw[offset] if size == 1 else struct.unpack_from("<H", self.raw, offset)[0]
        return out

    def problems(self) -> list[str]:
        """Why this block must not be written back; empty when it can be trusted."""
        out = []
        if self.signature not in TRUSTED:
            out.append(f"signature 0x{self.signature:08X} ({self.signature_name}) is not one the firmware or a "
                       "Linux tool writes after a good boot")
        if self.checksum != self.computed_checksum:
            out.append(f"checksum 0x{self.checksum:04X} does not match the bytes (0x{self.computed_checksum:04X})")
        values = self.fields()
        for name, _, _, allowed in FIELDS:
            if allowed and not allowed[0] <= values[name] <= allowed[1]:
                out.append(f"{name} = {values[name]} is outside {allowed[0]}-{allowed[1]}")
        if not 256 <= self.uma_mb < 16384:
            out.append(f"UMA_SIZE = {self.uma_mb} MB is outside 256-16383")
        return out

    def to_json(self) -> dict:
        return {"hex": self.raw.hex(), "signature": f"0x{self.signature:08X}", "signature_name": self.signature_name,
                "checksum": f"0x{self.checksum:04X}", "computed_checksum": f"0x{self.computed_checksum:04X}",
                "uma_mb": self.uma_mb, "fields": self.fields(), "problems": self.problems()}


def checksum(raw: bytes) -> int:
    return sum(raw[CHECKSUM_FROM:BLOCK_SIZE]) & 0xFFFF


def align_uma(mb: int) -> int:
    return mb - mb % UMA_STEP


def check_uma(mb: int) -> None:
    if mb % UMA_STEP:
        raise CmosError(f"{mb} MB is not a multiple of {UMA_STEP} MB.")
    if not UMA_MIN <= mb <= UMA_MAX:
        raise CmosError(f"{mb} MB is outside {UMA_MIN}-{UMA_MAX} MB.")


def with_uma(block: Block, mb: int) -> Block:
    """The block to write: the same timings, UMA_SIZE changed, the Linux tool signature and a new checksum."""
    raw = bytearray(block.raw)
    struct.pack_into("<I", raw, 0, SIG_LINUX_TOOL)
    struct.pack_into("<H", raw, UMA_OFFSET, mb)
    struct.pack_into("<H", raw, 4, checksum(raw))
    return Block(bytes(raw))


# --- Port access -----------------------------------------------------------------------------------------------

class Bank:
    """CMOS bank 2 through an index and a data port. *port* is /dev/port, or a fake in the tests."""

    def __init__(self, port):
        self.port = port

    def read(self, offset: int) -> int:
        self.port.write(INDEX_PORT, offset)
        return self.port.read(DATA_PORT)

    def write(self, offset: int, value: int) -> None:
        if not BLOCK_START <= offset < BLOCK_START + BLOCK_SIZE:
            raise CmosError(f"refusing to write offset 0x{offset:02X}, outside the memory block")
        self.port.write(INDEX_PORT, offset)
        self.port.write(DATA_PORT, value)

    def read_all(self) -> bytes:
        return bytes(self.read(off) for off in range(BANK_SIZE))

    def read_block(self) -> Block:
        return Block(bytes(self.read(BLOCK_START + i) for i in range(BLOCK_SIZE)))

    def write_block(self, block: Block) -> None:
        for i, value in enumerate(block.raw):
            self.write(BLOCK_START + i, value)


class DevPort:
    """/dev/port: a byte at file offset N is I/O port N. Needs root and no kernel lockdown."""

    def __init__(self, path: str = "/dev/port"):
        try:
            self.fd = os.open(path, os.O_RDWR)
        except OSError as exc:
            raise CmosError(f"cannot open {path}: {exc.strerror}") from exc

    def read(self, port: int) -> int:
        return os.pread(self.fd, 1, port)[0]

    def write(self, port: int, value: int) -> None:
        os.pwrite(self.fd, bytes([value]), port)

    def close(self) -> None:
        os.close(self.fd)


# --- Checks on the running system ------------------------------------------------------------------------------

def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def lockdown(sys_root: Path = Path("/sys")) -> str:
    """The active kernel lockdown mode: none, integrity or confidentiality ("" when the kernel has no lockdown)."""
    text = read_text(sys_root / "kernel/security/lockdown")
    start, end = text.find("["), text.find("]")
    return text[start + 1:end] if 0 <= start < end else ""


def board_problem(sys_root: Path = Path("/sys")) -> str:
    """Why this machine's CMOS must not be touched; "" on a BC-250 without lockdown."""
    board = read_text(sys_root / "class/dmi/id/board_name")
    if board != BOARD_NAME:
        return f"This is not a BC-250 (board name {board or 'unknown'!r}); its CMOS layout is unknown."
    mode = lockdown(sys_root)
    if mode not in ("", "none"):
        return f"Kernel lockdown ({mode}) blocks direct port access; Secure Boot usually turns it on."
    return ""


# --- The helper ------------------------------------------------------------------------------------------------

def do_read(bank: Bank) -> dict:
    return {"ok": True, "block": bank.read_block().to_json(), "bank": bank.read_all().hex()}


def do_set_uma(bank: Bank, mb: int) -> dict:
    check_uma(mb)
    before = bank.read_block()
    problems = before.problems()
    if problems:
        raise CmosError("The memory block in CMOS cannot be trusted, so nothing was written: " + "; ".join(problems)
                        + ". Clearing CMOS (jumper or battery) restores the firmware's defaults.")
    wanted = with_uma(before, mb)
    bank.write_block(wanted)
    after = bank.read_block()
    if after.raw != wanted.raw:
        raise CmosError(f"Read back {after.raw.hex()} instead of {wanted.raw.hex()}: the write did not stick.")
    return {"ok": True, "before": before.to_json(), "after": after.to_json()}


def main(argv: list[str] | None = None, sys_root: Path = Path("/sys"), port_factory=DevPort) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="cmos.py", description="BC-250 CMOS memory block (root helper)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--read", action="store_true")
    group.add_argument("--set-uma", type=int, metavar="MB")
    args = parser.parse_args(argv)
    try:
        problem = board_problem(sys_root)
        if problem:
            raise CmosError(problem)
        port = port_factory()
        try:
            bank = Bank(port)
            result = do_read(bank) if args.read else do_set_uma(bank, args.set_uma)
        finally:
            close = getattr(port, "close", None)
            if close:
                close()
    except CmosError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
