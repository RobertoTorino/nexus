<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Vita3K Manager

Plays your PS Vita games on a Windows handheld with Vita3K, the PS Vita emulator: Vita3K build 4186 for Windows from
Vita3K's own builds, checked against the checksum this version of the app was tested with, for your own user; Vita3K
keeps its settings, the firmware, your games and your saves in its portable folder beside its program, in the app's
folder. Vita3K installs the PS Vita's firmware and your own games (a .vpk, a .zip, a dumped game folder, or a .pkg with
its license key), without its window. The app offers Vita3K's settings, puts the games installed in Vita3K in Steam
(with the game's own pictures, and a cover from SteamGridDB when you give it your key), and keeps a log. Vita3K's own
window is never needed: a game starts full screen from Steam. Remove takes Vita3K's program away and leaves what you
made.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it:
[Vita3K Manager in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/vita3k/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\vita3k\run.ps1             # full screen
windows-portable\apps\vita3k\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-vita3k.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\`, and Vita3K with its settings, firmware, games and
saves in `emulator\` there.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Vita3K is a separate program (GPL-2.0), downloaded from its own builds.
