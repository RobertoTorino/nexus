<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PCSX2 Manager](../images/apps/pcsx2.webp){ .app-logo }

# PCSX2 Manager

Gets your PS2 games ready to play from Steam with PCSX2, the PlayStation 2 emulator, and takes care of everything
around it: it installs one tested release of PCSX2 for your own user, sets it up, takes your BIOS, finds your games
in the folders you choose, puts them in Steam, shows your memory cards and keeps a log of what was played. You play
from Steam, and never need PCSX2's own window: a game starts alone and full screen, and when it ends you are back in
Steam.

PCSX2 Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **PCSX2 Manager**). It opens full
screen; **⧉** (View) exits it.

## What you need

- **The PS2's BIOS, from your own console.** PCSX2 cannot start a game without it, and it is not the app's to give.
  Dump it from your PlayStation 2 with biosdrain, a homebrew tool, as
  [PCSX2's BIOS page](https://pcsx2.net/docs/setup/bios) says, and copy the dump (a `.bin` of 4 MB, often with
  `.nvm` and `.mec` files beside it) to the device, for instance into Downloads. **X Choose BIOS** on the PCSX2
  card takes it from there.
- **Your PS2 games** as disc images (ISO, CHD, CSO, ZSO or GZ), dumped from your own discs, in a folder on the device
  or an SD card.
- **Steam**, started once on the device, to play the games from Steam (optional).

## The screen

Five cards on the left, **PCSX2**, **Your games**, **Settings**, **Memory cards** and **Log**; the right side shows
what the focused card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the
row at the bottom with what it does on the pane that shows: **A** included (**A Install**, **A Steam mark**, **A View
log**). Press the button, or tap the entry. **B** goes back: from a list or a page to where you came from, from a pane
to its card on the left (on a card it does nothing). Once you are in a pane, the d-pad stays in it: at the top or
bottom of a list the focus stops, and only **B** takes you back to the cards. **⧉** (View) exits the app. **☰** (Menu)
opens the information of the pane that shows, and closes it again; the **information icon** at a pane's top right does
the same by touch.

The amber edge shows where you are. On a card it comes with a glow under it; once the focus moves into the pane at
the right, the pane takes the edge and the glow, and its card keeps only the edge. In a list the row with the focus
is lighter, with the amber edge. Nothing is ever grayed out: when a button cannot do its job now, pressing it says why
on the pane's status line. Every card, row and entry also works by touch, and a long list scrolls with the d-pad or a
finger.

## PCSX2

The pane shows the PCSX2 that is installed, the one this version of the app installs, the BIOS and the folder.
PCSX2's own window is never opened: your games are on the **Your games** card.

- **A Install** (also **A** on the PCSX2 card) downloads PCSX2 2.8.2 for Windows from PCSX2's own release on GitHub
  (26 MB), checks it against the checksum this version of the app was tested with, and unpacks it. The page counts
  the megabytes while it downloads. Nothing is downloaded before you press A.
- **RB Remove PCSX2** removes PCSX2's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. Your BIOS, memory cards, save states and settings stay in the folder, so a new install
  finds them again.
- **Y Reinstall** or **Y Update** shows when PCSX2 replaced its program with another build, or an older PCSX2 is
  installed: it puts the tested release in, and what you made stays.

**⧉** during the download asks first: a second **⧉** within five seconds exits the app and stops the download.

PCSX2 runs in **portable mode** (an empty `portable.txt` beside `pcsx2-qt.exe`): it keeps its settings, the BIOS, the
memory cards and the save states in its own folder, not in Documents.

The **BIOS** row says which dump PCSX2 uses, or **No BIOS yet** (the PCSX2 card says so too):

- **X Choose BIOS** opens the app's own browser, made for the controller, in your Downloads: it shows the folders and
  the BIOS dumps (`.bin`, `.rom`). **A** opens a folder, **B** goes a level up, and **A** on the dump chooses it: the
  app copies it, with the files beside it under the same name (`.nvm`, `.mec`, `.erom`), into PCSX2's `bios` folder
  and makes PCSX2 use it. The next time the browser opens in the folder you took the dump from.
- **LB Remove BIOS** takes the dump PCSX2 uses out of that folder again, with its files. Press it twice: the first
  press only asks, for five seconds. The dump you chose it from stays where it is; with another dump in the folder,
  PCSX2 uses that one.

Both work once PCSX2 is installed and not while it runs (it writes its settings back when it closes); pressed then,
they say why. Without a BIOS no game starts from Steam: PCSX2 would stop at its own error window, so Update Steam asks
for one first. The information says where a BIOS comes from.

A newer PCSX2 never reaches the device by itself: a new release of PCSX2 may change how games run, so it comes only
with a new version of PCSX2 Manager, tried first, which the portal offers as an update. Then **Y Update** puts it in.

## Your games

The games are the PS2 disc images in your game folders and up to five folders below them: ISO, CHD, CSO, ZSO and GZ.
An ISO is read for its serial (SLUS-21553), and the title comes from PCSX2's own list of games; a compressed image
is listed under its file's name. **A** on the Your games card goes to the list.

You play the games from Steam; the app puts them there, and starts them there with **X**.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[PS2] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer found, is taken out. Steam closes for it and starts again in the background.
  Steam must have been started once on the device. When there is nothing to change, **Y** says so on the status line
  instead. Right after writing, the app reads Steam's file back and counts the games in Steam from that; should a game
  it wrote not be found, the status line and the log say which.
- **X Play** on a game that is in Steam starts it through Steam, as its tile in Steam's library would; Steam
  starts first when it is not open. A game that is not in Steam yet says so: mark it with **A**, then
  **Y Update Steam**.
- **Open Steam**, the row above the games, opens Steam's library in Big Picture mode with **A**.
- **LB Folders** shows your game folders instead of the games; **LB** or **B** goes back to the games. The usual
  places that are on the device (Games, Downloads and Documents in your user folder) and each removable drive, such as
  an SD card, are offered as **+ Add**. **A** twice on a folder takes it off the list: the first press asks, for five
  seconds. Its games stay where they are.
- **+ Browse to a folder…** opens the app's own browser, made for the controller: your Games, Downloads, Documents and
  Desktop folders and every drive first. **A** opens the folder the focus is on, **B** goes a level up (and from the
  places back to your folders), and **X Add this folder** adds the folder that is open. The browser opens again in
  the folder you added last, while it is there.

In a game started from Steam, View and Menu held together end the game (see Settings), and PCSX2 closes by itself.

The pictures in Steam are drawn from the app's icon with the game's title. With a SteamGridDB API key, Update Steam
takes each game's pictures from SteamGridDB instead: **RB Steam artwork** opens the page that keeps the key (**X
Paste**, **A Save**, **Y Remove key** twice, **B** back without saving). See
[Steam artwork from SteamGridDB](covers.md).

## Settings

PCSX2 opens ready to play: right after the install, and each time before it opens, the app sets in PCSX2's settings
(`inis\PCSX2.ini` in its folder):

- its first-start setup skipped (it would ask for what the app already did);
- its own updates off (they would replace the tested release);
- the mouse pointer hidden over a game;
- the BIOS: the dump in its `bios` folder, unless the settings already name one that is there;
- player 1 on the device's controller (PCSX2 maps only the keyboard by itself), the buttons by their place: A is
  Cross, B Circle, X Square, Y Triangle, View Select and Menu Start. A controller mapping already in PCSX2's
  settings stays;
- View and Menu (☰) held together end a game, without a question (the PS2's Select and Start);
- PCSX2's Big Picture mode off: it is PCSX2's own menu, and the app starts every game without it.

The quit chord stays as you set it below: turned off, the app does not turn it on again. Everything else in the file
stays as PCSX2 wrote it. Without a settings file the app starts from PCSX2's own defaults, as PCSX2 2.8.2 writes them
at its first start.

The Settings card's pane has four tabs, **Picture**, **Game**, **Controller** and **On screen**: **LB** and **RB**
step through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and
saves it at once (the row at the bottom says **A Change**, **LB Previous tab**, **RB Next tab**). PCSX2 reads it the
next time it opens; while PCSX2 is open, the pane asks you to close it first, since PCSX2 writes its own settings back
when it closes. The **information icon** at the pane's top right says what each setting of the tab does.

**Picture**

| Setting | Values |
|---|---|
| Renderer | Automatic (PCSX2 chooses), Direct3D 12, Direct3D 11, Vulkan, OpenGL, Software (on the CPU: exact but slow) |
| Resolution | Native (the PS2's), 2x (720p), 3x (1080p, the device's screen), 4x (1440p), 5x (1800p), 6x (2160p, a 4K TV), 8x (2880p); higher asks more of the graphics chip and the battery |
| Aspect ratio | Auto (the game's own shape, black at the sides), 4:3, 16:9 (fills the screen), Stretch to the screen |
| Video aspect ratio | As the game, Auto, 4:3, 16:9: the shape of a game's videos when they are not the game's own |
| Widescreen patches | On or Off: 16:9 in the games PCSX2 has a patch for, with Aspect ratio on 16:9 |
| Anisotropic filtering | Off, 2x, 4x, 8x, 16x: sharper textures seen at an angle |
| VSync | On or Off: no tearing, a little more delay |

**Game**

| Setting | Values |
|---|---|
| Fast boot | On or Off: skips the PS2's start-up screen |
| No-interlacing patches | On or Off: a steadier picture in the games PCSX2 has a patch for |
| Cheats | On or Off: the cheats in PCSX2's `cheats` folder, for the games they are made for |
| Save state when quitting | On or Off: a save state when a game ends, to load from PCSX2's pause menu next time |
| Volume | 100%, 75%, 50%, 25%, Muted: PCSX2's own volume, before Windows' |

**Controller**

| Setting | Values |
|---|---|
| Vibration | On or Off: the controller's rumble |
| Stick dead zone | Off, Small, Medium, Large: how far a stick moves before the game sees it, for a stick that drifts |
| Stick range | PCSX2's (1.33), As the stick (1.00), Wider (1.66): how the stick's travel maps onto the PS2's |
| Player 2 | On or Off: a second controller is player 2, with the same buttons |
| Quit with View + Menu | On or Off: View and Menu (☰) held together end the game |

**On screen**

| Setting | Values |
|---|---|
| Show FPS | On or Off: the frames a second in a corner |
| Show speed | On or Off: the game's speed in percent |
| Show resolution | On or Off: the picture's size in pixels |
| Show CPU and GPU use | On or Off: how busy the processor and the graphics chip are |
| Show frame times | On or Off: a graph of how long each frame took |
| Show inputs | On or Off: the controller's buttons as they are pressed |
| Text size | Normal, Larger, Largest: the size of PCSX2's text on the screen |

The values show once PCSX2 is installed. A value in PCSX2's settings that the app does not offer is shown as it is,
and **A** goes on from the first value.

## Memory cards

The PS2 memory cards in PCSX2's `memcards` folder, each with the slot PCSX2 puts it in, how many saves it holds and
its free space. **A Saves** on a card lists its saves (their titles, sizes and dates); **B** (or **A** on **‹ The
cards**) goes back.

- **X New card** makes an empty 8 MB card, the size of the PS2's own, named `Mcd001.ps2` or the next free number.
- **Y Copy card** copies the card the focus was on last, with its saves, under a new name (`Mcd001 copy.ps2`).

A card is not copied while PCSX2 runs: it keeps the card in memory and writes it back. Folder memory cards and PS1
cards are listed with the reason they are not read.

## Log

PCSX2's last run as its own log tells it: when, which game, how long it was played and which controllers PCSX2
opened; the play time PCSX2 counted in all; and the newest lines of this app's log (Steam's changes, the installs,
the settings changed). **A View log**, or a tap on the pane, shows the whole log in the pane: the d-pad scrolls it,
and **B** goes back.

## How it works

A game starts from Steam as `pcsx2-qt.exe -nogui -fullscreen -batch -- "<game>"`: `-nogui` keeps PCSX2's own window
away, `-fullscreen` gives the game the whole screen, and `-batch` closes PCSX2 when the game ends, so you are back in
Steam. The app itself never starts a game. Everything PCSX2's window would be used for is in the app: the BIOS, the
settings, the controllers and the memory cards. Its setup wizard and its own updates stay off.

Every Monday the suite checks whether PCSX2 has a newer release than the one this app brings, and whether the file it
downloads is still the one it was tested with; what moved goes to the suite's developers, and a newer PCSX2 comes in
a new version of the app.

## Install it on its own

The portal installs it. To install it on its own, download `wp-pcsx2-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-pcsx2-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-pcsx2-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-pcsx2-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and PCSX2 with your BIOS and memory cards stay |
| `--uninstall --purge` | also remove the settings, the log and PCSX2's folder, with the BIOS, the memory cards and the save states in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\app\` | The program, `PCSX2-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\emulator\` | PCSX2 (`pcsx2-qt.exe`), its settings, BIOS, memory cards and save states, and `installed.json` (the version and the files the app installed) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\covers\` | The pictures from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\windows-portable-pcsx2.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-pcsx2.ini` | The settings, with your game folders |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |
