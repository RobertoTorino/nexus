<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![RPCS3 Manager](../assets/rpcs3/bc250-rpcs3-manager.webp){ .app-logo }

# RPCS3 Manager

Plays **PS3 games** on the **AMD BC-250** with [RPCS3](https://rpcs3.net), an open-source PS3 emulator. The app
installs the RPCS3 build it was tried with, takes the PS3's firmware, finds your games and adds them to Steam, so a
game starts straight away, on the desktop or from Steam's **Big Picture Mode** (Game Mode on a handheld). The app
has no Play button: a game is started from Steam. The app sets RPCS3 up for that: its welcome dialog and its own
update check off, player 1 on your controller, each game's screen. RPCS3's own window is opened for what RPCS3 does
only there: the firmware and the packages, which RPCS3 installs itself, and [RPCS3's settings](#rpcs3s-settings).

Whether a game runs, and how well, is up to RPCS3. Its [compatibility list](https://rpcs3.net/compatibility) shows
what others found.

## What you need

- **Your games**, from your own discs or installed from your own packages. The app never downloads games.
- **The PS3's firmware** (`PS3UPDAT.PUP`), the PS3's system software. RPCS3 needs it to start any game.
  The app cannot ship it: download the firmware from
  [PlayStation's firmware page](https://www.playstation.com/en-us/support/hardware/ps3/system-software/), then
  pick it with **Firmware Install**.
- **Steam**, started at least once: a game is started from Steam.
- About 80 MB for RPCS3 itself. Its firmware, saves, settings and installed games go in `~/.config/rpcs3`, its
  shader cache in `~/.cache/rpcs3`.
- **fusermount** (FUSE), which Bazzite has. RPCS3 comes as an AppImage, which mounts itself with it. Without it, it
  unpacks itself to a temporary folder on every start, which takes longer.

## Using it

The header shows the **RPCS3 version**, **Your games** (the games found), those **Available in Steam** and the
**Play time**: the time spent in all your games together, as RPCS3 counts it, with each game's time in the
tooltip. **Refresh** reads everything again. Beside the title, next to the app's state, stands the controller's:
**Controller connected**, or **No controller** when none is, looked at again every few seconds. A game started
from Steam reads the controller that is connected when it starts, so switch yours on, or press its PS button to
wake it, before starting a game. When Steam starts a game without one, the app also says so in a desktop
notification. A controller that switches off during a game (its idle timer, its battery) is not picked up again
by this RPCS3 build when it comes back: quit the game and start it again (see [Controllers](#controllers)). Under the introduction, which links to **RPCS3's release notes** and to this wiki, a row of five
pills does the setting up, each with what it is for on top and what it does under it: **RPCS3 Install** and
**RPCS3 Uninstall**, **Firmware Install**, **Games Install** and **Games Add folder**. Four lines below them say
where each stands, short, with more in their tooltips, and then come three tabs: **Your games**, **Settings**
and **Log**.

- **RPCS3**: the version installed (the build is in the tooltip; when this version of the app brings another
  build, the tooltip and the log say so, and **Install** puts it in). **Install** downloads RPCS3 from GitHub
  (about 80 MB): the build this version of the app was tried with, checked against its checksum before it is
  installed.
  **Uninstall** takes it out again; RPCS3's own folder, with the firmware, your saves, settings and installed
  games, stays.
- **Firmware**: which version of the PS3's firmware RPCS3 has (the folder's path is in the tooltip). **Install**
  asks for the `PS3UPDAT.PUP` you downloaded and gives it to RPCS3, which installs it in its own window. Close
  that window when it is done; the line shows the new version.
- **Disc games**: the folders the app looks for disc games in, by name (the paths and how many disc games were
  found are in the tooltip). **Add folder** adds one; clicking a folder's name in the line stops looking in it,
  after a question (the games stay where they are). Games in subfolders are found too, up to five folders deep,
  so one folder with a folder per game is enough.
- **PKG games**: RPCS3's games folder, `dev_hdd0/game/` within RPCS3's own folder, while a game is installed in
  it, or **—** while none is (the whole path and the count are in the tooltip). **Install** asks for the folder
  with your `.pkg` files and has RPCS3 install them without opening its window: the `.rap` (or `.edat`) license of
  a PSN game that is beside them first, copied into RPCS3's own folder, then each package, a game's update last
  (an update needs its game installed first). RPCS3 is started once per file, and a large package takes minutes;
  the line under the tabs says what came, and the line and the table follow. The files in the folder itself are
  taken, not those in its subfolders. A game's update is a package too: RPCS3 uses it when it starts the game,
  and the table lists the game once.

### Your games

The table lists every game found: its title and **Id** (BLUS…, NPUB…) from the game's own files, its version and
its **Folder** (the folder's name; the path is in the tooltip), and its **Screen setting**. It has three kinds of
games:

- **Disc games** in the game folders, each in a folder of its own, as copied from the disc: `PS3_DISC.SFB` and the
  `PS3_GAME` folder. RPCS3 does not start a disc game without its `PS3_DISC.SFB`; the table shows its folder in red.
- **Disc games RPCS3 knows**: those it started before, wherever they are.
- **Installed games**: games installed from a package, in RPCS3's `dev_hdd0/game`.

```
PS3/
└── Demon's Souls/
    ├── PS3_DISC.SFB
    └── PS3_GAME/          PARAM.SFO, ICON0.PNG, USRDIR/EBOOT.BIN, ...
```

#### Screen setting

How the game fills the screen, chosen per game and kept in the game's own settings in RPCS3 (the file RPCS3's own
window writes for a game's custom configuration; the app changes its two lines and leaves the rest):

- **16:9**: the PS3's picture for a wide screen, as RPCS3 draws it by default.
- **4:3**: the picture for a 4:3 screen, with borders on a wide one; for a game made for it.
- **Fill screen**: the picture stretched to fill the window, whatever its shape.

The choice is written the moment you change it, while RPCS3 does not run (RPCS3 writes its own settings when it
closes, over any change made meanwhile). A game is started full screen from Steam; `bc250-rpcs3-run` without
`--fullscreen` starts it in a window (see [From a terminal](#from-a-terminal)).

#### Steam

Tick the games you want in Steam and press **Update Steam**. The app adds them to Steam as non-Steam games, with
the game's own icon and background as their pictures and its icon (`ICON0.PNG`) as the logo on the banner, and
takes out the games you unticked and games it no longer finds. Steam keeps these files in memory, so it closes for
the change and starts again in the background.

In Steam each game's name starts with its system, for example **[PS3] Lumines**, so it stands apart from the same
title on Steam or on another system in Steam's menus. A game whose name in Steam differs from its title in the app
is renamed the next time you press **Update Steam**, which is on for it until then. Steam sees the renamed game as
a new one: its play time stays, but a controller layout or collection you set for it in Steam has to be set again.

The games are in the library under **Non-Steam**, on the desktop and in Big Picture Mode alike. They start the
game alone in RPCS3, full screen. Steam's menu and **Exit game** work as for any game; on the controller,
**Share + Options** together open RPCS3's own menu with **Exit Game** (see [Controllers](#controllers)).

Steam's overlay works over a game started from Steam, in Big Picture Mode and on the desktop: press **Shift+Tab**
or the **PS button** for the game's page, its controller layout and its settings, without leaving the game. In
Big Picture Mode the PS button opens Steam's menu over the game; pressed again there, it opens the power menu,
with **Exit game** and the way out of Big Picture Mode.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

On a handheld image of Bazzite, whose Game Mode is a Steam session of its own, change Steam from Desktop Mode: in
that session Steam cannot close for the change.

##### Covers

A PS3 game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on
a dark background. With a SteamGridDB API key, entered under **Steam artwork…**, the app takes a cover from
SteamGridDB for each game instead; the background and the logo on the game's page stay the game's own. See
[Covers from SteamGridDB](covers.md) for the key, how a game is looked up and how to use a cover of your own.

**Steam** in the line under the table is a link: it opens Steam's library (Steam starts when it does not run).

### Settings

RPCS3's settings that matter for playing, each written into RPCS3's own settings file (`config.yml`) the moment
you change it, while RPCS3 does not run; RPCS3 reads them when a game starts, and a game's own settings in RPCS3
(the Screen setting, or settings made for the game in RPCS3's window) come before them. The tooltips say what
each does.

- **Picture**: the renderer (Vulkan on the BC-250), the resolution scale (150 % fills a 1080p screen, 300 % a 4K
  one; higher asks more of the GPU), anisotropic filtering, anti-aliasing, VSync, the frame limit, output scaling
  (bilinear, nearest or AMD's FidelityFX Super Resolution) and **Fill the screen**, the stretch for every game
  without a Screen setting of its own.
- **Emulation**: the PPU and SPU decoders (the recompilers are the fast ones, the interpreters exact and slow).
- **Sound**: the sound output library, the volume (up to 200 %) and buffering. Beside the volume stands **Bazzite's
  volume for RPCS3**, which is not RPCS3's: Bazzite's sound settings remember a volume and a mute per application,
  also once it is closed, so a game plays without a sound while RPCS3 is muted there. The app says so, in red, when
  RPCS3 is muted or turned down to nothing. **Unmute** beside it turns a muted RPCS3 on again, and Bazzite keeps it
  on from then on; a volume turned down is changed in the sound applet (the speaker in the panel, under
  Applications) while a game plays.
- **Messages in a game**: the trophy message and the shader compilation message.

A value RPCS3 knows and the app does not is shown as it is. Everything else RPCS3 can set stays in RPCS3's own
window (**RPCS3 settings**).

#### RPCS3's settings

**RPCS3 settings** opens RPCS3's own window for what the app does not set: its other settings, its controllers
beyond player 1 and 2 (**Pads**) and its online service (RPCN). What the app sets by itself, before RPCS3's
window first opens: RPCS3's welcome dialog off (it would wait for a tick in "I have read the Quickstart guide"
first), RPCS3's own update check off (see [New RPCS3 builds](#new-rpcs3-builds)), RPCS3's dark style when the
suite's theme is dark (the welcome dialog would have offered it) and player 1 on your controller (see
[Controllers](#controllers)). What the app set up goes to the log.

When RPCS3's Settings open with a `config.yml` another build of RPCS3 wrote, RPCS3 asks **Remove obsolete
settings?**: the two builds know different settings. That happened on the board after RPCS3 updated itself in
its own window; with its update check off it no longer does. Answer **Yes** to let RPCS3 tidy its file for the
build that runs; the app's settings are not in it.

### Log

Everything the app said and did, with the time: RPCS3 installed or removed, what the app set up in RPCS3, the
firmware, the packages (what RPCS3's own log, `~/.cache/rpcs3/RPCS3.log`, says each package came to) and the
folders chosen, every change to Steam, and every error. Each game started from Steam is logged by its folder's name when it
starts, with whether a controller was connected. The same lines are in
`~/.local/share/bc250-rpcs3-manager/bc250-rpcs3-manager.log`, which turns over at 1 MB (the three older files are
kept). The log holds what the app did, not your SteamGridDB key or anything personal.

## From a terminal

`bc250-rpcs3-run` starts the installed RPCS3 with the options you give it. The Steam shortcuts use it, so they
keep working when a newer version of the app brings a newer RPCS3.

```bash
bc250-rpcs3-run --no-gui --fullscreen "/path/to/PS3_GAME/USRDIR/EBOOT.BIN"   # a game alone, full screen
bc250-rpcs3-run --no-gui "/path/to/PS3_GAME/USRDIR/EBOOT.BIN"                # a game alone, in a window
bc250-rpcs3-run --installfw "/path/to/PS3UPDAT.PUP"                          # install the firmware
bc250-rpcs3-run --installpkg "/path/to/folder"                               # install the .pkg (and .rap) files in a folder
bc250-rpcs3-run --headless --installpkg "/path/to/file.pkg"                  # the same without RPCS3's window (the app's way)
bc250-rpcs3-run                                                              # RPCS3's own window
```

## New RPCS3 builds

RPCS3 has no stable releases: it publishes a new build for almost every change, and now and then marks one with a
version number (0.0.43). Each version of the app installs one build, the one it was tried with. When the window
opens, the app asks GitHub for RPCS3's newest version number. When that one is newer, the RPCS3 line says so, with
a link to what is new; the app does not install it. A newer RPCS3 comes with a newer version of the app, once it has
been tried, from the [portal](../portal.md): after updating the app, the RPCS3 line says so, and **Install** brings
it.

RPCS3's own window looks for a newer build when it opens and offers to update itself; the app turns that check
off, so the build stays the one the app was tried with (RPCS3's **Help** menu can still update it by hand). If
you update it there, the RPCS3 line says that RPCS3 updated itself, and **Install** puts the tried build back;
RPCS3's Settings then ask once to remove the settings the other build left (see
[RPCS3's settings](#rpcs3s-settings)). A game started from Steam never asks.

## How it works

The Steam shortcuts start `bc250-rpcs3-run`, which starts RPCS3. Two things change because Steam is the one that
starts it.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). With RPCS3's SDL controller
setting, RPCS3 then sees only that virtual controller: it has no motion sensors, and on the desktop it follows the
layout Steam has active, which may be Steam's desktop layout (mouse and keys).

So the run wrapper undoes it: while a real controller is connected, RPCS3 reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.

RPCS3 only reads a controller that its pad settings name; until they name one, it plays with the keyboard. So the
app writes them: player 1 on the controller connected (a second one is player 2), through RPCS3's SDL controller
setting with RPCS3's own button layout for it, so Cross is the bottom face button and **Share + Options**
together (or the Guide button) open RPCS3's own menu in the game, with **Exit Game** in it: RPCS3 has no button
chord that quits a game outright, that menu is its way out on the controller, beside Steam's. RPCS3 knows a
controller by the name SDL gives it, which is not the kernel's: the app asks SDL (Bazzite's SDL3 library, the same RPCS3 uses) for
the names whenever the controllers connected change, and the log says which player went on which name. Once you
save RPCS3's own **Pads** settings in its window, that file is RPCS3's and the app leaves it alone. On a system
without SDL3 the app writes the kernel's name, which RPCS3 may not match; the log says so.

A controller that leaves during a game and comes back (switched off by its idle timer or an empty battery, then
woken with its PS button) stays unknown to this RPCS3 build until the game is started again: RPCS3 knows a
controller it had by its name, its device path and its serial together, and a Bluetooth controller that
reconnects gets a new device path from the kernel. RPCS3 has changed this since (a reconnected controller is
matched by name and serial); a later version of the app brings a build with it, once it has been tried on the
board. Until then, quit the game (Steam's menu, or **Share + Options** and **Exit Game**) and start it again from
Steam with the controller on.

### Steam's overlay on the desktop

The KDE desktop of Bazzite is a Wayland session. RPCS3 opens its windows through Wayland when it can, but Steam on
the desktop only sees windows that go through X11 (XWayland, the X11 server within the Wayland session). A game
window Steam cannot see has no overlay: **Shift+Tab** and the **PS button** do nothing.

So when Steam starts a game on the Wayland desktop, the run wrapper has RPCS3 open its windows through XWayland
(`QT_QPA_PLATFORM=xcb`), and Steam's overlay works as in any other game. A handheld's Game Mode runs every game
through X11 already.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-rpcs3-manager/app` |
| RPCS3 | `~/.local/share/bc250-rpcs3-manager/emulator` |
| RPCS3's firmware, saves, settings, installed games | `~/.config/rpcs3` (RPCS3's own folder) |
| RPCS3's play time per game | `~/.config/rpcs3/GuiConfigs/persistent_settings.dat`, RPCS3's own |
| RPCS3's settings (the Settings tab) | `~/.config/rpcs3/config.yml`, RPCS3's own |
| RPCS3's GUI settings (the welcome dialog, the update check, the style) | `~/.config/rpcs3/GuiConfigs/CurrentSettings.ini`, RPCS3's own |
| Player 1 and 2 on your controllers | `~/.config/rpcs3/input_configs/global/Default.yml`, RPCS3's own |
| Each game's screen setting | `~/.config/rpcs3/custom_configs/config_<Id>.yml`, RPCS3's own |
| RPCS3's shader cache and its own log (`RPCS3.log`, read for what an install did) | `~/.cache/rpcs3` |
| The volume Bazzite remembers for RPCS3 (read only) | `~/.local/state/wireplumber/stream-properties`, WirePlumber's |
| The app's settings, with the game folders | `~/.config/bc250-rpcs3-manager` |
| The app's log | `~/.local/share/bc250-rpcs3-manager/bc250-rpcs3-manager.log` |
| The Steam shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The covers found on SteamGridDB | `~/.local/share/bc250-rpcs3-manager/covers` |
| Launchers | `~/.local/bin/bc250-rpcs3-manager`, `~/.local/bin/bc250-rpcs3-run` |

RPCS3 can keep its drives elsewhere (its **Configuration > Virtual File System**); the app reads where they are.

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app
and the RPCS3 it installed; RPCS3's own folder (the firmware, your saves) and your games stay. The games in Steam
then no longer start: take them out first by unticking them and pressing **Update Steam**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the RPCS3 it installed; keeps its settings and log
./install.sh --uninstall --purge     # also remove its settings, covers and log
```

## Disclaimer

RPCS3 Manager is an independent project, not affiliated with or endorsed by the makers of PlayStation.
PlayStation and PS3 are trademarks of their owner.

## License

GPL-3.0-or-later. RPCS3 is a separate program under its own license (GPL-2.0), downloaded from its own release.
