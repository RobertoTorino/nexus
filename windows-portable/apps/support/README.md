<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Support Checker

What the suite's apps need on this handheld: Windows' updates, the tools and runtimes, the apps' versions.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [Support Checker in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/support/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\support\run.ps1             # full screen
windows-portable\apps\support\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-support.ini`, the log in `%LOCALAPPDATA%\windows-portable-suite\windows-portable-support\`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
