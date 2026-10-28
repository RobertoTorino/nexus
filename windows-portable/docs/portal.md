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
| Update x.y.z | An older release is installed; this portal brings x.y.z. |
| Installed, version unknown | The app is there, but not installed by this portal. |
| Downloading… 40 MB | The release is coming in. |
| Installing… | Its installer runs in a PowerShell window. |

The strip under the tiles shows the focused app: its name, its versions, what it does and its pills.

| Button | What it does |
|---|---|
| D-pad, left stick | Move the amber focus between the tiles |
| LB, RB | The tab to the left or right |
| A | Install the app, or open it once it is installed |
| Y | Update or reinstall the app, when the strip shows that pill |
| X | The app's details |
| ☰ (Menu) | The Suite page |
| ⧉ (View) | The Settings page |
| B | Close the portal |

Every tile and pill also works by touch. On a keyboard, the arrow keys move, Enter presses and Escape goes back.

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
program is. Its pills are **Open** and **Remove**. Remove asks for a second press within five seconds instead of a
dialog; the pill says **Press again to remove** meanwhile. **B** goes back to the tiles.

## The Suite page

**☰** shows the Suite page: this portal's version, the newest portal release, and what that release
changes (which apps it updates). With a newer release, its pill says **Update to x.y.z**; otherwise **Check again**.
The status line at the top, with the battery, the date and the time, says **Suite x.y.z available** while there is
one.

**A** on **Update to x.y.z** downloads the new portal; the page counts the megabytes. The portal then closes,
installs the new release in a PowerShell window and starts again. The new release brings the apps it pins: their
tiles then say **Update** where a newer release is pinned.

## Settings

**⧉** (View) shows the Settings page: how the portal looks, kept for the next start. **A** switches the focused
setting, **B** goes back.

| Setting | |
|---|---|
| Wallpaper | A picture behind the tiles, which show it through them. Off: the plain dark background. |

The window fits the screen it is on: it is laid out for the Ally's 1280 x 720 (at Windows' 150 % scaling) and drawn
larger on a larger screen, such as a TV, and smaller on a smaller one.

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\portal\app\` | The portal's program |
| `%LOCALAPPDATA%\windows-portable-suite\portal\releases\<tag>\` | The release each app was installed from, kept for its uninstaller |
| `%LOCALAPPDATA%\windows-portable-suite\portal\installed.json` | Which release of each app the portal installed |
| `%LOCALAPPDATA%\windows-portable-suite\portal\portal.log` | The portal's log |
| `%APPDATA%\windows-portable-suite\portal.ini` | Its settings: the last tab |
