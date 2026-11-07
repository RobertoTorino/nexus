<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![shadPS4 Manager](../assets/shadps4/ps5-shadps4-manager.webp){ .app-logo }

# shadPS4 Manager

shadPS4 Manager installs shadPS4, organizes PS4 game folders, and creates Steam entries for launching games. It
also includes tools for extracting PKG files and managing the emulator's online-service sign-in. Use game files
and keys that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/shadps4/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/shadps4/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/shadps4/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-shadps4-manager`; the app runs on the suite's shared Python environment.

## Use it

Install shadPS4, add folders containing your game files, and refresh the library. Use **Extract PKG** for a game or
update package, then select a game to manage its Steam entry. shadPS4 is an experimental PS4 emulator; compatibility
and performance vary by game and are not guaranteed on PlayStation 5 hardware running Bazzite.
