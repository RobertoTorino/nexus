<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 USB Wi-Fi](../assets/wdriver/bc250-usb-wifi.webp){ .app-logo }

# BC-250 USB Wi-Fi

The driver for **AIC8800D80 USB Wi-Fi sticks** on the **AMD BC-250** with **Bazzite**. The UGREEN AX900 and many
other small Wi-Fi 6 sticks use this chip, and Bazzite's kernel has no driver for it: the stick shows up, and no
`wlan0` comes. The app builds the driver on the board for the running kernel, installs it with a system service
that loads it at every boot, and builds it again after a kernel update.

The driver is a kernel module, so this app **changes the board**. It is software-only: Remove unloads it and takes
every file away, and the board is as before.

## What you need

- An AIC8800D80 stick. It is sold under many names; `lsusb` shows it as `a69c:5723` (or a nearby number) in
  storage mode and as `a69c:8d80` or `a69c:8d81` once switched.
- The kernel's build tree (`kernel-devel`), `gcc`, `make` and `git`. Bazzite's image has all four. The Dependency
  Checker shows them.
- The network, once, for the sources: a shallow fetch of one commit, about 13 MB.

## Using it

The top row shows the **stick** (storage mode, waiting for its firmware, or Wi-Fi mode), the **chip** (its
revision and MCU as the loader reported it in the kernel log), the **driver** (built, or the installed branch) and
the **Wi-Fi** interface the driver created.

1. **Driver branch:** chosen from the chip's answer. A chip that reports MCU 1 takes `legacy-mcu1`; MCU 0 takes
   `main`. When the chip has not answered yet, the app proposes `main`, and says what to do when the firmware
   upload then breaks off (see below).
2. **Build:** fetches the pinned sources into your home folder and builds the two modules against the running
   kernel, as your own user. The output shows in the window; it takes a minute or two. The sources come from a
   mirror of the driver's repository under the suite's own account, and from the original repository when the
   mirror does not answer.
   **Newest sources (untested)** fetches the branch's current head instead of the tested commit: for the day a
   new kernel breaks the pinned build and the fix is already upstream but not yet in a release of this app. The
   window marks such a driver as newest; the next release brings a tested pin again.
3. **Install…:** copies the build and the sources to `/var/lib/bc250-usb-wifi`, writes the stick's udev rule and
   the service, and starts the service, which loads the driver now. The app asks first, then asks for your
   password. A stick in storage mode is switched at the same time.
4. Connect in the desktop's network settings. **The stick's firmware does WPA2, not WPA3:** when your router
   offers both on one network, set the connection to WPA2 (in the connection's Wi-Fi security, or
   `nmcli connection modify "<network>" wifi-sec.key-mgmt wpa-psk`). With WPA3 chosen, the router rejects every
   attempt and the desktop keeps asking for the password.

**Update…** replaces the installed driver with the current build (another branch, or the service of a newer app
version). **Remove…** unloads the driver and removes it, its service and its rule; the build in your home folder
stays. **What the service did** shows the service's last run: what it built, loaded and ejected, and any error.

**Wi-Fi adapters** lists every Wi-Fi adapter on the board, of any chip, and whether the running kernel has a
driver and firmware for it: plug a stick in and press **Refresh** to see whether it works on Bazzite, before or
instead of this app's driver. It is the same check as [BC-250 Bazzite Test's](check.md) test 53, and only reads.

## The chip and its two firmware sets

The AIC8800D80 exists in two MCU revisions, and the loader prints which one it found before it uploads anything:
`chip_id=7, chip_mcu_id = 1` in the kernel log. The newer firmware (SDK 5, the `main` branch) is larger than the
older MCU takes: its upload breaks off at address 0x170400, the stick gets no firmware, and it then answers
`chip_id=0` until it is unplugged and plugged in again. The `legacy-mcu1` branch carries the older firmware (SDK 3)
with a loader matched to it; on that MCU, Wi-Fi on both bands and Bluetooth through the kernel's own `btusb` work.

So, when the chip is unknown: install `main`; if the log then shows the failed upload, the app says so and
proposes `legacy-mcu1`; build and install that, and plug the stick in again. The app reads the chip's answer from
every boot the journal keeps, so after the first time it knows.

## Compatibility

The driver is for the AIC8800 chip family, not for one stick. Its match tables claim AICSemi's two USB vendor IDs
(`a69c` and `368b`) with the 8800, 8801, D80, D81, D40 and D41 product IDs, the DC, DE, DW, DLN and DWN siblings,
the D80N and D40N parts, the M80 and FC customer IDs, and the branded IDs of Tenda (U2, U11, U11 Pro, TX1U Nano)
and UGREEN (`8d88`). A stick with one of these IDs is claimed by the modules the app builds, whatever name it is
sold under. Wi-Fi-only sticks and Wi-Fi/Bluetooth combo sticks both work: the Bluetooth side goes to the kernel's
own `btusb`.

The firmware is what narrows it. The driver's sources carry firmware for six variants (8800, D80, D80N, D80X2, DC
and DLN); the app installs the **AIC8800D80** set only, in the two MCU revisions described above. A stick with a
D80N, DC or DLN chip binds to the driver but needs a firmware set the app does not install, so it gets no
`wlan0`; its chip line in the kernel log says which chip it is.

What the window recognises is narrower than the driver: the stick box knows the storage-mode IDs `a69c:5721`
to `a69c:572c`, the loader ID `a69c:8d80` and the Wi-Fi ID `a69c:8d81`, and shows any other ID as unknown mode.
The udev rule that ejects the virtual disk is written for vendor `a69c`, so a `368b` stick in storage mode is not
switched by the rule; `eject` on its disk does it by hand. Both vendor IDs count as a stick for the rest of the
window.

The modules are built on the board against the running kernel, so they follow Bazzite's kernel rather than one
version; the pinned sources build on kernels up to 7.3, and the service builds them again after a kernel update.
The driver's own tests, upstream, were on 6.1 and 6.16. Tested in the suite: the UGREEN AX900 (`a69c`, MCU 1,
`legacy-mcu1`) on the BC-250.

## The service

`bc250-usb-wifi.service` runs `driver.py load` at every boot:

- when there are no modules for the running kernel, it builds them from the kept sources with the kernel's build
  tree (no network; a minute or two, in the background, with a desktop notification when done or when it failed);
- loads `cfg80211`, then the loader `aic_load_fw` with the firmware folder as its parameter, then `aic8800_fdrv`;
- ejects the virtual disk of a stick that sits in storage mode, which switches it to loader mode; the udev rule
  does the same for a stick plugged in later.

The loader uploads the firmware, the stick re-enumerates in Wi-Fi mode, and `aic8800_fdrv` creates `wlan0`.
Stopping the service unloads the modules. Its log: `journalctl -u bc250-usb-wifi`.

Bazzite's `/usr` is read-only, so the modules cannot go where `modprobe` looks and the firmware cannot go under
`/lib/firmware`; the service loads them with `insmod` from `/var/lib` instead, and the driver's own firmware-path
parameter points at the folder there.

## Files

- `~/.local/share/bc250-usb-wifi/src/<branch>/`: the sources, at the pinned commit.
- `~/.local/share/bc250-usb-wifi/build/<branch>/<kernel>/`: the modules, the firmware folder and the build log.
- `/etc/bc250-usb-wifi/driver.py` and `driver.json`: the service's helper and which branch is installed.
- `/etc/systemd/system/bc250-usb-wifi.service` and `/etc/udev/rules.d/90-bc250-usb-wifi.rules`.
- `/var/lib/bc250-usb-wifi/src/<branch>/` and `modules/<kernel>/`: what the service builds from and loads.
- `/run/bc250-usb-wifi/state.json`: the service's last run, which the app shows.
- `~/.config/bc250-usb-wifi/bc250-usb-wifi.ini`: the window's size and place, and a branch chosen by hand.

## When it does not work

- **The stick stays in storage mode:** the udev rule ejects its virtual disk when the stick is plugged in and the
  service does so at boot. By hand: `sudo eject /dev/sdX` (the disk `lsblk` shows with vendor AIC).
- **The chip box turns red:** the firmware upload broke off. The chip needs the other branch; build and install
  it, then unplug the stick and plug it in again, so it starts afresh.
- **No wlan0 after a kernel update:** the service builds at boot; give it two minutes and watch for the
  notification. When the build failed, the window shows the error and `journalctl -u bc250-usb-wifi` the log. A
  kernel the pinned driver does not build on yet needs a newer pin (a new release of this app); until then, tick
  **Newest sources**, Build and Update: when the fix is upstream already, that build works.
- **The desktop keeps asking for the Wi-Fi password:** the connection uses WPA3; set it to WPA2, see Using it.
- **Bluetooth:** the stick's Bluetooth comes up on the kernel's own `btusb` driver once the firmware runs; the app
  does nothing for it.

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app and the driver's service; keeps its settings and builds
./install.sh --uninstall --purge     # also remove its settings and the builds in your home folder
```

Installing and removing the driver needs `pkexec` and the system `python3`; Bazzite has both. Uninstalling the app
also unloads and removes the driver (with `sudo`).

## License

GPL-3.0-or-later. See [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/apps/wdriver/LICENSE).
The driver it builds is [shenmintao/aic8800d80](https://github.com/shenmintao/aic8800d80), GPL-2.0-only, fetched
at a pinned commit from the suite's mirror [RobertoTorino/aic8800d80](https://github.com/RobertoTorino/aic8800d80)
or from the original; the firmware files in it are AICSemi's.
