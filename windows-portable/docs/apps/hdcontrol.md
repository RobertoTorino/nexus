<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![HD Controller](../images/apps/hdcontrol.webp){ .app-logo }

# HD Controller

The **DualSense** and **DualSense Edge** controllers on your Windows handheld: their battery, their firmware, a test of
their buttons, sticks, motors and light bar, and the Edge's profiles. Officially the controllers' firmware is updated
on a PS5 and in an app for Windows. This app sends the same firmware, from the official update server, over a USB
cable.

Windows' own driver drives the controller, so games and Steam see it as usual. The app talks to the controller beside
it, as a HID device, the way Windows gives one to every user: it needs no driver, no rule and no administrator.

HD Controller is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **HD Controller**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **A DualSense or DualSense Edge**, plugged in with a USB-C cable or paired over Bluetooth (hold **Create** and the
  **PS** button until the light bar flashes, then pair it in Windows' Bluetooth settings).
- **A USB cable** for the firmware update and for changing the Edge's profiles: neither goes over Bluetooth.

## The screen

Five cards on the left, **Controller**, **Test**, **Firmware**, **Profiles** and **Settings**; the right side shows
what the focused card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in
the row at the bottom with what it does on the pane that shows: **A** included. Press the button, or tap the entry.
**B** goes back: from a list to its card, from a page to where it came from. **⧉** (View) exits the app. **☰**
(Menu) opens the information of the pane that shows; the **information icon** at a pane's top right does the same by
touch. Nothing is grayed out: when a button cannot do its job now, pressing it says why on the pane's status line.
An action that needs care asks for a second press within five seconds; the row at the bottom says **Press again**
meanwhile.

## Controller

While no controller is connected, the pane shows a drawing of the controller with a USB-C cable going into its
port. The app finds the controller by itself once it is plugged in or paired.

Nothing is read from the controller before you press **A** (**Read**) on the Controller card. Then the app reads its
firmware and its profiles, and follows it: the card shows its model, its connection and its battery, for example
**Edge · USB · 85 %**. From then on, the app reads each controller as it connects, until it closes. **A** again
(**Read again**) reads it anew, for instance after you changed its profiles on a PS5.

The pane lists what the controller reports: its model and connection, the firmware it runs (as the update server
numbers it, for example `0x0217`, with its build date), the firmware's target, the hardware version, the battery,
the light bar's color and **Reports**, how many input reports a second it sends now. Steady and high is a good
connection; a low or jumpy number over Bluetooth points to interference or distance.

The battery stands at the right as a phone shows it, with the percentage inside it: five modules from the bottom up
for the level, amber at 20 % or less, red at 10 % or less. While the controller charges, the modules above its level
fill one after another. The controller reports its level in tens of percent.

With two or more controllers connected, **LB** and **RB** choose the one the app shows; the card says which, for
example **1 of 2**.

**☰** (Menu) shows the controller's spec sheet: what it reports now, the model's specifications with the official
source of each (for the DualSense Edge its instruction manual and the PlayStation Blog: model CFI-ZCP1, released 26
January 2023 at $199.99, a 1,050 mAh battery, about 325 g), and the parts the drawing leaves out because the controller
does not report them: the L2 and R2 stop sliders, the RELEASE latch, the reset button, the headset jack, the charging
contacts, the microphone and the speaker. The plain DualSense has no specifications in the app yet: only facts from an
official source go in.

## Test

The drawing follows your controller live: a button lights while you press it (the Edge's Fn and back buttons too),
the sticks move and the triggers fill as far as you pull them. A tap on a part names it (Cross, L2 trigger, Left
back button, Light bar). The drawing is the app's own, with the face buttons in the colors of the first PlayStation
pads.

- **A** (**Start the test**): from then on every button of every controller only lights the drawing. The controller
  you test is also one the app answers to (its Cross is A, its Circle B), so during the test it does not move the
  app. **Hold B for two seconds** to end the test, or tap **B** in the row at the bottom.
- **X** (**Test vibration**) runs the left motor, then the right one, almost a second each, and the drawing shakes on
  that side: you should feel each on its own side. A motor that stays still while the drawing shakes is worth a
  closer look.
- **Y** (**Light bar**) gives the light bar the next color: Blue, Red, Green, Purple, White, Off, and **as the system
  sets it**, where the app leaves it alone. The app sets the color at once and again each time the controller
  connects while the app is open; the drawing shows it. The controller does not keep it: it forgets it when it
  disconnects, and Steam or a game may set another. **Off** saves some battery.

The five small lights under the touchpad are the player indicator. Steam or a game sets them; Windows does not say
which are on, so the drawing shows them dark.

## Firmware

**Y** (**Check for an update**) asks the official update server (`fwupdater.dl.playstation.net`) for the latest
version of each controller. With **Check for an update when the app opens** on (the default, on the Settings card),
the app asks by itself, at most once a day. The pane shows the firmware installed, the latest official one and when
the app last asked. The Firmware card turns amber when a newer version is out.

**A** (**Update**) asks first, on the status line: it names the version, what the controller runs, the file's
SHA-256 check and the battery's level. Press **A** again within five seconds, and the app:

1. downloads the firmware from the update server (about 1 MB) and keeps it, so a second try needs no network;
2. checks that it fits: the firmware names the controller it is for (its USB product ID and its *target*), and its
   version must be newer than the one the controller runs;
3. saves a backup of the Edge's profiles (see [Profiles](#profiles));
4. sends it to the controller. The pane shows the cable plugged in, data flowing down it and the touchpad filling,
   with the step and the kilobytes sent.

It takes about half a minute. The controller then checks the firmware's signature, switches to it and restarts. It
leaves USB for a moment and comes back; the pane then shows the new version. The profiles stay as they were. The
Bluetooth pairing does not: to use the controller without the cable again, remove it from Windows' Bluetooth settings
first, then pair it anew.

Before it starts:

- **Connect the controller with a USB cable.** The update does not go over Bluetooth.
- **Quit Steam** (Steam, Exit), and DS4Windows, DSX or another program that talks to the controller. The app names the
  one that runs and does not start while it does, so that nothing else talks to the controller during the update.
- Leave the cable in until the pane says the update is done. The update cannot be stopped halfway: the app does not
  close while it runs.

If the controller refuses the firmware or stops answering, the pane says what it reported. Unplug the controller and
plug it in again: the pane then shows which firmware it runs, and the update can be tried again.

**X** (**Use a file**) sends a firmware file you have, for example one kept from the update server before. Pick it
with the controller: **A** opens a place or a folder and picks a file, **B** goes a level up. The app checks it the
same way, refuses a file for another controller or one that is not newer, and asks for the second press.

### The firmware files

The update server has one file per *target* and only the latest version of it. The DualSense's target depends on its
revision; the DualSense Edge's is `0044`. The app knows the files that were on the update server on 23-10-2026 by their
SHA-256:

| Target | Controller | Version | SHA-256 |
|---|---|---|---|
| `0044` | DualSense Edge | `0x0217` | `c157eec635f809232e06c255a0847e6b915b0032ca661b12ae35fb2e4eac49df` |
| `0004` | DualSense | `0x0630` | `861ad95a99b16805ff20f5690372988662c4f69c6ad0b266e793d7fc2292315a` |
| `000B` | DualSense | `0x0630` | `b66528795683d214ca06fe4672d298de75bf019bd5046442cbec63fc02974f86` |
| `000E` | DualSense | `0x0641` | `b9c217d8ded5f09f03034e7e5037af0c174c3c77a3cbd201ee5fd219ee448fc8` |

A newer file from the update server works too; the question then says the app does not know it yet. The controller
checks its signature either way. The files are kept in the app's `firmware` folder (see [Files](#files)), named after
their target and version (`FWUPDATE0044-0217.bin`). The pane names the kept file of the latest version with its
SHA-256 check: a ✓ for a file the app knows, a ! for one it does not.

## Profiles

The DualSense Edge keeps four profiles; Fn and Triangle, Square, Cross or Circle chooses one (Triangle is the default
profile). The pane shows them as rows, as the controller reports them; the one the controller uses now says
**Active**, and follows when you switch with Fn. Under the rows, what the focused one sets: each stick's curve
(Default, Quick, Precise, Steady, Digital or Dynamic), each trigger's range, and the buttons that send something other
than themselves (the back buttons included); the drawing beside it lights the Fn buttons and what the profile changes.
A profile whose checksum does not match is marked.

With the controller on the USB cable:

- **A** on an empty slot (**Create**) makes a profile there, starting from the default profile's settings; on a
  profile (**Edit**) it changes it.
- **X** (**Clear**) removes a profile from the controller, on a second press.

The default profile (Fn + Triangle) is never changed. Over Bluetooth the profiles are read and backed up, not changed.

**Y** (**Back up**) saves them in a JSON file, exactly as the controller holds them, and **LT** (**Read again**) reads
them anew. The app also saves a backup before every firmware update and before every change to a profile, in the
app's `profiles` folder (see [Files](#files)).

### The editor

A page of rows, one for each setting. **A** gives the row with the focus its next value, **X** the one before; the
d-pad moves between the rows.

- **Name**: **A** opens a page to type it, up to 39 characters; **R3** opens Windows' touch keyboard, **A** takes the
  name, **B** goes back without it.
- **Sticks**: each stick's curve (Default, Quick, Precise, Steady, Digital or Dynamic) and its sensitivity, 0 to 10.
  A profile made on a PS5 says **as it is**: its curve stays exactly as it was until you change the curve or the
  sensitivity.
- **Triggers**: where on its travel L2 and R2 start and stop counting, in steps of 5 %.
- **Buttons**: what each one sends, the back buttons included: its own, another button, Options or the touchpad's
  click.

**Y** (**Save to the controller**) saves a backup of all four profiles, writes the profile, and reads it back to
check that the controller kept it. If it did not, the pane says so and names the backup. **B** goes back and saves
nothing. The parts of a profile the app does not show stay as the controller holds them.

The controller applies a profile itself: after Fn + Square, a button you set to send another sends that one, and the
sticks follow their curves (on Digital a stick jumps to the edge). The triggers' range is kept in the profile; whether
a game on Windows uses it is up to the controller and the game.

The plain DualSense has no profiles.

## Settings

- **Check for an update when the app opens**: **A** switches it on or off.
- **Show the introduction**: the three short pages shown after the first controller was read, on what the app does,
  the firmware update and the Edge's profiles (the battery, on a plain DualSense). **A** goes to the next page, **X**
  to the one before, **B** skips the rest.

## A controller on Bluetooth

A controller left on over Bluetooth drains its battery in a few hours. To switch it off, hold the PS button for ten
seconds, or disconnect it in Windows' Bluetooth settings; the PS button switches it on again.

Over Bluetooth a DualSense first sends a short report without its touchpad, motion and battery. The app asks it once
for its calibration, as Steam and Linux's driver do, and it then sends its full reports; the app changes nothing on
the controller by that.

## Install it on its own

The portal installs it. To install it on its own, download `wp-hdcontrol-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-hdcontrol-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-hdcontrol-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-hdcontrol-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log, the firmware files and the profiles' backups stay |
| `--uninstall --purge` | also remove those |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\app\` | The program, `HD-Controller.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\windows-portable-hdcontrol.log` | The log |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\firmware\` | The firmware files from the update server |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcontrol\profiles\` | The backups of the Edge's profiles |
| `%APPDATA%\windows-portable-suite\windows-portable-hdcontrol.ini` | The settings |

## Credits

The update protocol comes from [dualsense-updater-rs](https://github.com/nchie/dualsense-updater-rs) (nchie), the
layout and writing of the Edge's profiles from
[dualsense-edge-profile-web-application](https://github.com/steffalon/dualsense-edge-profile-web-application)
(steffalon). The firmware report, the battery and the output reports are read and written as Linux's
`hid-playstation` driver does it. The code ported from the two projects above is MIT; the app's README keeps their
notice. The controllers' firmware is Sony's and is not part of the app.
