<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-17b6a7)
[![CI Nexus](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-nexus.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus Deps

A window that lists the Python packages and external tools of a suite's apps installed on this machine, which apps
use them, what is missing or must be updated (with the known vulnerabilities from OSV.dev), and Bazzite's update
state; **Fix** installs what is missing or outdated, after it shows every command and asks. A weekly notification
says when something needs you. A Nexus app: it runs from the checkout it lives in and has no releases of its own.
Start it from [Nexus Dashboard](../dash), or:

| | Linux |
|---|---|
| Open it | `dev/deps/run.sh` (`--fix` offers Fix at once, `--remind` is the weekly check) |
| Menu entry, Desktop icon and weekly reminder | `dev/deps/install.sh` (`--no-desktop-shortcut`, `--uninstall`, `--uninstall --purge`) |

Nothing is copied: the entry starts the app of the checkout you installed it from. It checks the BC250 Bazzite
Suite, whose catalog is `nexus_deps/catalogs/bc250-bazzite.toml`.

How to use it: [Nexus Dashboard on the Nexus page](https://robertotorino.github.io/nexus/dashboard/#deps).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
