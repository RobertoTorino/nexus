<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Upscale Boost

HelixSR, the DLSS-like upscaler for AMD graphics, in your games: its build, deployed per game and set.

[HelixSR](https://github.com/lonewolf0622/HelixSR) runs NVIDIA's DLSS upscaling network on AMD graphics, and a game
talks to it as AMD FSR 3.1. Upscale Boost gets the newest HelixSR 2.x release from GitHub (checked against the SHA-256
GitHub publishes), downloads what HelixSR's own setup pins (NVIDIA's DLSS DLL, Python with numpy, Microsoft's shader
compiler, each checked), runs HelixSR's own builder on the handheld and keeps the result. It then puts HelixSR into a
game in place of the game's FSR 3.1 DLL, keeping the game's own file for Go back; it lists your Steam games and any
folder you add, sets HelixSR's `helixsr.ini`, and puts HelixSR and OptiScaler into a game without FSR 3.1. Everything
runs as your own user; nothing needs an administrator.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [Upscale Boost in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/upscale/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\upscale\run.ps1             # full screen
windows-portable\apps\upscale\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-upscale.ini`, the log in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\`, and HelixSR there too: the payload in `payload\`,
the downloaded releases in `work\`, the builder's Python and shader compiler in `HelixSR\`, the list of games HelixSR
was put in in `deployments.json`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). HelixSR is a separate project under its own license, downloaded from its
own release; what its builder makes from NVIDIA's DLSS DLL is NVIDIA's and stays on your device.
