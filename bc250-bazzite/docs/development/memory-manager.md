<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Memory Manager internals

How BC-250 Memory Manager reads and writes the VRAM split in CMOS, and the board dumps the layout was checked
against. The user's side is in [its chapter](../apps/vram.md).

## Where the split is stored

The firmware (AMI Aptio, AMD's ABL for the memory setup) keeps the memory configuration in **CMOS bank 2**: the
battery-backed RAM behind I/O ports **0x72** (index) and **0x73** (data). Bank 1 (0x70/0x71) is the RTC and the
usual CMOS settings; the kernel's `cmos_nvram0` device only covers bank 1, so bank 2 is reached through
`/dev/port`, where file offset N is I/O port N.

The memory block is 28 bytes at 0x90-0xAB, little-endian:

| Offset | Size | Field | Allowed range |
|---|---|---|---|
| 0x90 | 4 | Signature | see below |
| 0x94 | 2 | Checksum: 16-bit sum of the bytes 0x96-0xAB | |
| 0x96 | 2 | ClockSpeed (MHz) | 450-1750 |
| 0x98 | 1 | tCL | 8-33 |
| 0x99 | 1 | tRAS | 21-58 |
| 0x9A | 1 | tRCDRD | 8-27 |
| 0x9B | 1 | tRCDWR | 8-27 |
| 0x9C | 1 | tRCAb | 40-90 |
| 0x9D | 1 | tRCPb | 0-11 |
| 0x9E | 1 | tRPAb | 8-27 |
| 0x9F | 1 | tRPPb | 0-11 |
| 0xA0 | 1 | tRRDS | 4-12 |
| 0xA1 | 1 | tRRDL | 4-12 |
| 0xA2 | 1 | tRTP | 0-14 |
| 0xA3 | 1 | tFAW | 4-34 |
| 0xA4 | 2 | tREF | any |
| 0xA6 | 2 | RFCPb | any |
| 0xA8 | 2 | tRFC | any |
| 0xAA | 2 | UMA_SIZE: the split in MB, in 16 MB steps | 256-16383 |

Signatures:

| Value | Bytes | Name | Meaning |
|---|---|---|---|
| 0x4C424124 | `24 41 42 4C` ("$ABL") | ABL | written by the firmware |
| 0x42435041 | `41 50 43 42` | LINUX_TOOL | written by a Linux tool (bc250_memcfg, this app) |
| 0x42534D43 | | CMOS_BAD | error codes the firmware leaves after a failed boot |
| 0x46544457 | | WATCH_DOG_TIMER_FIRED | |
| 0x454B4843 | | CHECKSUM_ERROR | |
| 0x45474953 | | SIGNATURE_ERROR | |

The layout, the ranges and the signatures come from
[fanoush/bc250_memcfg](https://github.com/fanoush/bc250_memcfg) (MIT), which credits an earlier tool by ethkey.

## The layout on two boards

Bank 2 was read on two BC-250 boards (BIOS P5.00 05/03/2022, kernel lockdown off, both with a 6 GB split). The
reads only set the index port and read the data port.

The memory block is byte for byte the same on both:

```
090  24 41 42 4C 10 04 D6 06 18 34 1B 13 4E 00 1A 00
0A0  08 08 02 20 F7 26 D2 00 18 01 00 18
```

| Field | Board 1 | Board 2 |
|---|---|---|
| Signature | 0x4C424124 (ABL) | 0x4C424124 (ABL) |
| Checksum stored / computed | 0x0410 / 0x0410 | 0x0410 / 0x0410 |
| ClockSpeed | 1750 MHz | 1750 MHz |
| tCL, tRAS, tRCDRD, tRCDWR, tRCAb | 24, 52, 27, 19, 78 | 24, 52, 27, 19, 78 |
| tRCPb, tRPAb, tRPPb | 0, 26, 0 | 0, 26, 0 |
| tRRDS, tRRDL, tRTP, tFAW | 8, 8, 2, 32 | 8, 8, 2, 32 |
| tREF, RFCPb, tRFC | 9975, 210, 280 | 9975, 210, 280 |
| UMA_SIZE | 6144 MB | 6144 MB |
| `mem_info_vram_total` | 6442450944 (6 GiB) | 6442450944 (6 GiB) |

Every timing is inside its range, and UMA_SIZE matches the split the kernel got.

The rest of bank 2:

- **0x00-0x0F and 0x40-0x46** are the same on both boards (`FF 00 00 00 00 00 00 00 98 42 EE 7D FF 30 3F 00` and
  `00 00 01 02 56 90 F0`): the firmware keeps something else there.
- **0x47-0x7F** is zero on both.
- **0x10-0x3F, 0x80-0x8F and 0xAC-0xFF** are mostly `FF` with single bits cleared in different places on each
  board: unused memory that was never written.

So nothing outside 0x90-0xAB belongs to the memory configuration, and the app never writes there. The tests use
both reads as fixtures (`bc250-bazzite/apps/vram/tests/dumps.py`).

## Reading and writing

The GUI runs as the user. Everything that touches CMOS is in `vram_manager/cmos.py`, which pkexec runs as
root with the system Python in isolated mode:

```
pkexec /usr/bin/python3 -I .../vram_manager/cmos.py --read
pkexec /usr/bin/python3 -I .../vram_manager/cmos.py --set-uma 6144
```

`-I` keeps the user's environment and the current folder out of the root process; the helper only needs the
standard library. It prints one JSON object: `{"ok": true, ...}` or `{"ok": false, "error": "..."}`.

Before it opens `/dev/port`, the helper checks that the DMI board name is `AMD BC-250` and that kernel lockdown is
off.

`--set-uma MB`:

1. Checks the split: a multiple of 16 MB, from 512 to 10240 MB. Above 10 GB the system keeps less than 6 GB.
2. Reads the block and checks that it can be trusted: signature ABL or LINUX_TOOL, a matching checksum, every
   timing in range, UMA_SIZE 256-16383. If not, it writes nothing. bc250_memcfg writes back whatever it read, so a
   damaged block would reach the firmware with its wrong timings.
3. Builds the new block: the same timings, the new UMA_SIZE, the LINUX_TOOL signature and a new checksum.
4. Writes the whole block from 0x90 upwards, as bc250_memcfg does, so the bytes the firmware finds are the same as
   with that tool.
5. Reads the block back and compares all 28 bytes.

It answers with the block before and after; the GUI saves both in `backups/cmos-<time>.json`. `--read` answers
with the decoded block and all 256 bytes of bank 2, which the GUI shows and saves as `backups/cmos-dump-<time>.txt`.

## After a reboot

The firmware reads the block at boot. The GUI keeps the split it wrote with the boot ID it wrote it in
(`/proc/sys/kernel/random/boot_id`). At the next boot it compares `mem_info_vram_total` with that split and says
whether the kernel got it. Undo writes back the UMA_SIZE of the block before the last change.

## The figures without root

`vram_manager/system.py` reads, without root:

| Figure | Source |
|---|---|
| Split | `/sys/class/drm/card*/device/mem_info_vram_total` |
| GTT | `/sys/class/drm/card*/device/mem_info_gtt_total` |
| System RAM | `MemTotal` in `/proc/meminfo` |
| TTM limit | `/sys/module/ttm/parameters/pages_limit` (4 KiB pages), and whether it is on `/proc/cmdline` |
| Swap | `/proc/swaps` (zram and disk swap) and `/sys/module/zswap/parameters/enabled`, as Bazzite Test's test 14 |
| Swappiness | `/proc/sys/vm/swappiness` |

amdgpu sizes GTT from the TTM limit and caps it at the RAM on this APU (`amdgpu_ttm_init`: "Capping GTT to …M to
not exceed available system memory"). When the split is smaller than GTT, amdgpu also prefers GTT for the GPU's
allocations (`apu_prefer_gtt`).
