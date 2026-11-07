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
- About 86 MB for Vita3K itself. Its settings go in `~/.config/Vita3K`, the PS Vita's storage (firmware, installed
  games, saves) in `~/.local/share/Vita3K/Vita3K`.
- **fusermount** (FUSE), which Bazzite has. Vita3K comes as an AppImage, which mounts itself with it. Without it, it
  unpacks itself to a temporary folder on every start, which takes longer.

## Using it

The header shows the **Vita3K version** (its build number), the **Firmware** (Ready, Partly or —), **Your games**
(the games installed) and those **Available in Steam**. **Refresh** reads everything again. Beside the title stands
the app's state. Under the introduction, which links to **Vita3K's release notes** and to this wiki, a row of three
pills does the setting up, each with what it is for on top and what it does under it: **Vita3K Install**,
**Vita3K Uninstall** and **Games Install**. Three lines below the pills say where each stands, and then come three
tabs: **Your games**, **Settings** and **Log**.

- **Vita3K**: **Not installed.** or **Installed.**, with the button to use under it. The tooltip says which build
  is installed, or what Install takes, and when a newer build is out. **Install** downloads Vita3K from GitHub
  (about 86 MB) and checks it against the checksum this version of the app was tried with before installing it;
  when another build is installed, the tooltip and the log say so, and **Install** puts the app's in.
  **Uninstall** takes it out again; Vita3K's own folders, with the firmware, your games, saves and settings, stay.
- **Firmware**: which parts of the PS Vita's firmware Vita3K has: the system software, the font package and the
  preinstalled apps. Put the `PSP2UPDAT.PUP` files you downloaded in `~/Games/Vita/Firmware` (each in a folder of
  its own there if you like, since Sony names all three the same): once Vita3K is installed, the app gives them to
  Vita3K by itself, the largest first, one after the other, when the window opens and on **Refresh**; the line
  under the tabs then says which part each was. A file is given once as it is, also one Vita3K could not use; a
  file you replace is given again. The files stay in the folder.
- **Games**: how many games Vita3K has installed. **Games Install** installs one of yours; its window opens in
  `~/Games/Vita`, the app's own folder (also on a USB drive or an SD card with a `Games/Vita` folder on it):
    - **From a file**: a `.vpk` or `.zip` is handed to Vita3K, which installs it and then starts it in its own
      window; a `.pkg` asks for the game's zRIF license key, and Vita3K installs it without a window.
    - **From a dumped folder**: Vita3K installs the folder's game and starts it in its own window.

    The list shows the game once it is installed.

### Your games

The table lists every game Vita3K has installed: its title and ID (PCSB…, PCSE…) from the game's own files, its
version and its folder in Vita3K's storage (`ux0/app`).

**Remove game…** deletes the chosen game from the disk. A window first lists what would go, a row each with its
size: the game in Vita3K's storage, and its update and extra content when they are there, and its Steam shortcut when it is in Steam. Every row is ticked; untick what you want to keep, then
**Delete marked**; **Cancel** deletes nothing. The saves stay. A game the app will not delete (one at the top of a
drive, or in a folder that holds another game) is said so under the tabs: delete it by hand.

**Vita3K settings** opens Vita3K's own window, with its other settings, its controls and its game list. The app
has no Play button: a game is started from Steam.

#### Game updates and extra content

Install an update or extra content (DLC) as a game: **Games Install** with its `.pkg` and zRIF key. Vita3K puts an
update in `ux0/patch` and extra content in `ux0/addcont`, and uses them when it starts the game. The table lists the
game once.

#### Steam

Tick the games you want in Steam and press **Update Steam**. The app adds them to Steam as non-Steam games, with
the game's own icon and LiveArea picture as their pictures and its icon (`icon0.png`) as the logo on the banner,
and takes out the games you unticked and games no longer installed. Steam keeps these files in memory, so it closes
for the change and starts again in the background.

In Steam each game's name starts with its system, for example **[PS Vita] Gravity Rush**, so it stands apart from the
same title on Steam or on another system in Steam's menus.

The games are in the library under **Non-Steam**, on the desktop, in Big Picture Mode and in Game Mode alike. They
start the game alone in Vita3K, full screen, and Vita3K quits when the game ends. Steam's menu and **Exit game** work
as for any game.

Steam's overlay works over a game started from Steam, in Game Mode and on the desktop: press **Shift+Tab** or the
**PS button** for the game's page, its controller layout and its settings, without leaving the game.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

Change Steam from Desktop Mode: in Game Mode Steam is the session itself and cannot close for the change.

##### Covers

A PS Vita game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on
a dark background. With a SteamGridDB API key, entered under **Steam artwork…**, the app takes a cover from
SteamGridDB for each game instead; the background and the logo on the game's page stay the game's own. See
[Covers from SteamGridDB](covers.md) for the key, how a game is looked up and how to use a cover of your own.

**Steam** in the line under the table is a link: it opens Steam's library (Steam starts when it does not run).

### Settings

Vita3K's settings that matter for playing, each written into Vita3K's own settings file (`config.yml`) the moment
you change it. A game's own settings in Vita3K come before these; everything else is in Vita3K's own window
(**Vita3K settings**, under the games).

- **Picture**: the **Renderer** (Vulkan; OpenGL helps only a game that fails with Vulkan), the **Resolution** (a
  multiple of the PS Vita's 960 × 544: 2x fills a 1080p screen sharply; a higher one asks more of the GPU), the
  **Screen filter** (Bilinear smooth, Nearest sharp pixels, Bicubic sharper, FXAA smooths edges, FidelityFX Super
  Resolution with Vulkan only), **Anisotropic filtering**, **Fill the screen** (the picture stretched to the whole
  screen; off, the PS Vita's shape with borders) and **VSync**.
- **Speed**: **High accuracy** (draws more exactly, for a game that shows errors; slower), **Compile shaders in
  the background** (the game goes on while Vita3K compiles, with a stutter less), the **FPS hack** (may double a
  30 FPS game to 60, but makes some run twice as fast), the **Performance overlay** (the frames per second over the
  game) and the **Shader compilation message**.
- **Sound**: the **Volume**, the **Sound output** (SDL, Vita3K's own choice, or Cubeb when the sound crackles) and
  **NGS sound** (the PS Vita's sound engine; off, many games are silent, for one that hangs on it).
- **System**: the **Confirm button** (Cross as on a PS Vita sold outside Japan, Circle as in Japan) and the
  **Language** of the PS Vita, which a game with that language shows.

Each setting shows what Vita3K's settings file holds, or Vita3K's own default while the file does not name it; a
value set in Vita3K that the app does not offer is shown as it is. Nothing is written while Vita3K runs: Vita3K
writes its settings back when it closes, over any change.

### Log

Everything the app said and did, with the time: Vita3K installed or removed, what the app set up in Vita3K, the
firmware files given to Vita3K, the games installed or deleted, every change to Steam, and every error. The same
lines are in `~/.local/share/bc250-vita3k-manager/bc250-vita3k-manager.log`, which turns over at 1 MB (the three
older files are kept). The log holds what the app did, not your SteamGridDB key or anything personal.

## From a terminal

`bc250-vita3k-run` starts the installed Vita3K with the options you give it. The Steam shortcuts use it, so they keep
working when a newer version of the app brings a newer Vita3K.

```bash
bc250-vita3k-run --frontend sdl -r PCSB00245                   # a game alone, by its ID; Vita3K quits with it
bc250-vita3k-run --firmware "/path/to/PSP2UPDAT.PUP"           # install a part of the firmware
bc250-vita3k-run --pkg "/path/to/game.pkg" --zrif KO5i...      # install a game from its package and license
bc250-vita3k-run "/path/to/game.vpk"                           # install a game and start it
bc250-vita3k-run                                               # Vita3K's own window
```

## New Vita3K builds

Vita3K has no stable releases: it publishes a new build for almost every change, numbered over its whole history
(4269). Each version of the app installs one build, the one it was tried with. When the window opens, the app asks
GitHub for Vita3K's newest build. When that one is newer, the Vita3K line's tooltip and the log say so, with a link
to what is new; the app does not install it. A newer Vita3K comes with a newer version of the app, once it has been
tried, from the [portal](../portal.md): after updating the app, the tooltip and the log say so, and **Install**
brings it.

Vita3K's own window (**Vita3K settings**) would look for a newer build when it opens; the app turns that check off
in Vita3K's settings, with Vita3K's welcome window (see below). The AppImage Vita3K comes in can update itself, but
the app starts Vita3K with that turned off. Should Vita3K have been updated all the same, the Vita3K line's tooltip
says so, and **Install** puts the tried build back.

## How it works

The Steam shortcuts start `bc250-vita3k-run`, which starts Vita3K with its plain game window: the game alone, and
Vita3K quits with it, so Steam sees the game end. Two things change when Steam is the one that starts it. Started
from outside Steam (**Vita3K settings**, or `bc250-vita3k-run` in a terminal), Vita3K runs as it is.

Once Vita3K is installed, each time the window opens and while Vita3K does not run, the app sets two lines of
Vita3K's settings (`config.yml` in its settings folder): its welcome window off, which would wait for a click
before a game, and its own update check off, which would offer a build the app was not tried with. Everything else
in the file stays as Vita3K wrote it, and what changed goes to the log.

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
| The firmware files you put there, and your games to install | `~/Games/Vita/Firmware` and `~/Games/Vita` (the app's own folder) |
| Vita3K's settings | `~/.config/Vita3K` (Vita3K's own folder) |
| The PS Vita's storage: firmware, installed games, saves | `~/.local/share/Vita3K/Vita3K` (Vita3K's own folder) |
| Vita3K's shader cache and log | `~/.cache/AppImage-Cache/Vita3K` |
| The app's settings | `~/.config/bc250-vita3k-manager` |
| The app's log | `~/.local/share/bc250-vita3k-manager/bc250-vita3k-manager.log` |
| The Steam shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The covers found on SteamGridDB | `~/.local/share/bc250-vita3k-manager/covers` |
| Launchers | `~/.local/bin/bc250-vita3k-manager`, `~/.local/bin/bc250-vita3k-run` |

Vita3K can keep its storage elsewhere (its **Settings**, the storage folder); the app reads where it is.

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app
and the Vita3K it installed; Vita3K's own folders (the firmware, your games, your saves) stay. The games in Steam
then no longer start: take them out first by unticking them and pressing **Update Steam**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the Vita3K it installed; keeps its settings and log
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

GPL-3.0-or-later. Vita3K is a separate program under its own license (GPL-2.0), downloaded from its own release.
