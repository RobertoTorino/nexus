<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PCSX2 Manager](../assets/pcsx2/ps5-pcsx2-manager.webp){ .app-logo }

# PCSX2 Manager

PCSX2 Manager installs and configures PCSX2, manages PS2 BIOS files and game folders, and creates Steam entries for
Game Mode. It also provides PCSX2 settings, per-game display options, and memory-card management. Supply BIOS and
game files that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/pcsx2/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/pcsx2/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/pcsx2/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-pcsx2-manager`; the app runs on the suite's shared Python environment.

## Use it

Install PCSX2, add a BIOS file, and choose folders for your games. Refresh the library, then select a game to manage
its settings, memory cards, or Steam entry. PCSX2 game compatibility and performance vary by title and are not
guaranteed on PlayStation 5 hardware running Bazzite.

Under the **PCSX2 Install** and **PCSX2 Uninstall** pills, the PCSX2 line says **Not installed.** or **Installed.**,
with the button to use. Its tooltip says which release is installed, or what Install takes, and when a newer PCSX2
is out. When another release than the one pinned for this version of the app is installed, or PCSX2 updated itself
in its own window, the tooltip says so, and **Install** puts the pinned release back. Another release and a newer
PCSX2 also go to the log, once.
