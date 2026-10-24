<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# BC-250 ACE Queues

Lets games on the **AMD BC-250** use its dedicated compute queues (async compute) on **Bazzite**, through a
patched RADV that is built on the board and installed beside the system Mesa. Games use it only after its test
passed on the running kernel.

How to install and use it: [BC-250 ACE Queues in the manual](https://robertotorino.github.io/nexus/apps/ace/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The Mesa patch in `mesa/` is MIT, as the Mesa file it changes.
