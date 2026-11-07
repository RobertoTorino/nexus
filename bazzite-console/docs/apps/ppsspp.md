<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PPSSPP Manager](../assets/ppsspp/ps5-ppsspp-manager.webp){ .app-logo }

# PPSSPP Manager

PPSSPP Manager installs PPSSPP, finds PSP games in the folders you choose, and creates Steam entries for Game Mode.
It also exposes common PPSSPP graphics, audio, controller, and display settings, and can rename ISO/CSO files from
their game metadata. Use game files you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/ppsspp/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/ppsspp/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/ppsspp/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-ppsspp-manager`; the app runs on the suite's shared Python environment.

## Use it

Install PPSSPP, add folders containing PSP games, and refresh the library. Select a game to add or update its Steam
entry. Use **Settings** for common playback options and **Rename files** to name ISO or CSO images; PBP files are
not renamed. PSP game compatibility and performance vary by title and are not guaranteed on PlayStation 5 hardware
running Bazzite.
