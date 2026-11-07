<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PPSSPP Manager](../assets/ppsspp/ps5-ppsspp-manager.webp){ .app-logo }

# PPSSPP Manager

PPSSPP Manager installs PPSSPP, finds your PSP games and puts them in Steam, so a game starts from Steam, also in
Game Mode. It also sets PPSSPP's common graphics, audio, controller and display settings, and can rename ISO/CSO
files from their game metadata. Use game files you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/ppsspp/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/ppsspp/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/ppsspp/install.sh --uninstall             # remove it; --purge removes its settings and log too
```

The launcher is `~/.local/bin/ps5-ppsspp-manager`; the app runs on the suite's shared Python environment.

## Use it

The header shows the **PPSSPP version**, **Your games** (the games found) and those **Available in Steam**;
**Refresh** reads everything again. Beside the title stands the app's state. Under the introduction, which links to
**PPSSPP's release notes** and to this wiki, a row of pills does the setting up: **PPSSPP Install**, **PPSSPP
Uninstall** and **Games Rename**. Two lines below the pills say where each stands, and then come three tabs: **Your
games**, **Settings** and **Log**.

- **PPSSPP**: **Not installed.** or **Installed.**, with the button to use under it. The tooltip says which release
  is installed, or what Install takes, and when a newer PPSSPP is out. When another release than the one pinned for
  this version of the app is installed, the tooltip and the log say so, and **Install** puts the pinned one in.
  **Uninstall** takes PPSSPP out again; its own folder, with your saves and settings, stays.
- **Game folder**: the app looks for games in `~/Games/PSP`, and in `Games/PSP` on a USB drive or an SD card;
  nothing is chosen or browsed to.

### Your games

Tick the games you want in Steam and press **Update Steam**: the app adds them to Steam as non-Steam games and takes
out the ones you unticked. The games are in Steam's library under **Non-Steam**, on the desktop, in Big Picture Mode
and in Game Mode alike. The app has no Play button: a game is started from Steam. Change Steam from Desktop Mode: in
Game Mode Steam is the session itself and cannot close for the change. **Steam artwork…** takes a SteamGridDB API
key, with which the app takes the covers from SteamGridDB. **Steam** in the line under the table opens Steam's
library, and **PPSSPP settings** opens PPSSPP's own window, for what the Settings tab does not set.

**Games Rename** opens the Rename files window, which names ISO or CSO images after their game metadata; PBP files
are not renamed, and with no ISO or CSO image found the pill is off. A renamed game that is in Steam needs **Update
Steam** afterwards.

### Settings

PPSSPP's common graphics, audio, controller and display settings, each written into PPSSPP's own settings file the
moment you change it.

### Log

Everything the app said and did, with the time. The same lines are in
`~/.local/share/ps5-ppsspp-manager/ps5-ppsspp-manager.log`, which turns over at 1 MB (the three older files are
kept). `install.sh --uninstall` keeps it; `--purge` removes it.

PSP game compatibility and performance vary by title and are not guaranteed on PlayStation 5 hardware running
Bazzite.
