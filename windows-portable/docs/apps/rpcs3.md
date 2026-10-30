<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![RPCS3 Manager](../images/apps/rpcs3.webp){ .app-logo }

# RPCS3 Manager

Gets your PS3 games ready to play from Steam with [RPCS3](https://rpcs3.net), the PS3 emulator, and takes care of
everything around it: it installs one tested build of RPCS3 for your own user, takes the PS3's firmware and your
packages, offers its settings, finds your games in the folders you choose and in RPCS3, puts them in Steam, and keeps
a log. You play from Steam, and never need RPCS3's own window: a game starts alone and full screen, and when you leave
it you are back in Steam.

RPCS3 Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it is
installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **RPCS3 Manager**). It opens full
screen; **⧉** (View) exits it.

Whether a game runs, and how well, is up to RPCS3. Its [compatibility list](https://rpcs3.net/compatibility) shows
what others found; a PS3 game asks a lot of a handheld.

## What you need

- **Your PS3 games**: disc games copied from your own discs (a folder per game, with `PS3_DISC.SFB` and the `PS3_GAME`
  folder), or games bought digitally as packages (`.pkg`, with the `.rap` license of a PSN game), on the device or an
  SD card. The app never downloads a game.
- **The PS3's firmware** (`PS3UPDAT.PUP`), the PS3's system software. RPCS3 needs it to start any game, and the app
  cannot ship it: download it from
  [PlayStation's firmware page](https://www.playstation.com/en-us/support/hardware/ps3/system-software/) in a browser
  on the device, into Downloads. **LB Firmware** finds it there.
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
your games (as RPCS3 counts it) and the folder. RPCS3's own window is never opened: your games are on the **Your
games** card, the firmware and the packages are installed from here.

- **A Install** (also **A** on the RPCS3 card) downloads RPCS3 0.0.43, build 20395, for Windows from RPCS3's own
  builds on GitHub (37 MB), checks it against the checksum this version of the app was tested with, and unpacks it.
  The page counts the megabytes while it downloads. Nothing is downloaded before you press A.
- **LB Firmware** opens the app's own browser, made for the controller, in your Downloads: it shows the folders and
  the firmware files (`.PUP`). **A** opens a folder, **B** goes a level up, and **A** on `PS3UPDAT.PUP` gives it to
  RPCS3, which installs it without opening its window; it takes a minute or two, and the Firmware row then shows its
  version (4.92). RPCS3's firmware page says which version is the newest; RPCS3 takes any it supports.
- **RB Packages** opens the browser for the folder with your packages: it shows the `.pkg` files and the `.rap` and
  `.edat` licenses. **X Install from this folder** has RPCS3 install the open folder's files, without opening its
  window: the licenses first, copied into RPCS3's own folder, then each package, a game's update last (an update
  needs its game installed first). RPCS3 starts once per file, and a large package takes minutes; the status line
  says what came. **A** on one file installs that file alone. To install some of the folder's files, **Y Mark** the
  ones you want (a ✓ shows before each; **Y Unmark** takes it away), then **X Install marked**: those are installed
  together, in the same order. The marks go when you open another folder. The files in the folder itself are taken,
  not those in its subfolders. A game's update is a package too: RPCS3 uses it when it starts the game, and Your games lists the
  game once.
- **X Remove RPCS3** removes RPCS3's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. RPCS3's folder, with the firmware, your saves, its settings and the installed games,
  stays, so a new install finds them again. It does not work while RPCS3 runs.
- **Y Update** shows when an older RPCS3 is installed, and puts in the one this version of the app brings.

**⧉** during a download or an install asks first: a second **⧉** within five seconds exits the app. A download stops
then; RPCS3 goes on installing a firmware or the package it is on by itself.

RPCS3 on Windows keeps everything beside its program, in the app's `emulator` folder: its settings in `config`
(`config.yml`, `games.yml`, the controller and the per-game settings), the PS3's drives `dev_hdd0` (the installed
games, the saves) and `dev_flash` (the firmware), its window's settings in `GuiConfigs` and its own log in
`log\RPCS3.log`. Before RPCS3's first start, and each time the app opens, the app sets up what RPCS3 would otherwise
ask for in its window: its welcome dialog, its question before a game's window closes (View and Menu held close it)
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

## Your games

The games are the **disc games** in your game folders and up to five folders below them, each in a folder of its own
as copied from the disc (`PS3_DISC.SFB` and the `PS3_GAME` folder; RPCS3 does not start one without its
`PS3_DISC.SFB`, and the list says **no PS3_DISC.SFB** then), the **games installed from packages** in RPCS3's
`dev_hdd0`, and the **disc games RPCS3 knows** from before, wherever they are. Each is listed with its title and ID
(BLUS30443, NPUB30001) from its own `PARAM.SFO`. **A** on the Your games card goes to the list.

```
PS3/
└── Demon's Souls/
    ├── PS3_DISC.SFB
    └── PS3_GAME/          PARAM.SFO, ICON0.PNG, USRDIR/EBOOT.BIN, ...
```

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
- Steam's library opens from the portal: **RT Steam** in its bottom row.
- **LB Folders** shows your game folders instead of the games; **LB** or **B** goes back to the games. The usual
  places that are on the device (Games, Downloads and Documents in your user folder) and each removable drive, such as
  an SD card, are offered as **+ Add**. **A** twice on a folder takes it off the list: the first press asks, for five
  seconds. Its games stay where they are.
- **+ Browse to a folder…** opens the app's own browser, made for the controller: your Games, Downloads, Documents and
  Desktop folders and every drive first. **A** opens the folder the focus is on, **B** goes a level up (and from the
  places back to your folders), and **X Add this folder** adds the folder that is open. Every browser of the app opens again in the folder you last took a folder or picked a file in, while it is there.

In a game started from Steam, RPCS3 takes the device's controller as player 1: A is Cross, B Circle, X Square, Y
Triangle, View Select, Menu Start, LB and RB are L1 and R1, the triggers L2 and R2.

To quit a game, **hold View and Menu together for two seconds**: RPCS3 closes as its window would close, and you are
back in Steam, or in the app when it started the game. It works the same in every game manager of the suite, started
from Steam's library or from the app. The line at the bottom of Your games says so when a game starts. A short press
of View and Menu opens RPCS3's own menu over the game, with **Exit Game** in it; the guide button opens it too, where
Windows leaves that button to the game (on the ROG Xbox Ally the Xbox button is Windows' own).

The pictures in Steam come from inside the game: its icon (`ICON0.PNG`) on the cover, the wide picture and as the logo,
its background (`PIC1.PNG`) on the banner; without them the title is drawn on a dark background. With a SteamGridDB
API key, Update Steam also takes a cover for each game from SteamGridDB: **RB Steam artwork** opens the page that
keeps the key (**X Paste**, **A Save**, **Y Remove key** twice, **B** back without saving). See
[Steam artwork from SteamGridDB](covers.md).

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

RPCS3's folder, with the firmware's version, how many games are installed in it and how many saves it keeps, and the
newest lines of this app's log (the installs, what RPCS3's log said of the firmware and each package, the Steam
changes, the settings changed). **A View log**, or a tap on the pane, shows the whole log in the pane: the d-pad
scrolls it, and **B** goes back. The newest lines show at the bottom of a box of their own, which a finger can scroll; a tap on it shows the whole log too.

## How it works

A game's shortcut in Steam starts the app itself in its play mode, `RPCS3-Manager.exe --play --no-gui --fullscreen
"<game>\PS3_GAME\USRDIR\EBOOT.BIN"`, which shows no window: it starts `rpcs3.exe --no-gui --fullscreen
"<game>\PS3_GAME\USRDIR\EBOOT.BIN"` in RPCS3's folder, watches the controller for View and Menu held, and ends when
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
| `%APPDATA%\windows-portable-suite\windows-portable-rpcs3.ini` | The settings, with your game folders |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |

RPCS3 can keep its drives elsewhere (its **Virtual File System** settings, in its own window); the app reads where
they are.
