<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Xenia Manager](../assets/xenia/ps5-xenia-manager.webp){ .app-logo }

# Xenia Manager

Xenia Manager installs Xenia Canary, finds Xbox 360 games in the folders you choose, and creates Steam entries for
Game Mode. Use game files that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/xenia/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/xenia/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/xenia/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-xenia-manager`; the app runs on the suite's shared Python environment.

## Use it

Install Xenia Canary, add folders containing your games, and refresh the library. Select a game to create or update
its Steam entry. Xenia is an experimental emulator; compatibility and performance vary by title and are not
guaranteed on PlayStation 5 hardware running Bazzite. Its Linux build can have different compatibility from the
Windows build.
