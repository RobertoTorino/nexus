<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# shadPS4 Manager

Plays your PS4 games on a Windows handheld with shadPS4, the PS4 emulator: shadPS4 0.20.0 for Windows from shadPS4's
own release, checked against the checksum this version of the app was tested with, for your own user; shadPS4 keeps
its settings, your saves and the system modules in its portable folder beside its program, in the app's folder. It
copies the system modules of your PS4 into shadPS4, unpacks your packages (.pkg) into game folders in the layout
shadPS4 loads (an update beside its game), offers shadPS4's settings and the shadNet account it signs in with, finds
your games in the folders you choose and puts them in Steam (with the game's own pictures, and a cover from
SteamGridDB when you give it your key), and keeps a log. shadPS4's own window is never needed: a game starts full
screen from Steam, and View and Menu together open shadPS4's quit window. Remove takes shadPS4's program away and
leaves what you made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it:
[shadPS4 Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/shadps4/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\shadps4\run.ps1             # full screen
windows-portable\apps\shadps4\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-shadps4.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\`, and shadPS4 with its settings, saves and system
modules in `emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). shadPS4 is a separate program (GPL-2.0), downloaded from its own release.
Extract PKG's PKG/PFS/PSF code is a port of shadPS4's (GPL-2.0-or-later).
