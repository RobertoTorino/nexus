<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Vita3K Manager](../assets/vita3k/bc250-vita3k-manager.webp){ .app-logo }

# Vita3K Manager

Plays **PS Vita games** on the **AMD BC-250** with [Vita3K](https://vita3k.org), an open-source PS Vita emulator. The
app installs the Vita3K build it was tried with, installs the PS Vita's firmware and your games through it, and adds
the games to Steam, so they start from **Game Mode** like any other game.

Whether a game runs, and how well, is up to Vita3K. Its [compatibility list](https://vita3k.org/compatibility.html)
shows what others found.

## What you need

- **Your games**, dumped from your own PS Vita: a `.vpk` or `.zip`, a `.pkg` with its zRIF license key, or a dumped
  game folder. The app never downloads games.
- **The PS Vita's firmware**, the PS Vita's system software. Vita3K needs it, and its font package, to start most
  games. The app cannot ship them; each is a file named `PSP2UPDAT.PUP`:
    - the firmware: download it [here](https://www.playstation.com/en-us/support/hardware/psvita/system-software/)
      (official page);
    - the font package: download it
      [here](http://dus01.psp2.update.playstation.net/update/psp2/image/2019_0924/sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP?dest=us)
      (Sony's file);
    - optional, the preinstalled apps: download them
      [here](http://dus01.psp2.update.playstation.net/update/psp2/image/2022_0209/pre_efd1ef6c1cc2fe92e72e9e783e421237/PSP2UPDAT.PUP?dest=us)
      (Sony's file).

    Then press **Install firmware** in the app, once for each file.
- **Steam**, started at least once, for Game Mode.
- About 75 MB for Vita3K itself. Its settings go in `~/.config/Vita3K`, the PS Vita's storage (firmware, installed
  games, saves) in `~/.local/share/Vita3K/Vita3K`.
- **fusermount** (FUSE), which Bazzite has. Vita3K comes as an AppImage, which mounts itself with it. Without it, it
  unpacks itself to a temporary folder on every start, which takes longer.

## Using it

The window has three steps, then the list of games.

1. **Vita3K**: **Install** downloads Vita3K from GitHub (about 75 MB) and checks it against the checksum this version
   of the app was tried with before installing it. **Remove** takes it out again; Vita3K's own folders, with the
   firmware, your games, saves and settings, stay.
2. **Firmware**: which parts of the PS Vita's firmware Vita3K has: the system software, the font package and the
   preinstalled apps. **Install firmware…** asks for a `PSP2UPDAT.PUP` you downloaded and has Vita3K install it,
   without a window; the step then says which part it was.
3. **Games**: how many games Vita3K has installed. **Install game…** installs one of yours:
    - **From a file**: a `.vpk` or `.zip` is handed to Vita3K, which installs it and then starts it in its own
      window; a `.pkg` asks for the game's zRIF license key, and Vita3K installs it without a window.
    - **From a dumped folder**: Vita3K installs the folder's game and starts it in its own window.

    The list shows the game once it is installed.

The table lists every game Vita3K has installed: its title and ID (PCSB…, PCSE…) from the game's own files, its
version and its folder in Vita3K's storage (`ux0/app`).

- **Play** (or a double-click) starts the chosen game on the desktop, alone in a window. Closing the window ends it.
- **Vita3K settings** opens Vita3K's own window, with its settings, its controls and its game list.

### Game updates and extra content

Install an update or extra content (DLC) as a game: **Install game…** with its `.pkg` and zRIF key. Vita3K puts an
update in `ux0/patch` and extra content in `ux0/addcont`, and uses them when it starts the game. The table lists the
game once.

### Game Mode

Tick the games you want in Game Mode and press **Update Game Mode**. The app adds them to Steam as non-Steam games,
with the game's own icon and LiveArea picture as their pictures and its icon (`icon0.png`) as the logo on the
banner, and takes out the games you unticked and games no longer installed. Steam keeps these files in memory, so it
closes for the change and starts again in the background.

In Steam each game's name starts with its system, for example **[PS Vita] Gravity Rush**, so it stands apart from the
same title on Steam or on another system in Steam's menus.

In Game Mode the games are in the library under **Non-Steam**. They start the game alone in Vita3K, full screen, and
Vita3K quits when the game ends. Steam's menu and **Exit game** work as for any game.

Steam's overlay works over a game started from Steam, in Game Mode and on the desktop: press **Shift+Tab** or the
**PS button** for the game's page, its controller layout and its settings, without leaving the game.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

Change Game Mode from Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change.

#### Covers

A PS Vita game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on
a dark background. With a SteamGridDB API key, the app takes a cover from SteamGridDB for each game instead; the
background and the logo on the game's page stay the game's own. See [Covers from SteamGridDB](covers.md) for the
key, how a game is looked up and how to use a cover of your own.

## From a terminal

`bc250-vita3k-run` starts the installed Vita3K with the options you give it. The Game Mode shortcuts use it, so they
keep working when a newer version of the app brings a newer Vita3K.

```bash
bc250-vita3k-run --frontend sdl -r PCSB00245                   # a game alone, by its ID; Vita3K quits with it
bc250-vita3k-run --firmware "/path/to/PSP2UPDAT.PUP"           # install a part of the firmware
bc250-vita3k-run --pkg "/path/to/game.pkg" --zrif KO5i...      # install a game from its package and license
bc250-vita3k-run "/path/to/game.vpk"                           # install a game and start it
bc250-vita3k-run                                               # Vita3K's own window
```

## New Vita3K builds

Vita3K has no stable releases: it publishes a new build for almost every change, numbered over its whole history
(4186). Each version of the app installs one build, the one it was tried with. When the window opens, the app asks
GitHub for Vita3K's newest build. When that one is newer, the first step says so, with a link to what is new; the app
does not install it. A newer Vita3K comes with a newer version of the app, once it has been tried, from the
[portal](../portal.md): after updating the app, the first step says so, and **Install** brings it.

Vita3K's own window (**Vita3K settings**) also looks for a newer build when it opens, and says when there is one, with
a link to its download page; it does not replace itself. The AppImage Vita3K comes in can update itself, but the app
starts Vita3K with that turned off. Should Vita3K have been updated all the same, the first step says so, and
**Install** puts the tried build back.

## How it works

The Game Mode shortcuts start `bc250-vita3k-run`, which starts Vita3K with its plain game window: the game alone, and
Vita3K quits with it, so Steam sees the game end. Two things change when Steam is the one that starts it. Started
with **Play**, from outside Steam, Vita3K runs as it is.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). Vita3K then sees only that
virtual controller: it has no motion sensors or touchpad, and on the desktop it follows the layout Steam has active,
which may be Steam's desktop layout (mouse and keys).

So the run wrapper undoes it: while a real controller is connected, Vita3K reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is. The
buttons are set in Vita3K's own window (**Vita3K settings**, then **Controls**).

### Steam's overlay on the desktop

The KDE desktop of Bazzite is a Wayland session. Vita3K opens its windows through Wayland when it can, but Steam on
the desktop only sees windows that go through X11 (XWayland, the X11 server within the Wayland session). A game
window Steam cannot see has no overlay: **Shift+Tab** and the **PS button** do nothing.

So when Steam starts a game on the Wayland desktop, the run wrapper has Vita3K open its windows through XWayland
(`SDL_VIDEO_DRIVER=x11`, and `QT_QPA_PLATFORM=xcb` for its own window), and Steam's overlay works as in any other
game. Game Mode runs every game through X11 already.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-vita3k-manager/app` |
| Vita3K | `~/.local/share/bc250-vita3k-manager/emulator` |
| Vita3K's settings | `~/.config/Vita3K` (Vita3K's own folder) |
| The PS Vita's storage: firmware, installed games, saves | `~/.local/share/Vita3K/Vita3K` (Vita3K's own folder) |
| Vita3K's shader cache and log | `~/.cache/AppImage-Cache/Vita3K` |
| The app's settings | `~/.config/bc250-vita3k-manager` |
| The Game Mode shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The covers found on SteamGridDB | `~/.local/share/bc250-vita3k-manager/covers` |
| Launchers | `~/.local/bin/bc250-vita3k-manager`, `~/.local/bin/bc250-vita3k-run` |

Vita3K can keep its storage elsewhere (its **Settings**, the storage folder); the app reads where it is.

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app
and the Vita3K it installed; Vita3K's own folders (the firmware, your games, your saves) stay. The games in Game
Mode then no longer start: take them out first by unticking them and pressing **Update Game Mode**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the Vita3K it installed; keeps its settings
./install.sh --uninstall --purge     # also remove its settings and covers
```

## Disclaimer

Vita3K Manager is an independent project, not affiliated with or endorsed by the makers of PlayStation.
PlayStation and PS Vita are trademarks of their owner.

## License

GPL-3.0-or-later. Vita3K is a separate program under its own license (GPL-2.0), downloaded from its own release.
