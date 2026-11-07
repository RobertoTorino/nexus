<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci-bazzite-console.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-bazzite-console.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# USB HD Cam

USB HD Cam is an optional desktop utility for Sony USB cameras on Bazzite. Its code recognizes the PS5 HD Camera
(CFI-ZEY1) and the PS4 Camera (CUH-ZEY1 or CUH-ZEY2) connected through Sony's PlayStation Camera Adapter
(CFI-ZAA1). Recognition is based on the camera's USB identifiers; the Console Suite port has not been validated on
PS5 hardware, so these identifiers do not guarantee compatibility with every system or adapter.

The cameras start in a firmware-loading mode. The app can download a pinned firmware file with a checksum check or
use a file you provide. Sony's firmware is not included with the app. After loading, Linux exposes the camera as a
USB video device for apps such as OBS or a browser. The window shows the connection, preview, supported camera modes
and controls, and can record or capture the preview.

Installing the app does not change system permissions. When you choose **Allow access** in the app, a password
dialog asks permission to install a system-wide udev rule for the camera's USB boot loader. The app itself then runs
as your user. The installer also adds a per-user service that loads firmware at login and when the camera is
connected; the udev rule starts it for a newly connected camera.

## Install

Run the installer from a checkout:

```bash
bazzite-console/apps/hdcam/install.sh
bazzite-console/apps/hdcam/install.sh --no-desktop-shortcut
bazzite-console/apps/hdcam/install.sh --uninstall
bazzite-console/apps/hdcam/install.sh --uninstall --purge
```

The launcher is `~/.local/bin/ps5-usb-hdcam`; the app uses the Console Suite's shared Python environment.

How to use it: [USB HD Cam in the wiki](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/hdcam/).

## License and firmware

The app is GPL-3.0-or-later; see [LICENSE](LICENSE). Camera firmware belongs to Sony and is not part of this app.
The pinned PS5 camera image is published by [prosperodev/hdcamera](https://github.com/prosperodev/hdcamera); PS4
camera firmware is published by [psxdev/luke_firmwares](https://github.com/psxdev/luke_firmwares). The app checks
downloaded files against pinned sizes and SHA-256 hashes.
