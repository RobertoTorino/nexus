<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# USB HD Cam

!!! warning "Changes the board"
    Allow access installs a system-wide udev rule for supported camera identifiers. A per-user service loads camera firmware when the camera connects. The udev rule is removed when the app is uninstalled.

USB HD Cam loads firmware for supported Sony USB cameras and provides a preview, camera controls, recording and
capture tools. The app recognizes the PS5 HD Camera (CFI-ZEY1) and PS4 Camera (CUH-ZEY1 or CUH-ZEY2) identifiers in
its code. The PS4 Camera uses Sony's PlayStation Camera Adapter (CFI-ZAA1).

The Console Suite port has not been validated on PS5 hardware. Recognition of these camera identifiers does not
establish that every PS5 Bazzite system, USB port or adapter is compatible.

## Install

Run the installer from a repository checkout:

```bash
bazzite-console/apps/hdcam/install.sh
bazzite-console/apps/hdcam/install.sh --no-desktop-shortcut
bazzite-console/apps/hdcam/install.sh --uninstall
bazzite-console/apps/hdcam/install.sh --uninstall --purge
```

The app is available from the desktop menu or `~/.local/bin/ps5-usb-hdcam`.

## Allow camera access

The first time you choose **Allow access**, the app opens a password dialog and asks to add a system-wide udev rule.
This permission is needed to send firmware to the camera's USB boot loader. The rule is limited to the supported
camera identifiers and is removed by `install.sh --uninstall`. The app and its firmware loader run as your user;
the app does not run as root.

The installer creates a per-user service that sends firmware at login and when the camera is connected. The camera's
udev rule starts the service for a newly connected camera. No camera firmware is included with the app; the app can
download pinned files with checksum checks or use a firmware file you provide.

## Use

Connect the camera, allow access when prompted, and choose a preview mode. Linux exposes a camera with loaded
firmware as a video device that other applications can use. If the camera is not detected, reconnect it and check
the USB connection. The app offers a reduced-bandwidth mode for systems whose USB controller cannot use the full
video endpoint bandwidth.

## Firmware and license

The camera firmware belongs to Sony and is not included. The pinned PS5 camera image is published by
[prosperodev/hdcamera](https://github.com/prosperodev/hdcamera); PS4 camera firmware is published by
[psxdev/luke_firmwares](https://github.com/psxdev/luke_firmwares). USB HD Cam is GPL-3.0-or-later; see the app's
README and LICENSE in `bazzite-console/apps/hdcam/`.
