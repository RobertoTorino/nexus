<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Memory Manager](../assets/vram/bc250-memory-manager.webp){ .app-logo }

# BC-250 Memory Manager

Sets the **VRAM split** of the **AMD BC-250** on **Bazzite** and the **GTT limit** on its kernel command line, and
shows the memory figures that go with them: the GTT, the TTM limit, the system RAM and the swap layout.

The split is stored in the board's CMOS and the GTT limit in the next boot's kernel arguments, so this app
**changes the board**. Both are software-only and can be undone: in the app, by clearing CMOS, or with rpm-ostree.

## The split, GTT and RAM

The BC-250 has 16 GB of GDDR6, shared by the CPU and the GPU. At boot the firmware divides it in two:

- **The split (VRAM):** the part the GPU keeps for itself, from 512 MB up.
- **System RAM:** the rest. Linux and the games run in it.

The GPU can also borrow system RAM on top of the split. That is the **GTT**. amdgpu sizes it from
`ttm.pages_limit` on the kernel command line (by default half the RAM) and never makes it larger than the RAM.

A small split leaves the most RAM, and the GPU grows into GTT when it needs more. But the screen's framebuffers
must fit in the split itself: when a game fills a 512 MB split, the next frame cannot be shown and the session
ends. Bazzite Test reports this as a framebuffer pin failure (test 37). A 6 GB split fixes it, which is why the app
marks 6 GB as recommended for games.

## Using it

The top row shows what the kernel got at this boot: the **VRAM split**, the **GTT**, the GTT limit
**ttm.pages_limit** (marked default when it is not on the command line), the **system RAM** and the **swap**
layout; under it `vm.swappiness`, how readily Linux moves pages out of the RAM into swap (0 to 200; 60 is the
kernel's default, more prefers swap to the file cache, usual with zram), the board's own setting, which the app only
shows. When the limit is above the RAM, the GTT box says so: the GTT is all the RAM, and
a higher limit has no effect. While a new limit waits for a reboot, the ttm.pages_limit box's caption names it
("next boot 16.0 GiB"). Hover a box for the details.

The **memory map** under it draws the 16 GB as one bar and follows it live, every two seconds:

- **The split:** the VRAM in use and the VRAM that is free.
- **The system RAM:** what the GPU borrows from it now (GTT), what zram or zswap take, what Linux and the apps use,
  and what is still available.
- **What the firmware keeps** at boot, the last part of the bar.

The bracket under the RAM is the GTT limit: how much RAM the GPU may borrow, and what the TTM limit does to it.
Parts too narrow for a label are named in the line under it. Under the bar is the swap: for zram, the pages it holds
and the RAM that costs (light and dark), and whether zswap or disk swap is in use. Hover any part for what it is.
Picking a split under **New split**, or a limit under **Next boot**, draws the next boot under the bar: the new
split, the RAM that leaves, and about how much the GPU may then borrow.

- **New split** and **Apply…:** pick a split and apply it. The app asks first and shows how much RAM the system
  keeps, then asks for your password. The status next to the title turns to **Reboot to apply**. Apply is off
  while the split picked is the one the board has, or the one waiting for the reboot.
- **Reboot.** After the reboot the app says whether the kernel got the new split.
- **Undo:** writes back the split from before the last change. Also takes effect after a reboot.
- **Read CMOS…:** shows the memory block in CMOS (signature, checksum, the split and the memory timings) and the
  whole of CMOS bank 2, and saves the same text as a dump. Read-only.

Only the split changes. The memory timings in the same block stay as they are.

## The GTT limit

The GTT limit is how much RAM the GPU may borrow on top of the split. amdgpu takes it from `ttm.pages_limit` on
the kernel command line, in 4 KiB pages; without the argument the kernel takes half the RAM. Whatever the argument
says, the GTT never grows past the RAM: with a 6 GB split and 9.4 GB of RAM, a limit of 11.5 GiB already means all
of it, and a higher one changes nothing. A small split is where the argument counts: with 512 MB, the kernel's
default stops the GPU at half of the 15 GB of RAM.

The limit does not fix the framebuffer pin failures (Bazzite Test, test 37): those need a larger split.

Under **GTT limit on the kernel command line**:

- **Next boot** and **Apply…:** pick a limit and apply it (Apply is off while the limit picked is the next boot's
  already). The app asks first and says what the GTT will be after the reboot with this split: with a limit above the
  RAM it stays where it is, since the kernel caps it at the RAM. Then rpm-ostree asks for your password and writes a
  new deployment with the argument. That takes a minute or two, since rpm-ostree puts the layered packages on the new
  deployment again: the status next to the title says **Writing…** meanwhile, and the note under the row counts
  the seconds. When it is done the app says so, the
  status turns to **Reboot to apply**, and the reboot is yours to do: the app never reboots the board (`systemctl
  reboot`, or the menu). The choices:
    - **Kernel default: half the RAM.** The argument is removed.
    - **11.5 GiB, the suite's value.** What Bazzite Test advises; all of the RAM with a 6 GB split.
    - **16 GiB: all the RAM, whatever the split.** The kernel caps it at the RAM, so this is the most the GPU can
      borrow with any split.
    - A limit set by hand that is none of these appears as a fourth choice, **as set now**.
- **Reboot.** After the reboot the app says whether the kernel got the new limit. When the board started another
  deployment (a rollback), it says that instead.

The split and the limit are independent: each is applied on its own, and either can wait for the reboot. The
round **i** at the end of each row opens what the split and the limit are, with a link to this chapter.

## Profiles

Under **Profiles** two buttons set the split and the limit at once:

- **Default profile:** the firmware's 512 MB split and the kernel's GTT limit, half the RAM. What a board runs
  without any change, as after a CMOS clear on a kernel command line without `ttm.pages_limit`.
- **Games profile:** the 6 GB split that prevents the framebuffer pin failures (Bazzite Test, test 37) and the
  11.5 GiB limit, all the RAM with that split. What the suite's boards run.

A profile writes only what differs from the board: the split to CMOS, the limit to the next boot's kernel
arguments. It asks once, names what it will write, and needs a password prompt for each of the two. A profile the
board already has is off. Both take effect after you reboot the board, which stays yours to do.

## When it refuses

The app reads and writes CMOS only when all of these hold. Otherwise the buttons are off, or the write stops before
anything changes, with the reason:

- **The board is a BC-250.** Other boards keep other things at the same place in CMOS.
- **The kernel has no lockdown.** Lockdown blocks direct port access; Secure Boot usually turns it on.
- **The memory block can be trusted:** a checksum that matches and every timing in its normal range. A damaged
  block is never written back, because the firmware would then start the memory with wrong timings. A note the
  firmware left in the block's signature (its watchdog fired at a boot, a checksum it found wrong) is no reason
  to refuse when the numbers are intact: Read CMOS shows it as a note, and a write replaces it.

The GTT limit needs rpm-ostree, which reads and writes the kernel arguments. Without it (another Linux), or while
its daemon cannot be reached, the **Apply…** of the limit is off, with the reason. While Bazzite's updater runs
(an update in progress), rpm-ostree refuses with "transaction in progress": wait for it and apply again. After
every change the app reads the next boot's arguments back; when they do not hold the limit asked for, it says so,
with the command to run by hand, and nothing counts as written.

## Undoing a change

The split:

- **In the app:** Undo, then reboot.
- **Without the app:** clear CMOS with the jumper on the board, or take the battery out for a minute. The firmware
  then starts with its own default split.

The GTT limit:

- **In the app:** pick the limit you had before, or the kernel default, and apply it; then reboot.
- **Without the app:** `rpm-ostree kargs --delete=ttm.pages_limit=N`, with the value `rpm-ostree kargs` prints,
  and reboot. `rpm-ostree rollback` also undoes it, together with everything else in that deployment. Clearing
  CMOS does not touch it.

## Files

- `~/.config/bc250-memory-manager/bc250-memory-manager.ini`: the pending changes (the split and the GTT limit)
  and the split to undo to.
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

Reading and writing CMOS needs `pkexec` and the system `python3`, the GTT limit `rpm-ostree`; Bazzite has all
three. Uninstalling the app changes neither the split in CMOS nor the kernel arguments.

## License

GPL-3.0-or-later. See [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/vram/LICENSE).
The CMOS layout comes from [fanoush/bc250_memcfg](https://github.com/fanoush/bc250_memcfg) (MIT).
