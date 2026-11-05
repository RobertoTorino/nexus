<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# DatStation

PlayStation knowledge on your handheld: a quiz against the clock, the consoles' history, system software versions, region codes, user guides and PS news.

The PlayStation knowledge part of the [DatStation](https://github.com/RobertoTorino/DatStation) Android app, as
the BC250 Bazzite Suite's Bazzite DatStation has it: a front page of tiles that opens a PlayStation quiz against the
clock, the history of every PlayStation console, every system software release, the region codes explained, Sony's
user guides and the latest PlayStation news, and keeps your quiz scores and trophies.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [DatStation in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/datstat/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\datstat\run.ps1             # full screen
windows-portable\apps\datstat\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-datstat.ini`, the quiz scores and the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-datstat\`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
