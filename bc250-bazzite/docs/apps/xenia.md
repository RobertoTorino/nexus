<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Xenia Manager](../assets/xenia/bc250-xenia-manager.webp){ .app-logo }

# Xenia Manager

Plays **Xbox 360 games** on the **AMD BC-250** with [Xenia](https://xenia.jp), an Xbox 360 emulator, in its
[Xenia Canary](https://github.com/xenia-canary/xenia-canary) builds. The app installs a tested build, finds your
games and adds them to Steam, so they start from **Game Mode** like any other game.

Xenia's Linux build is experimental: not every game starts, and a game that runs on Windows may not run here.
Whether a game runs, and how well, is up to Xenia. Its
[compatibility list](https://github.com/xenia-canary/game-compatibility/issues) says what is known.

## What you need

- **Your games**, from your own discs and console: disc images (`.iso`), discs unpacked to a folder with a
  `default.xex`, Xenia's `.zar` archives, and Games on Demand and Arcade packages as the console keeps them. The app
  never downloads games.
- **Steam**, started at least once, for Game Mode.
- **FUSE**, which Bazzite has: Xenia comes as an AppImage.
- No BIOS or firmware: Xenia does not need the console's.

## Using it

The window has two steps, then the list of games.

1. **Xenia**: **Install** downloads Xenia (about 18 MB) and checks it against the checksum of the build the app was
   tried with before installing it. **Remove** takes it out again; Xenia's own folder, with its settings, saves and
   installed content, stays.
2. **Game folders**: the folders the app looks for games in. **Add folder…** adds one, **Remove folder…** stops
   looking in one (the games stay where they are). A game may sit up to six folders deep.

The table lists every game found:

- A **disc image** is a game when it is an Xbox 360 disc (the app looks for the disc's mark where Xenia looks for
  it), listed under its file's name.
- An **unpacked disc** is its `default.xex`, listed under its folder's name; the other `.xex` files in that folder
  are its parts. Any other `.xex` is listed under its own name.
- A **.zar** archive is listed under its file's name; the app does not look into it.
- A **Games on Demand** or **Arcade** package is listed under the name in its header. Keep it in the folders the
  console made (`<title ID>/00007000/` or `<title ID>/000D0000/`). Saves, downloadable content and title updates are
  not games and are left out.

The **Title ID** column shows the game's ID (4D5307E6), from the `.xex` or the package, where the app can read it.

- **Play** (or a double-click) starts the chosen game on the desktop, in a window.
- **Xenia settings** opens Xenia's own window, with its settings, profiles and installed content.

### Game Mode

Tick the games you want in Game Mode and press **Update Game Mode**. The app adds them to Steam as non-Steam games
and takes out the games you unticked and games it no longer finds. Steam keeps these files in memory, so it closes
for the change and starts again in the background. The pictures on the tiles are drawn from the app's icon, with the
game's title, on a background in the icon's color, and the icon is the logo on the banner.

In Steam each game's name starts with its system, for example **[X360] Halo 3**, so it stands apart from the same
title on Steam or on another system in Steam's menus.

In Game Mode the games are in the library under **Non-Steam**. They start the game alone in Xenia, full screen.
Steam's overlay works over a game started from Steam, in Game Mode and on the desktop: press **Shift+Tab** or the
**Steam button** for the game's page, its controller layout and its settings, without leaving the game.

Change Game Mode from Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change.

#### Covers

With a SteamGridDB API key, the app takes all four pictures from SteamGridDB instead of drawing them: the cover, the
wide picture, the banner and the logo. Press **Covers…** to enter the key, one for the whole suite. A picture
SteamGridDB does not have stays drawn. See [Covers from SteamGridDB](covers.md) for the key, how a game is looked up
and how to use pictures of your own.

## From a terminal

`bc250-xenia-run` starts the installed Xenia with the options you give it. The Game Mode shortcuts use it, so they
keep working when a newer version of the app brings a newer Xenia. Xenia's options take the form `--name=value`.

```bash
bc250-xenia-run --fullscreen=true "/path/to/game.iso"   # a game full screen (Game Mode)
bc250-xenia-run "/path/to/game.iso"                     # a game in a window
bc250-xenia-run                                         # Xenia's own window
```

## New Xenia builds

Xenia has no stable releases: Xenia Canary publishes a build for almost every change, named after the change
(`e6cd2e4`). Each version of the app installs one build, the one it was tried with. When the window opens, the app
asks GitHub for the newest build; when one was published after the app's, the first step says so, with a link to
what changed. The app does not install it. A newer build comes with a newer version of the app, once it has been
tried, from the [portal](../portal.md): after updating the app, the first step says so, and **Install** brings it.

## How it works

The Game Mode shortcuts start `bc250-xenia-run`, which starts Xenia. Started with **Play**, from outside Steam,
Xenia runs as it is.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). Xenia then sees only that
virtual controller, and on the desktop it follows the layout Steam has active, which may be Steam's desktop layout
(mouse and keys).

So the run wrapper undoes it: while a real controller is connected, Xenia reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. Without a real controller, as on a Steam Deck whose own controls exist
only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.

### Steam's overlay on the desktop

Xenia's window goes through X11 (XWayland on the KDE desktop of Bazzite) by itself, so Steam's overlay sees it on
the desktop too, and the run wrapper has nothing to change for it.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-xenia-manager/app` |
| Xenia | `~/.local/share/bc250-xenia-manager/emulator` |
| Xenia's settings, saves and installed content | `~/.local/share/Xenia` (Xenia's own folder) |
| The app's settings, with the game folders | `~/.config/bc250-xenia-manager` |
| The Game Mode shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The pictures found on SteamGridDB | `~/.local/share/bc250-xenia-manager/covers` |
| Launchers | `~/.local/bin/bc250-xenia-manager`, `~/.local/bin/bc250-xenia-run` |

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app and the
Xenia it installed; Xenia's own folder (your settings, saves and installed content) and your games stay. The games in
Game Mode then no longer start: take them out first by unticking them and pressing **Update Game Mode**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the Xenia it installed; keeps its settings
./install.sh --uninstall --purge     # also remove its settings and covers
```

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite
/ Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other programs the
apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3,
PS2, PSP, PS Vita, PSN, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud Gaming, Game Pass and
Windows are Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's consoles, of the
emulators (shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their
owners. The suites use them only to say what their apps work with.

## License

GPL-3.0-or-later. Xenia (BSD-3-Clause) is a separate program under its own license, downloaded from its own releases.
