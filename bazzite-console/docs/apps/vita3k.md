<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Vita3K Manager](../assets/vita3k/ps5-vita3k-manager.webp){ .app-logo }

# Vita3K Manager

Vita3K Manager installs Vita3K and provides access to its firmware and game-install flows. It can create Steam
entries for installed titles. Supply firmware and game files that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/vita3k/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/vita3k/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/vita3k/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-vita3k-manager`; the app runs on the suite's shared Python environment.

## Use it

Install Vita3K, use its firmware and game installers, and select installed titles to add them to Steam. Vita3K
compatibility and performance vary by title and are not guaranteed on PlayStation 5 hardware running Bazzite.
