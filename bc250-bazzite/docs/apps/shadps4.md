<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![shadPS4 Manager](../assets/shadps4/bc250-shadps4-manager.webp){ .app-logo }

# shadPS4 Manager

Plays **PS4 games** on the **AMD BC-250** with [shadPS4](https://github.com/shadps4-emu/shadPS4), an open-source
PS4 emulator. The app installs the shadPS4 release it was tried with, finds the games in your game folders and adds
them to Steam, so a game starts straight away like any other, on the desktop or from Steam's **Big Picture Mode**.
It also unpacks package files (`.pkg`) into a game folder, with **Games Install** (Extract PKG).

Whether a game runs, and how well, is up to shadPS4. Its
[compatibility list](https://github.com/shadps4-emu/shadps4-game-compatibility/issues) shows what others found.

## What you need

- **Your games**, installed from your own PS4: each game in a folder of its own, with its `eboot.bin` and its
  `sce_sys` folder, or as a package file (`.pkg`) that **Extract PKG** unpacks into that layout. The app never
  downloads games.
- **System modules** for some games: libraries of the PS4's firmware (`.sprx` files), from your own console. Many
  games run without them. The app cannot ship them; it shows which ones are there.
- **Steam**, started at least once.
- About 35 MB for shadPS4 itself. Its saves, settings and shader cache go in `~/.local/share/shadPS4`.
- **FUSE 2** (`libfuse.so.2`), which Bazzite has. shadPS4 comes as an AppImage, which mounts itself with it.
  Without it, it unpacks itself to a temporary folder on every start, which takes longer.

## Using it

The header shows the **shadPS4 version**, **Your games** (the games found), those **Available in Steam** and the
**Play time**: the time spent in all your games together, as shadPS4 counts it, with each game's time and when it
was last played in the tooltip. **Refresh** reads everything again. Beside the title, next to the app's state,
stand shadNet's state (see [shadNet](#shadnet)) and the controller's: **Controller connected**, or **No
controller** when none is, looked at again every few seconds. A game started from Steam reads the controller that
is connected when it starts, so switch yours on, or press its PS button to wake it, before starting a game. When
Steam starts a game without one, the app also says so in a desktop notification. Under the introduction, which
links to **shadPS4's release notes** and to this wiki, a row of four pills does the setting up, each with what it is
for on top and what it does under it: **shadPS4 Install** and **shadPS4 Uninstall**, **Games Install** and
**shadNet Account**. Your games and the system modules go into the app's own folder (see [Where your games
go](#where-your-games-go)); nothing is chosen or browsed to for them. Four lines below the pills say where each
stands, short, with more in their tooltips, and then come three tabs: **Your games**, **Settings** and **Log**.

- **shadPS4**: **Not installed.** or **Installed.**, with the button to use under it; the version box in the header
  shows the version installed. When this version of the app brings another one, the tooltip and the log say so, and
  **Install** puts it in. **Install** downloads shadPS4 from its GitHub release (about 31 MB) and checks it against
  the checksum this version of the app was tried with before unpacking it. **Uninstall** takes it out again; shadPS4's
  own folder, with your saves, settings and system modules, stays.
- **Sys modules**: **Ok** in green when every module that shadPS4 cannot do without is in its module folder,
  **Missing sys modules** in red when one is not (how many there are, which are missing and the folder's path are in
  the tooltip). Many games run without them. Put the modules (`.sprx` files) you copied from your own PS4's
  firmware in `~/Games/PS4/Modules`: the app copies them into shadPS4's module folder by itself, when the window
  opens and on **Refresh**, only what is new or changed.
- **Game folders**: where the app looks for games, `~/Games/PS4` and a removable drive's `Games/PS4`, each game
  in a folder of its own (the paths and how many games were found are in the tooltip). The app makes them
  shadPS4's own game folders too, so shadPS4's window lists the games. A game may sit up to five folders deep.
  A package file (`.pkg`) put in one of them waits under **Your games** to be unpacked: see
  [Packages](#packages). **Install** opens [Extract PKG](#extract-pkg) for a package anywhere else.
- **shadNet**: the name of the account shadPS4 signs in with, **Off** while none is set up, **—** while shadPS4 has
  not run yet (the server is in the tooltip). **Account** sets it up: see [shadNet](#shadnet).

### Where your games go

The app has folders of its own, which it makes when it opens; you never choose or browse to a folder for them:

- `~/Games/PS4`: put your games there, each in a folder of its own (with its `eboot.bin`), and they show on **Your
  games**. On a USB drive or an SD card, make a folder `Games/PS4` on it, and the app looks there too while the
  drive is mounted (under `/run/media` or `/media`, as Bazzite mounts it). The app makes these shadPS4's own game
  folders as well, in its `config.json`, so shadPS4's window lists the games too.
- `~/Games/PS4/Modules`: put the system modules from your own PS4 there, and the app copies them into shadPS4.

Folders added in the app before (**Add folder**, until version 3.1) are no longer looked in: move those games to
`~/Games/PS4`.

### Your games

The table lists every game found: its title and **Id** (CUSA…) from the game's own files, its version and its
**Folder** (the folder's name; the path is in the tooltip). Updates and mods are not listed as games: see
[Game updates and mods](#game-updates-and-mods). A PS4 game draws its picture for a wide screen itself, so there is
no screen setting per game as in the PS2 and PS3 managers.

**Remove game…** deletes the chosen game from the disk. A window first lists what would go, a row each with its
size: the game's folder, and its update, patch and mods beside it, and its Steam shortcut when it is in Steam. Every row is ticked; untick what you want to keep, then
**Delete marked**; **Cancel** deletes nothing. The saves, the play time and the package stay. A game the app will not delete (one at the top of a
drive, or in a folder that holds another game) is said so under the tabs: delete it by hand.

#### Game updates and mods

Put a game's update in a folder of its own beside the game, named like the game's folder with `-UPDATE` added
(`-patch` works too). shadPS4 finds it there and uses it when it starts the game: the update's files take the place
of the game's, and the game's own folder stays as it is. Mods go the same way, in a folder ending in `-mods`.

```
shadps4_games/
├── CUSA11624/            the game: eboot.bin, sce_sys, ...
├── CUSA11624-UPDATE/     its update: its own eboot.bin, sce_sys and the files it changes
└── CUSA11624-mods/       mods for it
```

Nothing more is needed, and the table lists the game once. An update
found beside its game (the same ID, CUSA…) is left out of the table whatever its folder is called. A game copied
from a PS4 that had its update installed already has the update in it: it needs no `-UPDATE` folder and is listed
with the update's version.

#### Steam

Tick the games you want in Steam and press **Update Steam**. The app adds them to Steam as non-Steam games, with
the game's own icon and background as their pictures and its icon (`sce_sys/icon0.png`) as the logo on the
banner, and takes out the games you unticked and games it no longer finds. Steam keeps these files in memory, so it
closes for the change and starts again in the background. A game added before the app set the logo gets it the
next time you press **Update Steam**, which is on for it until then.

In Steam each game's name starts with its system, for example **[PS4] Lumines**, so it stands apart from the same
title on Steam or on another system in Steam's menus. A game added under its title alone is renamed the next time
you press **Update Steam**, which is on for it until then. Steam sees the renamed game as a new one: its play time
stays, but a controller layout or collection you set for it in Steam has to be set again.

The games are in the library under **Non-Steam**, on the desktop and in Big Picture Mode alike. They start
shadPS4 full screen. Steam's menu and **Exit game** work as for any game, and so does shadPS4's quit window (see
[Quit a game](#quit-a-game)).

Steam's overlay works over a game started from Steam, in Big Picture Mode and on the desktop: press **Shift+Tab**
or the **PS button** for the game's page, its controller layout and its settings, without leaving the game. In Big
Picture Mode the PS button opens Steam's menu over the game; pressed again there, it opens the power menu, with
**Exit game** and the way out of Big Picture Mode. On the desktop the overlay needs **Enable the Steam Overlay while
in-game** in Steam's settings (In Game).

On a handheld image of Bazzite, whose Game Mode is a Steam session of its own, change Steam from Desktop Mode: in
that session Steam cannot close for the change.

##### Covers

A PS4 game has no cover in the shape Steam's library uses, so the app draws one: the game's icon with its title on a
dark background. With a SteamGridDB API key, entered under **Steam artwork…**, the app takes a cover from
SteamGridDB for each game instead; the background and the logo on the game's page stay the game's own. See
[Covers from SteamGridDB](covers.md) for the key, how a game is looked up and how to use a cover of your own.

**Steam** in the line under the table is a link: it opens Steam's library (Steam starts when it does not run).
**shadPS4 settings** beside it opens shadPS4's own window (Big Picture) for what the app does not set: the
controller's buttons, a game's own settings and shadPS4's game list.

#### Quit a game

shadPS4's quit window asks whether to quit: **Cross** or **Enter** quits, **Circle** or **Esc** goes back to the game.
Open it with:

- **Share + Options** on a DualShock 4 or DualSense (Back + Start on other controllers: View + Menu on an XBOX
  controller), pressed together;
- **Ctrl+Shift+End** on the keyboard, also with the keypad's End (the 1 key with Num Lock off) on a keyboard without
  an End key of its own.

The app adds these to shadPS4's `input_config/global.ini` when it starts, and says so in the log; the rest of the
file stays as it is. The controller works on the desktop as well, where the keyboard may stay with Big Picture after
Steam started the game.

A game started from Steam reads your controllers itself, a DualShock 4 or DualSense with its touchpad and motion
sensors. [How it works](#how-it-works) explains both.

### Packages

A package (`.pkg`) is how the PS4 gets a game bought digitally, or its update. Put it in one of the game folders
(`~/Games/PS4`, or a drive's `Games/PS4`), anywhere up to five folders deep, and press **Refresh**: it is a row of its
own under the games, **PKG** for a game to unpack before it plays, **PKG update** for an update of a game you have.
Hover over the row to see where it goes.

- **Unpack all** unpacks every package that waits, one after the other: the games first, then the updates. **Unpack**
  unpacks only the chosen one. The line under the tabs says which one of how many and counts its files; a large game
  takes minutes.
- **A game** goes into a folder named by its ID, `CUSA00001`, beside its package.
- **An update** goes beside its game, wherever that is, into a folder named like the game's with `-UPDATE`, which
  shadPS4 lays over the game when it starts; the game's folder stays as it was. An update newer than the one there
  replaces it: the new one is unpacked first, and the old one goes only when every file of the new one was written.
  An update whose game is still a package waits for it: **Unpack** on it says so, and **Unpack all** unpacks both. An
  update without its game is unpacked as a game of its own. Add-on content is not listed: use Extract PKG for it.
- When the packages are unpacked, a window lists them, each with its size: a package takes as much room as its game
  and is not needed to play. Untick what you want to keep, then **Delete marked**; **Cancel** keeps them all. A
  package that was unpacked whole is no longer listed, kept or not; one with files that could not be written stays,
  with `extraction_errors.txt` naming them in its folder.

The same extractor works in the [Extract PKG](#extract-pkg) window, which also previews a package, salvages a damaged
one, compares two extractions and renames a package to its content ID.

### Settings

shadPS4's settings that matter for playing, each written into shadPS4's own settings file (`config.json`) the
moment you change it, while shadPS4 does not run (it writes its own settings back when it ends); shadPS4 reads them
when a game starts, and a game's own settings in shadPS4 (made in its own window) come before them. They are the
settings shadPS4's own window offers for every game; the tooltips say what each does.

- **Picture**: VSync (Mailbox, shadPS4's default, shows the newest frame at each refresh without tearing; On waits
  for each refresh; Off may tear), AMD's FidelityFX upscaling (FSR) with its sharpening (RCAS), HDR and a frame rate
  counter.
- **Sound**: the sound output library (SDL or OpenAL) and the volume (up to 500 %). Beside the volume stands
  **Bazzite's volume for shadPS4**, which is not shadPS4's: Bazzite's sound settings remember a volume and a mute
  per application, also once it is closed, so a game plays without a sound while shadPS4 is muted there. The app
  says so, in red, when shadPS4 is muted or turned down to nothing. **Unmute** beside it turns a muted shadPS4 on
  again, and Bazzite keeps it on from then on; a volume turned down is changed in the sound applet (the speaker in
  the panel, under Applications) while a game plays.
- **Controller and mouse**: the controller's motion sensors, and when the mouse pointer hides over the game.
- **In a game**: the PS4's system language, in which a game that has it shows its text, the trophy message and the
  game's splash screen.

A value shadPS4 knows and the app does not is shown as it is. Everything else shadPS4 can set stays in its own
window (**shadPS4 settings**).

### Log

Everything the app said and did, with the time: shadPS4 installed or removed, what the app set up in shadPS4, the
system modules copied, the game folders added and taken out, the settings changed, shadNet saved, every change to
Steam, and every error. Each game started from Steam is logged by its folder's name when it starts, with whether a
controller was connected. The same lines are in `~/.local/share/bc250-shadps4-manager/bc250-shadps4-manager.log`,
which turns over at 1 MB (the three older files are kept). The log holds what the app did, not your SteamGridDB key,
your shadNet password or anything else personal.

### shadNet

shadNet is shadPS4's online service: online trophies, friends and online play, in the games shadPS4 supports online.
shadPS4 signs in by itself when a game starts, once it knows your account. **shadNet Account** opens a window for it:

- **Server**: the shadNet server, `srv.shadps4.net:31313` (shadPS4's own) unless you use another one.
- **shadPS4 user**: which of shadPS4's users signs in. Games play as player 1, the first user.
- **shadNet name** and **Password**: your account. The name has 3 to 16 letters, digits, `-` or `_`, and is
  case-sensitive when you sign in.
- **Email**: needed to create an account.
- **Registration key**: only for a server that asks for one to create an account; its owner gives it to you.

**Create account** makes a new account on the server with that name, password and email. **Try sign-in** signs in
once and out again, to check the name and password. **Save** keeps it all in shadPS4's own files, with **Sign in to
shadNet when a game starts** ticked to use it, or unticked to stop. Close shadPS4 before you save: it writes its own
settings back when it ends.

The header shows the state of shadNet beside the app's own:

- **shadNet Online**: while a game runs, shadPS4 is signed in. Without a game, the server answers, so shadPS4 can
  sign in when one starts. The app asks the server without signing in.
- **shadNet Offline**: the server does not answer, or shadPS4's sign-in was refused or dropped. Hold the pointer
  over it to see why.
- **shadNet Off**: no account is set up, or **Sign in to shadNet when a game starts** is off.

While shadPS4 runs, the app reads shadPS4's log every few seconds to see whether it signed in.

shadPS4 keeps the password as it is in its `users.json`, and shadNet sends it over the network unencrypted. Use a
password you use nowhere else.

## Extract PKG

**Games Install** (or a `.pkg` dropped on the window) opens Extract PKG, a window that unpacks package files
(`.pkg`: games, patches and add-on content) into the folder layout shadPS4 loads: a `TITLE_ID` folder (for example
`CUSA41215`) with `sce_sys/` and the game's files. Extracted into one of the game folders, a game shows up in the
list when the window closes, ready for Steam. It needs no shadPS4 installed.

It can only open a package that shadPS4 can use: a fake-signed (re-encrypted) PKG. Retail packages that still carry
their original encryption cannot be opened; the window says **Failed to find PFSC header** then. A game unpacks to
roughly its package size, so the output folder needs that much room.

Drop a `.pkg` on the window or **Browse** to it: the icon and the SFO preview fill in at once, before anything is
extracted.

Several packages at once: choose more than one in **Browse**, drop them together, or open them together from the
file manager. The first is loaded as above and the rest wait their turn, listed under the PKG line, the games
first, then their updates and add-on content. **Extract PKG** then unpacks the loaded package and every waiting
one after it, into the same output folder, with the log running on from one to the next; a package you do not
want to replace an update with is skipped. **Preview Only**, the rename and the comparisons work on the loaded
package alone and leave the others waiting.

- **SFO Preview:** five keys from `param.sfo`: CATEGORY (`gd` game, `gp` patch, `ac` add-on content), CONTENT_ID,
  TITLE, TITLE_ID and VERSION. When the package has no readable `param.sfo`, CONTENT_ID and TITLE_ID come from the
  package header. Right-click the preview to copy a line, only its value, or everything.
- **icon preview (click):** the package's `icon0.png`, or the app's logo when there is none. Click it to see the
  package's `pic0.png` (or `pic1.png`) full screen; a click, Esc or the B button closes it. Right-click the icon,
  or the full screen picture, for **save as wallpaper**: it saves the picture as a PNG, named after the content id,
  to your Pictures folder or wherever you choose. The icon's menu also has **show full screen**.
- **Rename to CONTENT_ID:** renames the package file to its content id, `UP9000-CUSA00038_00-ASTRONAUT0000002.pkg`.
  A game or patch gets its APP_VER appended without the dot (`...-0100.pkg`), add-on content (CATEGORY `ac`) keeps
  the content id alone. The window says so when the file already has that name or another file has it.
- **Output:** the folder the `TITLE_ID` folder goes into: the one you used last, or else the first of shadPS4's game
  folders. The line below it says whether it is a game folder; a game extracted elsewhere shows up only once you add
  that folder (**Games Add folder**). The window refuses to extract into a `TITLE_ID` folder that already has something
  in it, and lists what it found: each extraction or preview needs a fresh folder, so nothing is mixed with an
  earlier run.
- **Updates:** an update (CATEGORY `gp`) for a game that is in the output folder goes into a folder beside it,
  `TITLE_ID-UPDATE` (for example `CUSA41215-UPDATE`). shadPS4 lays it over the game when the game starts, so the
  game's own folder stays as it is, and deleting the `-UPDATE` folder takes the update out. When the folder holds an
  update already, the window asks whether to replace it: the new one is extracted beside it first and takes its
  place only when every file was written, else the old one stays. An update package extracted without its game in
  the output folder goes into `TITLE_ID`, as a game does: a package with the game and its update in one says `gp`
  too.
- **Extract PKG:** writes `sce_sys/` (the package's metadata files: `param.sfo`, icons, pictures, trophies, the
  decrypted `license.dat`, `nptitle.dat` and `npbind.dat`), then every file of the package, with the progress bar
  counting files. When it is done, the output folder opens in your file manager. The log at the bottom shows each
  step and each file; the same lines go to the log file (see [What goes where](#what-goes-where)).
- **Preview Only:** writes only `sce_sys/` and `filelist.txt`, the list of every file the package holds with its
  inode and the path it would get. Use it to see what is inside, or to check a package, without the full extraction.
- **Salvage Mode (skip bad metadata):** a package with damaged metadata normally stops the extraction at the first
  bad entry, so you see that something is wrong. With Salvage Mode on, bad entries are skipped and the rest is
  extracted; the log ends with a recovery summary, and the folder gets `salvage_report.txt` (the skipped entries)
  and `extraction_errors.txt` (every error). Files that failed are missing or incomplete; shadPS4 may still run the
  game when they are not needed.
- **Compare Extractions** opens a menu with two tools. **Compare two extraction folders…** compares, for example,
  this window's output with another tool's: which files only one of them has, which differ in size and, when you
  answer **Yes** to the hash question, which differ in content (SHA-256, slower). The summary goes to the log and
  a JSON report (`compare_report_<date>.json`) into the first folder. Both folders' `filelist.txt`, when present,
  are compared too. **Delta between two compare reports…** takes a before and an after report, for example from
  before and after a change in the extractor, and tells per count what went up or down and which files were fixed
  or are new; the text goes to the log and to `<after report>_delta.txt` next to the after report.

While an extraction runs, the buttons are grayed out and the window stays open until it has finished. When the window
opens and finds that an earlier one did not end cleanly (the app stopped while it was open), it says so, with the
last file it was extracting; a partial `TITLE_ID` folder from then is refused by the empty-folder check: delete it.

```
<game folder>/CUSA00038/
├── sce_sys/            param.sfo, icon0.png, pic0.png, pic1.png, trophy/, license.dat, ...
├── eboot.bin           the game's files, in the package's own folder tree
├── ...
└── filelist.txt        every entry of the package: index, inode, type, name and path
```

Patches and add-on content extract the same way into their own folders. For an update, rename its folder after the
game's with `-UPDATE` added: see [Game updates and mods](#game-updates-and-mods).

A small add-on package that only carries metadata (an unlock key) has no files besides `sce_sys/`; the window says
"no extractable outer PFS entries detected" and extracts what there is. Some such packages name no files at all;
their one data block is then written as `inode_1.bin`.

When a package does not extract:

- **"is not a valid PKG file":** the file does not start with the PKG magic; it is not a package, or it is
  truncated at the start.
- **"Failed to find PFSC header":** the package's file system could not be decrypted: the package keeps its retail
  encryption, or it is damaged. Only fake-signed packages can be extracted.
- **"Guardrail: target output folder is not empty":** choose or make an empty folder; the `TITLE_ID` folder under
  it must not exist yet or must be empty. An update is the exception: see **Updates** above.
- **"PKG file size is different":** the file is shorter than its header says: an incomplete download or copy.
- **Preflight failed for file N:** the package's metadata for that file is inconsistent. Switch on Salvage Mode to
  get the other files.

A package is a table of metadata entries followed by an encrypted PFS file system image. The window reads the table,
derives the keys the way the console does for fake-signed packages (the "derived key 3" RSA block in `entry_keys`,
the image key in `image_key`, from them the EKPFS key, and with the seed in the image header the AES-XTS data and
tweak keys), decrypts the PFS, finds the compressed PFSC container in it, reads its inodes and directory entries,
and inflates each file block by block. It is a port of the C++ tool
[pkgxtractor](https://github.com/RobertoTorino/pkgxtractor) (`src/core/file_format/pkg.cpp`, `crypto.cpp`,
`psf.cpp`, themselves from shadPS4), so the two give the same files, and the same messages when a package is bad.

## From a terminal

`bc250-shadps4-run` starts the installed shadPS4 with the options you give it. The Steam shortcuts use it, so
they keep working when a newer version of the app brings a newer shadPS4.

```bash
bc250-shadps4-run -f true -g "/path/to/game/eboot.bin"   # a game, full screen
bc250-shadps4-run -g "/path/to/game/eboot.bin"           # a game, as shadPS4's settings say
bc250-shadps4-run -b                                     # shadPS4's own window
```

The app itself takes packages: `bc250-shadps4-manager file.pkg` opens it in Extract PKG, as opening a package with
the app from the file manager does; `bc250-shadps4-manager a.pkg b.pkg` opens the first and queues the rest. When
the app is open already, the packages go to the open window.
`bc250-shadps4-pkg-cli` extracts without a window:

```bash
bc250-shadps4-pkg-cli <file.pkg> [output folder] [--salvage] [--preview-only] [--no-subfolder]
```

It prints the package's content id, title and SFO keys, extracts into `<output>/<TITLE_ID>/` (the output folder
defaults to the package's folder; `--no-subfolder` extracts straight into it), and writes `filelist.txt`.
`--preview-only` stops after `sce_sys/` and the list; `--salvage` skips bad entries. It exits with 0 when every file
was written, 2 when some failed, 1 when the package could not be opened. The two comparison tools run from the app
folder (`~/.local/share/bc250-shadps4-manager/app`, with the app's venv's python):

```bash
python -m shadps4_manager.pkgxtractor.compare <folder A> <folder B> [--hash] [--json-out report.json]
python -m shadps4_manager.pkgxtractor.compare_delta <before.json> <after.json> [--out delta.txt]
```

## New shadPS4 releases

Each version of the app installs one shadPS4 release, the one it was tried with. When the window opens, the app asks
GitHub for shadPS4's newest release (its stable releases, not the daily development builds). When that one is newer,
the shadPS4 line's tooltip and the log say so, with a link to what is new; the app does not install it. A newer
shadPS4 comes with a newer version of the app, once it has been tried, from the [portal](../portal.md): after
updating the app, the tooltip says so, and **Install** brings it.

## How it works

The Steam shortcuts start `bc250-shadps4-run`, which starts shadPS4. Two things change when Steam is the one that
starts it. Started from a terminal, outside Steam, shadPS4 runs as it is.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). shadPS4 then sees only that
virtual controller:

- it has no motion sensors and no touchpad, so a game that uses them cannot;
- on the desktop it follows the layout Steam has active. While Steam does not know that the game has the focus, that
  is Steam's desktop layout (mouse and keys), and the game gets no controller input at all.

So the run wrapper undoes it: while a real controller is connected, shadPS4 reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.

### A game renamed, moved or gone

A game renamed or moved after it was put in Steam keeps its mark: the app knows each game in Steam by its code (or,
without one, its file's size), so on **Refresh** it finds the game again under its new name, ticked, and says so
under the tabs; **Update Steam** then takes the old shortcut out and puts the game in under its new name. A
shortcut to a game that is no longer there (deleted, or on a drive that is not in) does not start shadPS4: a
window says which file is missing and what to do, and closes by itself, so Steam sees the game end.

### Steam's overlay on the desktop

The KDE desktop of Bazzite is a Wayland session. shadPS4 opens its window through Wayland when it can, but Steam on
the desktop only sees windows that go through X11 (XWayland, the X11 server within the Wayland session). A game
window Steam cannot see has no overlay: **Shift+Tab** and the **PS button** do nothing, and there is no way to the
game's page, controller layout or settings while it runs. Steam also cannot tell that the game has the focus, which
is why its desktop layout stays active (see above).

So when Steam starts a game on the Wayland desktop, the run wrapper has shadPS4 open its window through XWayland
(`SDL_VIDEO_DRIVER=x11`), and Steam's overlay works as in any other game. A handheld's Game Mode runs every game
through X11 already.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-shadps4-manager/app` |
| Its Python, with PyQt6 and cryptography | `~/.local/share/bc250-shadps4-manager/venv` |
| shadPS4 | `~/.local/share/bc250-shadps4-manager/emulator` |
| Extract PKG's log, and its crash marker and progress while it is open | `~/.local/share/bc250-shadps4-manager/pkgxtractor.log`, `.state`, `.progress` |
| Your games and the system modules you put there | `~/Games/PS4` and `~/Games/PS4/Modules` (the app's own folder), and `Games/PS4` on a removable drive |
| shadPS4's saves, settings, system modules | `~/.local/share/shadPS4` (shadPS4's own folder) |
| shadPS4's settings (the Settings tab) | `~/.local/share/shadPS4/config.json`, shadPS4's own |
| shadPS4's play time per game | `~/.local/share/shadPS4/play_time.txt`, shadPS4's own |
| The app's log | `~/.local/share/bc250-shadps4-manager/bc250-shadps4-manager.log` |
| Your shadNet account | `~/.local/share/shadPS4/users.json`, the server in its `config.json` |
| The quit hotkeys | `~/.local/share/shadPS4/input_config/global.ini` |
| The app's settings, with Extract PKG's last used folders | `~/.config/bc250-shadps4-manager` |
| The Steam shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The covers found on SteamGridDB | `~/.local/share/bc250-shadps4-manager/covers` |
| Launchers | `~/.local/bin/bc250-shadps4-manager`, `~/.local/bin/bc250-shadps4-run`, `~/.local/bin/bc250-shadps4-pkg-cli` |

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app and the shadPS4 it installed;
shadPS4's own folder (your saves) and your games stay. The games in Steam then no longer start: take them out
first by unticking them and pressing **Update Steam**.

Installing the app also removes the standalone Bazzite pkgxtractor, whose package extraction is in this app now
(Extract PKG). Its settings stay: Extract PKG starts in the folders you last used there.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the shadPS4 it installed; keeps its settings and log
./install.sh --uninstall --purge     # also remove its settings, covers and logs
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

GPL-3.0-or-later. shadPS4 is a separate program under its own license (GPL-2.0), downloaded from its own release.
Extract PKG's PKG/PFS/PSF code is a port of shadPS4's (GPL-2.0-or-later).
