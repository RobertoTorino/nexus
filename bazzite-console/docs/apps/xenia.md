<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Xenia Manager](../assets/xenia/ps5-xenia-manager.webp){ .app-logo }

# Xenia Manager

Xenia Manager installs Xenia Canary, finds your Xbox 360 games and puts them in Steam, so a game starts from Steam,
also in Game Mode. Use game files that you are entitled to use.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/xenia/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/xenia/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/xenia/install.sh --uninstall             # remove it; --purge removes its settings and log too
```

The launcher is `~/.local/bin/ps5-xenia-manager`; the app runs on the suite's shared Python environment.

## Use it

The header shows the **Xenia version**, **Your games** (the games found) and those **Available in Steam**;
**Refresh** reads everything again. Beside the title stands the app's state. Under the introduction, which links to
**Xenia's release notes** and to this wiki, a row of pills does the setting up: **Xenia Install** and **Xenia
Uninstall**. Two lines below the pills say where each stands, and then come three tabs: **Your games**, **Settings**
and **Log**.

- **Xenia**: **Not installed.** or **Installed.**, with the button to use under it. The tooltip says which build is
  installed, or what Install takes, and when a newer build is out. When another build than the one pinned for this
  version of the app is installed, the tooltip and the log say so, and **Install** puts the pinned one in.
  **Uninstall** takes Xenia out again; its own folder, with its settings, saves and installed content, stays.
- **Game folder**: the app looks for games in `~/Games/XBOX360`, and in `Games/XBOX360` on a USB drive or an SD
  card; nothing is chosen or browsed to.

### Your games

Tick the games you want in Steam and press **Update Steam**: the app adds them to Steam as non-Steam games and takes
out the ones you unticked. The games are in Steam's library under **Non-Steam**, on the desktop, in Big Picture Mode
and in Game Mode alike. The app has no Play button: a game is started from Steam. Change Steam from Desktop Mode: in
Game Mode Steam is the session itself and cannot close for the change. **Steam artwork…** takes a SteamGridDB API
key, with which the app takes the pictures from SteamGridDB. **Steam** in the line under the table opens Steam's
library, and **Xenia settings** opens Xenia's own window, for what the Settings tab does not set.

### Settings

Xenia's settings that matter for playing, each written into Xenia's own settings file the moment you change it;
Xenia reads it when it starts.

### Log

Everything the app said and did, with the time. The same lines are in
`~/.local/share/ps5-xenia-manager/ps5-xenia-manager.log`, which turns over at 1 MB (the three older files are kept).
`install.sh --uninstall` keeps it; `--purge` removes it.

Xenia is an experimental emulator; compatibility and performance vary by title and are not guaranteed on
PlayStation 5 hardware running Bazzite. Its Linux build can have different compatibility from the Windows build.
