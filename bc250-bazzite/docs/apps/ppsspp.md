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

The header shows the **PPSSPP version**, **Your games** (the games found) and those **Available in Steam**.
**Refresh** reads everything again. Beside the title stands the app's state. Under the introduction, which links
to **PPSSPP's release notes** and to this wiki, a row of three pills does the setting up, each with what it is for
on top and what it does under it: **PPSSPP Install**, **PPSSPP Uninstall** and **Games Rename**. Two lines below
the pills say where each stands, and then come three tabs: **Your games**, **Settings** and **Log**, and
**Start game**, a tab that is a button.

- **PPSSPP**: **Not installed.** or **Installed.**, with the button to use under it. The tooltip says which
  release is installed, or what Install takes, and when a newer PPSSPP is out. **Install** downloads PPSSPP from
  its GitHub release (about 48 MB) and checks it against the checksum this version of the app was tried with before
  installing it; when another release is installed, the tooltip and the log say so, and **Install** puts the app's
  in. **Uninstall** takes it out again; PPSSPP's own folder, with your saves and settings, stays.
- **Game folder**: where the app looks for games, `~/Games/PSP` and a removable drive's `Games/PSP` (see [Where
  your games go](#where-your-games-go)); nothing is chosen or browsed to. The **i** beside them says what goes
  there, and the tooltip how many games are on PPSSPP's memory stick. A game may sit up to five folders deep.
- **Games Rename** renames the ISO and CSO images after their `PARAM.SFO`: see [Renaming the
  files](#renaming-the-files).

### Where your games go

The app has a folder of its own, which it makes when it opens; you never choose or browse to a folder: `~/Games/PSP`.
Put your disc images and your `EBOOT.PBP` folders there, or in folders in it, and they show in the table. On a USB
drive or an SD card, make a folder `Games/PSP` on it, and the app looks there too while the drive is mounted (under
`/run/media` or `/media`, as Bazzite mounts it). Folders added in the app before (**Add folder…**, until version
1.0) are no longer looked in: move those games to `~/Games/PSP`.

### Your games

The table lists every game found: its title and ID (ULUS…, UCES…) from the `PARAM.SFO` inside the image, its kind
and its file. It has two kinds of games:

- **Disc images** in the game folders: ISO and CSO are read for their title, ID and pictures. A **CHD** is listed
  under its file name: the app does not look into MAME's archive format, so Steam gets no pictures from it, but
  PPSSPP plays it the same.
- **Memory stick games**: folders with an `EBOOT.PBP`, in the game folders and on PPSSPP's own memory stick
  (`~/.config/ppsspp/PSP/GAME`), where PPSSPP keeps homebrew and installed games. A game's update there (its
  `PARAM.SFO` says category PG) is not a game to start: PPSSPP lays it over the disc game by itself.

**Remove game…** deletes the chosen game from the disk. A window first lists what would go, a row each with its
size: the disc image, or a memory stick game's own folder, and its Steam shortcut when it is in Steam. Every row is ticked; untick what you want to keep, then
**Delete marked**; **Cancel** deletes nothing. The saves on the memory stick stay. A game the app will not delete (one at the top of a
drive, or in a folder that holds another game) is said so under the tabs: delete it by hand.

**PPSSPP settings** opens PPSSPP's own window, with its other settings, its controller settings and its game list.
A game runs from Steam:
[**Start game**](#start-game) starts the chosen one there.

#### Steam

Tick the games you want in Steam and press **Update Steam**. The app adds them to Steam as non-Steam games, with
the game's own icon and background (from inside the image) as their pictures and its icon (`ICON0.PNG`) as the
logo on the banner, and takes out the games you unticked and games it no longer finds. Steam keeps these files in
memory, so it closes for the change and starts again in the background.

In Steam each game's name starts with its system, for example **[PSP] Lumines**, so it stands apart from the same
title on Steam or on another system in Steam's menus. A game added under its title alone is renamed the next time you
press **Update Steam**, which is on for it until then. Steam sees the renamed game as a new one: its play time
stays, but a controller layout or collection you set for it in Steam has to be set again.

The games are in the library under **Non-Steam**, on the desktop, in Big Picture Mode and in Game Mode alike. They
start the game full screen in PPSSPP, with an **Exit** entry in PPSSPP's pause menu. Steam's menu and **Exit game**
work as for any game.

Steam's overlay works over a game started from Steam, in Game Mode and on the desktop: press **Shift+Tab** or the
**PS button** for the game's page, its controller layout and its settings, without leaving the game.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

Change Steam from Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change.

##### Covers

A PSP game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on a
dark background. With a SteamGridDB API key, entered under **Steam artwork…**, the app takes a cover from
SteamGridDB for each game instead; the background and the logo on the game's page stay the game's own. See
[Covers from SteamGridDB](covers.md) for the key, how a game is looked up and how to use a cover of your own.

**Steam** in the line under the table is a link: it opens Steam's library (Steam starts when it does not run).

#### Start game

The last tab, **Start game**, is a button. Choose a game in the table and click it: the game starts through Steam,
as its shortcut in Steam starts it, and Steam starts first when it does not run. The tab you were on stays open. A
game that is not in Steam yet is not started: the line under the tabs says to tick it and press **Update Steam**
first.

### Settings

PPSSPP's settings that matter for playing, each written into PPSSPP's own settings file the moment you change
it. Everything else is in PPSSPP's own window (**PPSSPP settings**, under the games).

- **Picture**: the **Renderer** (Vulkan, PPSSPP's own choice on the BC-250, or OpenGL when a game shows faults),
  the **Internal resolution** (Automatic follows the screen; 3x fills a 1080p screen sharply, 6x a 4K one; a higher
  one asks more of the GPU), **Stretch to the screen**, **Integer scaling**, **Texture filtering** (Nearest keeps
  pixel art sharp), **Anisotropic filtering** and **VSync**.
- **Game**: **Frame skipping** (frames left out to keep a slow game at full speed) and **Cheats** (the cheats in
  PPSSPP's cheats folder).
- **Sound**: the **Volume**.
- **Controller**: the **Stick dead zone** (how far a stick moves before the game sees it, for a stick that drifts)
  and the **Stick sensitivity** (how far the PSP's stick goes for the stick's travel: PPSSPP's 1.10 reaches the
  edge a little sooner).
- **On screen**: **Show FPS** and **Show speed**, in a corner of the picture.

Each setting shows what PPSSPP's settings file holds, or PPSSPP's own default while the file does not name it; a
value set in PPSSPP that the app does not offer is shown as it is. Nothing is written while PPSSPP runs: PPSSPP
writes its settings back when it closes, over any change.

### Log

Everything the app said and did, with the time: PPSSPP installed or removed, what the app set up in PPSSPP, files
renamed, every change to Steam, and every error. The same lines are in
`~/.local/share/bc250-ppsspp-manager/bc250-ppsspp-manager.log`, which turns over at 1 MB (the three older files are
kept). The log holds what the app did, not your SteamGridDB key or anything personal.

## Renaming the files

A dumped disc often gets a meaningless file name. **Games Rename** opens a window with the ISO and CSO images the
app found and the name each would get from its own `PARAM.SFO`: pick one of eight naming templates, such as
`ULJM05437 - Ever17.iso` or `Ever17 [ULJM05437].iso`, and press **Rename all**. The window shows the selected
game's pictures (a click cycles ICON0, PIC0 and PIC1), and for a title in another language you can type a
**translation**, used as the title in that file's new name (**Translate** opens the title in Google Translate). A
name another file already has is never taken over; characters that are illegal in file names are removed.

A memory stick game is never renamed (its file must stay `EBOOT.PBP`), and a CHD is not read; with no ISO or CSO
image found, **Games Rename** is off. A renamed game that is in Steam needs **Update Steam** afterwards: its
shortcut names the file.

This window is the former standalone app **Bazzite UMD File Renamer**, absorbed into PPSSPP Manager. Installing
PPSSPP Manager removes the standalone app and adopts its saved naming template; your images stay where they are.

## From a terminal

`bc250-ppsspp-run` starts the installed PPSSPP with the options you give it. The Steam shortcuts use it, so
they keep working when a newer version of the app brings a newer PPSSPP.

```bash
bc250-ppsspp-run --fullscreen --pause-menu-exit "/path/to/game.iso"   # a game full screen (Steam)
bc250-ppsspp-run "/path/to/game.iso"                                  # a game, as PPSSPP is set up
bc250-ppsspp-run                                                      # PPSSPP's own window
```

## New PPSSPP releases

Each version of the app installs one PPSSPP release, the one it was tried with. When the window opens, the app
asks GitHub for PPSSPP's newest release. When that one is newer, the PPSSPP line's tooltip and the log say so,
with a link to what is new; the app does not install it. A newer PPSSPP comes with a newer version of the app, once
it has been tried, from the [portal](../portal.md): after updating the app, the tooltip and the log say so, and
**Install** brings it.
PPSSPP's own notice of a new release is turned off by the app (see below); on Linux PPSSPP does not update itself.

## How it works

The Steam shortcuts start `bc250-ppsspp-run`, which starts PPSSPP. Two things change when Steam is the one that
starts it. Started from outside Steam (**PPSSPP settings**, or `bc250-ppsspp-run` in a terminal), PPSSPP runs as
it is.

Once PPSSPP is installed, each time the window opens and while PPSSPP does not run, the app turns off PPSSPP's
notice of a newer release in its settings (`PSP/SYSTEM/ppsspp.ini` on its memory stick): a newer PPSSPP comes with
the app. Everything else in the file stays as PPSSPP wrote it, and what changed goes to the log.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). PPSSPP then sees only that
virtual controller, and on the desktop it follows the layout Steam has active, which may be Steam's desktop layout
(mouse and keys).

So the run wrapper undoes it: while a real controller is connected, PPSSPP reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.
Controls are mapped in PPSSPP's own window (**PPSSPP settings**, then **Settings > Controls**).

### A game renamed, moved or gone

A game renamed or moved after it was put in Steam keeps its mark: the app knows each game in Steam by its code (or,
without one, its file's size), so on **Refresh** it finds the game again under its new name, ticked, and says so
under the tabs; **Update Steam** then takes the old shortcut out and puts the game in under its new name. A
shortcut to a game that is no longer there (deleted, or on a drive that is not in) does not start PPSSPP: a
window says which file is missing and what to do, and closes by itself, so Steam sees the game end.

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
| Your games | `~/Games/PSP` (the app's own folder), and `Games/PSP` on a removable drive |
| The app's settings | `~/.config/bc250-ppsspp-manager` |
| The app's log | `~/.local/share/bc250-ppsspp-manager/bc250-ppsspp-manager.log` |
| The Steam shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The pictures found on SteamGridDB | `~/.local/share/bc250-ppsspp-manager/covers` |
| Launchers | `~/.local/bin/bc250-ppsspp-manager`, `~/.local/bin/bc250-ppsspp-run` |

PPSSPP can keep its memory stick elsewhere (its `--root` option and settings); the app reads the standard place.

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app and the
PPSSPP it installed; PPSSPP's own folder (your saves, settings and memory stick games) and your games stay. The
games in Steam then no longer start: take them out first by unticking them and pressing **Update Steam**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the PPSSPP it installed; keeps its settings and log
./install.sh --uninstall --purge     # also remove its settings, covers and log
```

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite /
Universal Blue project, Sony, Microsoft, Valve, or the makers of the emulators and the other programs the apps work
with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3, PS2, PSP, PS
Vita, PSN, DualSense and Remote Play are Sony's; XBOX, XBOX 360, XBOX Cloud Gaming, Game Pass and Windows are
Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of the emulators (shadPS4, RPCS3, PPSSPP, PCSX2,
Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their owners. The suites use them only to say what
their apps work with.

## License

GPL-3.0-or-later. PPSSPP is a separate program under its own license (GPL-2.0-or-later), downloaded from its own
release.
