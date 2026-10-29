<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# PPSSPP Manager

Plays your PSP games on a Windows handheld with PPSSPP, the PSP emulator: PPSSPP 1.20.4 for Windows from PPSSPP's own
release, checked against the checksum this version of the app was tested with, for your own user and in PPSSPP's
portable mode, so its settings, the saves and the save states stay on its memory stick in its folder. It offers
PPSSPP's settings that matter on the handheld, finds your PSP games in the folders you choose and on PPSSPP's memory
stick, plays them and puts them in Steam (with the game's own pictures, and a cover from SteamGridDB when you give it
your key), and keeps a log. PPSSPP's own window is never needed: a game starts alone and full screen, and the pause
menu's Exit closes PPSSPP. Remove takes PPSSPP's program away and leaves what you made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it:
[PPSSPP Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/ppsspp/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\ppsspp\run.ps1             # full screen
windows-portable\apps\ppsspp\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-ppsspp.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\`, and PPSSPP with its memory stick in `emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). PPSSPP is a separate program (GPL-2.0-or-later), downloaded from its own
release.
