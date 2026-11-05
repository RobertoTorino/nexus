<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![SSD Check](../assets/ssd/bc250-ssd.webp){ .app-logo }

# SSD Check

Three values that say how an SSD is doing: its **health**, its **power cycles** and its **power-on hours**. It
only reads them: nothing on the drive changes, and it needs no root.

| Box | What it shows | NVMe | SATA SSD |
|---|---|---|---|
| Health | how much of its rated life the drive has left, in percent | 100 minus "percentage used" | an attribute of the drive's maker, see below |
| Power cycles | how often the drive was switched on | "power cycles" | attribute 12 |
| Power-on hours | how long it has run in all; hover it to see the days and years | "power-on hours" | attribute 9 |

## Using it

- **Drive:** with more than one drive, choose it in the list under the boxes. Each is named by its model, its
  device (`nvme0n1`, `sda`) and its size.
- **Refresh** reads the drives again.
- The state beside the name:

  | State | Meaning |
  |---|---|
  | No problems reported | the drive flags nothing |
  | The drive reports a problem | the drive itself flags a problem; hover the state to see which (little spare space left, too hot or too cold, less reliable, read-only, its backup power failed, or SMART says it is failing). Back up what you want to keep. |
  | Health not reported | the drive gives its hours and cycles, but no health value SSD Check knows |
  | Partly read | the drive's SMART attributes could not be read this time; the boxes show what udisks had. Refresh tries again. |
  | No drive reports SMART | udisks knows no NVMe or SATA drive with SMART values |
  | udisks does not answer | the udisks service is not running; the line under the boxes says what it answered |

- The **Health** box is green, orange at 0 % and red when the drive reports a problem. At 0 % the drive has used
  its rated endurance. Many drives keep working long after that, but make sure your backup is current.
- The small **i** explains the three values.

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
it came from. A drive on a USB adapter often hides its SMART values behind the adapter, and is then not listed. A
hard disk is listed too, with its hours and cycles.

A drive's serial number stays out of the window.

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
