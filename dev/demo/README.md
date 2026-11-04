<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-17b6a7)
[![CI Nexus](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus Demo Recorder

Records a demo of a portal installation with OBS: a portal release extracted in Downloads, or the BC250 Bazzite
Suite in this checkout, installed in a terminal while OBS records the screen, then the portal opened and one
optional app installed and shown. On Windows it records the Windows Portable Suite's portal from an extracted
portal release, installed in a PowerShell window. A Nexus app: it runs from the checkout it lives in and has no
releases of its own. Start it from [Nexus Dashboard](../dash), or:

| | Linux | Windows |
|---|---|---|
| Open it | `dev/demo/run.sh` | `dev\demo\run.ps1` (PowerShell), or `dev/demo/run.sh` (Git Bash) |
| Menu entry and Desktop icon | `dev/demo/install.sh` (`--no-desktop-shortcut`, `--uninstall`, `--uninstall --purge`) | |

Nothing is copied: the entry starts the app of the checkout you installed it from.

How to use it: [Nexus Dashboard on the Nexus page](https://robertotorino.github.io/nexus/dashboard/#demo-recorder).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
