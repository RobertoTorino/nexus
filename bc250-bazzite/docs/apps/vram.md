<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Memory Manager](../assets/vram/bc250-memory-manager.webp){ .app-logo }

# BC-250 Memory Manager

Sets the **VRAM split** of the **AMD BC-250** on **Bazzite**, and shows the memory figures that go with it: the
GTT, the TTM limit, the system RAM and the swap layout.

The split is stored in the board's CMOS, so this app **changes the board**. It is software-only and can be undone:
in the app, or by clearing CMOS.

## The split, GTT and RAM

The BC-250 has 16 GB of GDDR6, shared by the CPU and the GPU. At boot the firmware divides it in two:

- **The split (VRAM):** the part the GPU keeps for itself, from 512 MB up.
- **System RAM:** the rest. Linux and the games run in it.

The GPU can also borrow system RAM on top of the split. That is the **GTT**. amdgpu sizes it from
`ttm.pages_limit` (by default half the RAM) and never makes it larger than the RAM.

A small split leaves the most RAM, and the GPU grows into GTT when it needs more. But the screen's framebuffers
must fit in the split itself: when a game fills a 512 MB split, the next frame cannot be shown and the session
ends. Bazzite Test reports this as a framebuffer pin failure (test 37). A 6 GB split fixes it, which is why the app
marks 6 GB as recommended for games.

## Using it

The top row shows what the kernel got at this boot: the **VRAM split**, the **GTT**, the **system RAM** and the
**swap** layout. Under it are the TTM limit and `vm.swappiness`. When `ttm.pages_limit` is above the RAM, the app
says so: GTT stops at the RAM, so that limit has no effect.

The **memory map** under it draws the 16 GB as one bar and follows it live, every two seconds:

- **The split:** the VRAM in use and the VRAM that is free.
- **The system RAM:** what the GPU borrows from it now (GTT), what zram or zswap take, what Linux and the apps use,
  and what is still available.
- **What the firmware keeps** at boot, the last part of the bar.

The bracket under the RAM is the GTT limit: how much RAM the GPU may borrow, and what the TTM limit does to it.
Parts too narrow for a label are named in the line under it. Under the bar is the swap: for zram, the pages it holds
and the RAM that costs (light and dark), and whether zswap or disk swap is in use. Hover any part for what it is.
Picking a split under **New split** draws the next boot under the bar: the new split, the RAM that leaves, and
about how much the GPU may then borrow.

- **New split** and **Apply…:** pick a split and apply it. The app asks first and shows how much RAM the system
  keeps, then asks for your password. The status next to the title turns to **Reboot to apply**.
- **Reboot.** After the reboot the app says whether the kernel got the new split.
- **Undo:** writes back the split from before the last change. Also takes effect after a reboot.
- **Read CMOS…:** shows the memory block in CMOS (signature, checksum, the split and the memory timings) and the
  whole of CMOS bank 2, and saves the same text as a dump. Read-only.

Only the split changes. The memory timings in the same block stay as they are.

## When it refuses

The app reads and writes CMOS only when all of these hold. Otherwise the buttons are off, or the write stops before
anything changes, with the reason:

- **The board is a BC-250.** Other boards keep other things at the same place in CMOS.
- **The kernel has no lockdown.** Lockdown blocks direct port access; Secure Boot usually turns it on.
- **The memory block can be trusted:** a signature the firmware or a Linux tool writes, a checksum that matches,
  and every timing in its normal range. A damaged block is never written back, because the firmware would then
  start the memory with wrong timings.

## Undoing a change

- **In the app:** Undo, then reboot.
- **Without the app:** clear CMOS with the jumper on the board, or take the battery out for a minute. The firmware
  then starts with its own default split.

## Files

- `~/.config/bc250-memory-manager/bc250-memory-manager.ini`: the pending change and the split to undo to.
- `~/.local/share/bc250-memory-manager/backups/`: the CMOS block before and after every change
  (`cmos-<time>.json`) and every CMOS read (`cmos-dump-<time>.txt`).

How the app reads and writes CMOS: [Memory Manager internals](../development/memory-manager.md).

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app; keeps its settings and CMOS backups
./install.sh --uninstall --purge     # also remove its settings and CMOS backups
```

Reading and writing CMOS needs `pkexec` and the system `python3`; Bazzite has both. Uninstalling the app does not
change the split in CMOS.

## License

GPL-3.0-or-later. See [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/vram/LICENSE).
The CMOS layout comes from [fanoush/bc250_memcfg](https://github.com/fanoush/bc250_memcfg) (MIT).
