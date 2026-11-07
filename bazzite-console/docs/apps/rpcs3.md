<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![RPCS3 Manager](../assets/rpcs3/ps5-rpcs3-manager.webp){ .app-logo }

# RPCS3 Manager

RPCS3 Manager installs and configures RPCS3 for PS3 games. It can install the emulator, open its firmware installer,
scan game folders, and create Steam entries that launch a selected game. The manager also keeps an activity log.
Use firmware and game files that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/rpcs3/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/rpcs3/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/rpcs3/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-rpcs3-manager`; the app runs on the suite's shared Python environment.

## Use it

Install RPCS3, then use its firmware setup before adding games. Add folders that contain your PS3 games and refresh
the library; select a game to manage its Steam entry. RPCS3 is a desktop emulator, so game compatibility and
performance vary by title and are not guaranteed on PlayStation 5 hardware running Bazzite.
