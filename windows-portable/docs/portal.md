<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Windows Portable Suite](images/wiki-icon.webp){ .app-logo }

# Portal

The portal installs, updates, opens and removes the suite's apps. Each app comes from its own GitHub release, checked
against the checksum the portal carries for it. Windows Portable Test is always installed with the portal and is the
first tile.

Start it from the Start menu (**Windows Portable Suite**) or the Desktop shortcut. It opens full screen with a short
intro; any button, key or tap skips it.

## The apps page

The apps are tiles under tabs: one tab per category that has apps (Sustainable, Graphics, Gaming, Utilities), two
rows of four tiles each. A tile shows the app's icon, its name and its state:

| State | Meaning |
|---|---|
| Not installed | The app is not on this device. |
| Installed x.y.z | The version this portal pins is installed. |
| Update x.y.z | An older release is installed; this portal brings x.y.z. The tile has a red dot at its top right. |
| Installed, version unknown | The app is there, but not installed by this portal. |
| Downloading… 40 MB | The release is coming in. |
| Installing… | Its installer runs in a PowerShell window. |

The strip under the tiles shows the focused app: its name, its versions and what it does.

| Button | What it does |
|---|---|
| D-pad, left stick | Move the amber focus between the tiles |
| LB, RB | The tab to the left or right |
| A | Install the app, or open it once it is installed |
| Y | Update or reinstall the app, when the row at the bottom offers it |
| X | The app's details |
| ☰ (Menu) | The Settings page, with the settings; on it, what the settings do |
| LT | The portal to the next screen, with a second screen attached |
| RT | Steam's library, in Big Picture mode, when Steam is installed |
| R3 (the right stick pressed) | Windows' touch keyboard, shown or hidden; the Settings page shows **R3 Keyboard** |
| B | Back: from a page to the tiles; on a tile nothing |
| ⧉ (View) | Exit the portal |

Every action is a button, in the row at the bottom with what it does for the focused app (**A Install** or **A
Open**, **X Details**, **Y Update**, **☰ Settings**, **RT Steam**, **⧉ Exit app**). Every tile works by touch, and so does the row: a
tap on an entry does what the button does. On a keyboard, the arrow keys move, Enter presses and
Escape goes back.

On the Settings page the setting with the focus has the amber edge; the d-pad stays on the page, and **B** goes back to
the tiles.

## Steam

**RT Steam**, in the row at the bottom of every page, opens Steam's library in Big Picture mode, where the games the
game managers put in Steam are played. A Steam that does not run is started first and opens its library once it has
signed in. Pull RT past halfway, or tap the entry. Without Steam on the device the entry is not there; the game
managers then start a game in its emulator themselves.

## Installing and updating an app

**A** on an app that is not installed downloads its release, checks it and runs its installer in a PowerShell
window. The tile counts the megabytes while it downloads. When the installer is done, the window closes by itself;
when it fails, the window stays open so you can read why, and the strip says so too.

**B** while a download or an installer runs asks first: the strip says what closing does (the download stops; an
installer finishes in its window, but the portal does not record it), and a second **B** within five seconds closes
the portal.

An app the portal installs gets a Start-menu entry in the **Windows Portable Suite** folder and no Desktop shortcut:
you start it from the portal.

**Y** updates an app whose tile says **Update x.y.z**: the portal installs the release it pins over the older one.

## The details page

**X** shows the app's details: the version installed and the one this portal pins, its category and where its
program is. **A Open** opens it and **Y Remove** removes it. Remove asks for a second press within five seconds
instead of a dialog; the row at the bottom says **Press again to remove** meanwhile. **B** goes back to the tiles.

## The Settings page

**☰** shows the Settings page: this portal's version, the newest portal release, and what that release
changes (which apps it updates). With a newer release, the row at the bottom offers **Y Update to x.y.z**;
otherwise **Y Check again**. A portal newer than every published release (a draft on its device test) says so: the
newest release is **older than this portal, which is not published yet**.
The status line at the top right shows the date and the time, and **Suite x.y.z available** while there is one.
The line under it shows the CPU and the GPU live, each with its load and its temperature (**CPU 12% 48°**, **GPU 7%
47°**, read every two seconds from AMD's driver and Windows; on a device without AMD's driver the GPU shows only its
temperature), and the battery last, at the right: its percentage, or **Plugged in** while the device is on its
charger. The apps' status lines show the battery the same way. On the ROG Xbox Ally X, the operating mode's letter
stands just before the battery: **S** Silent, **P** Performance, **T** Turbo or **W** Windows, read from Windows'
power plan and power mode, which Armoury Crate's modes set (`CPU 12% 48°  |  GPU 7% 47°  |  T  |  82%`); the **T**
of Turbo is red. No letter
shows when the plan and the power mode match none of them. Armoury Crate's Command Center keeps its own record of
the mode, so it can show another one.

**Y Update to x.y.z** downloads the new portal; the page counts the megabytes. The portal then closes,
installs the new release in a PowerShell window and starts again. The new release brings the apps it pins: their
tiles then say **Update** where a newer release is pinned.

The settings are on the Settings page too, under the release: how the portal looks and sounds, kept for the next start.
The d-pad moves between them, **A** on a setting changes it; **B** goes back to the tiles. What each setting does
is behind the information icon at the top right of the page: **☰** on the Settings page, or a tap on the icon,
shows it, with the pictures in your wallpaper folder that cannot be used and why, and what each button at the
bottom does.

| Setting | |
|---|---|
| Wallpaper | A picture behind the tiles, which show it through them, in every app of the suite, each from its next start. **A** picks the next: **Off** (the plain dark background), **Built-in** (the suite's own picture), then each of your own pictures, by file name (see below). |
| Transparency | How much of the dark background lies over the picture, so the text stays easy to read. **A** adds 10 %, up to 90 %, then starts at 0 %. It starts at 59 %. |
| Sound | The intro's sound when the portal starts. Off: the intro plays without it. |
| Xbox menu | Only with the Xbox app on the device. **Add** puts the suite in the Xbox app's library, so Xbox mode starts the portal from its home; the Xbox app closes for a moment while its library changes. **In the menu** once it is there; **A** on it takes the suite out of the Xbox app's library again, the Xbox app closed for a moment as well. The Xbox app keeps its library in a file of its own that Microsoft does not document: when a newer Xbox app keeps it otherwise, the row says so and nothing is changed; add the suite in the Xbox app then (**My Library**, **+**). |
| Operating mode | Only on the ROG Xbox Ally X: the active mode (**Other** when the power plan and the power mode match none of them). **A** opens the Operating Mode page, below. |
| Screen | Only with a second screen attached, such as a TV or a monitor: the screen the portal is on. **A**, or **LT** on any page, moves it to the next screen (see below). |

**Your own wallpapers** go in the folder `%LOCALAPPDATA%\windows-portable-suite\wallpapers`, which the installer
makes: paste that address in File Explorer's address bar and drop the pictures there. Only pictures in that folder
are offered, and only those that fill the screen without blurring: PNG, JPEG or WebP, wider than high, at least
1280 x 720 pixels (1920 x 1080 or larger looks sharp on a TV too). The picture is cropped to the screen, never
stretched. A picture that does not follow these rules is named in the page's information with the reason (**Not
used: small.png (800 x 450, smaller than 1280 x 720)**). Take a picture out of the folder and the apps show the built-in
one again. Your pictures stay when the suite is uninstalled.

## The Operating Mode page

On the ROG Xbox Ally X, the Settings page's **Operating mode** row opens a page with the operating modes Armoury
Crate's Command Center offers: **Silent**, **Performance**, **Turbo** and **Windows**. Each row shows the mode's
watt limits on the power source the device is on now (the line under the title: **On the charger** or **On
battery**): sustained, slow and fast, as measured on the Ally X. Armoury Crate keeps one set for the charger and one
for the battery; the rows change when the charger is plugged in or out. The active mode says **(active)**, and has the
focus when the page opens.

| Mode | On the charger | On battery |
|---|---|---|
| Silent | 13 / 16 / 20 W | 13 / 16 / 20 W |
| Performance | 17 / 21 / 26 W | 17 / 21 / 26 W |
| Turbo | 35 / 44 / 55 W | 25 / 30 / 36 W |
| Windows | 17 / 21 / 26 W | 17 / 21 / 26 W |

**Silent** uses the least power and stays the coolest and quietest; **Performance** is the middle; **Turbo** uses
the most and drains the battery fastest, and in a game that already reaches its frame cap it buys nothing.
**Windows** goes back to Windows' own Balanced power plan, with Windows' power mode left as you chose it.

**A** sets the mode with the focus: its power plan and Windows' power mode, at once, as Command Center would, and
its watt limits through the helper (below). The letter in the header follows. The line at the bottom of the page says
what happened: **Turbo set, with its watts: 25 / 30 / 36 W.**, or why the watts were not written. **B** goes back to
the Settings page, **☰** shows what the page does.

**Watt limits**, under the modes: only an administrator may write the watts, so a small helper does, installed once.
**A** on **Install** shows Windows' administrator prompt; after a yes the row says **Installed**. From then on a
mode set here gets its watts too, and the helper sets the whole mode again a few seconds after the charger is plugged
in or out, after Armoury Crate has set its own mode for that power source. **A** on **Installed** removes it, with
the same prompt; uninstalling the suite removes it too. Without the helper, a mode set here leaves the watts as
Armoury Crate set them.

The helper is the suite's one part that runs as administrator. It is a script in
`C:\Program Files\windows-portable-suite\`, which only an administrator may change, run by the scheduled task
**Windows Portable Suite\Operating Mode** (Task Scheduler) as the system account. The portal only names the mode, in
`C:\ProgramData\windows-portable-suite\operating-mode` (one letter); the watts are the helper's own table. What it
did last is in `operating-mode-result` and `operating-mode.log` beside it.

The helper also sets the mode again after a restart: 20 seconds and 2 minutes after you sign in, once Armoury Crate's
services have set their own mode at Windows' start.

Command Center keeps its own record of the mode: after a change here it may still show the mode picked there.

The window fits the screen it is on: it is laid out for the Ally's 1280 x 720 (at Windows' 150 % scaling) and drawn
larger on a larger screen, such as a TV, and smaller on a smaller one.

**With a second screen** attached, such as a TV or a monitor, the portal and the suite's apps open on the screen they
were last moved to, while it is attached, otherwise on Windows' main display. To move one to the other screen, use
the Settings page's **Screen** row or **LT** (the row at the bottom shows **LT Screen** then), or press **Win +
Shift + Left** (or **Right**) with its window in front, which works for every app of the suite; the row at the bottom
shows those keys at its left, after **Switch screen**. The window cannot be dragged: it is full screen, without a title bar. On a screen
of another size the app starts again there, sized for that screen, in a second or two; a download or an install
finishes first, and the portal says it will move once that is done.

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\portal\app\` | The portal's program |
| `%LOCALAPPDATA%\windows-portable-suite\portal\releases\<tag>\` | The release each app was installed from, kept for its uninstaller |
| `%LOCALAPPDATA%\windows-portable-suite\portal\installed.json` | Which release of each app the portal installed |
| `%LOCALAPPDATA%\windows-portable-suite\portal\portal.log` | The portal's log |
| `%APPDATA%\windows-portable-suite\portal.ini` | Its settings: the last tab |
| `C:\Program Files\windows-portable-suite\` | The Operating Mode helper, on the ROG Xbox Ally X once installed from its page |
| `C:\ProgramData\windows-portable-suite\` | The mode the helper applies, its last result and its log |
