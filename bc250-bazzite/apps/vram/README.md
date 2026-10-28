<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# BC-250 Memory Manager

Sets the VRAM split of the **AMD BC-250** on **Bazzite** in the board's CMOS, and shows the GTT, the TTM limit, the
system RAM and the swap layout that go with it. The split changes only when you apply one, and takes effect after a
reboot.

How to install and use it: [BC-250 Memory Manager in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/vram/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The CMOS layout comes from
[fanoush/bc250_memcfg](https://github.com/fanoush/bc250_memcfg) (MIT).
