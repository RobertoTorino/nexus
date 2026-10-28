<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<div class="hero" markdown>

![A Windows handheld](images/home/device.webp)

# Windows Portable Suite

Tools for Windows 10/11 running on portable gaming devices.

</div>

The Windows Portable Suite is a set of apps for a Windows handheld, first the ASUS ROG Xbox Ally X. They are made for
the device in your hands: full screen, a small screen, a controller and touch, often without a keyboard. Every
button you can press shows its controller button, and the amber focus shows where the next press of A goes.

The suite is part of [Nexus](https://robertotorino.github.io/nexus/), beside the BC250 Bazzite Suite.

## The apps

| App | What it does |
|---|---|
| [Portal](portal.md) | Installs, updates, opens and removes the suite's apps, each from its own release. |
| [Windows Portable Test](apps/test.md) | What Windows reports about the handheld, and a test of every button, stick and trigger of its controller. Always installed with the portal. |
| [PCSX2 Manager](apps/pcsx2.md) | Installs PCSX2, the PlayStation 2 emulator, in portable mode, and opens it. |

## Get started

[Install](install.md) the portal: it brings Windows Portable Test along, and installs every other app of the suite
from its tiles. The apps install for your own user, not as administrator, and keep their files in your own folders.

## Your files

Every app of the suite keeps its files in one folder per suite:

| Folder | What is in it |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\` | The programs (`<app>\app\`), the logs and what an app saves, such as Windows Portable Test's reports. |
| `%APPDATA%\windows-portable-suite\` | The settings, one `.ini` file per app. |

Nothing goes into the Windows registry.

## Disclaimer

<!-- disclaimer -->
