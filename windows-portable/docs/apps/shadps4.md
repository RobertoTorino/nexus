<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![shadPS4 Manager](../images/apps/shadps4.webp){ .app-logo }

# shadPS4 Manager

Gets your PS4 games ready to play from Steam with [shadPS4](https://shadps4.net), the PS4 emulator, and takes care of
everything around it: it installs one tested release of shadPS4 for your own user, takes the system modules of your
PS4, unpacks your packages (`.pkg`) into game folders, offers shadPS4's settings and the shadNet account it signs in
with, finds your games in the folders you choose, puts them in Steam, and keeps a log. You play from Steam, and never
need shadPS4's own window: a game starts full screen, and when you quit it you are back in Steam.

shadPS4 Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it is
installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **shadPS4 Manager**). It opens
full screen; **B** goes back and **⧉** (View) exits it.

Whether a game runs, and how well, is up to shadPS4. Its
[compatibility list](https://github.com/shadps4-compatibility/shadps4-game-compatibility/issues) shows what others
found; a PS4 game asks a lot of a handheld.

## What you need

- **Your PS4 games**: games dumped from your own PS4, each in a folder of its own with `eboot.bin` (as the app unpacks
  them), or packages (`.pkg`: a game, its update or add-on content) that the app unpacks for you, on the device or an
  SD card. The app never downloads a game.
- **The PS4's system modules** (`.sprx` files), libraries of the PS4's own firmware, copied from your own PS4 into a
  folder on the device. Many games run without them; a game that needs a missing one does not start. The app cannot
  ship them. **LB Modules** copies them into shadPS4.
- **Microsoft's Visual C++ runtime**, which Steam and most games install already. shadPS4 for Windows does not start
  without it; the shadPS4 pane says so when it is missing, and
  [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) from Microsoft installs it.
- **Steam**, started once on the device, to play the games from Steam (optional).

## The screen

Five cards on the left, **shadPS4**, **Your games**, **Settings**, **shadNet** and **Log**; the right side shows what
the focused card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row
at the bottom with what it does on the pane that shows: **A** included (**A Install**, **A Steam mark**, **A View
log**). Press the button, or tap the entry. **B** goes back: from a list or a page to where you came from, from a pane
to its card on the left (on a card it does nothing). Once you are in a pane, the d-pad stays in it: at the top or
bottom of a list the focus stops, and only **B** takes you back to the cards. **⧉** (View) exits the app. **☰** (Menu)
opens the information of the pane that shows, and closes it again; the **information icon** at a pane's top right
does the same by touch.

The amber edge shows where you are, as in every app of the suite. Nothing is ever grayed out: when a button cannot do
its job now, pressing it says why on the pane's status line. Every card, row and entry also works by touch, and a long
list scrolls with the d-pad or a finger.

## shadPS4

The pane shows the shadPS4 that is installed, the one this version of the app installs, how many of the system modules
shadPS4 cannot do without are there, the time spent in your games (as shadPS4 counts it) and the folder. shadPS4's own
window is never opened: your games are on the **Your games** card, the modules and the packages are taken from here.

- **A Install** (also **A** on the shadPS4 card) downloads shadPS4 0.20.0 for Windows from shadPS4's release on GitHub
  (32 MB), checks it against the checksum this version of the app was tested with, and unpacks it. The page counts the
  megabytes while it downloads. Nothing is downloaded before you press A.
- **LB Modules** opens the app's own browser, made for the controller, in your Downloads: it shows the folders and the
  system modules (`.sprx`). **A** opens a folder, **B** goes a level up, and **X Copy from this folder** copies the open
  folder's modules into shadPS4's module folder (**A** on one module does the same for its folder). A module that is
  there already is replaced. The pane then says how many of the 24 that shadPS4 cannot do without are there.
- **RB Packages** opens the browser showing the packages (`.pkg`). **A** on one shows where it can go: your game
  folders first, then the usual places (Games, Downloads, Documents and each SD card), then the package's own folder.
  **A** on a place unpacks the package there, into a folder named by the game's ID (`CUSA00001`), in the layout
  shadPS4 loads; the status line counts the files, and a large game takes minutes. The place becomes a game folder, so
  the game shows on **Your games**. A game needs about as much room as its package. See [Packages](#packages).
- **X Remove shadPS4** removes shadPS4's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. shadPS4's folder, with your saves, its settings and the system modules, stays, so a new
  install finds them again. It does not work while shadPS4 runs.
- **Y Update** shows when another shadPS4 is installed, and puts in the one this version of the app brings.

**⧉** during a download or while a package is unpacked asks first: a second **⧉** within five seconds exits the app.
A download stops then; a package is left half unpacked, so remove its folder and unpack it again.

shadPS4 keeps its files in a folder named `user` beside its program (its portable mode), in the app's `emulator`
folder: its settings (`config.json`), its users and their shadNet accounts (`users.json`), the saves (`home`, per user),
the system modules (`sys_modules`), the controller's hotkeys (`input_config`), the time spent in each game
(`play_time.txt`) and its own log (`log\shad_log.txt`). After the install, and each time the app opens, the app adds
shadPS4's quit hotkeys (see [In a game](#in-a-game)); what it added goes to the log.

A newer shadPS4 never reaches the device by itself: a new release may change how games run, so it comes only with a
new version of shadPS4 Manager, tried first, which the portal offers as an update. Then **Y Update** puts in its
program, and what you made stays.

## Packages

A package (`.pkg`) is how the PS4 gets a game bought digitally, its update or its add-on content. **RB Packages** on the
shadPS4 pane unpacks one into a game folder, with the same extractor as the BC250 suite's shadPS4 Manager. The
package says what it is: the heading says **Unpack the game**, **the update** or **the add-on**.

- **A game** goes into a folder named by its ID, `CUSA00001`, in the place you choose.
- **An update** goes beside its game, into `CUSA00001-UPDATE`, which shadPS4 lays over the game when it starts; the
  game's folder stays as it was. So choose the place the game is in. When an update is there already, **A** asks for a
  second press to replace it: the new one is unpacked first, and the old one goes only when every file of the new one
  was written. An update without its game in that place goes into `CUSA00001`, as a game with its update in it.
- **A folder that is there already** is never written into: the status line says so, and you choose another place or
  remove that folder first.

```
PS4/
├── CUSA00001/            eboot.bin, sce_sys/ (param.sfo, icon0.png, pic1.png), ...
└── CUSA00001-UPDATE/     the update, laid over the game
```

When some files of a package could not be written, the status line says how many, and `extraction_errors.txt` in the
game's folder names them; the game may not start. `filelist.txt` there lists every file of the package.

## Your games

The games are the folders with an `eboot.bin` in your game folders and up to five folders below them, each listed with
its title and ID (CUSA00001) from its own `param.sfo`, and the time spent in it. An update or a mod beside a game (a
folder named like the game's with `-UPDATE`, `-patch` or `-mods`) is no game of its own: shadPS4 lays it over the
game. **A** on the Your games card goes to the list.

You play the games from Steam; the app puts them there.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[PS4] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer found, is taken out. Steam closes for it and starts again in the background.
  Steam must have been started once on the device, and shadPS4 must be installed. When there is nothing to change,
  **Y** says so on the status line instead. Right after writing, the app reads Steam's file back and counts the games
  in Steam from that; should a game it wrote not be found, the status line and the log say which.
- **LB Folders** shows your game folders instead of the games; **LB** or **B** goes back to the games. The usual
  places that are on the device (Games, Downloads and Documents in your user folder) and each removable drive, such as
  an SD card, are offered as **+ Add**. **A** twice on a folder takes it off the list: the first press asks, for five
  seconds. Its games stay where they are.
- **+ Browse to a folder…** opens the app's own browser, made for the controller: your Games, Downloads, Documents and
  Desktop folders and every drive first. **A** opens the folder the focus is on, **B** goes a level up (and from the
  places back to your folders), and **X Add this folder** adds the folder that is open.

The pictures in Steam come from inside the game: its icon (`sce_sys\icon0.png`) on the cover, the wide picture and as
the logo, its background (`sce_sys\pic1.png`) on the banner; without them the title is drawn on a dark background. With
a SteamGridDB API key, Update Steam also takes a cover for each game from SteamGridDB: **RB Steam artwork** opens the
page that keeps the key (**X Paste**, **A Save**, **Y Remove key** twice, **B** back without saving). See
[Steam artwork from SteamGridDB](covers.md).

### In a game

shadPS4 plays with the device's controller as the PS4's: A is Cross, B Circle, X Square, Y Triangle, Menu Options, LB
and RB are L1 and R1, the triggers L2 and R2, and View alone is the touchpad. **View and Menu together** open
shadPS4's quit window: **A** quits the game, and you are back in Steam; **B** goes back to the game. On a keyboard,
Ctrl+Shift+End does the same. The app adds these hotkeys to shadPS4's `input_config\global.ini`, since shadPS4 by itself
opens its quit window only from a keyboard; the file's other lines stay as they are.

## Settings

The Settings card's pane has four tabs, **Picture**, **Sound**, **Controller** and **In a game**: **LB** and **RB**
step through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and
saves it at once into shadPS4's settings (`user\config.json` in its folder; the row at the bottom says **A Change**,
**LB Previous tab**, **RB Next tab**). They are the settings shadPS4's own settings window offers for every game.
shadPS4 reads them when a game starts; while shadPS4 is open, the pane asks you to close it first, since shadPS4 writes
its own settings back when it ends. A game's own settings in shadPS4 come before these. The **information icon** at
the pane's top right says what each setting of the tab does.

**Picture**

| Setting | Values |
|---|---|
| VSync | Mailbox (no tearing, shadPS4's choice), On, Off: how a frame goes to the screen |
| FidelityFX upscaling (FSR) | On or Off: AMD's upscaler, sharper than plain scaling when the game draws at a lower resolution than the screen's |
| Sharpening (RCAS) | On or Off: FSR's sharpening, only with FidelityFX upscaling on |
| HDR | On or Off: for a game and a screen that support it |
| Frame rate counter | On or Off: the frames a second in a corner of the picture |

**Sound**

| Setting | Values |
|---|---|
| Sound output | SDL (shadPS4's choice), OpenAL |
| Volume | 100%, 75%, 50%, 25%, Muted, 150%, 200%, 300%, 500%: shadPS4's own volume, before Windows' |

**Controller**

| Setting | Values |
|---|---|
| Motion controls | On or Off: the controller's motion sensors, for a game that reads them (a DualShock 4 or DualSense; the device's own controller has none) |
| Hide the mouse pointer | Never, After a few seconds (shadPS4's choice), Always |

**In a game**

| Setting | Values |
|---|---|
| Language | The PS4's system language, in which a game that has it shows its text: 31 languages, English (United States) by default |
| Trophy messages | On or Off: a message in the game when a trophy is won |
| Splash screen | On or Off: the game's own splash picture while it starts |

The values show once shadPS4 is installed; until shadPS4 has written its settings, they are its own defaults. A value
in shadPS4's settings that the app does not offer is shown as it is, and **A** goes on from the first value.

## shadNet

shadNet is shadPS4's online service, for online trophies, friends and online play in the games it supports. shadPS4
signs in by itself when a game starts, with the account kept here for one of its four users; player 1 plays with the
device's controller. The line under the heading says who signs in where, and what the last game's sign-in did (from
shadPS4's own log).

Each row shows its value; **A** on it changes it, and each change is kept in shadPS4's own files at once
(`users.json` and `config.json` in its folder; before shadPS4's first start the app makes them, with shadPS4's own four
users). Not while shadPS4 runs.

| Row | **A** |
|---|---|
| Sign in when a game starts | On or Off; on only with a name and a password |
| Player | The next of shadPS4's four users, with its own account |
| shadNet name | Its page: 3 to 16 letters, digits, `-` or `_`; names are case-sensitive |
| Password | Its page; the row shows dots |
| Email | Its page: needed to create an account |
| Server | Its page: `host:port`; empty is shadPS4's own server, `srv.shadps4.net:31313` |
| Registration key | Its page: only when a server asks for one to create an account; kept nowhere |

A text row's page has the field alone, with the touch keyboard: **A Keep** keeps it and goes back to the row, **X
Paste** puts in what you copied in a browser on the device, **B** goes back without keeping it.

- **X Create account** creates the account on the server, with the name, the password and the email address (and the
  registration key, when you gave one).
- **Y Try sign-in** signs in as shadPS4 would, and out again: it tells whether the account works.

The password goes over the network as it is, as shadPS4 itself sends it: use one you use nowhere else.

## Log

shadPS4's folder, how many of the system modules it cannot do without are there, how many game folders you have, and
the newest lines of this app's log (the installs, the modules copied, the packages unpacked, the Steam changes, the
settings and the shadNet account changed). **A View log**, or a tap on the pane, shows the whole log in the pane: the
d-pad scrolls it, and **B** goes back.

## How it works

A game starts from Steam as `shadPS4.exe -f true -g "<game>\eboot.bin"`, in shadPS4's folder, so that shadPS4 finds
its `user` folder there: `-f true` gives the game the whole screen. shadPS4's own window (its Big Picture mode) is never
shown, and the app itself never starts a game.

Every Monday the suite checks whether shadPS4 has a newer release than the one this app brings, and whether the file
it downloads is still the one it was tested with; what moved goes to the suite's developers, and a newer shadPS4 comes
in a new version of the app.

## Install it on its own

The portal installs it. To install it on its own, download `wp-shadps4-v<x.y.z>.zip` and `SHA256SUMS` from its
release, then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-shadps4-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-shadps4-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-shadps4-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and shadPS4 with your saves and system modules stay |
| `--uninstall --purge` | also remove the settings, the log and shadPS4's folder, with your saves, its settings and the system modules in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\app\` | The program, `shadPS4-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\emulator\` | shadPS4 (`shadPS4.exe`), `installed.json` (the version the app installed) and `user\`, everything shadPS4 keeps: `config.json` (its settings), `users.json` (its users and their shadNet accounts), `home\` (the saves, per user), `sys_modules\` (the system modules), `input_config\` (the hotkeys), `play_time.txt` (the time spent in each game), `log\shad_log.txt` (its own log) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\covers\` | The covers from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-shadps4\windows-portable-shadps4.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-shadps4.ini` | The settings, with your game folders |
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |
