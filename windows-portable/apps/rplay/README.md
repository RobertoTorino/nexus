<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

# Remote Play

Finds, wakes and registers your PS4 and PS5 on the network, for Remote Play from the handheld: the BC250 Bazzite
Suite's Console Link, its search, registration, wake-up, test session and rest mode, made for the handheld.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [Remote Play in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/rplay/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\rplay\run.ps1             # full screen
windows-portable\apps\rplay\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-rplay.ini`, the log and the registered
consoles (`consoles.json`) in `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\`.

## License

AGPL-3.0, see [LICENSE](LICENSE). The protocol code is ported from [chiaki-ng](https://github.com/streetpea/chiaki-ng)
(AGPL-3.0-only with an OpenSSL exception), through the BC250 Bazzite Suite's Console Link; those files keep that
license. They are the files marked `SPDX-License-Identifier: AGPL-3.0-only`, modified from chiaki-ng's code (ported
to Python from 12-10-2026 on); the code and tests call chiaki-ng "the reference". The app's own files are
AGPL-3.0-or-later.
