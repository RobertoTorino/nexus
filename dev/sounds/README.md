<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-17b6a7)
[![CI Nexus](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus Sound Lab

A window that makes and tries short sound effects for the suites' windows, such as the tick a menu makes when the
controller moves the focus: a preset and a waveform to start from, a slider for each number of the sound, the
sound drawn beside them and played at every change, a row of buttons to try it while moving between them, and
Save as WAV for a suite's sounds folder. A Nexus app: it runs from the checkout it lives in and has no releases of
its own. Start it from [Nexus Dashboard](../dash), or:

| | Linux | Windows (Git Bash) |
|---|---|---|
| Open it | `dev/sounds/run.sh` | `dev/sounds/run.sh` (PowerShell: `dev\sounds\run.ps1`) |
| Menu entry and Desktop icon | `dev/sounds/install.sh` (`--no-desktop-shortcut`, `--uninstall`, `--uninstall --purge`) | |

Nothing is copied: the entry starts the app of the checkout you installed it from.

How to use it: [Nexus Dashboard on the Nexus page](https://robertotorino.github.io/nexus/dashboard/#sound-lab).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
