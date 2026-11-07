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
bazzite-console/apps/vita3k/install.sh --uninstall             # remove it; --purge removes its settings and log too
```

The launcher is `~/.local/bin/ps5-vita3k-manager`; the app runs on the suite's shared Python environment.

## Use it

The header shows the **Vita3K version** (its build number), the **Firmware**, **Your games** (the games installed)
and those **Available in Steam**; **Refresh** reads everything again. Beside the title stands the app's state. Under
the introduction, which links to **Vita3K's release notes** and to this wiki, a row of pills does the setting up:
**Vita3K Install**, **Vita3K Uninstall** and **Games Install**. Three lines below the pills say where each stands,
and then come three tabs: **Your games**, **Settings** and **Log**.

- **Vita3K**: **Not installed.** or **Installed.**, with the button to use under it. The tooltip says which build
  is installed, or what Install takes, and when a newer build is out. When another build than the one pinned for
  this version of the app is installed, the tooltip and the log say so, and **Install** puts the pinned one in.
  **Uninstall** takes Vita3K out again; its own folders, with the firmware, your games, saves and settings, stay.
- **Firmware**: which parts of the PS Vita's firmware Vita3K has. Put the `PSP2UPDAT.PUP` files you downloaded in
  `~/Games/Vita/Firmware`: once Vita3K is installed, the app gives them to Vita3K by itself.
- **Games**: how many games Vita3K has installed. **Games Install** installs one of yours, **From a file** (a
  `.vpk` or `.zip`, or a `.pkg` with its zRIF license key) or **From a dumped folder**.

### Your games

Tick the installed titles you want in Steam and press **Update Steam**: the app adds them to Steam as non-Steam
games and takes out the ones you unticked. The games are in Steam's library under **Non-Steam**, on the desktop, in
Big Picture Mode and in Game Mode alike. The app has no Play button: a game is started from Steam. Change Steam from
Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change. **Steam artwork…** takes a
SteamGridDB API key, with which the app takes the covers from SteamGridDB. **Steam** in the line under the table
opens Steam's library, and **Vita3K settings** opens Vita3K's own window, for what the Settings tab does not set.

### Settings

Vita3K's settings that matter for playing, each written into Vita3K's own settings file the moment you change it.

### Log

Everything the app said and did, with the time. The same lines are in
`~/.local/share/ps5-vita3k-manager/ps5-vita3k-manager.log`, which turns over at 1 MB (the three older files are
kept). `install.sh --uninstall` keeps it; `--purge` removes it.

Vita3K compatibility and performance vary by title and are not guaranteed on PlayStation 5 hardware running Bazzite.
