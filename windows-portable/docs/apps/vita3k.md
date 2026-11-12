<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Vita3K Manager](../images/apps/vita3k.webp){ .app-logo }

# Vita3K Manager

Gets your PS Vita games ready to play from Steam with [Vita3K](https://vita3k.org), the PS Vita emulator, and takes
care of everything around it: it installs one tested build of Vita3K for your own user, has Vita3K install the PS
Vita's firmware and your games, offers Vita3K's settings, puts the games in Steam, and keeps a log. You play from
Steam, and never need Vita3K's own window: a game starts full screen.

Vita3K Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it is
installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Vita3K Manager**). It opens
full screen; **B** goes back and **⧉** (View) exits it.

Whether a game runs, and how well, is up to Vita3K. Its [compatibility list](https://vita3k.org/compatibility.html)
shows what others found.

## What you need

- **Your PS Vita games**, dumped from your own PS Vita: a `.vpk` or `.zip`, a dumped game folder (with `sce_sys` and
  `eboot.bin`), or a `.pkg` with its license key (a zRIF, a long line that starts with `KO5i`). You put them in the
  app's own folder, `Games\Vita` in your user folder, or in `Games\Vita` on an SD card (see
  [Installing a game](#installing-a-game)). The app never downloads a game.
- **The PS Vita's firmware**. Vita3K needs it, and its font package, to start most games. The app cannot ship them;
  each is a file named `PSP2UPDAT.PUP`, which you download in a browser on the device and put in
  `Games\Vita\Firmware` in your user folder (see [The firmware](#the-firmware)):
    - the system software, from [PlayStation's page](https://www.playstation.com/en-us/support/hardware/psvita/system-software/);
    - the font package, [Sony's file](http://dus01.psp2.update.playstation.net/update/psp2/image/2019_0924/sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP?dest=us);
    - optional, the preinstalled apps, [Sony's file](http://dus01.psp2.update.playstation.net/update/psp2/image/2022_0209/pre_efd1ef6c1cc2fe92e72e9e783e421237/PSP2UPDAT.PUP?dest=us).

    All three have the same name: rename the font package (`PSP2UPDAT-fonts.PUP`), or put each in a folder of its
    own in `Firmware` (`Firmware\Fonts\PSP2UPDAT.PUP`).
- **Microsoft's Visual C++ runtime**, which Steam and most games install already. Vita3K for Windows does not start
  without it; the Vita3K pane says so when it is missing, and
  [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) from Microsoft installs it.
- **Windows 11**: Vita3K comes as a `.7z`, which the app unpacks with Windows' own `tar`; the `tar` of Windows 10
  cannot, and the pane says so.
- **Steam**, started once on the device, to play the games from Steam (optional: without Steam, **X Play** starts a
  game in Vita3K itself).

## The screen

Four cards on the left, **Vita3K**, **Your games**, **Settings** and **Log**; the right side shows what the focused
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

## Vita3K

The Vita3K card on the left says only whether Vita3K is installed and which button acts: **Not installed.** and
**Install with the A button.** until it is installed, then **Installed.** and **Remove with the X button.**

The pane shows the Vita3K build that is installed, the one this version of the app installs, which parts of the
firmware Vita3K has, how many games are installed in it and the folder. When Vita3K has published a newer build than
the one this app brings, a row says so. Vita3K's own window is never opened: the firmware and your games are given to
Vita3K from here.

- **A Install** (also **A** on the Vita3K card) downloads Vita3K build 4282 for Windows from Vita3K's builds on GitHub
  (25 MB), checks it against the checksum this version of the app was tested with, and unpacks it. The page counts the
  megabytes while it downloads. Nothing is downloaded before you press A.
- **X Remove Vita3K** removes Vita3K's program. Press it twice: the first press only changes the entry to **Press
  again** for five seconds. Vita3K's folder, with the firmware, your games, your saves and its settings, stays, so a
  new install finds them again. It does not work while Vita3K runs.
- **Y Update** shows when another Vita3K build is installed, and puts in the one this version of the app brings.

**⧉** during a download or an install asks first: a second **⧉** within five seconds exits the app. A download stops
then; Vita3K goes on with an install by itself.

### The firmware

Put the firmware files in `Games\Vita\Firmware` in your user folder: the app makes the folder when it opens. Nothing
is chosen or browsed to. When the app opens and each time the Vita3K card gets the focus, it gives each new file to
Vita3K, which installs it without opening its window; it takes a minute or two a file, the system software first.
The pane then says which part each was: the system software, the font package or the preinstalled apps. A file is
given once; it is given again only when you replace it with another. A file Vita3K could not use is not tried again
either: the pane says so once. The files stay in the folder. While the firmware or its font package is missing, the
status line names the folder.

Vita3K keeps its files in a folder named `portable` beside its program (its portable mode), in the app's `emulator`
folder: its settings (`config.yml`), its own log (`vita3k.log`, written anew each time it starts) and the PS Vita's
storage in `fs`: the firmware, the installed games (`ux0\app`), their updates and extra content, and the saves. After
the install, each time the app opens, before each install and before a game starts, the app sets four of Vita3K's
settings: games start full screen, its welcome window and its own update check are off, and so is its question
"Do you really want to exit?" (`confirmExitApp` in `portable\gui-configs\CurrentSettings.ini`), so View, LB and RB
held close the game at once. What it changed goes to the log.

A newer Vita3K never reaches the device by itself: Vita3K publishes a new build almost every day, which may change how
games run, so it comes only with a new version of Vita3K Manager, tried first, which the portal offers as an update.
Then **Y Update** puts in its program, and what you made stays.

## Installing a game

Vita3K plays only the games it has installed, in its own storage. Put yours in the app's own folder, `Games\Vita` in
your user folder (the app makes it), or in `Games\Vita` on an SD card or USB drive (make that folder there yourself),
also in a folder below it. Nothing is chosen or browsed to. Each game that is not installed yet is a short row of
**Your games**, its title, its ID and what it is: **VPK**, **ZIP**, **PKG** or **Folder** (a dumped game's own folder,
with `sce_sys\param.sfo` in it).

- **A Install** on a `.vpk`, `.zip` or folder gives it to Vita3K, which installs it. Vita3K then opens its window to
  start the game; the app closes it at once, so the window may show for a moment. A large game takes minutes.
- **X Install all** installs every `.vpk`, `.zip` and folder waiting, one after the other. A `.pkg` waits for its
  license key: the status line says so.
- **A** on a `.pkg` opens a page for its license key, with the touch keyboard: copy the zRIF in a browser on the device,
  then **X Paste** puts it in the field (**R3 ⌨** opens or closes Windows' touch keyboard to type it) and
  **A Install** has Vita3K install the package, without its window. **B**
  goes back to Your games without installing. The key is used for this install and kept nowhere.
- **RB Remove game** on a row that waits shows the [keep page](#deciding-what-to-keep) with its file, or the dumped
  game's folder: one that cannot be installed (a download cut short) stays a row until it is deleted or replaced.

Once a `.vpk`, `.zip` or `.pkg` is installed, Vita3K has the game in its storage, and the app asks what to do with
the file: a page lists the files the install took in (see [Deciding what to keep](#deciding-what-to-keep)). A file
you keep stays where you put it and is not listed to install again, until you replace it. A dumped folder is never
on the page: it stays where you put it, and is no longer listed once its game is installed.

An update or extra content installs the same way: Vita3K puts an update in `ux0\patch` and extra content in
`ux0\addcont`, and uses them when it starts the game. The status line names what came in, with the game's title and
ID; when nothing came in, it says so (a Vitamin dump, for one, is something Vita3K refuses).

## Your games

The games are the ones installed in Vita3K, each listed with its title, its ID (PCSB00245) and its version, from its
own `param.sfo`, then the games waiting in `Games\Vita` to be installed (see [Installing a game](#installing-a-game)).
**A** on the Your games card goes to the list.

You play the games from Steam; the app puts them there.

- **A Steam mark** on a game marks it for Steam, or takes the mark away. **Y Update Steam** then makes Steam match the
  marks: each marked game is a non-Steam game named `[PS Vita] <title>` in Steam's library and its Big Picture mode; a
  game without the mark, or no longer installed, is taken out. Steam closes for it and starts again in the
  background. Steam must have been started once on the device, and Vita3K must be installed with the firmware and its
  font package. When there is nothing to change, **Y** says so on the status line instead. Right after writing, the
  app reads Steam's file back and counts the games in Steam from that; should a game it wrote not be found, the status
  line and the log say which.
- **X Play** on a game that is in Steam starts it, through Steam: Steam starts first when it does not run, then
  Vita3K with the game, full screen, as from Steam's library. A game that is not in Steam yet says so: **A** marks
  it, **Y** puts it there. On a device without Steam (not installed, or never started), **X Play** starts the game in
  Vita3K itself, full screen, the same way Steam would.
- **RB Remove game** shows what of a game would go, on the page described below: the game in Vita3K's storage, its
  update and its extra content, each on a row of its own, and its shortcut in Steam when it is in Steam. Its saves
  are never on the page; they stay in Vita3K's storage. It does not work while Vita3K runs.
- **LT Refresh** reads the game folders again: a game or a package put there while the app is open shows at
  once.
- A game taken out of Vita3K's storage by hand keeps its shortcut in Steam until **Y Update Steam**; started,
  it shows a screen that says the game is no longer there, instead of starting Vita3K. **A** closes it.
- Steam's library opens from the portal: **RT Steam** in its bottom row.

The pictures in Steam come from inside the game: its icon (`sce_sys\icon0.png`) on the cover, the wide picture and as
the logo, its LiveArea picture (`sce_sys\pic0.png`) on the banner; without them the title is drawn on a dark
background. With a SteamGridDB API key, Update Steam also takes a cover for each game from SteamGridDB: **LB Steam
artwork** opens the page that keeps the key (**X Paste**, **R3 ⌨**, **A Save**, **Y Remove key** twice, **B** back without
saving). See [Steam artwork from SteamGridDB](covers.md).

### In a game

A game from Steam starts full screen, with only the game in sight: Vita3K always opens its library window beside the
game (with a second screen attached, on the device's own screen), and the app minimizes it as soon as the game's window
is up. The device's controller is the PS Vita's: A is Cross, B Circle, X Square, Y Triangle, Menu Start, View Select,
LB and RB are L and R.

To quit a game, **hold View, LB and RB together for two seconds**: Vita3K closes as its window would close, and you are
back in Steam, or in the app when it started the game. *Closing the game* at the top of the screen says the hold
was seen. It works the same in every game manager of the suite, started
from Steam's library or from the app. The line at the bottom of Your games says so when a game starts. **Steam's own
menu** (the Steam button, or the guide button where Windows does not take it) and its **Exit game** still end the game
too. Vita3K's own pause menu, on its PS button, has **Exit**, which ends the game but leaves Vita3K's window; holding
View, LB and RB closes that too.

**When the device runs hot**, you are warned without the game stopping. While a game runs, the app reads the chip's
temperature every two seconds. When the CPU or the GPU stays above 90 °C for half a minute, a banner shows at the top of
the screen for a few seconds (on every screen, with a second one attached), and the controller rumbles three times; it
warns again at most every five minutes while the chip stays that hot. The banner takes no press and does not take the
focus from the game. A pause, or a lower performance mode (the portal's Performance Mode page), lets the device cool down.
When the game ends, the log (**A View log** on the Log pane) says how hot the chip got and for how long. Windows cannot
read how hot the outside of the device is: the chip's temperature is the closest reading, and the chip slows itself down
at its own limit.

## Deciding what to keep

The app deletes nothing before you decide what to keep. After an install, and with **RB Remove game**, a page lists
what would be deleted, one row each with its size, and every row starts as **Delete**:

- **A** on a row turns it to **Keep**, and back to **Delete**.
- **X Delete marked** deletes the rows still marked **Delete** and keeps the others. Back on Your games, the status
  line says what was deleted and what was kept. With nothing marked, **X** says so and deletes nothing.
- **B** goes back and deletes nothing. After an install, the files then all stay where they are.

## Settings

The Settings card's pane has four tabs, **Screen**, **Speed**, **Sound** and **System**: **LB** and **RB** step
through them, or tap one. A tab is a row per setting with its value; **A** on one steps to the next value and saves it
at once into Vita3K's settings (`portable\config.yml` in its folder; the row at the bottom says **A Change**, **LB
Previous tab**, **RB Next tab**). They are settings of Vita3K's own settings window. Vita3K reads them when a game
starts; while Vita3K is open, the pane asks you to close it first. A game's own settings in Vita3K come before these.
The **information icon** at the pane's top right says what each setting of the tab does.

**Screen**

| Setting | Values |
|---|---|
| Renderer | Vulkan (Vita3K's choice), OpenGL |
| Resolution | Native (544p), 1.5x (816p), 2x (1088p), 3x (1632p): the PS Vita's 960 × 544 times this |
| Screen filter | Bilinear (Vita3K's choice), Nearest, Bicubic, FXAA, FidelityFX Super Resolution (with Vulkan only) |
| Anisotropic filtering | Off, 2x, 4x, 8x, 16x |
| Fill the screen | On or Off: stretched to the whole screen, or the PS Vita's shape with borders |
| VSync | On or Off |

**Speed**

| Setting | Values |
|---|---|
| High accuracy | On or Off: draws more exactly, slower (Vulkan only) |
| Compile shaders in the background | On or Off: fewer stutters, something may show a moment late |
| FPS hack | On or Off: may double a 30 FPS game to 60, but makes some games run twice as fast |
| Performance overlay | On or Off: the frames a second over the game |
| Shader compilation message | On or Off |

**Sound**

| Setting | Values |
|---|---|
| Volume | 100%, 75%, 50%, 25%, Muted |
| Sound output | SDL (Vita3K's choice), Cubeb |
| NGS sound | On or Off: the PS Vita's sound engine; off only for a game that hangs on it |

**System**

| Setting | Values |
|---|---|
| Confirm button | Cross (X), as on a PS Vita sold outside Japan, or Circle (O), as in Japan |
| Language | The PS Vita's language, in which a game that has it shows its text: 20 languages, English (United States) by default |

The values show once Vita3K is installed; until Vita3K has written its settings, they are its own defaults. A value in
Vita3K's settings that the app does not offer is shown as it is, and **A** goes on from the first value.

## Log

Vita3K's folder, which parts of the firmware it has, how many games are installed in it, where the app's `Games\Vita`
folder is, and the newest lines of this app's log (the installs, the firmware and the games given to Vita3K, the Steam changes and the settings changed).
**A View log**, or a tap on the pane, shows the whole log in the pane: the d-pad scrolls it, and **B** goes back.
The newest lines show at the bottom of a box of their own, which a finger can scroll; a tap on it shows the whole log too.

## How it works

A game's shortcut in Steam starts the app itself in its play mode, `Vita3K-Manager.exe --play -r <ID>`, which shows
no window: it starts `Vita3K.exe -r <ID>` in Vita3K's folder, the game's ID as Vita3K installed it, so Vita3K starts
that game at once, full screen; it minimizes Vita3K's library window once the game's window is up (again if Vita3K
shows it again), watches the controller for View, LB and RB held, and ends when Vita3K ends, so Steam
sees the game end. Asked to close, Vita3K gets ten seconds before it is ended. On a device without Steam the app starts
a game the same way. A shortcut made by an earlier version, which starts `Vita3K.exe` itself, shows **(Update Steam)**
on its game: **Y Update Steam** writes it again.

Vita3K installs the firmware as `Vita3K.exe --firmware <file>` and a package as `Vita3K.exe --pkg <file> --zrif <key>`:
it installs and quits, without a window. A `.vpk`, `.zip` or folder it installs only when started with the file, and
then it starts the game: the app starts it as `Vita3K.exe --frontend sdl <file>`, and closes it as soon as its window
opens. In every case the app reads what Vita3K installed from the files it wrote in its storage.

Every Monday the suite checks that the file Vita3K Manager downloads is still the one it was tested with; Vita3K's
newer builds, out almost every day, are not reported there, the Vita3K pane shows the newest.

## Install it on its own

The portal installs it. To install it on its own, download `wp-vita3k-v<x.y.z>.zip` and `SHA256SUMS` from its
release, then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-vita3k-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-vita3k-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-vita3k-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and Vita3K with the firmware, your games and saves stay |
| `--uninstall --purge` | also remove the settings, the log and Vita3K's folder, with the firmware, your games, your saves and its settings in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\app\` | The program, `Vita3K-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\emulator\` | Vita3K (`Vita3K.exe` and its files), `installed.json` (the build the app installed) and `portable\`, everything Vita3K keeps: `config.yml` (its settings), `vita3k.log` (its own log), `fs\` (the PS Vita's storage: the firmware, `ux0\app` the games, `ux0\patch` their updates, `ux0\addcont` extra content, the saves) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\covers\` | The covers from SteamGridDB, per game |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-vita3k\windows-portable-vita3k.log` | The log |
| `%USERPROFILE%\Games\Vita\` | Your games waiting to be installed (`.vpk`, `.zip`, `.pkg`, dumped folders), and `Firmware\` with the firmware files; `Games\Vita\` on an SD card holds games too |
| `%APPDATA%\windows-portable-suite\windows-portable-vita3k.ini` | The app's settings | (with the firmware files given to Vita3K and the installed files you kept)
| `%APPDATA%\windows-portable-suite\steamgriddb-key` | Your SteamGridDB API key, when you put one there |
| Steam's `userdata\<user>\config\shortcuts.vdf` and `grid\` | The games in Steam and their pictures |
