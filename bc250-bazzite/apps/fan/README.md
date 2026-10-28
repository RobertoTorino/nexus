<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# BC-250 Fan Control

Shows the temperatures and fans of the **AMD BC-250** on **Bazzite**, and runs a thermal guard: a system service
that watches the GPU and the CPU, also when no app is open, and warns, turns the fans to full speed and performance
mode off, and at a critical temperature shuts the board down cleanly.

How to install and use it: [BC-250 Fan Control in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/fan/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). Where the fan headers are comes from
[mothenjoyer69/bc250-documentation](https://github.com/mothenjoyer69/bc250-documentation).
