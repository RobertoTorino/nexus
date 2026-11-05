<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![RPCS3 Manager](../images/apps/rpcs3.webp){ .app-logo }

# RPCS3 Manager

Gets your PS3 games ready to play from Steam with [RPCS3](https://rpcs3.net), the PS3 emulator, and takes care of
everything around it: it installs one tested build of RPCS3 for your own user, has RPCS3 install the PS3's firmware
and your packages, offers its settings, finds your games in its own `Games\PS3` folder and in RPCS3, puts them in
Steam, and keeps a log. You never choose a folder: you put the files there, and the app takes care of them. You play from Steam, and never need RPCS3's own window: a game starts alone and full screen, and when you leave
it you are back in Steam.

RPCS3 Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it is
installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **RPCS3 Manager**). It opens full
screen; **⧉** (View) exits it.

Whether a game runs, and how well, is up to RPCS3. Its [compatibility list](https://rpcs3.net/compatibility) shows
what others found; a PS3 game asks a lot of a handheld.

## What you need

- **Your PS3 games**: disc games copied from your own discs (a folder per game, with `PS3_DISC.SFB` and the `PS3_GAME`
  folder), or games bought digitally as packages (`.pkg`, with the `.rap` license of a PSN game), put in `Games\PS3`
  on the device or an SD card (see [Where your games go](#where-your-games-go)). The app never downloads a game.
- **The PS3's firmware** (`PS3UPDAT.PUP`), the PS3's system software. RPCS3 needs it to start any game, and the app
  cannot ship it: download it from
  [PlayStation's firmware page](https://www.playstation.com/en-us/support/hardware/ps3/system-software/) in a browser
  on the device, and put it in `Games\PS3\Firmware`. The app has RPCS3 install it by itself.
- **Microsoft's Visual C++ runtime**, which Steam and most games install already. RPCS3 for Windows does not start
  without it; the RPCS3 pane says so when it is missing, and
  [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) from Microsoft installs it.
- **Steam**, started once on the device, to play the games from Steam (optional: without Steam, **X Play** starts a
  game in RPCS3 itself).

## The screen

Four cards on the left, **RPCS3**, **Your games**, **Settings** and **Log**; the right side shows what the focused
card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row at the
bottom with what it does on the pane that shows: **A** included (**A Install**, **A Steam mark**, **A View log**).
Press the button, or tap the entry. **B** goes back: from a list or a page to where you came from, from a pane to its
card on the left (on a card it does nothing). Once you are in a pane, the d-pad stays in it: at the top or bottom of a
list the focus stops, and only **B** takes you back to the cards. **⧉** (View) exits the app. **☰** (Menu) opens the
information of the pane that shows, and closes it again; the **information icon** at a pane's top right does the same
by touch.

The amber edge shows where you are, as in every app of the suite. Nothing is ever grayed out: when a button cannot do
its job now, pressing it says why on the pane's status line. Every card, row and entry also works by touch, and a long
list scrolls with the d-pad or a finger.

## RPCS3

The pane shows the RPCS3 that is installed, the one this version of the app installs, the firmware, the time spent in
your games (as RPCS3 counts it) and the folder. RPCS3's own window is never opened: your games and packages are on
the **Your games** card, and the firmware is installed by itself.

- **A Install** (also **A** on the RPCS3 card) downloads RPCS3 0.0.43, build 20395, for Windows from RPCS3's own
  builds on GitHub (37 MB), checks it against the checksum this version of the app was tested with, and unpacks it.
  The page counts the megabytes while it downloads. Nothing is downloaded before you press A.
- **The firmware** you put in `Games\PS3\Firmware` is given to RPCS3 by the app itself, when the app opens, when the
  RPCS3 card gets the focus and right after RPCS3 is installed, while RPCS3 is closed. RPCS3 installs it without
  opening its window; it takes a minute or two, the status line says so meanwhile, and the Firmware row then shows its
  version (4.92). A firmware whose version is installed already is not given again. A file RPCS3 refused (the status
  line says why) is not given again either, until you put in another one or a new download of it. The file stays in
  the folder. RPCS3's firmware page says which version is the newest; RPCS3 takes any it supports.
- **X Remove RPCS3** removes RPCS3's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. RPCS3's folder, with the firmware, your saves, its settings and the installed games,
  stays, so a new install finds them again. It does not work while RPCS3 runs.
- **Y Update** shows when an older RPCS3 is installed, and puts in the one this version of the app brings.

**⧉** during a download, an install or a removal asks first: a second **⧉** within five seconds exits the app. A
download stops then; RPCS3 goes on installing a firmware or the package it is on by itself, and the rest waits for
the next time.

RPCS3 on Windows keeps everything beside its program, in the app's `emulator` folder: its settings in `config`
(`config.yml`, `games.yml`, the controller and the per-game settings), the PS3's drives `dev_hdd0` (the installed
games, the saves) and `dev_flash` (the firmware), its window's settings in `GuiConfigs` and its own log in
`log\RPCS3.log`. Before RPCS3's first start, and each time the app opens, the app sets up what RPCS3 would otherwise
ask for in its window: its welcome dialog, its question before a game's window closes (View, LB and RB held close it)
and its own update check off (a newer RPCS3 comes with the app), and the
device's controller as player 1 through RPCS3's XInput handler, with RPCS3's own button layout for it (see
[Controller](#controller)). What it set up goes to the log.

A newer RPCS3 never reaches the device by itself: RPCS3 has no stable releases, it publishes a build for almost every
change and now and then marks one with a version number (0.0.43), and a new build may change how games run. So it
comes only with a new version of RPCS3 Manager, tried first, which the portal offers as an update. Then **Y Update**
unpacks it over the older one, and what you made stays.

RPCS3's archive is a `.7z`, which the app unpacks with the `tar` that Windows brings (`C:\Windows\System32\tar.exe`,
built for that on Windows 11). On a Windows whose `tar` cannot (Windows 10's), the RPCS3 pane says so before
downloading anything.

## Where your games go

The app has folders of its own, which it makes when it opens; you never choose or browse to a folder:

- `Games\PS3` in your user folder (`C:\Users\<you>\Games\PS3`): put your disc games there, and your packages
  (`.pkg`) with their licenses (`.rap`, `.edat`), and they show on **Your games**. On an SD card or a USB drive, make a
  folder `Games\PS3` on it, and the app looks there too.
- `Games\PS3\Firmware`: put the PS3's firmware (`PS3UPDAT.PUP`) there, and RPCS3 installs it.

The **Log** card shows where the folder is.

```
Games\PS3\
├── Firmware\             PS3UPDAT.PUP, the firmware you put here
├── UP4055-NPUB30048_00-LUMINES000000001.pkg   a package you put here
├── NPUB30048.rap          its license
└── Demon's Souls\        a disc game: PS3_DISC.SFB, PS3_GAME\ (PARAM.SFO, ICON0.PNG, USRDIR\EBOOT.BIN, ...)
```

## Packages

A package (`.pkg`) is how the PS3 gets a game bought digitally, its update or an add-on; a game from PSN also needs
its license (`.rap`, or `.edat`). On **Your games** each one that waits is a row of its own: **PKG** for a game or an
add-on, **PKG update** for a game's update, **License** for a license.

- **X Install all** has RPCS3 install every one, without opening its window: the licenses first, which RPCS3 copies
  into its own folder, then each package, a game's update last (an update needs its game installed first). RPCS3
  starts once per file; the status line says which one of how many, and a large package takes minutes. **A Install**
  on one installs only that one.
- **You decide which packages to delete** once RPCS3 installed them without a problem, as each takes as much room as
  its game in RPCS3's folder: a page lists them, each marked **Delete**, with its size (see
  [Deciding what to keep](#deciding-what-to-keep)). A package you keep is not listed again, and **X Install all**
  leaves it alone, until the file changes. A package RPCS3 could not install stays, and the status line says why.
- **A license stays** where you put it; once RPCS3 keeps it, it no longer shows as a row.

The packages go into RPCS3's own folder (`dev_hdd0\game`), and the game shows on Your games once. A game's update is a
package too: RPCS3 uses it when it starts the game.

## Your games

The games are the **disc games** in the app's `Games\PS3` folders (see [Where your games go](#where-your-games-go))
and up to five folders below them, each in a folder of its own
as copied from the disc (`PS3_DISC.SFB` and the `PS3_GAME` folder; RPCS3 does not start one without its
`PS3_DISC.SFB`, and the list says **no PS3_DISC.SFB** then), the **games installed from packages** in RPCS3's
`dev_hdd0`, and the **disc games RPCS3 knows** from before, wherever they are. Each is listed with its title and ID
(BLUS30443, NPUB30001) from its own `PARAM.SFO`. **A** on the Your games card goes to the list.

You play the games from Steam; the app puts them there.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[PS3] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer found, is taken out. Steam closes for it and starts again, its window open and signed in.
  Steam must have been started once on the device, RPCS3 must be installed with its firmware. When there is nothing
  to change, **Y** says so on the status line instead. Right after writing, the app reads Steam's file back and counts
  the games in Steam from that; should a game it wrote not be found, the status line and the log say which.
- **X Play** on a game that is in Steam starts it, through Steam: Steam starts first when it does not run, then
  RPCS3 with the game, full screen, as from Steam's library. A game that is not in Steam yet says so: **A** marks
  it, **Y** puts it there. On a device without Steam (not installed, or never started), **X Play** starts the game
  in RPCS3 itself, full screen, the same way Steam would.
- **LT Refresh** reads the game folders again: a game put there, renamed or taken away while the app is open
  shows at once. A game in Steam that you rename or move keeps its mark when the app can tell it is the same
  game (by its title ID or serial, or a disc image by its size): **Y Update Steam** then puts it in Steam under
  its new name and takes the old shortcut out. Until then, its shortcut in Steam shows a screen that says the
  game is no longer there, instead of starting the emulator; **A** closes it.
- Steam's library opens from the portal: **RT Steam** in its bottom row.
- **RB Remove game** on a game shows what would go, on a page of its own (see
  [Deciding what to keep](#deciding-what-to-keep)): a disc game's folder in `Games\PS3` and its update in RPCS3's
  folder as rows of their own, or a game installed from a package in RPCS3's folder, and its Steam shortcut (taken
  out with Steam closed for it; it starts again signed in). Your saves and the licenses are never on the page. The
  app offers no game whose folder is one of the app's `Games\PS3` folders itself, a drive, a folder holding another
  game, or a disc game outside the app's folders that RPCS3 knows from before: the status line says to delete it by
  hand. It does not work while RPCS3 runs.
- A package or a license that waits is a row of its own, **PKG**, **PKG update** or **License**: **A Install** and
  **X Install all**, see [Packages](#packages).

In a game started from Steam, RPCS3 takes the device's controller as player 1: A is Cross, B Circle, X Square, Y
Triangle, View Select, Menu Start, LB and RB are L1 and R1, the triggers L2 and R2.

To quit a game, **hold View, LB and RB together for two seconds**: RPCS3 closes as its window would close, and you are
back in Steam, or in the app when it started the game. *Closing the game* at the top of the screen says the hold
was seen. It works the same in every game manager of the suite, started
from Steam's library or from the app. The line at the bottom of Your games says so when a game starts. A short press
of View and Menu opens RPCS3's own menu over the game, with **Exit Game** in it; the guide button opens it too, where
Windows leaves that button to the game (on the ROG XBOX Ally the XBOX button is Windows' own).

**When the device runs hot**, you are warned without the game stopping. While a game runs, the app reads the chip's
temperature every two seconds. When the CPU or the GPU stays above 90 °C for half a minute, a banner shows at the top of
the screen for a few seconds (on every screen, with a second one attached), and the controller rumbles three times; it
warns again at most every five minutes while the chip stays that hot. The banner takes no press and does not take the
focus from the game. A pause, or a lower performance mode (the portal's Performance Mode page), lets the device cool down.
When the game ends, the log (**A View log** on the Log pane) says how hot the chip got and for how long. Windows cannot
read how hot the outside of the device is: the chip's temperature is the closest reading, and the chip slows itself down
at its own limit.

The pictures in Steam come from inside the game: its icon (`ICON0.PNG`) on the cover, the wide picture and as the logo,
its background (`PIC1.PNG`) on the banner; without them the title is drawn on a dark background. With a SteamGridDB
API key, Update Steam also takes a cover for each game from SteamGridDB: **LB Steam artwork** opens the page that
keeps the key (**X Paste**, **R3 ⌨**, **A Save**, **Y Remove key** twice, **B** back without saving). See
[Steam artwork from SteamGridDB](covers.md).

## Deciding what to keep

The app deletes nothing before you decide what to keep. **RB Remove game**, and the end of a package install, show a
page of what would go, a row each with its size, every row marked **Delete** at first:

- **A** on a row turns it to **Keep**, and back to **Delete**.
- **X Delete marked** deletes the rows still marked **Delete**, then goes back to Your games; the status line says
  what was deleted and what was kept. With nothing marked, it says so and deletes nothing.
- **B** goes back and deletes nothing.

## Settings

The Settings card's pane has four tabs, **Picture**, **Speed**, **Sound** and **Messages**: **LB** and **RB** step
through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and saves it
at once into RPCS3's settings (`config\config.yml` in its folder; the row at the bottom says **A Change**, **LB
Previous tab**, **RB Next tab**). RPCS3 reads them when a game starts; while RPCS3 is open, the pane asks you to close
it first, since RPCS3 writes its own settings back when it closes. A game's own settings in RPCS3, where a game has
them, come before these. The **information icon** at the pane's top right says what each setting of the tab
does.

**Picture**

| Setting | Values |
|---|---|
| Renderer | Vulkan (RPCS3's choice, the device's graphics), OpenGL: slower, for when Vulkan fails |
| Resolution scale | Native (720p), 150% (1080p, the device's screen), 200% (1440p), 300% (2160p, a 4K TV); higher asks more of the graphics chip and the battery, and breaks some games |
| Anisotropic filtering | As the game, 2x, 4x, 8x, 16x: sharper textures seen at an angle |
| Anti-aliasing (MSAA) | As the game, Off: smooth edges as the game asks, or none, faster |
| Output scaling | Bilinear (smooth), Nearest (sharp pixels), FidelityFX Super Resolution (AMD's upscaler, sharper from a lower resolution scale) |
| Screen | 16:9 (the PS3's picture for a wide screen, RPCS3's default), 4:3 (with borders on a wide screen, for a game made for it), Fill screen (the picture stretched to fill the screen) |

**Speed**

| Setting | Values |
|---|---|
| VSync | Off, On, Adaptive: no tearing, a little more delay; Adaptive waits only while the game keeps up |
| Frame limit | Automatic, Off, 30, 50, 60, 120, The screen's rate, As the PS3, No limit |
| PPU decoder | Recompiler (LLVM), Interpreter: how the PS3's main processor is run, fast or exact and slow |
| SPU decoder | Recompiler (LLVM), Recompiler (ASMJIT), Interpreter (dynamic), Interpreter (static): how the PS3's SPU cores are run |

**Sound**

| Setting | Values |
|---|---|
| Sound output | Cubeb (RPCS3's choice on Windows), XAudio2 (Windows' own), FAudio, No sound |
| Volume | 100%, 75%, 50%, 25%, Muted, 150%, 200%: RPCS3's own volume, before Windows' |
| Buffering | On or Off: sound kept a little ahead so it does not crackle; off, less delay |

**Messages**

| Setting | Values |
|---|---|
| Trophy messages | On or Off: a message in the game when a trophy is won |
| Shader compilation message | On or Off: a message while RPCS3 compiles shaders, the first time a game shows something new |

The values show once RPCS3 is installed; until RPCS3 has written its settings, they are its own defaults. A value
in RPCS3's settings that the app does not offer is shown as it is, and **A** goes on from the first value.

## Log

RPCS3's folder, with the firmware's version, how many games are installed in it and how many saves it keeps, where
your `Games\PS3` folder is, and the newest lines of this app's log (the installs, what RPCS3's log said of the firmware and each package, the Steam
changes, the settings changed). **A View log**, or a tap on the pane, shows the whole log in the pane: the d-pad
scrolls it, and **B** goes back. The newest lines show at the bottom of a box of their own, which a finger can scroll; a tap on it shows the whole log too.

## How it works

A game's shortcut in Steam starts the app itself in its play mode, `RPCS3-Manager.exe --play --no-gui --fullscreen
"<game>\PS3_GAME\USRDIR\EBOOT.BIN"`, which shows no window: it starts `rpcs3.exe --no-gui --fullscreen
"<game>\PS3_GAME\USRDIR\EBOOT.BIN"` in RPCS3's folder, watches the controller for View, LB and RB held, and ends when
RPCS3 ends, so Steam sees the game end. With `--no-gui` RPCS3 boots the game without its own window and ends when the
game ends; `--fullscreen` (which RPCS3 takes only with it) gives the game the whole screen. Asked to close, RPCS3 gets
ten seconds before it is ended. On a device without Steam the app starts a game the same way. A shortcut made by an
earlier version, which starts `rpcs3.exe` itself, shows **(Update Steam)** on its game: **Y Update Steam** writes it
again.

The firmware and the packages go to RPCS3 as `rpcs3.exe --headless --installfw "<PS3UPDAT.PUP>"` and `rpcs3.exe
--headless --installpkg "<file>"`, one run per file, without any window; RPCS3 writes what it did to its log
(`log\RPCS3.log` in its folder), which the app reads for the result, as RPCS3's exit code says nothing of it.

Every Monday the suite checks whether RPCS3 has a newer version number than the one this app brings, and whether the
build it downloads is still the one it was tested with; what moved goes to the suite's developers, and a newer RPCS3
comes in a new version of the app.

### Controller

RPCS3 only reads a controller that its pad settings name; until they name one, it plays with the keyboard. So the app
writes them (`config\input_configs\global\Default.yml` in RPCS3's folder): player 1 on the first XInput pad, the
device's own controller, through RPCS3's XInput handler with RPCS3's own button layout for it, in which the PS button
is the guide button, or View and Menu together. The file starts with a line that says the app wrote it; once you save
RPCS3's own **Pads** settings in its window, that file is RPCS3's and the app leaves it alone. A second XInput
controller is not set up by the app.

## Install it on its own

The portal installs it. To install it on its own, download `wp-rpcs3-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-rpcs3-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-rpcs3-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-rpcs3-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and RPCS3 with its firmware, saves and installed games stay |
| `--uninstall --purge` | also remove the settings, the log and RPCS3's folder, with the firmware, the saves, its settings and the installed games in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\app\` | The program, `RPCS3-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\emulator\` | RPCS3 (`rpcs3.exe`) and everything it keeps: `config\` (its settings, the controller), `dev_hdd0\` (the installed games, the saves), `dev_flash\` (the firmware), `GuiConfigs\` (its window's settings, the play time), `log\RPCS3.log` (its own log), and `installed.json` (the build and the files the app installed) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\covers\` | The covers from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rpcs3\windows-portable-rpcs3.log` | The log |
| `%USERPROFILE%\Games\PS3\` | Your games, packages and licenses; `Firmware\` in it, the firmware you put there |
| `%APPDATA%\windows-portable-suite\windows-portable-rpcs3.ini` | The settings, with the firmware file last given to RPCS3 |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |

RPCS3 can keep its drives elsewhere (its **Virtual File System** settings, in its own window); the app reads where
they are.
