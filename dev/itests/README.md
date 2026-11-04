<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-17b6a7)
[![CI Nexus](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus Installer Tests

A window that runs a suite's installer tests one at a time, with their live output and each one's result: a
Bazzite suite's `tools/installer-tests/*.sh` on Linux, a Windows suite's `*.ps1` on Windows. The Suite box in the
header picks the suite. A Nexus app: it runs from the checkout it lives in and has no releases of its own. Start it
from [Nexus Dashboard](../dash), or:

| | Linux | Windows (Git Bash) |
|---|---|---|
| Open it | `dev/itests/run.sh` | `dev/itests/run.sh` (PowerShell: `dev\itests\run.ps1`) |
| Menu entry and Desktop icon | `dev/itests/install.sh` (`--no-desktop-shortcut`, `--uninstall`, `--uninstall --purge`) | |

Nothing is copied: the entry starts the app of the checkout you installed it from.

How to use it: [Nexus Dashboard on the Nexus page](https://robertotorino.github.io/nexus/dashboard/#installer-tests).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
