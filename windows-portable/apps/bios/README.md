<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# BIOS Reader

The BIOS's setup screens and defaults, hidden menus included, from a BIOS file. It only reads.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [BIOS Reader in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/bios/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\bios\run.ps1             # full screen
windows-portable\apps\bios\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-bios.ini`, the log in `%LOCALAPPDATA%\windows-portable-suite\windows-portable-bios\`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
