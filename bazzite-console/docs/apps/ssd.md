<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![SSD Check](../assets/ssd/ps5-ssd-check.webp){ .app-logo }

# SSD Check

SSD Check is an optional utility for PlayStation 5 hardware running Bazzite. It shows drive information exposed by
udisks and can measure a writable filesystem. It does not install firmware or require root to read information.

## Compatibility

The app lists udisks NVMe controllers, SMART-capable ATA drives, and USB drives with a medium. It depends on
systemd's `busctl`, udisks and the interfaces and data they expose. A USB bridge may hide SMART data; other storage,
including devices not exposed as these udisks drive types, is not listed. Encrypted or layered storage and mount
mapping can also prevent the speed test from finding a writable filesystem. **PS5 internal storage and attached-drive
visibility have not been verified on hardware**: no drive found does not mean there is no storage, and a missing value
is not evidence of a healthy drive. Check important data and backups independently.

## Using it

Choose a detected drive and press **Refresh** to show the last values read by udisks. Health uses NVMe percentage
used or a known vendor-specific ATA attribute; the latter is not universal. Power cycles, hours, data transferred,
firmware, interface and link values appear when reported. The serial number stays hidden until selected; screenshots
hide it. The maker's rated speeds are a small model-specific reference list from manufacturers' data sheets, not a
measurement. Link and port limits are estimates from sysfs, not verified PS5 hardware specifications.

**Measured R / W** runs only when a writable mount can be identified. Clicking Test writes up to 1 GiB of random data
and reads it back, then removes the test file. It requires twice that space free, causes drive writes and may affect
performance or wear. It tries direct I/O; results depend on the filesystem, caching, load and hardware. A preexisting
test file is not overwritten. If interrupted, a test file may remain in the selected mount or the app's cache folder.

The **Update** field asks fwupd about firmware through the Linux Vendor Firmware Service (LVFS) metadata. A missing
fwupd service or metadata gives an unknown result; a drive fwupd does not know is not supported *by fwupd*. An
available update is not installed by this app. Back up before using another tool to install firmware.

## License

GPL-3.0-or-later, see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bazzite-console/apps/ssd/LICENSE).
