<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![SSD Check](../images/apps/ssd.webp){ .app-logo }

# SSD Check

How the handheld's SSD is doing: its **health**, **power cycles** and **power-on hours**, its specs, and how fast
it runs in this handheld. A memory card and a drive on USB are listed too, with their specs. It only reads the drives
(the speed test writes a test file and deletes it): nothing on a drive changes, it needs no administrator, and it
never reads a drive's serial number.

| Value | What it shows |
|---|---|
| Health | how much of its rated life the drive has left, in percent: 100 minus the drive's own "percentage used" |
| Power cycles | how often the drive was switched on |
| Power-on hours | how long it has run in all |
| Power-on days | the power-on hours in full days (4,025 hours are 167 days): a day not yet complete does not count |

SSD Check is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **SSD Check**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## The screen

A card on the left for each drive, **Drive 1**, **Drive 2** and so on, in the order Windows' Disk Management numbers
them, with the drive's health or what kind of drive it is. The card with the focus shows its drive on the right: its
model, its kind, size and drive letters, its state and its values. **☰** (Menu) explains the values.

| Button | What it does |
|---|---|
| **X Test speed** | measures the drive's read and write speed in this handheld, see below |
| **Y Read again** | reads the drives again |
| **RB Screenshot** | saves the window as a PNG in your Pictures folder, in a folder named SSD Check (`SSD Check 2026-11-06 18-04-09.png`, the date and time in its name); Explorer then opens on that folder with the new file selected |

The values, beside the health, power cycles and hours:

| Value | What it shows |
|---|---|
| Host reads | how much data the handheld has read from the drive in all |
| Host writes | how much data the handheld has written to the drive in all |
| Firmware | the version of the drive's firmware |
| Interface | NVMe with its version, SATA, USB or SD card |
| Speed | the PCIe link the drive runs at now; the line under the values says whether that is all the drive can do |
| Board link | the most the port above the drive offers, when Windows says: amber when that carries less than the drive can do |
| Rated R / W MB/s | the maker's rated read and write speed, from SSD Check's list of drives, see below |
| Measured R / W MB/s | what **X** measured in this handheld |

The state under the drive's model:

| State | Meaning |
|---|---|
| No problems reported | the drive flags nothing |
| The drive reports a problem | the drive itself flags a problem, named after it (little spare space left, too hot or too cold, less reliable, read-only, its backup power failed). Back up what you want to keep. The card says so too. |
| Its rated endurance is used up | the health is 0 %: the drive has used its rated endurance. Many drives keep working long after that, but keep your backup current. |
| Health needs an administrator | a SATA drive: see below |
| No SMART over USB | a drive on USB: Windows passes no SMART values through its adapter |
| No SMART on a memory card | an SD card reports none |

### Where the values come from

Windows' storage driver gives an NVMe drive's health log (its SMART values) to any user: SSD Check asks it for
them. The list of drives, their firmware and their drive letters come from Windows' storage inventory, and the link
from the drive's controller in Device Manager.

A **SATA drive** keeps its SMART values where Windows lets only an administrator read them: SSD Check shows its
specs, and its health, power cycles and hours stay empty. A **drive on USB** and a **memory card** pass no SMART
values on; their specs show. A memory card's **Speed** is the card reader's link, not the card's.

Windows does not report every port's link: on the ROG XBOX Ally X the drive gives its link (PCIe 4.0 x4) and its
port gives none, so **Board link** says **Not reported** there.

### Speed: the drive, the port and the measurement

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

  A drive that is not in the list shows **Unknown**, and the line under the values says what its fastest link
  carries instead. The SSD a handheld comes with is often a maker's OEM model (the Ally X's
  `SAMSUNG MZVMA1T0HCLD-00BTW`), which has no public data sheet: it shows **Unknown**. Netac's NVMe drives never
  report which model they are, and CUSU publishes no specifications: both always show Unknown.
- **Measured R / W** is what the drive does in this handheld. **X** writes a test file of 1 GB to the drive, reads
  it back and deletes it, which takes a few seconds (at most ten seconds of writing on a slow drive). The file goes
  in the app's own folder when that is on the drive, else at the root of the drive's first drive letter (an SD card,
  a USB stick), hidden. A drive without a drive letter cannot be measured. The test needs 2 GB of free space, writes
  random data and bypasses Windows' cache, so the numbers are the drive's.

## Install it on its own

The portal installs it. To install it on its own, download `wp-ssd-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-ssd-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-ssd-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-ssd-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings and the log stay |
| `--uninstall --purge` | also remove the settings and the log |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ssd\app\` | The program, `SSD-Check.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ssd\windows-portable-ssd.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-ssd.ini` | The settings |
