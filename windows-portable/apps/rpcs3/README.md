<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# RPCS3 Manager

Plays your PS3 games on a Windows handheld with RPCS3, the PS3 emulator: RPCS3 0.0.43 (build 20395) for Windows from
RPCS3's own builds, checked against the checksum this version of the app was tested with, for your own user; RPCS3
keeps the firmware, your saves, its settings and the games installed from packages beside its program, in the app's
folder. You put your games, packages and the firmware in its own folder, `Games\PS3` in your user folder (or on an SD
card), and it takes care of them: RPCS3 installs the firmware and the packages without its window, and you decide
whether a package installed is deleted. Nothing is deleted before you decide what to keep. It offers RPCS3's settings that matter on the handheld, finds your disc games there and
the games installed in RPCS3, puts them in Steam (with the game's own pictures, and a cover from SteamGridDB when you
give it your key), removes a game you no longer want, and keeps a log. RPCS3's own window is never needed: a game starts alone and full screen from
Steam, and View and Menu together open RPCS3's menu with Exit Game. Remove takes RPCS3's program away and leaves what
you made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it:
[RPCS3 Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/rpcs3/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\rpcs3\run.ps1             # full screen
windows-portable\apps\rpcs3\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-rpcs3.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\`, and RPCS3 with its firmware, saves and installed
games in `emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). RPCS3 is a separate program (GPL-2.0), downloaded from its own release.
