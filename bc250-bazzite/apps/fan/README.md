<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# BC-250 Fan Control

Shows the temperatures and fan speeds of the **AMD BC-250** on **Bazzite**. It can also turn on a thermal guard, a
background service that protects the board from overheating. The guard keeps watching when no app is open. When the
board gets too hot it warns you. If it gets hotter still, it runs the fans at full speed and switches performance
mode off. As a last resort it shuts the board down cleanly.

How to install and use it:
[BC-250 Fan Control in the wiki](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/fan/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The information on the fan headers comes from
[mothenjoyer69/bc250-documentation](https://github.com/mothenjoyer69/bc250-documentation).
