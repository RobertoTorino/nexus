<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Decky Loader Manager](../assets/decky/ps5-decky-manager.webp){ .app-logo }

# Decky Loader Manager

!!! warning "Changes the board"
    Installs Decky Loader under the user's homebrew folder, adds and enables a root systemd service, and labels the loader binary for SELinux. The Decky install and service are system-wide, not isolated to this manager. It does not change firmware or boot settings. Uninstalling Decky Loader Manager leaves Decky Loader and its service in place; remove Decky with `ujust setup-decky uninstall`. Use only on a Bazzite image with Steam/Game Mode and systemd support.

Decky Loader Manager installs and manages Decky Loader and its plugins for Steam Game Mode. It displays the
system-wide service state and the installed plugins.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/decky/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/decky/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/decky/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-decky-manager`; the app runs on the suite's shared Python environment.

## The window

The header shows the app's state beside its name and a status box under it; **Refresh** reads again.
