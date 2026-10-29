<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PPSSPP Manager](../images/apps/ppsspp.webp){ .app-logo }

# PPSSPP Manager

Gets your PSP games ready to play from Steam with PPSSPP, the PSP emulator, and takes care of everything around it:
it installs one tested release of PPSSPP for your own user, offers its settings, finds your games in the folders you
choose and on PPSSPP's memory stick, puts them in Steam, and keeps a log. You play from Steam, and never need PPSSPP's
own window: a game starts alone and full screen, and when you leave it you are back in Steam.

PPSSPP Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **PPSSPP Manager**). It opens full
screen; **⧉** (View) exits it.

## What you need

- **Your PSP games**, dumped from your own UMDs as disc images (ISO, CSO or CHD), or memory stick games (a folder with
  an `EBOOT.PBP`), in a folder on the device or an SD card. PPSSPP needs no BIOS.
- **Steam**, started once on the device, to play the games from Steam (optional).

## The screen

Four cards on the left, **PPSSPP**, **Your games**, **Settings** and **Log**; the right side shows what the focused
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

## PPSSPP

The pane shows the PPSSPP that is installed, the one this version of the app installs, and the folder. PPSSPP's own
window is never opened: your games are on the **Your games** card.

- **A Install** (also **A** on the PPSSPP card) downloads PPSSPP 1.20.4 for Windows from PPSSPP's own release on
  GitHub (20 MB), checks it against the checksum this version of the app was tested with, and unpacks it. The page
  counts the megabytes while it downloads. Nothing is downloaded before you press A.
- **X Remove PPSSPP** removes PPSSPP's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. PPSSPP's memory stick, with your saves, save states and settings, stays in the folder, so
  a new install finds them again. It does not work while PPSSPP runs.
- **Y Update** shows when an older PPSSPP is installed, and puts in the one this version of the app brings.

**⧉** during the download asks first: a second **⧉** within five seconds exits the app and stops the download.

PPSSPP runs in **portable mode**: without an `installed.txt` beside `PPSSPPWindows64.exe`, it keeps its memory stick
in the `memstick` folder beside it, with the PSP's own folders (`PSP\SAVEDATA` for the saves, `PSP\PPSSPP_STATE` for
the save states, `PSP\GAME` for memory stick games, `PSP\SYSTEM\ppsspp.ini` for its settings), not in Documents.

A newer PPSSPP never reaches the device by itself: a new release of PPSSPP may change how games run, so it comes only
with a new version of PPSSPP Manager, tried first, which the portal offers as an update. Then **Y Update** unpacks
it over the older one, and what you made stays.

## Your games

The games are the PSP disc images (ISO, CSO and CHD) and the memory stick games (a folder with an `EBOOT.PBP`) in your
game folders and up to five folders below them, and the games on PPSSPP's memory stick. An ISO, a CSO and a PBP are
read for the game's title and disc ID (ULUS10044); a CHD is listed under its file's name. A game's update on the
memory stick is no game of its own: PPSSPP lays it over the game. **A** on the Your games card goes to the list.

You play the games from Steam; the app puts them there.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[PSP] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer found, is taken out. Steam closes for it and starts again in the background.
  Steam must have been started once on the device. When there is nothing to change, **Y** says so on the status line
  instead. Right after writing, the app reads Steam's file back and counts the games in Steam from that; should a game
  it wrote not be found, the status line and the log say which.
- **LB Folders** shows your game folders instead of the games; **LB** or **B** goes back to the games. The usual
  places that are on the device (Games, Downloads and Documents in your user folder) and each removable drive, such as
  an SD card, are offered as **+ Add**. **A** twice on a folder takes it off the list: the first press asks, for five
  seconds. Its games stay where they are.
- **+ Browse to a folder…** opens the app's own browser, made for the controller: your Games, Downloads, Documents and
  Desktop folders and every drive first. **A** opens the folder the focus is on, **B** goes a level up (and from the
  places back to your folders), and **X Add this folder** adds the folder that is open.

In a game started from Steam, PPSSPP takes the device's controller as it is: A is Cross, B Circle, X Square, Y
Triangle, View Select, Menu Start, LB and RB the PSP's L and R, RT fast forward. **LT** (or the guide button) opens
PPSSPP's pause menu; its **Exit** ends the game and closes PPSSPP, and you are back in Steam.

The pictures in Steam come from inside the game: its icon on the cover, the wide picture and as the logo, its
background on the banner; a CHD gets its title on a dark background. With a SteamGridDB API key, Update Steam also
takes a cover for each game from SteamGridDB: **RB Steam artwork** opens the page that keeps the key (**X Paste**,
**A Save**, **Y Remove key** twice, **B** back without saving). See [Steam artwork from SteamGridDB](covers.md).

## Settings

Right after the install, and each time before PPSSPP opens, the app turns off PPSSPP's notice of a newer release in
its settings (`memstick\PSP\SYSTEM\ppsspp.ini` in its folder): a newer PPSSPP comes with the app. Everything else in
the file stays as PPSSPP wrote it.

The Settings card's pane has four tabs, **Picture**, **Game**, **Controller** and **On screen**: **LB** and **RB**
step through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and
saves it at once (the row at the bottom says **A Change**, **LB Previous tab**, **RB Next tab**). PPSSPP reads it the
next time it opens; while PPSSPP is open, the pane asks you to close it first, since PPSSPP writes its own settings
back when it closes. The **information icon** at the pane's top right says what each setting of the tab does.

**Picture**

| Setting | Values |
|---|---|
| Renderer | Vulkan (PPSSPP's choice on Windows), Direct3D 11, OpenGL: another one when a game shows faults |
| Resolution | Automatic (the screen's), 1x (480 × 272, the PSP's), 2x, 3x (1080p, the device's screen), 4x, 5x, 6x (a 4K TV), 8x; higher asks more of the graphics chip and the battery |
| Stretch to the screen | On or Off: the picture fills the whole screen; off, it keeps the PSP's shape |
| Integer scaling | On or Off: the picture a whole multiple of the PSP's, sharp pixels with black edges |
| Texture filtering | Automatic, Nearest (sharp pixels), Linear (smooth), Automatic, best quality |
| Anisotropic filtering | Off, 2x, 4x, 8x, 16x: sharper textures seen at an angle |
| VSync | On or Off: no tearing, a little more delay |

**Game**

| Setting | Values |
|---|---|
| Frame skipping | Off, 1, 2 or 3 frames: frames left out to keep a slow game at full speed |
| Cheats | On or Off: the cheats in PPSSPP's cheats folder, for the games they are made for |
| Volume | 100%, 75%, 50%, 25%, Muted: PPSSPP's own volume, before Windows' |

**Controller**

| Setting | Values |
|---|---|
| Stick dead zone | PPSSPP's (0.15), Off, Medium (0.25), Large (0.35): how far a stick moves before the game sees it, for a stick that drifts |
| Stick sensitivity | PPSSPP's (1.10), As the stick (1.00), Higher (1.30): how far the PSP's stick goes for the stick's travel |

**On screen**

| Setting | Values |
|---|---|
| Show FPS | On or Off: the frames a second in a corner |
| Show speed | On or Off: the game's speed in percent |
| Show battery | On or Off: the device's battery in percent |

The values show once PPSSPP is installed; until PPSSPP has written its settings, they are its own defaults. A value
in PPSSPP's settings that the app does not offer is shown as it is, and **A** goes on from the first value.

## Log

PPSSPP's memory stick, with how many saves and save states are on it, and the newest lines of this app's log (the
Steam changes, the installs, the settings changed). **A View log**, or a tap on the pane, shows the whole log in the
pane: the d-pad scrolls it, and **B** goes back.

## How it works

A game starts from Steam as `PPSSPPWindows64.exe --fullscreen --pause-menu-exit "<game>"`: with a game named, PPSSPP
goes straight to it without its own window, `--fullscreen` gives the game the whole screen, and `--pause-menu-exit`
makes the pause menu's **Exit** close PPSSPP, so you are back in Steam. The app itself never starts a game.

Every Monday the suite checks whether PPSSPP has a newer release than the one this app brings, and whether the file it
downloads is still the one it was tested with; what moved goes to the suite's developers, and a newer PPSSPP comes in
a new version of the app.

## Install it on its own

The portal installs it. To install it on its own, download `wp-ppsspp-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-ppsspp-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-ppsspp-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-ppsspp-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and PPSSPP with its memory stick stay |
| `--uninstall --purge` | also remove the settings, the log and PPSSPP's folder, with the saves and the save states on its memory stick |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\app\` | The program, `PPSSPP-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\emulator\` | PPSSPP (`PPSSPPWindows64.exe`), its memory stick (`memstick\`: settings, saves, save states, memory stick games), and `installed.json` (the version and the files the app installed) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\covers\` | The covers from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-ppsspp\windows-portable-ppsspp.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-ppsspp.ini` | The settings, with your game folders |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |
