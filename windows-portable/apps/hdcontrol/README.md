<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# HD Controller

The **DualSense** and **DualSense Edge** controllers on a Windows handheld. The app shows the controller's connection,
battery and firmware, updates its firmware from the official update server over a USB cable, tests its buttons,
sticks, motors and light bar, and shows the DualSense Edge's four profiles, creates and edits them, with a backup of
them. Windows' own driver keeps driving the controller; the app talks to it through hidapi and needs no administrator.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [HD Controller in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/hdcontrol/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md) and the app's
requirements in it (`hidapi` among them):

```powershell
.venv-windows\Scripts\python.exe -m pip install -r windows-portable\apps\hdcontrol\requirements.txt
windows-portable\apps\hdcontrol\run.ps1             # full screen
windows-portable\apps\hdcontrol\run.ps1 --windowed  # in a window
windows-portable\apps\hdcontrol\run.ps1 --info      # each controller's battery, firmware and profiles, as text
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-hdcontrol.ini`; the log, the firmware files and
the profiles' backups in `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The update protocol is ported from
[dualsense-updater-rs](https://github.com/nchie/dualsense-updater-rs), MIT, Copyright 2026 nchie, and the layout and
writing of the Edge's profiles from [dualsense-edge-profile-web-application](https://github.com/steffalon/dualsense-edge-profile-web-application),
MIT, Copyright (c) 2023 steffalon; the files ported from them (`updater.py`, `profiles.py`) say so in their header and
keep the MIT notice below. The controllers' firmware is Sony's: it is not part of this app.

```
MIT License

Copyright 2026 nchie (dualsense-updater-rs)
Copyright (c) 2023 steffalon (dualsense-edge-profile-web-application)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
