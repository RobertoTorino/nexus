<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# USB HD Control

USB HD Control is an optional utility for Sony DualSense and DualSense Edge controllers. Its code recognizes USB
product IDs `0x0CE6` and `0x0DF2` through Linux's `hid-playstation` driver and `hidraw` interface. It shows a
controller's connection, battery and firmware, checks Sony's update server, and updates firmware over USB. For a
DualSense Edge, it can also back up, display and edit the controller's profiles.

The Console Suite port has not been validated on PS5 hardware. Controller detection and functions depend on the
system's kernel driver and controller support.

## Install

Run the installer from a repository checkout:

```bash
bazzite-console/apps/hdcontrol/install.sh
bazzite-console/apps/hdcontrol/install.sh --no-desktop-shortcut
bazzite-console/apps/hdcontrol/install.sh --uninstall
bazzite-console/apps/hdcontrol/install.sh --uninstall --purge
```

The app is available from the desktop menu or `~/.local/bin/ps5-usb-hdcontrol`. It does not request root; access
depends on the system's permissions for the controller's `hidraw` device. Firmware updates require a USB cable;
leave the cable connected and the system powered on until the update finishes.

## Optional Bluetooth idle-off service

The installer does not install or enable this feature by default. To opt in, run:

```bash
bazzite-console/apps/hdcontrol/install.sh --enable-idle-service
```

This installs and enables a per-user systemd service, not a system-wide service. It disconnects a Bluetooth
controller after the idle interval selected in the app. The service leaves USB-connected controllers alone, and the
app removes it when uninstalled.

## Firmware and license

Controller firmware belongs to Sony and is not included with the app. USB HD Control is GPL-3.0-or-later; see the
app's README and LICENSE in `bazzite-console/apps/hdcontrol/`. Its update protocol and
DualSense Edge profile implementation retain the MIT attributions and license notice in the README.
