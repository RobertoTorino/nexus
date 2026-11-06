<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![SSD Check](../assets/ssd/bc250-ssd.webp){ .app-logo }

# SSD Check

How an SSD is doing: its **health**, **power cycles** and **power-on hours**, the drive's specs, and whether the
board lets it run at its full speed. It only reads the drive (the speed test writes a test file and deletes it):
nothing on the drive changes, and it needs no root.

| Value | What it shows | NVMe | SATA SSD |
|---|---|---|---|
| Health | how much of its rated life the drive has left, in percent | 100 minus "percentage used" | an attribute of the drive's maker, see below |
| Power cycles | how often the drive was switched on | "power cycles" | attribute 12 |
| Power-on hours | how long it has run in all; hover it to see the years | "power-on hours" | attribute 9 |

## Using it

- **The top row**, beside the icon:

  | Pill | What it does |
  |---|---|
  | Health | the drive's health, see above |
  | Serial | the drive's serial number, hidden: click the pill to see it in a small window below it, where you can select it to copy. A click anywhere else closes it, and it closes when you choose another drive or Refresh. |
  | Measured R / W MB/s | **Test**: click it to measure the drive's read and write speed in this board, see below |
  | Refresh | reads the drives again |

- **Drive:** with more than one drive, choose it by its number (Drive 1, Drive 2) in the list under the top row.
  Under the list are the drive's model and size, and a line with its bus and when udisks last read it.
- **Screenshot**, beside the list: saves the window with the values it shows now as a PNG in your Pictures folder,
  in a folder named SSD Check (`~/Pictures/SSD Check/SSD Check 2026-11-05 18-04-09.png`, the date and time in its
  name). The file manager opens on the folder with the new file selected. The line beside the button names the
  file; hover it for the folder. The serial stays hidden in the picture,
  even while its small window is open.
- The specs, a pill each:

  | Pill | What it shows |
  |---|---|
  | Power cycles | how often the drive was switched on |
  | Power-on hours | how long it has run in all |
  | Power-on days | the power-on hours in full days (4,025 hours are 167 days): a day not yet complete does not count |
  | Drive | the device name (`nvme0n1`, `sda`) |
  | Host reads | how much data the computer has read from the drive in all |
  | Host writes | how much data the computer has written to the drive in all |
  | Firmware | the version of the drive's firmware |
  | Update | whether fwupd knows a newer firmware for the drive, see below |
  | Interface | NVMe with its version, SATA or USB |
  | Speed | the link the drive runs at now: the PCIe generation and lanes of an NVMe drive, the speed of a SATA or USB link. Hover it to see what the drive could do. |
  | Board link | the most the board's port offers the drive (its PCIe slot, SATA port or USB bus). Orange when that carries less than the drive can do, so the board holds the drive back; green when it is fast enough. Hover it for the numbers. |
  | Rated R / W MB/s | the maker's rated read and write speed, from SSD Check's list of drives, see below |

- The state beside the name:

  | State | Meaning |
  |---|---|
  | No problems reported | the drive flags nothing |
  | The drive reports a problem | the drive itself flags a problem; hover the state to see which (little spare space left, too hot or too cold, less reliable, read-only, its backup power failed, or SMART says it is failing). Back up what you want to keep. |
  | Health not reported | the drive gives its hours and cycles, but no health value SSD Check knows |
  | Partly read | the drive's SMART attributes could not be read this time; the boxes show what udisks had. Refresh tries again. |
  | No SMART over USB | the drive is on USB and its adapter does not pass its SMART values on; the specs still show |
  | No drive found | udisks knows no NVMe or SATA drive with SMART values, and no drive on USB |
  | udisks does not answer | the udisks service is not running; the line under the boxes says what it answered |

- The **Health** box is green, orange at 0 % and red when the drive reports a problem. At 0 % the drive has used
  its rated endurance. Many drives keep working long after that, but make sure your backup is current.
- The small **i** explains the values.

### Where the values come from

udisks, the service that mounts drives on the desktop, reads each drive's SMART values now and then and answers
any user over D-Bus; SSD Check asks it with `busctl`. The line under the boxes says when udisks last read the
drive. Refresh shows what udisks read last; it does not make the drive read again.

An NVMe drive reports all three values in the same way on every make. A SATA SSD reports its health in an attribute
its maker chose. SSD Check reads the first of these it finds, as the life left in percent:

| Attribute | Name | Used by |
|---|---|---|
| 231 | SSD life left | Kingston, SandForce and many others |
| 169 | Remaining lifetime | Western Digital |
| 202 | Percent lifetime remaining | Crucial, Micron |
| 233 | Media wearout indicator | Intel |
| 177 | Wear leveling count | Samsung |

A SATA drive with none of them shows **Not reported** in the Health box; hover a known value to see which attribute
it came from. A hard disk is listed too, with its hours and cycles.

A drive on USB (a stick, an external SSD or disk, an M.2 drive in an enclosure) is listed with its specs. udisks
cannot read SMART values through most USB adapters (some pass them only to `smartctl`, which needs root): then the
health, the power cycles, the hours and the data read and written stay empty and the state says **No SMART over
USB**. An M.2 enclosure with a known NVMe bridge (Realtek RTL9210, ASMedia ASM2362, JMicron JMS583) shows **NVMe
over USB** as its interface.

**A drive stuck at USB 2.0.** A USB 3 port is two ports to Linux, one for USB 2.0 and one for USB 3. When a drive
links at USB 2.0 (480 Mb/s, about 40 MB/s in practice) in a port that does USB 3, the **Speed** pill turns orange,
and hovering it says what to try: another cable (many USB-C cables carry only USB 2.0), the drive straight in the
board instead of through a hub, or plugging it in again. **Board link** then shows what the port can do.

The speed test needs a folder on the drive you may write to. A drive with another system on it has file systems
that belong to root: the **Test** pill then stays empty, and hovering it says why.

**Host reads** and **Host writes** of an NVMe drive come from its own counters. A SATA drive keeps them in
attributes 242 and 241, which SSD Check counts as 512-byte sectors, as most makers do; a maker that counts in
other units shows a number that is off. The **Speed** comes from the kernel (sysfs).

### Speed: the drive, the board and the measurement

The last row of specs and the **Test** pill at the top answer whether the drive can run at its full speed in
this board.

- **Board link** is the most the board's port carries: a PCIe port's generation and lanes, a SATA port's limit or
  the USB bus's speed, with about how many MB/s that carries. On the BC-250, the M.2 slot is a PCIe 2.0 x2 port:
  at most about 1,000 MB/s, so a PCIe 3.0 or 4.0 drive is held back there.
- **Rated R / W** is what the maker says the drive reads and writes, in MB/s. No drive reports it, so SSD Check
  keeps a list from the makers' data sheets, of the NVMe drives of PCIe 3.0 and later and a few SATA SSDs, each
  capacity with its own speeds where the maker rates them per capacity:

    | Maker | Drive | Capacities |
    | --- | --- | --- |
    | Samsung | 970 EVO Plus | 250GB, 500GB, 1TB, 2TB |
    |  | 980 | 250GB, 500GB, 1TB |
    |  | 980 PRO | 250GB, 500GB, 1TB, 2TB; with heatsink 1TB, 2TB |
    |  | 990 EVO | 1TB, 2TB |
    |  | 990 EVO Plus | 1TB, 2TB, 4TB |
    |  | 990 PRO | 1TB, 2TB, 4TB, also with heatsink |
    |  | 9100 PRO | 1TB, 2TB, 4TB, 8TB, also with heatsink |
    |  | 860 EVO, 870 EVO (SATA) | every capacity |
    | WD_BLACK | SN750 | 250GB, 500GB, 1TB, 2TB, 4TB |
    |  | SN750 SE | 250GB, 500GB, 1TB |
    |  | SN770 | 250GB, 500GB, 1TB, 2TB |
    |  | SN770M | 500GB, 1TB, 2TB |
    |  | SN850 | 500GB, 1TB, 2TB |
    |  | SN850X, SN850P | 1TB, 2TB, 4TB, 8TB |
    |  | SN7100 | 500GB, 1TB, 2TB, 4TB |
    |  | SN8100 | 1TB, 2TB, 4TB, 8TB |
    | Crucial | P3, P3 Plus | 500GB, 1TB, 2TB, 4TB |
    |  | P5 Plus | 500GB, 1TB, 2TB |
    |  | T500 | 500GB, 1TB, 2TB, 4TB |
    |  | P310 | 500GB, 1TB, 2TB |
    |  | T700, T705, T710 | 1TB, 2TB, 4TB |
    |  | P510 | 1TB |
    |  | MX500 (SATA) | every capacity |
    | SK hynix | Gold P31, Platinum P41 | 500GB, 1TB, 2TB |

  A drive that is not in the list shows **Unknown**; hover it to see what its fastest link carries instead. A few
  drives are left out on purpose because their maker's rated speeds are not clear: the Crucial E100 (only shops
  give speeds), the Crucial P310 4TB and the P510 2TB, and SK hynix's Platinum P51 (the maker's only document rates
  it lower than the drive that went on sale). Two brands always show Unknown:
    - **Netac:** every Netac NVMe drive tells the system only its capacity ("Netac NVMe SSD 1TB"), never which
      model it is. A 1TB Netac can be anything from a PCIe 3.0 NV3000 (3,100 MB/s read) to a PCIe 5.0 NV150HK
      (13,000 MB/s), so SSD Check cannot know its rated speed. Netac's product pages list them per model.
    - **CUSU:** its drives do tell their model ("CUSU CV3500Q 1TB"), but CUSU publishes no specifications, and
      the speeds sellers list are not the maker's.
- **Measured R / W** is what the drive does in this board. Click the **Test** pill at the top: SSD Check writes a test file of 1 GB to the
  drive, reads it back and deletes it, which takes a few seconds (at most ten seconds of writing on a slow drive).
  The file goes in your home folder when that is on the drive (`~/.cache/bc250-ssd/`), else on the drive's first
  mount point you can write to, such as a USB stick. A drive that is not mounted cannot be measured. The test
  needs 2 GB of free space, writes random data and bypasses the cache, so the numbers are the drive's.

When the board holds the drive back, the measured speeds stay under what the board link carries, however fast the
drive is rated.

### Firmware updates

The **Update** pill asks fwupd, Bazzite's firmware updater, whether the LVFS (the Linux Vendor Firmware Service) has
a newer firmware for the drive:

| Update | Meaning |
|---|---|
| Available | a newer firmware is on the LVFS; hover the pill for its version. GNOME Software or `fwupdmgr update` installs it: back up first. |
| Up to date | fwupd knows no newer firmware for the drive |
| Unknown | fwupd does not answer, or has no firmware list yet: `fwupdmgr refresh` downloads it. Hover the pill to see which. |
| Not supported | fwupd does not know the drive, or cannot update its firmware |

SSD Check only asks: it never installs firmware.

The serial number shows only when you click its pill, and is never written to a log.

## Install

Install it from the portal (the **Utilities** tab), or from a checkout of the repository:

```bash
bc250-bazzite/apps/ssd/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bc250-bazzite/apps/ssd/install.sh --no-desktop-shortcut   # without the Desktop icon
bc250-bazzite/apps/ssd/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/bc250-ssd`; the app runs on the suite's shared Python environment. It needs
`busctl` (systemd's) and the udisks service, which every Bazzite has.

## License

GPL-3.0-or-later, see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/ssd/LICENSE).
