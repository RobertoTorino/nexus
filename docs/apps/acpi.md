![BC-250 Persistent ACPI](../assets/acpi/bc250-persistent-acpi.webp){ .app-logo }

# BC-250 Persistent ACPI

Safe alternative to BIOS flashing: a **persistent** ACPI fix for the AMD BC-250 that gives the
board CPU C-states (idle) and frequency scaling (800 MHz – 3.2 GHz, 8 steps) on Linux —
without the P3.00 MeiMeiDXE v3 modded BIOS.

The ACPI tables come from [e-tho/bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix)
(maintained fork of [bc250-collective/bc250-acpi-fix](https://github.com/bc250-collective/bc250-acpi-fix)),
vendored here from release **v1.1.1**. Three SSDT overrides are loaded from an early initrd via the
kernel's [ACPI table upgrade](https://docs.kernel.org/admin-guide/acpi/initrd_table_override.html):

| Table | Fixes |
|---|---|
| `SSDT-CPU` | Replaces the broken idle-state table (C-states) |
| `SSDT-PST` | Publishes the 8 frequency states |
| `SSDT-STUBS` | Defines missing firmware methods as no-ops |

Works on stock 6-core and unlocked 8-core boards, on all stock BIOS versions
(1.00, 2.00, 3.00 and 5.00 share the same DSDT).

## Is this ACPI fix persistent?

**Yes, it survives updates**:

* `/boot/acpi_override.cpio` — extra files in `/boot` are left alone by `rpm-ostree`
  / bootc image updates; only `/boot/ostree` and `/boot/loader` are managed.
* `/etc/default/grub` — `/etc` is machine-local state on ostree systems and is
  3-way-merged across deployments, so the `GRUB_EARLY_INITRD_LINUX_CUSTOM` line stays.
* **Kernel updates**: Fedora's `blscfg` GRUB module prepends the early initrd to **every**
  BLS boot entry at boot time, including kernels installed later. No re-install, no
  regeneration needed after a kernel or image update.

Unlike BIOS flashing it is fully reversible (Uninstall in the app,
`sudo ./bc250-acpi-override.sh --uninstall`, or just delete the file and the GRUB line) and
carries zero bricking risk.

## Install (Bazzite / Universal Blue)

Install the app from the BC250 Bazzite Suite portal, or from a clone or release folder, as your
own user (not with sudo):

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
```

Installing the app changes nothing on the board. Open **BC-250 Persistent ACPI** and click
**Install**, then reboot. The window shows whether the override is installed, the CPU's
frequency steps and idle states, and (with **Status with sudo**) whether the kernel loaded the
tables this boot.

From a terminal, without the app:

```bash
sudo ./bc250-acpi-override.sh --install
# reboot
```

The installer checks for a BC-250 GPU, warns on modded BIOSes (duplicate tables fail to
load — do **not** combine this with a modded BIOS that injects its own fixes), verifies
`CONFIG_ACPI_TABLE_UPGRADE`, installs the cpio, adds the GRUB line idempotently and runs
`ujust regenerate-grub` (or `grub2-mkconfig` on plain Fedora, where the path in
`GRUB_EARLY_INITRD_LINUX_CUSTOM` is relative to `/boot/grub2/`). In a terminal a warning asks
"Continue anyway?"; the app shows the warning in a dialog. `--yes` answers yes to both warnings.

### Manual install

```bash
sudo cp tables/acpi_override.cpio /boot/
echo 'GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"' | sudo tee -a /etc/default/grub
ujust regenerate-grub   # then reboot
```

## Verify

The app's status shows the same information. From a terminal:

```bash
./bc250-acpi-override.sh --status                    # installed? frequency steps, idle states
sudo dmesg | grep -iE 'ACPI.*(SSDT|Table Upgrade)'   # 3 tables loaded as override
cpupower frequency-info                              # 8 steps, 800 MHz - 3.2 GHz
cpupower idle-info                                   # POLL, C1, C2 (C2 at 0x414)
```

Or run test 26 of [BC-250 Bazzite Test](check.md),
which reports whether the ACPI tables came from the initrd override or the BIOS.

## Uninstall

Click **Uninstall** in the app and reboot, or from a terminal:

```bash
sudo ./bc250-acpi-override.sh --uninstall
# reboot
```

To remove the app itself: `./install.sh --uninstall` (add `--purge` to also remove its
settings). This leaves the override as it is; uninstall the override first if you want the
board back on the BIOS tables.

## Vendored artifacts

`tables/` contains the unmodified assets of e-tho/bc250-acpi-fix v1.1.1 (MIT):

```
b2f5cd6279ef5992f6482a1702e1dd5c0ebeeaf950fde487d7556ef7a291956b  acpi_override.cpio
9cfc1a254ea8814988d5a700e2dba8ebbe4f290a3895435512ea8afa3ba6a46f  SSDT-CPU.aml
cb3c96c622d2d653777020283c434f92c26bf2c83502a27d9a398f98424a771f  SSDT-PST.aml
c219ce775476725d49739024e149556228436a1c3faf0768a7c3eff9d85f66c2  SSDT-STUBS.aml
```

To rebuild from source instead, see the upstream `Makefile` (needs `acpica`/`iasl`).

## Acknowledgements

* [e-tho](https://github.com/e-tho/bc250-acpi-fix) — maintained tables and installation method.
* [shinf1x](https://github.com/bc250-collective/bc250-acpi-fix) — original tables.
* [rw-r-r-0644](https://github.com/rw-r-r-0644/bc250-acpi-fix) — idle-table diagnosis and ACPI error cleanup.
* [mendesrr](https://github.com/mendesrr/bc250-acpi-fix-updated-8c) — 8-core extension.

## License

MIT — see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/apps/acpi/LICENSE). Vendored tables are MIT-licensed by their upstream authors.
