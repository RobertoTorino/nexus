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
update package, then select a game to manage its Steam entry. **Remove game…** deletes the chosen game from the
disk, or the chosen package (a **PKG** row) when it cannot be unpacked: a window lists what would go, and nothing is
deleted before you press **Delete marked**. shadPS4 is an experimental PS4 emulator; compatibility
and performance vary by game and are not guaranteed on PlayStation 5 hardware running Bazzite.

Under the **shadPS4 Install** and **shadPS4 Uninstall** pills, the shadPS4 line says **Not installed.** or
**Installed.**, with the button to use. Its tooltip says which version is installed, or what Install takes, and when
a newer shadPS4 is out. When another version than the one pinned for this version of the app is installed, the
tooltip says so, and **Install** puts the pinned one in. Another version and a newer shadPS4 also go to the log,
once.
