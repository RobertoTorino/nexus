<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Xenia Manager](../images/apps/xenia.webp){ .app-logo }

# Xenia Manager

Gets your Xbox 360 games ready to play from Steam with [Xenia](https://xenia.jp), the Xbox 360 emulator, in its Xenia
Canary builds, and takes care of everything around it: it installs one tested build of Xenia for your own user,
offers Xenia's settings, finds your games in the folders you choose, puts them in Steam, and keeps a log. You play
from Steam, and never need Xenia's own window: a game starts full screen.

Xenia Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it is
installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Xenia Manager**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

Whether a game runs, and how well, is up to Xenia. Its
[compatibility list](https://github.com/xenia-canary/game-compatibility/issues) shows what others found.

## What you need

- **Your Xbox 360 games**, from your own discs and console, on the device or an SD card: disc images (`.iso`), discs
  unpacked to a folder with a `default.xex`, Xenia's `.zar` archives, and Games on Demand and Arcade packages as the
  console keeps them (`<title ID>\00007000\…` or `<title ID>\000D0000\…`). The app never downloads a game.
- No BIOS or firmware: Xenia does not need the console's.
- **Microsoft's Visual C++ runtime**, which Steam and most games install already. Xenia for Windows does not start
  without it; the Xenia pane says so when it is missing, and
  [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) from Microsoft installs it.
- **Windows 11**: Xenia comes as a `.7z`, which the app unpacks with Windows' own `tar`; the `tar` of Windows 10
  cannot, and the pane says so.
- **Steam**, started once on the device, to play the games from Steam (optional).

## The screen

Four cards on the left, **Xenia**, **Your games**, **Settings** and **Log**; the right side shows what the focused card
does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row at the bottom
with what it does on the pane that shows: **A** included (**A Install**, **A Steam mark**, **A View log**). Press the
button, or tap the entry. **B** goes back: from a list or a page to where you came from, from a pane to its card on the
left (on a card it does nothing). Once you are in a pane, the d-pad stays in it: at the top or bottom of a list the
focus stops, and only **B** takes you back to the cards. **⧉** (View) exits the app. **☰** (Menu) opens the
information of the pane that shows, and closes it again; the **information icon** at a pane's top right does the same
by touch.

The amber edge shows where you are, as in every app of the suite. Nothing is ever grayed out: when a button cannot do
its job now, pressing it says why on the pane's status line. Every card, row and entry also works by touch, and a long
list scrolls with the d-pad or a finger.

## Xenia

The pane shows the Xenia build that is installed, the one this version of the app installs, how many games were found
and the folder. When Xenia Canary has published a newer build than the one this app brings, a row says so.

- **A Install** (also **A** on the Xenia card) downloads Xenia Canary build e6cd2e4 for Windows from Xenia Canary's
  release on GitHub (4 MB), checks it against the checksum this version of the app was tested with, and unpacks it.
  The page counts the megabytes while it downloads. Nothing is downloaded before you press A.
- **X Remove Xenia** removes Xenia's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. Xenia's own files, your saves and its settings, stay, so a new install finds them again.
  It does not work while Xenia runs.
- **Y Update** shows when another Xenia build is installed, and puts in the one this version of the app brings.

**⧉** during a download asks first: a second **⧉** within five seconds exits the app, and the download stops.

Xenia keeps its files beside its program, in the app's `emulator` folder (on Windows it is portable by itself): its
settings (`xenia-canary.config.toml`), what your games keep (`content`, with the saves), its caches and its own log
(`xenia_canary.log`, written anew each time it starts).

A newer Xenia never reaches the device by itself: Xenia Canary publishes a new build almost every day, which may
change how games run, so it comes only with a new version of Xenia Manager, tried first, which the portal offers as an
update. Then **Y Update** puts in its program, and what you made stays.

## Your games

The games are found in your game folders and up to six folders below them, each listed with its title, its title ID
where the app can read it (4D5307E6) and its kind:

| Kind | What it is |
|---|---|
| ISO | A disc image (`.iso`) that is an Xbox 360 disc; named after its file |
| XEX | An unpacked disc: the `default.xex` in its folder, named after the folder (its other `.xex` files are its modules); or a single `.xex` |
| ZAR | Xenia's ZArchive of a disc, named after its file |
| Games on Demand | A package in a `00007000` folder, with the name it carries |
| Arcade | An Xbox Live Arcade package in a `000D0000` folder, with the name it carries |

Other packages, such as saves, downloadable content and title updates, are not games. **A** on the Your games card goes
to the list.

You play the games from Steam; the app puts them there, and starts them there with **X**.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[X360] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer found, is taken out. Steam closes for it and starts again, its window open and signed in.
  Steam must have been started once on the device, and Xenia must be installed. When there is nothing to change, **Y**
  says so on the status line instead. Right after writing, the app reads Steam's file back and counts the games in
  Steam from that; should a game it wrote not be found, the status line and the log say which.
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

The app reads no pictures from a game, so the pictures in Steam are drawn from this app's icon, with the game's title.
With a SteamGridDB API key, Update Steam takes all four of a game's pictures from SteamGridDB instead: **RB Steam
artwork** opens the page that keeps the key (**X Paste**, **A Save**, **Y Remove key** twice, **B** back without
saving). See [Steam artwork from SteamGridDB](covers.md).

### In a game

A game from Steam starts full screen, with the device's controller as the Xbox 360's. **Steam's own menu** (the Steam
button, or the guide button) and its **Exit game** end the game and Xenia with it, as for any game: Xenia has no button
combination of its own that ends a game.

## Settings

The Settings card's pane has four tabs, **Picture**, **Speed**, **Sound** and **Console**: **LB** and **RB** step
through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and saves it
at once into Xenia's settings (`xenia-canary.config.toml` in its folder; the row at the bottom says **A Change**, **LB
Previous tab**, **RB Next tab**). Xenia reads them when a game starts; while Xenia is open, the pane asks you to close
it first, since Xenia writes its settings when it starts. A game's own settings in Xenia come before these. The
**information icon** at the pane's top right says what each setting of the tab does.

**Picture**

| Setting | Values |
|---|---|
| Graphics | Automatic (Direct3D 12, Xenia's choice), Direct3D 12, Vulkan |
| Resolution scale | Native (720p), 2x (1440p), 3x (2160p): higher asks much more of the graphics chip, and breaks some games |
| Anti-aliasing | Off, FXAA, FXAA extreme |
| Scaling and sharpening | Bilinear, Contrast Adaptive Sharpening, FidelityFX Super Resolution |
| Keep the picture's shape | On (bars where the screen's shape differs) or Off (stretched) |
| VSync | On or Off |

**Speed**

| Setting | Values |
|---|---|
| Frame limit | As the game (60 with VSync on), 30, 60 |
| Readback resolve | Off, Fast, Full: for a game that shows wrong or missing effects |

**Sound**

| Setting | Values |
|---|---|
| Sound output | Automatic (XAudio2, Xenia's choice), XAudio2, SDL |
| Mute | On or Off |

**Console**

| Setting | Values |
|---|---|
| Arcade license | None, Full version, All licenses: for an Xbox Live Arcade game whose package has the trial alone licensed |
| Achievement messages | On or Off |
| Guide button to the game | On or Off: whether the guide button reaches the game |

The values show once Xenia is installed; until Xenia has written its settings, they are its own defaults. A value in
Xenia's settings that the app does not offer is shown as it is, and **A** goes on from the first value.

## Log

Xenia's folder, how many game folders you have and how many games are in them, and the newest lines of this app's log
(the install, the folders, the Steam changes and the settings changed). **A View log**, or a tap on the pane, shows
the whole log in the pane: the d-pad scrolls it, and **B** goes back.

## How it works

A game starts from Steam as `xenia_canary.exe --fullscreen=true "<game>"`, as the BC250 suite's Xenia Manager starts
it; the value on the command line is not written into Xenia's settings. The app itself never starts a game.

Every Monday the suite checks that the file Xenia Manager downloads is still the one it was tested with; Xenia
Canary's newer builds, out almost every day, are not reported there, the Xenia pane shows the newest.

## Install it on its own

The portal installs it. To install it on its own, download `wp-xenia-v<x.y.z>.zip` and `SHA256SUMS` from its
release, then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-xenia-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-xenia-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-xenia-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and Xenia with your saves stay |
| `--uninstall --purge` | also remove the settings, the log and Xenia's folder, with your saves and its settings in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\app\` | The program, `Xenia-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\emulator\` | Xenia (`xenia_canary.exe`), `installed.json` (the build the app installed), and everything Xenia keeps beside it: `xenia-canary.config.toml` (its settings), `content\` (your games' content and the saves), its caches, `xenia_canary.log` (its own log) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\covers\` | The pictures from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-xenia\windows-portable-xenia.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-xenia.ini` | The settings, with your game folders |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |
