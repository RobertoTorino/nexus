<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci-bazzite-console.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-bazzite-console.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# USB HD Control

USB HD Control is an optional utility for Sony DualSense and DualSense Edge controllers. Its code recognizes Sony
USB product IDs `0x0CE6` and `0x0DF2` when Linux's `hid-playstation` driver exposes them through `hidraw`. It shows
the connection, battery and firmware; updates firmware from Sony's update server over USB; and backs up, displays
and edits the DualSense Edge's profiles. The Console Suite port has not been validated on PS5 hardware, and behavior
depends on the kernel driver and the system's controller support.

The app does not request root; it relies on the system's permissions for the controller's `hidraw` device. Firmware
updates require a USB cable and should be left to finish without disconnecting the controller. Sony's firmware is
not included in the app.

Installing the app does not enable the Bluetooth idle-off feature. To opt in, pass `--enable-idle-service` to the
installer. This adds and enables a **per-user** systemd service (not a system-wide service); it disconnects idle
Bluetooth controllers after the interval selected in the app. The service is removed when you uninstall the app.

## Install

Run the installer from a checkout:

```bash
bazzite-console/apps/hdcontrol/install.sh
bazzite-console/apps/hdcontrol/install.sh --enable-idle-service
bazzite-console/apps/hdcontrol/install.sh --no-desktop-shortcut
bazzite-console/apps/hdcontrol/install.sh --uninstall
bazzite-console/apps/hdcontrol/install.sh --uninstall --purge
```

The launcher is `~/.local/bin/ps5-usb-hdcontrol`; the app uses the Console Suite's shared Python environment.

How to use it: [USB HD Control in the wiki](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/hdcontrol/).

## License and firmware

The app is GPL-3.0-or-later; see [LICENSE](LICENSE). The controller update protocol is ported from
[dualsense-updater-rs](https://github.com/nchie/dualsense-updater-rs), MIT, Copyright 2026 nchie. The Edge profile
layout and writing are ported from [dualsense-edge-profile-web-application](https://github.com/steffalon/dualsense-edge-profile-web-application),
MIT, Copyright (c) 2023 steffalon. The relevant files retain their attribution, and the MIT license notice is
included below. Sony's firmware is not part of this app.

```
MIT License

Copyright 2026 nchie (dualsense-updater-rs)
Copyright (c) 2023 steffalon (dualsense-edge-profile-web-application)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
