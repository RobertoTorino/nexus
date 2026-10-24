<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# BC-250 USB Wi-Fi

The driver for **AIC8800D80 USB Wi-Fi sticks** (the UGREEN AX900 and others) on the **AMD BC-250** with
**Bazzite**, whose kernel has none: built on the board for the running kernel from pinned sources, installed as a
system service that loads it at every boot, switches the stick out of its storage mode, and builds it again after a
kernel update.

How to install and use it: [BC-250 USB Wi-Fi in the manual](https://robertotorino.github.io/nexus/apps/wdriver/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The driver it builds is
[shenmintao/aic8800d80](https://github.com/shenmintao/aic8800d80) (GPL-2.0-only), fetched at a pinned commit from
the suite's mirror [RobertoTorino/aic8800d80](https://github.com/RobertoTorino/aic8800d80) or from the original;
its firmware files are AICSemi's, shipped in that repository.
