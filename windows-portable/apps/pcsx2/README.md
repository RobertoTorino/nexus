<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# PCSX2 Manager

Installs PCSX2, the PlayStation 2 emulator, on a Windows handheld and opens it: PCSX2 2.8.2 for Windows from
PCSX2's own release, checked against the checksum this version of the app was tested with, for your own user and in
PCSX2's portable mode, so its settings, the BIOS, the memory cards and the save states stay in its folder. It sets
PCSX2 up to open ready to play with the handheld's controller, in Big Picture mode, and offers PCSX2's settings that
matter on the handheld. Remove takes PCSX2's program away and leaves what you made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B closes the app, and
everything also works by touch. How to install and use it: [PCSX2 Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/pcsx2/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\pcsx2\run.ps1             # full screen
windows-portable\apps\pcsx2\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-pcsx2.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\`, and PCSX2 with its own files in `emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
