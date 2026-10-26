<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PCSX2 Manager](../assets/pcsx2/bc250-pcsx2-manager.webp){ .app-logo }

# PCSX2 Manager

Plays **PS2 games** on the **AMD BC-250** with [PCSX2](https://pcsx2.net), an open-source PS2 emulator. The app
installs the PCSX2 release it was tried with and sets it up, takes your PS2 BIOS, finds your games and adds them to
Steam, so a game starts straight away, on the desktop or from Steam's **Big Picture Mode** (Game Mode on a
handheld). Everything about PCSX2 is done in the app: its [settings](#settings), the
[memory cards](#memory-cards), each game's [screen](#screen). PCSX2's own window is never needed, and the app has
no Play button: a game is started from Steam.

Whether a game runs, and how well, is up to PCSX2. Its
[compatibility list](https://pcsx2.net/compat) shows what others found.

## What you need

- **Your games**, dumped from your own discs: ISO images, or the compressed CHD, CSO, ZSO or GZ. The app never
  downloads games.
- **The PS2's BIOS**, dumped from your own console.
  [PCSX2's BIOS page](https://pcsx2.net/docs/setup/bios) says how (the biosdrain homebrew). The app cannot ship
  it: pick the dump (a `.bin` file) with **BIOS Install**. PCSX2 needs it to start any game.
- **Steam**, started at least once: a game is started from Steam.
- About 60 MB for PCSX2 itself. Its BIOS, memory cards, saves and settings go in `~/.config/PCSX2`.
- **fusermount** (FUSE), which Bazzite has. PCSX2 comes as an AppImage, which mounts itself with it. Without it,
  it unpacks itself to a temporary folder on every start, which takes longer.

## Using it

The header shows the **PCSX2 version**, **Your games** (the games found), those **Available in Steam** and the
**Play time**: the time spent in all your games together, as PCSX2 counts it, with each game's time in the
tooltip. **Refresh** reads everything
again. Beside the title, next to the app's state, stands the controller's: **Controller connected**, or
**No controller** when none is, looked at again every few seconds. A game started from Steam reads the controller
that is connected when it starts, so switch yours on, or press its PS button to wake it, before starting a game.
When Steam starts a game without one, the app also says so in a desktop notification.
Under the introduction, which links to **PCSX2's release notes** and to this wiki, a row of six pills does the
setting up, each with what it is for on top and what it does under it: **PCSX2 Install** and **PCSX2 Uninstall**,
**BIOS Install** and **BIOS Uninstall**, **Games Add folder** and **Games Remove folder**. Three lines below them
say where each stands, and then come four tabs: **Your games**, **Settings**, **Memory cards** and **Log**.

- **PCSX2**: **Install** downloads PCSX2 from its GitHub release (about 57 MB): the stable release this version
  of the app was tried with, checked against its checksum before it is installed. The app then sets PCSX2 up; see
  [PCSX2's settings](#pcsx2s-settings). **Uninstall** takes it out again; PCSX2's own folder, with the BIOS, your
  memory cards and settings, stays.
- **BIOS**: the BIOS PCSX2 uses, by name. **Install** takes your dump: the app copies it into PCSX2's `bios`
  folder, with the files beside it under the same name (such as `.NVM` and `.MEC`), and PCSX2 uses it. Only the
  `.bin` is needed. **Uninstall** takes a dump out of that folder again, with those files; the dump you chose it
  from stays where it is, and PCSX2 uses another dump in the folder when there is one. The folder's path is in the
  tooltip.
- **Game folders**: the folders the app looks for games in, by name (the whole path is in the tooltip).
  **Add folder** adds one, **Remove folder** stops looking in one (the games stay where they are). Games in
  subfolders are found too, up to five folders deep, so one folder with a folder per game is enough.

### Your games

The table lists every game found:

- An **ISO** is read for its `SYSTEM.CNF`, which names the program the console boots: that name is the game's
  **Id** (SLUS-12345), shown beside the title.
- A **CHD, CSO, ZSO or GZ** (the **Type** column) holds the same disc compressed; the app does not look into
  those formats, so the row has no Id. PCSX2 plays them the same.
- **File name** is the image's name; its folder is in the tooltip.

A PS2 disc carries no title of its own. The app takes it from PCSX2's own catalog of PS2 games, by the serial,
and a game PCSX2 does not know gets its file's name, without a serial in it: `SLUS_215.53.Lumines Plus.iso` is
**Lumines Plus**.

#### Screen

A PS2 game shows a 4:3 picture, with borders on a wide screen. **Screen setting** sets, per game, how it fills the
screen:

- **Original**: the PS2's picture as it is.
- **Widescreen**: PCSX2's widescreen patch for the game, which draws a wider view without stretching. Offered only
  for a game PCSX2 has one for.
- **Fill screen**: the picture stretched to fill the screen. Round things look wider.

The choice is kept in the game's own settings in PCSX2. A compressed image has no choice here: the app does not
look into it, so it does not know the game's settings file.

#### Steam

Tick the games you want in Steam and press **Update Steam**. The app adds them to Steam as non-Steam games
and takes out the games you unticked and games it no longer finds. Steam keeps these files in memory, so it closes
for the change and starts again in the background. The pictures on the tiles are drawn from the app's icon, with the
game's title, on a background in the icon's color, and the icon is the logo on the banner: a PS2 disc gives no
pictures of its own.

In Steam each game's name starts with its system, for example **[PS2] Lumines Plus**, so it stands apart from the
same title on Steam or on another system in Steam's menus. A game whose name in Steam differs from its title in the
app is renamed the next time you press **Update Steam**, which is on for it until then. Steam sees the renamed game
as a new one: its play time stays, but a controller layout or collection you set for it in Steam has to be set again.

The games are in the library under **Non-Steam**, on the desktop and in Big Picture Mode alike. They start the
game alone in PCSX2, full screen, with the mouse pointer hidden; PCSX2 exits when the game does. Steam's menu and
**Exit game** work as for any game, and so does **Select + Start** on the controller (see [Settings](#settings)).

Steam's overlay works over a game started from Steam, in Big Picture Mode and on the desktop: press **Shift+Tab**
or the **PS button** for the game's page, its controller layout and its settings, without leaving the game. In
Big Picture Mode the PS button opens Steam's menu over the game; pressed again there, it opens the power menu,
with **Exit game** and the way out of Big Picture Mode.

Steam's overlay also takes **screenshots**: **F12** on a keyboard, or the Steam button with the right shoulder
button on a controller in Big Picture Mode. They go into Steam's screenshot library, from where Steam shows,
uploads or shares them. PCSX2's own screenshot key (**F8**) saves into PCSX2's `snaps` folder instead.

A game started from Steam reads your controllers itself. [How it works](#how-it-works) explains both.

On a handheld image of Bazzite, whose Game Mode is a Steam session of its own, change Steam from Desktop Mode: in
that session Steam cannot close for the change.

##### Covers

With a SteamGridDB API key, entered under **Steam artwork…**, the app takes the pictures for each game from
SteamGridDB instead of drawing them: the cover, the wide picture, the banner and the logo. A picture SteamGridDB
does not have stays drawn. The title the app looks up is the game's title in the list. See
[Covers from SteamGridDB](covers.md) for the key, how a game is looked up and how to use a picture of your own.

### Settings

PCSX2's settings that matter for playing, written into PCSX2's own settings file the moment you change one. A
game's own settings in PCSX2 come before these; how a game fills the screen is set per game, in the Your games
tab.

- **Picture**: the **Renderer** (Automatic picks Vulkan on the BC-250; Software draws on the CPU, exact but slow),
  the **Internal resolution** (Native is the PS2's; 3x fills a 1080p screen sharply, 6x a 4K one; a higher one
  asks more of the GPU), **Texture filtering**, **Anisotropic filtering**, **FXAA**, **Integer scaling**, **VSync**,
  **Blending accuracy** (how exactly the PS2's blending of transparent layers is copied; Basic suits most games, a
  higher level fixes glitches in some at a cost to the GPU), **Video (FMV) shape** (a game's videos as the game's
  screen setting, or 4:3 so Fill screen does not stretch them) and **Show FPS**.
- **Emulation**: **Fast boot** (skips the PS2's start-up screen), **Cheats** (PCSX2's `.pnach` cheat files for a
  game) and **No-interlacing patches** (a progressive picture instead of an interlaced one, sharper and without
  shimmer, for the games PCSX2 has a patch for).
- **Sound**: the **Volume**. Beside it stands **Bazzite's volume for PCSX2**, which is not PCSX2's: Bazzite's sound
  settings remember a volume and a mute per application, also once it is closed, so a game plays without a sound
  while PCSX2 is muted there. The app says so, in red, when PCSX2 is muted or turned down to nothing. **Unmute**
  beside it turns a muted PCSX2 on again, and Bazzite keeps it on from then on; a volume turned down is changed in
  the sound applet (the speaker in the panel, under Applications) while a game plays.
- **Controllers**: **Vibration**; **Player 2 on the second controller**: a second controller connected is
  player 2, with the same buttons as player 1; and **Quit a game with Select + Start**: the first controller's
  Select (Share, Create or View on other controllers) and Start (Options or Menu) pressed together end the game
  and close PCSX2, without a question, as Steam's **Exit game** does. It is on from the start. Turn it off for a
  game that uses the two buttons together itself; a game is then left through Steam's menu, or **Esc** on a
  keyboard opens PCSX2's own menu.

Each setting shows what PCSX2's settings file holds; a value set in PCSX2 that the app does not offer is shown as
it is. Nothing is written while PCSX2 runs: PCSX2 writes its settings back when it closes, over any change.

### Memory cards

The **Memory cards** tab shows the memory cards in PCSX2's memory card folder (`~/.config/PCSX2/memcards`, or the
folder set in PCSX2) and the saves on the card you choose: each save's title, its folder on the card, its size and
when it was saved. The card in each of PCSX2's slots is marked **(slot 1)** or **(slot 2)**; **Slot** puts the
chosen card in a slot, or takes it out of one. A game saves to the card in slot 1, and some use slot 2 too; a card
is in one slot at most, so a card put in a slot takes the place of the card there. Select a save to see its 3D icon
as the PS2's browser shows it, as a still picture.

- **Import…** puts save files on the card: MAX Drive (`.max`), EMS (`.psu`), SharkPort (`.sps`), X-Port (`.xps`),
  Code Breaker (`.cbs`) and PSV (`.psv`, from a PS3). A save that is already on the card is left as it is: delete
  it first to replace it. When the card has too little space for all of them, none is put on it.
- **Export…** saves the selected saves as `.psu` or `.max` files, to keep or to share. One save asks for a file
  name; several go into a folder you choose, each named after its folder, title and a checksum.
- **Copy to…** copies the selected saves onto another card.
- **Delete…** deletes the selected saves.
- **New card…** makes a new, empty card. A name ending in `.ps2` is PCSX2's own kind; `.mc2` is a card without the
  error-correcting code (ECC), as a MemCard PRO2 reads. The PS2's own card is 8 MB; PCSX2 also takes 16, 32 and
  64 MB, which not every game works with. **Slot** then puts it in a slot.
- **Format…** empties the card: every save on it goes.
- **Check** checks the card's file system, and every page against its ECC, and says what it found.

Before every change, the app copies the card beside it as `<card>.<date and time>.bak`, for example
`Mcd001.ps2.20261016-093000.bak`; the newest 10 per card are kept. PCSX2 does not list these as cards. To go back
to one, close PCSX2, rename the card and give the backup the card's name. A change is made on a copy of the card,
which takes its place when it is finished, so a change that fails leaves the card as it was.

Nothing is written while PCSX2 runs: it keeps the card in memory and would write its own copy over the change. The
tab says so, and import, copy, delete, format and the slot wait until PCSX2 is closed. Export and check only read
the card.

The tab reads PS2 cards. PCSX2 can also keep a card as a folder, and play PS1 games with PS1 cards (`.mcd`,
`.mcr`); the tab lists those and says it cannot read them. A PS1 save on a PS2 card, as a PS2 makes when it
copies one, is listed with its title.

### Log

Everything the app said and did, with the time: PCSX2 installed or removed, what it wrote in PCSX2's settings,
the BIOS and the folders chosen, each setting changed, each change to a memory card, every change to Steam, and
every error. The games, too: each game started from Steam is logged by its file's name when it starts, with
whether a controller was connected, and the next time the window looks, PCSX2's own log of its last run is summed
up in one line: which game, how long it was played, until when, and with which controller. PCSX2 writes its log over at every start, so when two games are
played before the window looks, only the last run is summed up. The same lines are in
`~/.local/share/bc250-pcsx2-manager/bc250-pcsx2-manager.log`, which turns over at 1 MB (the three older files are
kept). The log holds what the app did, not your SteamGridDB key or anything personal.

## From a terminal

`bc250-pcsx2-run` starts the installed PCSX2 with the options you give it. The Steam shortcuts use it, so they
keep working when a newer version of the app brings a newer PCSX2.

```bash
bc250-pcsx2-run -nogui -fullscreen -- "/path/to/game.iso"   # a game alone, full screen (the Steam shortcuts)
bc250-pcsx2-run -nogui -- "/path/to/game.iso"               # a game alone, in a window
bc250-pcsx2-run                                             # PCSX2's own window
```

## New PCSX2 releases

PCSX2 publishes a nightly build for almost every change and, now and then, a stable release (2.8.2). Each version
of the app installs one stable release, the one it was tried with, and nothing else. When the window opens, the
app asks GitHub for PCSX2's newest stable. When that one is newer, the first step says so, with a link to what is
new; the app does not install it. A newer PCSX2 comes with a newer version of the app, once it has been tried, from
the [portal](../portal.md): after updating the app, the first step says so, and **Install** brings it.

The app turns PCSX2's own update check off. If PCSX2 is updated in its own window anyway, the first step says that
PCSX2 updated itself, and **Install** puts the tried release back.

## How it works

The Steam shortcuts start `bc250-pcsx2-run`, which starts PCSX2. Two things change because Steam is the one that
starts it.

### Controllers

When Steam starts a game, it tells the game's controller library (SDL) to ignore the controllers Steam handles
itself, and gives the game Steam's virtual controller in their place (Steam Input). PCSX2 then sees only that
virtual controller: it has no motion sensors, and on the desktop it follows the layout Steam has active, which may
be Steam's desktop layout (mouse and keys).

So the run wrapper undoes it: while a real controller is connected, PCSX2 reads that controller itself and leaves
Steam's virtual one (USB ID `28DE:11FF`) out. The PS button stays Steam's. Without a real controller, as on a Steam
Deck whose own controls exist only as Steam's virtual controller, the wrapper leaves Steam's choice as it is.

PCSX2 itself maps the keyboard to player 1 and no controller. The app maps player 1 to the first controller
connected, whatever its kind, by the buttons' places: the bottom face button is Cross, the right one Circle, and so
on, over USB and Bluetooth alike. With two controllers connected, the first is the one SDL counts first; **Player 2
on the second controller** in the Settings tab gives the second one the same buttons. A mapping made in PCSX2's own
window stays: the app leaves player 1 alone once a controller is mapped to it.

### PCSX2's settings

The app sets PCSX2 up so a game started from Steam goes straight into the game. While PCSX2 is installed and not
running, it keeps these settings in PCSX2's own settings file (`~/.config/PCSX2/inis/PCSX2.ini`); everything else
in it stays as it is:

- PCSX2's setup wizard is marked done, so it does not open at the first start.
- PCSX2 does not look for updates itself: an update would replace the release the app installed.
- The mouse pointer is hidden over a full-screen game.
- PCSX2 uses the BIOS chosen in the app.
- Player 1 is mapped to the first controller (see [Controllers](#controllers)).
- Select + Start together on that controller end the game and close PCSX2 (the switch in the
  [Settings](#settings) tab turns it off).

The [Settings](#settings) tab writes into the same file, one setting at a time. Without a settings file yet, the
app starts from PCSX2's own defaults, as PCSX2 writes them at its first start, with its keyboard keys and hotkeys:
**Esc** opens PCSX2's pause menu, **F6** changes the picture's shape. While PCSX2 runs nothing is written, since
PCSX2 writes its settings back when it closes.

### Steam's overlay on the desktop

The KDE desktop of Bazzite is a Wayland session. PCSX2 (a Qt program) opens its windows through Wayland when it
can, but Steam on the desktop only sees windows that go through X11 (XWayland, the X11 server within the Wayland
session). A game window Steam cannot see has no overlay: **Shift+Tab** and the **PS button** do nothing.

So when Steam starts a game on the Wayland desktop, the run wrapper has PCSX2 open its windows through XWayland
(`QT_QPA_PLATFORM=xcb`), and Steam's overlay works as in any other game. A handheld's Game Mode runs every game
through X11 already.

## What goes where

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-pcsx2-manager/app` |
| PCSX2 | `~/.local/share/bc250-pcsx2-manager/emulator` |
| PCSX2's BIOS, memory cards, saves, settings | `~/.config/PCSX2` (PCSX2's own folder) |
| Each game's screen | `~/.config/PCSX2/gamesettings/<serial>_<CRC>.ini`, PCSX2's own settings per game |
| PCSX2's catalog (titles, patches) | Beside PCSX2, in `~/.local/share/bc250-pcsx2-manager/emulator` |
| The memory cards' backups | Beside each card, in PCSX2's memory card folder |
| The app's settings, with the game folders | `~/.config/bc250-pcsx2-manager` |
| The app's log | `~/.local/share/bc250-pcsx2-manager/bc250-pcsx2-manager.log` |
| The Steam shortcuts | Steam's `shortcuts.vdf` and `grid` folder, per Steam user |
| The pictures found on SteamGridDB | `~/.local/share/bc250-pcsx2-manager/covers` |
| Launchers | `~/.local/bin/bc250-pcsx2-manager`, `~/.local/bin/bc250-pcsx2-run` |

## Install and remove

Install the app from the [portal](../portal.md), where it is under Gaming. Removing it takes out the app and the
PCSX2 it installed; PCSX2's own folder (the BIOS, your memory cards and saves) and your games stay. The games in
Steam then no longer start: take them out first by unticking them and pressing **Update Steam**.

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app and the PCSX2 it installed; keeps its settings and log
./install.sh --uninstall --purge     # also remove its settings, covers and log
```

## Disclaimer

PCSX2 Manager is an independent project, not affiliated with or endorsed by the makers of PlayStation.
PlayStation and PS2 are trademarks of their owner.

## License

GPL-3.0-or-later. PCSX2 is a separate program under its own license (GPL-3.0), downloaded from its own release.
The memory card code is from [mymc++](https://github.com/Adubbz/mymcplusplus) (GPL-3.0-or-later) by Adubbz, based on
mymc+ by Florian Märkl and mymc by Ross Ridge.
