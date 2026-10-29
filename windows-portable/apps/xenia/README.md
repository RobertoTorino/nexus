<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Xenia Manager

Plays your Xbox 360 games on a Windows handheld with Xenia, the Xbox 360 emulator: Xenia Canary build e6cd2e4 for
Windows from Xenia Canary's own release, checked against the checksum this version of the app was tested with, for
your own user; Xenia keeps its settings, your games' content and your saves beside its program, in the app's folder.
The app offers Xenia's settings, finds your games in the folders you choose (disc images, unpacked discs, Games on
Demand and Arcade packages) and puts them in Steam (with pictures drawn from the app's icon, or from SteamGridDB when
you give it your key), and keeps a log. Xenia's own window is never needed: a game starts full screen from Steam.
Remove takes Xenia's program away and leaves what you made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it:
[Xenia Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/xenia/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\xenia\run.ps1             # full screen
windows-portable\apps\xenia\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-xenia.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\`, and Xenia with its settings, content and saves in
`emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Xenia is a separate program (BSD-3-Clause), downloaded from its own release.
