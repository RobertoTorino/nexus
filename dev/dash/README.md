<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-17b6a7)
[![CI Nexus](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus Dashboard

One door to the tools for working on the suites. Its tiles start the Nexus apps of the checkout, each in a window
of its own ([Nexus Release Tool](../nrt), [Nexus Installer Tests](../itests), [Nexus Demo Recorder](../demo),
[Nexus Sound Lab](../sounds)), and open the tools of the suite chosen in the header: the portal's and the apps' video tours, and the category icons.
A Nexus app: it runs from the checkout it lives in and has no releases of its own.

## Start it

From the repository's root, with the checkout's venv for the system (see the root CLAUDE.md):

| | Linux | Windows (PowerShell) |
|---|---|---|
| Open it | `dev/dash/run.sh` | `dev\dash\run.ps1` |
| Menu entry and Desktop icon | `dev/dash/install.sh` | `powershell -ExecutionPolicy Bypass -File dev\dash\install.ps1` |

Both installers take `--no-desktop-shortcut`, `--uninstall` and `--uninstall --purge` (the settings too). Nothing is
copied: the entry starts the app of the checkout you installed it from.

How to use it: [Nexus Dashboard on the Nexus page](https://robertotorino.github.io/nexus/dashboard/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
