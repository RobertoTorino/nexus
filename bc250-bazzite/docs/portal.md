<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC250 Bazzite Suite](assets/portal/bc250-bazzite-suite.webp){ .app-logo }

# Portal

The BC250 Bazzite Suite's front door: one fullscreen view that installs, opens, updates and removes the suite's
apps, for a TV and a controller as much as for a desk, as Steam's Big Picture is for Steam. It works with the
keyboard, the mouse or a controller alike. The [Portal Tour](portal-tour.md) shows it in a two-minute video.

The portal opens with a short animated intro, about three seconds, with its own sound: the suite's icon and its
name, **BC250 BAZZITE SUITE**, before the view appears. Press any key, click, or press any button on the controller
to skip it.

**The header**: the suite's icon, as large as a tile's (click it to open this wiki), its name with the version and the **Beta** stage,
a small **i** that says where the apps install from, and a line that says in a few words what the open category is
for, with **☰ Settings** at the top right. Under them, in a row that ends level with the icon's bottom, four big
symbols: **Refresh** (two circling arrows: look again at which apps are installed), **Sys info** (a chip),
**Install All apps** (a grid of apps with an arrow down) and **Install All updates** (a circular arrow around an
arrow down), each described below. Hover a symbol to see what it does. The one with the focus is framed in silver,
as a tile is; a symbol that has nothing to do is grayed out. When you have chosen a place on the Settings page, the
weather follows the symbols: its symbol and the place's name. On the right of the symbols, how many apps are
installed, and under it the status line: the CPU's and the GPU's load and temperature, then the date and the time,
for example **CPU 12% 54°C | GPU 3% 61°C | Thursday 11/5/26 | 07:44 PM CEST**. When the line does not fit beside
the symbols, the date and the time move to a second line under the loads. The line at the bottom says what the keys
and the controller's buttons do.

**Bazzite Test** is always installed with the portal; every other app is optional. Below the header is a strip
with a name for each [category](apps/categories.md): Sustainable, Graphics, Gaming and Utilities, and beside it
the notice of updates. Each app is a large tile under its category, left to right in the order of `apps.toml`
and as many to a row as the screen fits; Bazzite Test is always the first tile on Sustainable. The tile with the
focus is framed in silver; move it with the arrow keys, the d-pad or the stick, or point at a tile with the
mouse:

- **The icon**, its category's, drawn from a 512 px picture so it stays sharp on a 4K screen. It is gray while
  the app is not installed. Hover over the tile to see what the app does, its state and the release this portal
  pins.
- **The name**, without the suite's "BC-250" prefix.
- **Press the tile** (click it, Enter, or A on the controller) to open the app; an app with two windows (CU Bisect,
  Cores Bisect) asks which one. Pressing a tile that is not installed offers to install it. An app that is open
  already, also one behind the portal or minimized, comes to the front instead, without the board warning again;
  that needs KDE's desktop (KWin), which Bazzite's desktop is.
- **Update** (a right click, or Y on the controller): installs the tile's update or reinstall at once; an app
  that changes the board asks first. While a newer portal is out, they update the portal instead (see
  **Updates** below). A right click on a tile with nothing to update opens its menu.
- **The tile's menu** (the Menu key, or X on the controller) holds every action: **Open** (or the
  app's two windows), **Install** (an arrow into a tray; **Update**, in red, when an update is waiting;
  **Reinstall** for an installed app, in red with a circular arrow when its version is unknown) and
  **Uninstall** (a bin). What cannot be done now is grayed out. Bazzite Test has no Uninstall: it is removed
  together with the portal.
- **A red dot** in the icon and **Update** under the name: an update is available.
- **A red circular arrow** in the icon and **Reinstall needed** under the name: reinstall the app. It is
  installed, but not by this portal (by hand, or under an earlier name of the app), so the portal does not know its
  version. Reinstall in its menu installs the version this portal pins. An app installed from a checkout of the
  repository without its version recorded shows it too.
- **changes the board**, in orange under the name, for apps that change how the board runs. Hover over the tile:
  the popup says what the app touches, what stays after a reboot or a power off, what it never touches and how the
  change is undone, the same text that opens the app's chapter of this wiki.
- **App not available**, in red under the name: the release of this app was withdrawn because of a problem
  (privacy, security or another reason; hover over the tile to read which). It cannot be installed or opened. When
  it is installed, the portal says so at start and removes it with the app's own uninstaller in a terminal. If that
  fails, Uninstall stays in its menu, to try again.
- **Installing…**, **Removing…** or **Downloading…** in blue under the name while that runs on the app; a download
  counts its megabytes as it comes in (**Downloading… 40 MB**).

**The categories.** The line under the title says what the open category is for, and [The apps](apps/index.md)
lists the apps by category. Click a name in the strip, press LB or RB on the controller, or Page Up and Page Down
on the keyboard, to change the category. The portal always opens on the first one, Sustainable.

| Keyboard | Controller | Mouse | Does |
|---|---|---|---|
| Arrow keys | D-pad or left stick | Point | Move the focus between the tiles, the symbols and the notices |
| Enter | A | Click | Open the app, press a symbol, open a notice |
| U | Y | Right click | Update: the portal while a newer one is out, else the tile's app (update or reinstall) |
| Menu key, M | X | | The tile's menu: Open, Install, Update, Reinstall, Uninstall |
| Page Up, Page Down (or Q, E) | LB, RB | Click a name | The category before and after |
| S | ☰ (Start) | Click ☰ | The Settings page, and back from it |
| K | R3 (the right stick pressed) | | Bazzite's on-screen keyboard (Plasma Keyboard), and away again; R3 works in a question or the file dialog too |
| Escape | B | | Close a menu or a question; on the Settings page, go back to the apps; else exit the portal, after a question |

**Exiting.** Escape, B, the window's close button and Alt+F4 all ask *Do you really want to exit the Portal?* first.
**No** has the focus, so a stray press does not close the portal: move to **Yes** with the arrow keys, the d-pad or
the stick, and press Enter or A. B or Escape answers No. While a download or an install runs, the question also says
what exiting does to it: the download stops, or the installer finishes in its terminal window without the portal
recording it.

**Questions.** In a question (Yes and No, Install and Cancel) the arrow keys, the d-pad and the stick move between
the buttons, and Enter or A presses the one with the focus.

**The on-screen keyboard.** R3 shows Plasma Keyboard, the desktop's virtual keyboard, so you can type with the
controller, for example a file name when you choose a wallpaper. Bazzite shows it only after touch or pen input,
which a controller is not, so while it shows the portal sets it to show for any input, and R3 again (or closing the
portal) hides it and sets your own choice back. When no virtual keyboard is chosen for the desktop, R3 says where to
choose it: System Settings, Keyboard, Virtual Keyboard, Plasma Keyboard.

The controller is read with [pygame-ce](https://pypi.org/project/pygame-ce/), which the portal's installer adds to
the suite's venv; it takes any controller SDL knows (XBOX, PlayStation, Switch Pro and most others). The portal
listens to the controller only while its own window has the focus, so a game's input never moves it. Without a
controller, the keyboard and the mouse work as always.

**The touchpad as the mouse.** On a DualShock 4, a DualSense or a DualSense Edge the touchpad moves the mouse
pointer, as Steam does for the Steam Controller: slide a finger to move it, press the pad to click, and press it
with two fingers on it for a right click. **Touchpad** on the Settings page sets how fast the pointer goes. Like the
rest of the controller it works while the portal has the focus, in its menus and questions too. The portal makes a
mouse of its own for it (Wayland lets no program move the pointer), which the desktop lists as **BC250 Bazzite Suite
touchpad** while the portal runs; Bazzite gives you the access it needs. A controller Steam Input owns has the
touchpad of Steam's desktop layout instead.

**Handhelds.** The view is made for a TV at 1080 p or 4K as much as for the Steam Deck (1280 x 800) and the ROG
XBOX Ally X (1920 x 1080, shown at 1280 x 720 with the desktop's scaling): below 1000 px of height the icons, the
type, the header and its symbols are drawn smaller, down to about two thirds, so the header, two rows of icons
and the line of keys fit on the screen. You can also swipe a page with a finger on the touch screen. The built-in
controls are controllers like any other. Where Steam Input already turns them into keys (the Deck's desktop
layout does: d-pad to the arrow keys, A to Enter, B to Escape), the keyboard column above applies and works as it
is.

**The Steam Controller, and any controller Steam Input owns.** While Steam runs, it takes the controllers it has
Steam Input on for (always the Steam Controller and a Steam Deck's own controls): outside a game, its desktop layout
turns their buttons into keys and the mouse, and the portal sees only those keys. By default that layout gives the
d-pad the arrow keys, A Enter and B Escape, but LB, RB, R3, the back buttons and others have no key, so they do
nothing in the portal. There are two ways to get every button:

- **Start the portal from Steam.** In Steam, choose **Games**, **Add a Non-Steam Game to My Library**, and pick
  **BC250 Bazzite Suite** (or browse to `~/.local/bin/bc250-bazzite-suite`). Started from Steam, the portal reads
  the controller as an XBOX controller, with the buttons in the table above. Steam's controller settings for that
  entry can give the back buttons, the touchpads and the other extras any button or key you like.
- **Give the buttons keys in the desktop layout.** In Steam, open **Settings**, **Controller**, **Desktop Layout**
  (Edit), and set LB to Page Up, RB to Page Down, Y to U, X to M, ☰ to S and R3 to K (the keyboard column of the
  table). The back buttons can take any of these keys too. The layout is Steam's and applies to every program
  outside a game.

The tools for working on the suite are not in the portal: they are Nexus's, in `dev/` of the repository, run from a
checkout and have no release. [Nexus Dashboard](https://robertotorino.github.io/nexus/dashboard/) opens them all:
Nexus Release Tool, Nexus Installer Tests (the installer tests one at a time), Nexus Demo Recorder, Nexus Sound Lab
(short sound effects for the windows), the video tours and the icons. Start it from the checkout, or give it a menu entry with its `install.sh`.

- `apps/` may also contain standalone tools (with a `.standalone` marker) that do not appear in `apps.toml`
  and that the portal does not install or open.
- Install, update and uninstall run **the app's own installer** in a terminal window, which opens over the portal,
  because installers may ask for the sudo password and print what they do. The portal watches for the result and
  refreshes. A terminal whose installer ended well closes by itself; one that failed stays open with what happened
  until you press Enter.
- Apps that change how the board runs (CU/core unlocks, the GPU governor, GPU overclocking, the ACPI override, the VRAM
  split, a patched GPU driver) are marked **changes the board**. The portal warns before installing or opening them,
  and the tile's popup says what each one changes and how that is undone.
- Each portal release pins one tested release of every app in [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/portal/apps.toml). The portal downloads
  exactly those tarballs from the suite's GitHub releases and checks each against the SHA-256 pinned there, or
  against the release's `SHA256SUMS` until one is pinned. Then it unpacks the tarball without ever writing
  outside its folder.
- **Updates:** a red dot marks every app whose installed version differs from the one this portal pins; Update in
  its menu installs the pinned version. An app installed from a checkout of the repository counts as well:
  the portal records the checkout's version of it and compares that with the one it pins. A portal that runs from a
  checkout shows what it installed from there as installed, whatever it pins. The red notice beside the category
  strip counts them and the apps that need a reinstall, for example **● 2 updates, 1 reinstall**. Press it to list
  each one with its category and versions, and choose one to go to its tile. A category with such an app shows
  their number in red after its name, so none goes unseen on a category that is not open. Press Y or right-click
  a tile with an update to install it.
- **Portal updates:** newer app versions come with a newer portal release. At start the portal looks for one on
  GitHub; when there is one, an orange **PORTAL UPDATE AVAILABLE** shows under the name on the intro, and an
  orange **UPDATE AVAILABLE, PRESS Y TO UPDATE** beside the category strip. Its tooltip says what the release
  brings, for example **Portal 0.9.1: updates ACE Queues and Memory Manager**, with each app's old and new
  version. Press Y, right-click a tile, or click the banner (Enter or A with the focus on it) to update: the portal
  downloads the release, checks it against the release's `SHA256SUMS`, and runs its `install.sh` in a terminal,
  which asks for your sudo password for the copy to `/opt`. The banner says **DOWNLOADING THE UPDATE…** and then
  **INSTALLING THE UPDATE…**. When the installer has ended well, the portal starts again as the new version, and
  the installed apps it updates show the red dot. When it fails, the terminal stays open with what happened, and
  Y tries again. While an app installs, the portal update waits for it. A release built again under the portal's
  own version is offered too (the tooltip says **a new build of this version**): the installer keeps the checksum
  of the tarball it installed from (`build.sha256` beside the program, when the tarball is next to the unpacked
  folder, as the install steps and the portal's own update leave it), and the portal compares it with the newest
  release's. The download is kept in `~/.local/share/bc250-bazzite-suite/portal/portal-update/` until the next one.
- **Outside the suite**, in orange beside the red notice: a newer release of a program that an installed app
  installs in its newest version, so the app can install it now. Press it to list them, for example **Upscaler
  Manager (Graphics): HelixSR 1.9.3 is out**, with what to do in the app, and choose one to go to its tile; the
  tile says it too under the name. Today this is HelixSR (the BC-250 Upscaler Manager). The portal shows what the
  app found the last time it looked, so open the app now and then; when you come back to the portal, the notice
  follows. Programs an app pins (shadPS4, PPSSPP, RPCS3, Vita3K, PCSX2's stable release, Xenia,
  DirectMesh) are not listed: a newer one comes with a new version of the app, as an update above.
- **Restart: portal x.y.z is installed:** a portal window that is open while you install a newer portal by hand
  (its `install.sh` in a terminal) keeps running the old one, with its old app versions, and starting the portal again only brings that window to the
  front. When you come back to the window, it sees the newer portal and shows this red button: click it to restart
  into the new portal, which then shows the red dot on the apps it updates. While an app installs or uninstalls,
  the button waits for it to end.
- **Installed apps**, on the right of the symbols: how many of the portal's apps are installed, for example
  **12/27 installed**. An app that is not available any more is not counted.
- **The status line**, under it: the CPU's load and temperature, the GPU's load and temperature, the day, the date
  (month/day/year) and the time with its time zone, the loads read every two seconds and the time every second (not
  while the portal is minimized). **Clock** on the Settings page sets how the time reads. When the line does not fit
  beside the symbols, the date and the time go on a second line. The load is the share of the last two seconds.
  The GPU's load comes from the kernel's load sensor where there is one; the BC-250's stock kernel has none, so the
  portal adds up the GPU time of your own programs (the games and the desktop among them), or reads GPU Governor's
  corrected metrics when it has set them up. What the system does not report is left out of the line.
- **Install All updates**, a symbol at the top, enabled when the notice names any app; a red badge on it says how
  many, and its tooltip what it does.
  Click it to install them all, updates and reinstalls, one after the other. The portal asks once, with the list, and warns when one of them changes
  the board. Each app's installer runs in its own terminal, as a single install does. When one asks for your
  password, type it in that terminal: the next one waits until it has ended. While it runs, its badge shows which
  one of how many it is at, for example **2/5**. An install that fails does not stop the others; at the end the portal
  names those that failed, and Install in their tiles' menus tries again. **Refresh**, while it waits for a
  terminal that was closed, can stop waiting, and then stops the rest too.
- **Install All apps**, a symbol at the top, enabled when the open category has apps that are not installed yet
  (its tooltip says how many). Click it to install them, one after the other, the same way as **Install all updates**: one question with the
  list and the board warning, each installer in its own terminal, its badge showing which one of how many. It is
  disabled once every app of the category is installed. A portal installed for the first time fills a category with
  one click.
- **☰ Settings**, the symbol at the top right, or the ☰ button on the controller (Start, Options on a PlayStation
  controller): the Settings page, in place of the category strip and the tiles, under the same header. It holds
  the seven settings below, each a pill with a short line beside it; on a small screen the page scrolls, following
  the focus. Move between them with the arrow keys, the
  d-pad or the stick, and press A or Enter to change one. B, Escape or ☰ again goes back to the apps.
- **Icons on Desktop**, on the Settings page (Yes or No; click it to switch): on, every installed app has an icon on the Desktop; off, only the
  portal's icon is there and you start the apps from the portal. The apps stay in the app menu either way, so KDE's
  search and Steam's **Add a Non-Steam Game** still find them. The first time the portal starts with app icons on
  the Desktop, it asks whether to keep them. While the switch is off, the portal removes the icons the apps'
  installers put there, at start and after each install. It only touches the icons of the suite's apps, never its
  own or anything else on the Desktop.
- **Sound**, on the Settings page (Yes or No; click it to switch): the intro plays its sound when the portal opens,
  and every action gives a short sound: each move and button on a controller, each key that acts (the arrow keys,
  Enter, Space, Escape, Tab, Page Up and Page Down, Q, E, U, S, K, M and the Menu key) and each click on a tile, a
  symbol, a pill, a button, a category or a menu entry. Any controller works, also one Steam turns into keys. A key held down
  sounds once, and typing in a text field stays silent. No switches both off. The portal remembers the choice.
  When the board has no audio output, the pill says No and is disabled, and the portal stays silent.
- **Theme switcher**, on the Settings page, showing the theme; click it for the next one: the look of every app in the
  suite. **Gunmetal** (dark, cool blue-gray, the default), **Silver** (light) or **Warm** (dark warm gray with a
  bronze accent). It is one choice for all the apps, kept in `~/.config/bc250-bazzite-suite/theme`; each app takes
  it the next time it starts, the portal too.
- **Wallpaper**, on the Settings page: a picture behind the portal, none until you choose one, and seen through the
  pills that are not active. Click the pill, then
  **Choose a picture…** for your own (**Custom**), **Example wallpaper** to see how one looks with the picture that
  comes with the portal (**Example**), or **No wallpaper** for none. Your picture must be a PNG, JPEG or WebP of at least 1920 x 1080 pixels, in 16:9 (1920 x
  1080, 2560 x 1440, 3840 x 2160); the portal refuses another and says why. It fills the window, under a veil of the
  theme's color so the text stays readable. **Transparency**, a slider in the same menu, sets that veil from 0 to
  90 % (60 % at first): move it up for a dark or busy picture, so the icons stand out, down to see more of the
  picture. The window changes while you move it, and the portal remembers it. The portal keeps a copy in
  `~/.local/share/bc250-bazzite-suite/portal/`, so the original may be moved or deleted; the portal's `--purge`
  removes it. The menu also lists the last 10 wallpapers you chose, newest first, under **Used before**: click one to
  use it again. The portal remembers only where each picture was (in `wallpapers.json` in the same folder), so one
  moved or deleted since shows as not found until it is back.
- **Clock**, on the Settings page, showing **12 h** or **24 h**: how the time in the status line reads. Click it for
  its menu: **12-hour clock (AM/PM)** or **24-hour clock**, **Seconds** on or off, and the time zone: **the board's
  own** (the system's, as at first), **CET** (Central European Time, CEST in summer) or **UTC**. The date follows
  the zone too. The portal remembers the choice.
- **Weather**, on the Settings page, showing the place or **None**: the weather beside the symbols at the top, from
  [Open-Meteo](https://open-meteo.com/), free and without an account. Click it, then **Choose a place…**: type a
  city or town (R3 brings the on-screen keyboard), **Search**, pick the right one from the list and **Use this
  place**. Its symbol (sun or moon, clouds, fog, rain, snow or thunder) and its name then show beside **Install all
  updates**; hover over it for the sky, the temperature, the wind and the humidity, and click it for the same menu.
  The weather comes again every 30 minutes while the portal is not minimized, and **Update the weather now** asks at
  once. When Open-Meteo cannot be reached, the last weather stays and its tooltip says why. **No weather** removes
  it, and nothing goes to Open-Meteo any more. Until you choose a place nothing is sent; see
  [Privacy](privacy.md).
- **Touchpad**, on the Settings page, showing the speed: how fast the touchpad of a DualShock 4 or a DualSense moves
  the mouse pointer. Click it for the next speed: 50, 75, 100 (the normal speed, at first), 125 and 150 %, then 50
  again. The new speed applies at once, and the portal remembers it.
- **Sys info**, a symbol at the top: a small window with what the system reports about the board: the board, the BIOS
  (with UEFI and Secure Boot), the CPU (model, cores and threads online, top clock, microcode), each GPU (name,
  driver, VRAM, shared memory, clock levels, VBIOS, PCIe link), the memory, the drives with the free space in your
  home folder, the displays (each output, the monitor's name and its preferred mode), the sound cards, the network
  adapters and Bluetooth controllers (driver and link), the USB devices, the input devices (keyboards, mice and
  controllers, each with the bus it is on: USB, Bluetooth, PS/2), the sensors (temperatures, fan speeds and
  the GPU's power at that moment) and the OS (version, Bazzite image, kernel, desktop). It is read each time the
  window opens; what a system does not report is left out. **Copy** puts it all on the clipboard as text, for an
  issue or a forum post. It holds nothing personal: no host or user name, no serial numbers, no MAC or IP
  addresses.

## Install

From the [Nexus index](https://github.com/RobertoTorino/nexus/releases/latest), under BC250 Bazzite Suite,
download `portal-v<version>.tar.gz` and `SHA256SUMS`, then:

```shell
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf portal-v*.tar.gz
cd portal-v*/
./install.sh                 # as your own user; asks for the sudo password only for the copies to /opt
```

Later versions install from the portal itself: press Y when it says **UPDATE AVAILABLE** (see **Portal updates**
above).

What it installs:

| What | Where | Why there |
|---|---|---|
| The portal, its `apps.toml` and the `bc250_core` it was tested with | `/opt/bc250-bazzite-suite-v<version>`, root-owned, with `/opt/bc250-bazzite-suite` pointing at it | Same as bazzite-test's engine: code that starts root-run installers is not writable by a normal user |
| BC-250 Bazzite Test (bundled in the portal release) | `/opt/bc250-bazzite-test`, through its own installer | Its test engine runs as root and must be root-owned |
| The suite's shared venv with PyQt6 | `~/.local/share/bc250-bazzite-suite/venv` | One copy of the ~100 MB of Qt for all suite apps; removed with the last app that uses it (`venv-users/`) |
| What the portal installed, and the release each app was installed from | `~/.local/share/bc250-bazzite-suite/portal/` | So each app's matching uninstaller is at hand; an update removes the previous release |
| What the apps found outside the suite, one file per app | `~/.local/share/bc250-bazzite-suite/upstream/` | For **Outside the suite** in the notice; written by the apps, read by the portal |
| Launcher, menu entry, Desktop icon | `~/.local/bin/bc250-bazzite-suite`, `~/.local/share/applications/`, the Desktop | The portal's icon is the one way in; the apps' own icons are optional (**Icons on Desktop**) |

Uninstall: `/opt/bc250-bazzite-suite/install.sh --uninstall`. This removes the portal and Bazzite Test and
keeps settings; add `--purge` to remove those too. First it asks about each other suite app that is installed:
`y` uninstalls it, `s` skips it (it stays installed), `c` cancels the whole uninstall before anything is removed.
The list has every app this portal lists and the apps an earlier portal installed that this one no longer lists (an app dropped from the suite), each removed
with its own uninstaller. Those apps keep their own settings, also with `--purge`. Of the portal's own records,
only those of the apps you kept stay, with the release each one's uninstaller needs; with no app left, that folder
goes too. To remove the whole suite at once, `--uninstall --all` asks one question instead of one per app, after a
warning that names every app it will remove; with `--purge` the apps' own settings, history and results go as
well.

### What stays after an uninstall

Uninstalling an app removes the app. Two things stay on purpose: **changes it made to the board**, which you undo
in the app (or with its script) before you uninstall it, and **your settings and results**, which `--purge`
removes.

| App | Still active on the board after its uninstall | Undo it with |
|---|---|---|
| CU Bisect / Unlock | A persisted CU unlock: `bc250-cu-unlock.service` at every boot | **Uninstall** in the Unlock app, or `sudo /usr/local/sbin/bc250-cu-unlock.sh --uninstall`; stock CUs after the next reboot |
| Cores Bisect / Unlock | A persisted core unlock: its boot service | **Uninstall** in the Unlock app, or `sudo /usr/local/sbin/bc250-cores-unlock.sh --uninstall`; stock cores after the next full power off |
| GPU OC Bisect | The installed overclock in the governor's `config.toml` | **Uninstall** in the app, or `bc250-gpu-oc-bisect.sh --uninstall`: restores the backup |
| Persistent ACPI | The ACPI override (`/boot/acpi_override.cpio` and its GRUB line) | **Uninstall** in the app, or `sudo ./bc250-acpi-override.sh --uninstall`; then reboot |
| ACE Queues | An installed patched driver | **Remove** in the app |
| Memory Manager | The VRAM split in CMOS | Set the split back in the app (or **Undo**) and reboot |

The GPU Manager changes nothing of its own: the governor and its `config.toml` belong to the governor
package, which stays installed. HelixSR keeps the imported payload (`~/.local/share/bc250-upscaler`) and
leaves the games it deployed to as they are; **Remove** each deployment in the app first.

Settings live in `~/.config/bc250-*`, results and logs in `~/.local/share/bc250-*` (Bazzite Test also writes its
reports to `~/Desktop/bc250-bazzite-test`). Each app's `install.sh --uninstall --purge` removes them; the
portal's `--purge` does so for the portal and Bazzite Test.

## Development

Run the portal straight from the checkout. Apps then install from the local source, staged exactly as the
release workflow stages them, so everything can be tried before anything is released. It needs PyQt6, so use the
development venv from [Development](https://robertotorino.github.io/nexus/development/#set-up-and-test) on the Nexus page (Bazzite's own `python3` has no PyQt6):

```shell
cd bc250-bazzite/portal                  # from the repository's root
PYTHONPATH=../../core ../../.venv-linux/bin/python -m bc250_portal    # --source release: the pinned GitHub releases
```

To install from the checkout, run `./install.sh` in the suite's folder, `bc250-bazzite/` (or here in `portal/`). It
bundles the repository's `core/` and installs `../apps/check`. The installed portal then installs the other apps from the
checkout too, so keep the checkout where it is.

## apps.toml and releases

The comment at the top of [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/portal/apps.toml) describes its fields. The rules, checked in CI by
[`bc250-bazzite/tools/check_manifest.py`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/tools/check_manifest.py):

- **Pinned tags.** Every pinned tag must exist when the portal is released. On `main`, a tag may also be the
  next release, which means its version equals that app's `VERSION`.
- **Version bumps.** A change to `apps.toml` needs a `bc250-bazzite/portal/VERSION` bump at least as large as the largest app
  bump it pins: an app patch release needs at least a portal patch release, an app minor release at least a
  portal minor release, and so on. An added, removed or withdrawn app needs at least a minor portal release.
- **Withdrawn releases.** `withdrawn = "<reason>"` in an app's entry withdraws its pinned release (see
  [Withdrawing a release](#withdrawing-a-release)). Not for Bazzite Test, which is always installed.

A release of the suite is a **Nexus release**, made from the Nexus Release Tool's Nexus release tab with one action,
**Start new release**: it writes the versions, the CHANGELOG entries and the new tags in `apps.toml`, commits and
pushes, and [`release.yml`](https://github.com/RobertoTorino/nexus/blob/main/.github/workflows/release.yml), called
by Release Nexus, builds every new app release side by side, publishes each, pins its checksum in a commit *Pin ...*
on `main` and builds the portal as a draft. The draft is installed on a board by the **Device test** (below, [Testing
a portal release before its tag](#testing-a-portal-release-before-its-tag)) and published from the tool when it
works, which makes the portal tag. The steps, one by one, are on the Nexus page:
[The Nexus release](https://robertotorino.github.io/nexus/releases/#the-nexus-release). The same workflow still
builds a tag pushed by hand, one release at a time, which is the way below.

Releasing one app by hand and pinning it in the portal:

1. Bump `bc250-bazzite/apps/<app>/VERSION` (and the copies that `tools/check_versions.py` lists), and update its CHANGELOG.
2. Commit and push, then tag with `tools/tag-release.sh <app>-v<x.y.z>` (it waits until CI passed on that
   commit); [`release.yml`](https://github.com/RobertoTorino/nexus/blob/main/.github/workflows/release.yml) builds
   `<tag>.tar.gz` and `SHA256SUMS` with [`tools/build_release.py`](https://github.com/RobertoTorino/nexus/blob/main/tools/build_release.py).
   An app with a Windows executable (SFTP Tools) also gets a Windows job on its tag, which adds
   `<app-id>-<version>-windows.zip` and its `.sha256` to the release; the portal ignores them.
3. `python3 bc250-bazzite/tools/pin_app.py <tag>`: this sets the tag and checksum in `apps.toml`.
4. Bump `bc250-bazzite/portal/VERSION` as `bc250-bazzite/tools/check_manifest.py` asks, and list the app release in the portal CHANGELOG.
5. Once the pinned app releases are tested together on a BC-250 (see
   [Testing a portal release before its tag](#testing-a-portal-release-before-its-tag)), commit steps 3 and 4,
   push, and tag with `tools/tag-release.sh portal-v<x.y.z>`. That release bundles the pinned Bazzite Test release (`check-v…`).
6. Once `release.yml` has published it, the Nexus index (GitHub's **Latest** release) shows it under BC250 Bazzite
   Suite, where users download the portal: [The releases on GitHub](https://robertotorino.github.io/nexus/releases/#the-releases-on-github) on the Nexus page.

### The release front end

**Nexus Release Tool**, Nexus's release front end, makes these file edits for you and runs the board tests below. How to
start and use it: [Releases](https://robertotorino.github.io/nexus/releases/) on the Nexus page.

### Testing a portal release before its tag

A portal release promises one set of app releases, each with its checksum. Once its tag is out, every installed
portal offers those releases as updates. So before the tag, check on a BC-250 that exactly those pinned releases
install and run.

In a Nexus release the portal is a **draft** on GitHub, built by the workflow with the pins already in it, and the
check is the tool's **Device test** on the Nexus release tab, or by hand:

```bash
bc250-bazzite/tools/check-release.sh draft                 # the draft of bc250-bazzite/portal/VERSION
bc250-bazzite/tools/check-release.sh draft portal-v14.1.0
```

It downloads the draft's tarball and `SHA256SUMS` with `gh` (a draft needs the sign-in: `gh auth login`), checks the
checksum, installs it and starts it, as a user's board will once it is published. Test it as a user would, then
**Publish** in the tool, or **Not OK**, which leaves it a draft. The portal tag exists only once it is published.

For a release by hand, before the portal tag:

1. Bump the portal (step 4) and commit. Pushing is not needed for this test.
2. Click **Test app updates** on the release front end's **Test on this board** tab, or run `bc250-bazzite/tools/check-release.sh local`. It installs the portal
   from the checkout (`./install.sh` in the repository root: this portal version, with its new pins in
   `apps.toml`) and starts it with the pinned releases instead of the checkout:

    ```bash
    bc250-bazzite-suite --source release
    ```

    Apps then install as on a user's board: the portal downloads each pinned tarball from GitHub and refuses it
    unless its checksum matches the pin. Without `--source release`, a portal installed from a checkout installs
    the apps from the checkout.
4. The apps whose pin changed show a red dot and a red Install button. Update them, open each one and check that
   it starts and works; afterwards the red dots and the update count in the header are gone.
5. All good: tag the portal (step 5). Something wrong: fix the app and release a new patch version of it (steps 1
   to 4). Nothing has reached users yet.

This does not test the portal tarball itself, which GitHub builds from the tag; the release workflow checks it
(`bc250-bazzite/tools/check_manifest.py --require-tags`, and the bundled Bazzite Test against its pin). The next section tests
it on the board.

### Testing a portal release after its tag

Once GitHub's release workflow has built the portal release, click **Test Portal release** (tab **Test on this
board**), or run:

```bash
bc250-bazzite/tools/check-release.sh release              # the release of bc250-bazzite/portal/VERSION
bc250-bazzite/tools/check-release.sh release portal-v0.9.2
```

It downloads the release tarball and its `SHA256SUMS` from GitHub into `~/.cache/bc250-release-check/`, checks
the checksum, installs it and starts it. The board then runs the official release, as a user's board does: check
that the portal starts, that its version is the new one, and that the apps install. To go back to the checkout,
run `./install.sh` in the repository root (or Test app updates). A portal from the checkout shows an orange
banner at the top, "Local build"; the published release has none.

### Withdrawing a release

A release that must not be used any more is withdrawn with Nexus Release Tool: the steps are in
[Withdrawing a release](https://robertotorino.github.io/nexus/releases/#withdrawing-a-release) on the Nexus page.
On a BC-250, **Test withdrawal** installs the portal from the checkout and starts it (`check-release.sh local`):
the portal says the app is not available any more, removes it, and then shows **App not available** on its tile.
Bazzite Test, which is always installed, cannot be withdrawn.

### Checking a release

How to build a release's tag yourself and compare it with the published tarball:
[Checking a release](https://robertotorino.github.io/nexus/releases/#checking-a-release) on the Nexus page.

---

### a new app gets into the portal
#### Code

Create bc250-bazzite/apps/<name>/ with VERSION 0.1.0, a CHANGELOG, a LICENSE and a .gitignore. For an app that stays outside the
portal, add `.standalone` instead of adding it to `bc250-bazzite/portal/apps.toml`. An app that runs from the checkout and is
never released also gets `.checkout-only` and stays out of `apps.toml`: the portal lists only released apps.
Add an install.sh that supports --uninstall and puts a launcher in ~/.local/bin/, plus tests under tests/.        
Add the app to ./test.sh, the CI shellcheck list and an installer test in bc250-bazzite/tools/installer-tests/.       
Add its [apps.<name>] card to bc250-bazzite/portal/apps.toml: name, summary, changes_board, category (the same as its icon's in
bc250-bazzite/icons/categories.toml: it is the app's category in the portal), install/uninstall/detect/launch,          
and tag = "<name>-v<VERSION>" with sha256 left empty. CI accepts a tag that doesn't exist yet as long as it matches the app's VERSION.        
Run all the checks and hand over.

#### Release:
5. Commit and push. CI asks for a portal version bump: minor for a new app; for an app update, at least as big as the app's bump.             
6. Tag <name>-v0.1.0. release.yml builds the tarball and SHA256SUMS and publishes the release.              
7. Run python3 bc250-bazzite/tools/pin_app.py <name>-v0.1.0, which fills in the sha256.             
8. Tag portal-v<x.y.z>. The portal release checks with --require-tags that every pinned tag exists, then publishes.             

Users then see the new card, and installed apps whose version differs from the pinned one get the red update dot.                 

#### New Version
- Change bc250-bazzite/portal/VERSION from 0.1.0 to 0.2.0.
- Change __version__ in bc250-bazzite/portal/bc250_portal/init.py:6 to the same number.
