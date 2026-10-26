<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PPSSPP Manager](../assets/ppsspp/bc250-ppsspp-manager.webp){ .app-logo }

# PPSSPP Manager

Plays **PSP games** on the **AMD BC-250** with [PPSSPP](https://www.ppsspp.org), an open-source PSP emulator. The
app installs the PPSSPP release it was tried with, finds your games and adds them to Steam, so they start from
**Game Mode** like any other game.

Whether a game runs, and how well, is up to PPSSPP. Its
[compatibility list](https://report.ppsspp.org) shows what others found. The PSP is light work for the BC-250:
most games run at full speed.

## What you need

- **Your games**, dumped from your own discs: ISO, CSO or CHD images, or (for homebrew and games bought digitally)
  a folder with an `EBOOT.PBP`. The app never downloads games.
- **Steam**, started at least once, for Game Mode.
- About 50 MB for PPSSPP itself. Its saves, settings and memory stick games go in `~/.config/ppsspp`, the PSP's
  memory stick.
- **fusermount** (FUSE), which Bazzite has. PPSSPP comes as an AppImage, which mounts itself with it. Without it,
  it unpacks itself to a temporary folder on every start, which takes longer.

No firmware is needed: PPSSPP plays the PSP's system software itself.

## Using it

The window has two steps, then the list of games.

1. **PPSSPP**: **Install** downloads PPSSPP from its GitHub release (about 48 MB) and checks it against the
   checksum this version of the app was tried with before installing it. **Remove** takes it out again; PPSSPP's
   own folder, with your saves and settings, stays.
2. **Game folders**: the folders the app looks for games in. **Add folder…** adds one, **Remove folder…** stops
   looking in one (the games stay where they are). A game may sit up to five folders deep.

The table lists every game found: its title and ID (ULUS…, UCES…) from the `PARAM.SFO` inside the image, its kind
and its file. It has two kinds of games:

- **Disc images** in the game folders: ISO and CSO are read for their title, ID and pictures. A **CHD** is listed
  under its file name: the app does not look into MAME's archive format, so Steam gets no pictures from it, but
  PPSSPP plays it the same.
- **Memory stick games**: folders with an `EBOOT.PBP`, in the game folders and on PPSSPP's own memory stick
  (`~/.config/ppsspp/PSP/GAME`), where PPSSPP keeps homebrew and installed games. A game's update there (its
  `PARAM.SFO` says category PG) is not a game to start: PPSSPP lays it over the disc game by itself.

- **Play** (or a double-click) starts the chosen game on the desktop, as PPSSPP is set up.
- **PPSSPP settings** opens PPSSPP's own window, with its settings, its controller settings and its game list.
- **Rename files…** renames the ISO and CSO images after their `PARAM.SFO`: see
  [Renaming the files](#renaming-the-files).

### Game Mode

Tick the games you want in Game Mode and press **Update Game Mode**. The app adds them to Steam as non-Steam games,
with the game's own icon and background (from inside the image) as their pictures and its icon (`ICON0.PNG`) as the
logo on the banner, and takes out the games you unticked and games it no longer finds. Steam keeps these files in
memory, so it closes for the change and starts again in the background.

In Steam each game's name starts with its system, for example **[PSP] Lumines**, so it stands apart from the same
title on Steam or on another system in Steam's menus. A game added under its title alone is renamed the next time you
press **Update Game Mode**, which is on for it until then. Steam sees the renamed game as a new one: its play time
stays, but a controller layout or collection you set for it in Steam has to be set again.

In Game Mode the games are in the library under **Non-Steam**. They start the game full screen in PPSSPP, with an
**Exit** entry in PPSSPP's pause menu. Steam's menu and **Exit game** work as for any game.

Steam's overlay works over a game started from Steam, in Game Mode and on the desktop: press **Shift+Tab** or the
**PS button** for the game's page, its controller layout and its settings, without leaving the game.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

Change Game Mode from Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change.

#### Covers

A PSP game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on a
dark background. With a SteamGridDB API key, the app takes a cover from SteamGridDB for each game instead; the
background and the logo on the game's page stay the game's own. See [Covers from SteamGridDB](covers.md) for the
key, how a game is looked up and how to use a cover of your own.

## Renaming the files

A dumped disc often gets a meaningless file name. **Rename files…** opens a window with the ISO and CSO images the
app found and the name each would get from its own `PARAM.SFO`: pick one of eight naming templates, such as
`ULJM05437 - Ever17.iso` or `Ever17 [ULJM05437].iso`, and press **Rename all**. The window shows the selected
game's pictures (a click cycles ICON0, PIC0 and PIC1), and for a title in another language you can type a
**translation**, used as the title in that file's new name (**Translate** opens the title in Google Translate). A
name another file already has is never taken over; characters that are illegal in file names are removed.

A memory stick game is never renamed (its file must stay `EBOOT.PBP`), and a CHD is not read. A renamed game that
is in Game Mode needs **Update Game Mode** afterwards: its shortcut names the file.

This window is the former standalone app **Bazzite UMD File Renamer**, absorbed into PPSSPP Manager. Installing
PPSSPP Manager removes the standalone app and adopts its saved naming template; your images stay where they are.

## From a terminal

`bc250-ppsspp-run` starts the installed PPSSPP with the options you give it. The Game Mode shortcuts use it, so
they keep working when a newer version of the app brings a newer PPSSPP.

```bash
bc250-ppsspp-run --fullscreen --pause-menu-exit "/path/to/game.iso"   # a game full screen (Game Mode)
bc250-ppsspp-run "/path/to/game.iso"                                  # a game, as PPSSPP is set up
bc250-ppsspp-run                                                      # PPSSPP's own window
```

## New PPSSPP releases

Each version of the app installs one PPSSPP release, the one it was tried with. When the window opens, the app
asks GitHub for PPSSPP's newest release. When that one is newer, the first step says so, with a link to what is
new; the app does not install it. A newer PPSSPP comes with a newer version of the app, once it has been tried,
from the [portal](../portal.md): after updating the app, the first step says so, and **Install** brings it.
PPSSPP's own window also says when a new release is out; on Linux it does not update itself.

## How it works

The Game Mode shortcuts start `bc250-ppsspp-run`, which starts PPSSPP. Two things change when Steam is the one
that starts it. Started with **Play**, from outside Steam, PPSSPP runs as it is.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). PPSSPP then sees only that
virtual controller, and on the desktop it follows the layout Steam has active, which may be Steam's desktop layout
(mouse and keys).

So the run wrapper undoes it: while a real controller is connected, PPSSPP reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.
Controls are mapped in PPSSPP's own window (**PPSSPP settings**, then **Settings > Controls**).

### Steam's overlay on the desktop

The KDE desktop of Bazzite is a Wayland session. PPSSPP (an SDL program) may open its window through Wayland, but
Steam on the desktop only sees windows that go through X11 (XWayland, the X11 server within the Wayland session).
A game window Steam cannot see has no overlay: **Shift+Tab** and the **PS button** do nothing.

So when Steam starts a game on the Wayland desktop, the run wrapper has PPSSPP open its window through XWayland
(`SDL_VIDEODRIVER=x11`), and Steam's overlay works as in any other game. Game Mode runs every game through X11
already.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-ppsspp-manager/app` |
| PPSSPP | `~/.local/share/bc250-ppsspp-manager/emulator` |
| PPSSPP's saves, settings, memory stick games | `~/.config/ppsspp` (the PSP's memory stick) |
| The app's settings, with the game folders | `~/.config/bc250-ppsspp-manager` |
| The Game Mode shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The pictures found on SteamGridDB | `~/.local/share/bc250-ppsspp-manager/covers` |
| Launchers | `~/.local/bin/bc250-ppsspp-manager`, `~/.local/bin/bc250-ppsspp-run` |

PPSSPP can keep its memory stick elsewhere (its `--root` option and settings); the app reads the standard place.

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app and the
PPSSPP it installed; PPSSPP's own folder (your saves, settings and memory stick games) and your games stay. The
games in Game Mode then no longer start: take them out first by unticking them and pressing **Update Game Mode**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the PPSSPP it installed; keeps its settings
./install.sh --uninstall --purge     # also remove its settings and covers
```

## Disclaimer

PPSSPP Manager is an independent project, not affiliated with or endorsed by the makers of PlayStation.
PlayStation and PSP are trademarks of their owner.

## License

GPL-3.0-or-later. PPSSPP is a separate program under its own license (GPL-2.0-or-later), downloaded from its own
release.
