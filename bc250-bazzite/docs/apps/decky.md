<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Decky Loader Manager](../assets/decky/bc250-decky-manager.webp){ .app-logo }

# Decky Loader Manager

Brings **plugins to Game Mode** on the **AMD BC-250** with [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader),
the plugin loader made for the Steam Deck. The app installs the Decky release it was tried with, runs it as a system
service, and shows whether it runs and which plugins it has.

Decky's own menu is in Steam's Quick Access menu, in Game Mode and in Big Picture Mode; Steam's desktop window has
no Quick Access menu, so Decky does not show there. Open the Quick Access menu, the panel on the right, with the
**…** button, or **Ctrl + 2** on a keyboard; a controller without a **…** button has its own combination, which
Steam lists under **Show Controller Shortcuts** in its Power menu (hold the controller's Steam, PS or Xbox button).
Decky is the plug icon at the bottom of the menu's row of icons. There you open Decky's store, install plugins,
switch them off and set them up. What a plugin does, and whether it works on the
BC-250, is up to the plugin. A plugin that sets power limits or clocks changes how the board runs: that is your
choice in Decky, not this app's.

## What you need

- **Steam**, started at least once.
- **Your password**, for installing, removing and restarting Decky: it runs as root from a system service, as on
  the Steam Deck.
- About 33 MB for Decky itself, and room for the plugins you install.

## Using it

The window has four rows, then the list of plugins.

1. **Decky Loader**: **Install** downloads Decky from its GitHub release (about 33 MB), checks it against the
   checksum this version of the app was tried with, installs it in `~/homebrew/services` and starts its service.
   It asks for your password for that. When an older Decky is there, the button says **Update**. **Remove** stops
   Decky and removes it; your plugins and their settings stay, unless you tick the box to remove them too.
2. **Service**: whether Decky runs and starts at boot. **Restart** restarts it, as Decky's own Reload does. **Log**
   shows Decky's lines from the system journal, the place to look when it does not run.
3. **Steam**: Decky loads into Steam's interface through Steam's remote debugging, which Steam only turns on when a
   file in its folder says so. **Install** creates that file and **Remove** deletes it. **Switch on** and **Switch off**
   do the same by hand. A change takes effect the next time Steam starts.
4. **/home/deck**: some plugins written for the Steam Deck look for their files in `/home/deck` only. **Link** makes
   `/home/deck` point to your home folder, as Bazzite's `ujust setup-decky` does; **Unlink** removes the link. The app
   never touches a `/home/deck` that is a real folder (another user's home) or a link to somewhere else.

The table lists the plugins in `~/homebrew/plugins`: name, version, author, and whether Decky has them switched
off. **Open plugins folder** opens that folder.

Steps that need your password are grayed out in Game Mode, which has no password dialog. Use Desktop Mode for them.

After installing, start Steam again, or switch to Game Mode, and Decky appears in the Quick Access menu (**Ctrl + 2**).

## Updates

Each version of the app installs one Decky release, the one it was tried with. When a newer Decky release is out,
the first row says so. A newer version of the app from the [portal](../portal.md) brings it: after updating the
app, **Update** installs it.

Decky can also update itself from its own settings in Game Mode. The app then shows the version Decky updated to,
and leaves it as it is.

## Decky installed some other way

The app uses Decky's own folders and service name, so it finds a Decky installed with Bazzite's
`ujust setup-decky` or with Decky's own installer, and can update, restart and remove it. The same goes the other
way: `ujust setup-decky` sees a Decky that this app installed.

One difference: the app makes `~/homebrew/services` a folder that only root can change. Decky's service runs as root
from that folder, so a program running as you cannot swap the program that root starts. Decky's own updater runs as
root and can still write there.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-decky-manager/app` |
| Decky Loader | `~/homebrew/services/PluginLoader`, its version in `~/homebrew/services/.loader.version` |
| Decky's service | `/etc/systemd/system/plugin_loader.service` |
| Plugins, their settings and logs | `~/homebrew/plugins`, `~/homebrew/settings`, `~/homebrew/logs`, `~/homebrew/data` |
| Steam's switch for Decky | `.cef-enable-remote-debugging` in Steam's folder |
| The app's settings | `~/.config/bc250-decky-manager` |
| Launcher | `~/.local/bin/bc250-decky-manager` |

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing the app leaves Decky in place,
because Decky runs as root and the installer never asks for your password. To remove Decky as well, press
**Remove** in the app first. If the app is already gone, use `ujust setup-decky uninstall`.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app; keeps its settings and Decky Loader itself
./install.sh --uninstall --purge     # also remove its settings
```

## License

GPL-3.0-or-later. Decky Loader is a separate program under its own license (GPL-2.0), downloaded from its own
release.
