<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Smart Screen](../images/apps/smart.webp){ .app-logo }

# Smart Screen

Shows the handheld's live values on a **Turzx USB IPS screen**: the Turing Smart Screen 3.5" and the UsbMonitor
3.5", 5" and 7" of the same family. CPU, GPU, temperatures, power, memory, battery, network and disk, with the time,
the date and the weather if you want them, in six themes or your own colors. It is the BC250 Bazzite Suite's
[USB IPS3.5](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/ips35/) made for the handheld, and it
takes the place of the screen maker's own app (UsbMonitor).

Smart Screen is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Smart Screen**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **The screen**, plugged into the handheld or into its dock. It needs no driver: Windows gives it its own serial
  driver and makes it a COM port (such as COM3) by itself. Nothing needs an administrator.
- **The screen maker's app closed.** One program at a time can use the screen; while UsbMonitor has it, the Screen
  card says **In use by another program** and the app tries again by itself.

## The window

Six cards on the left, **Screen**, **Values**, **Look**, **Clock**, **Weather** and **Start**; the middle shows the
focused card's rows, and the right side the picture the screen shows now. The d-pad or the left stick moves the amber
focus. Every action is a button, listed in the row at the bottom with what it does where the focus is: **A**
included. Press the button, or tap the entry. **B** goes back, from a row to its card. **⧉** (View) exits the app;
while the screen is connected, it asks for a second press. **☰** (Menu) opens the information of the pane that
shows; the **information icon** at a pane's top right does the same by touch.

A row with choices steps to the next one with **A** or **RB**, and back with **LB**. The screen and the picture
beside the panes change at once.

The app looks for the screen as soon as it opens: that is its work. The first time it finds it, it restarts the
screen once, so it starts from a clean state (a picture cut off halfway before would shift everything after it).
Then it sends the picture every second, only the parts that changed: a few KB, where the whole screen takes almost
two seconds. A screen unplugged and plugged in again is found again and gets the whole picture.

## Screen

The screen's state: which screen it is, its COM port, its size and how much the last update sent.

| Row | What it does |
|---|---|
| Brightness | **A** and **RB** brighter, **LB** darker, in steps of 10 %. |
| Orientation | Portrait, Landscape, and each upside down: how the screen stands. Turn it upside down when its USB cable is at the bottom or on the other side. Lying down, the tiles go in two columns. |
| Backlight | **A** switches the screen dark and back on; the app keeps running. It is on at every start. |
| Save the picture | What the screen shows, at its own size, as a PNG in your Pictures folder, in a Smart Screen folder. |
| Save a report | Every value at this moment, with the date, the time and its offset from UTC, as a text file in your Documents folder, in a Smart Screen folder. |

## Values

What the screen shows, a tile each, in this order; **A** puts a value on the screen or takes it off. At first: CPU,
GPU, Power, RAM, Battery and Network.

| Tile | What it shows |
|---|---|
| CPU | The CPU's load, with its clock and temperature. |
| GPU | The GPU's load, with its temperature. |
| CPU temp, GPU temp | The temperature in large, with a bar from 0 to 100 °C. |
| Power | The power the whole chip draws, CPU and GPU together. |
| RAM | The memory in use, of what Windows has after the graphics took its share. |
| Battery | The charge, and whether the charger is in. |
| Network | Download and upload. |
| Disk | Reads and writes of the drives. |
| Weather | The temperature and the sky at the place chosen on the Weather card. |

A temperature turns orange from 80 °C and red from 90 °C; on battery, the charge turns orange at 20 % and red at
10 %. The **Network adapter** row picks the adapter the Network tile measures, or all of them added up.

The temperatures, the power and the GPU's load come from AMD's driver, as in Windows Portable Test. On a handheld
without it, the GPU's load is Windows' own and the CPU's temperature and the power show **—**. Windows does not report
a fan.

## Look

| Row | What it does |
|---|---|
| Theme | Dark (with the suite's amber), Light, Midnight, Ember, Forest or Mono. |
| Text, Tiles, Accent and Background color | Your own color instead of the theme's, from a palette of fourteen. **X** puts the theme's back. |
| Header text | Your own text in the screen's header, up to 24 characters: **A** opens a page with a field, **R3** (the right stick pressed) Windows' touch keyboard, **X** pastes what you copied, **A** keeps it. At first it is the handheld's name as its firmware gives it (ROG XBOX Ally X); empty, the header shows only the time. |
| Background | A picture of your own behind the tiles, cut to the screen's shape: **A** opens the browser (your usual folders and every drive; **A** opens a folder or takes the picture, **B** goes up), **X** takes it away. PNG, JPEG, WebP or BMP. The app keeps where the picture is, not a copy: leave it there. |

## Clock

The time in the screen's header is Windows', in its time zone: summer and winter time follow by themselves.

| Row | Choices |
|---|---|
| Time | 24-hour, or 12-hour with AM and PM. |
| Time zone | Not shown, or its offset from UTC (UTC+1 in winter, UTC+2 in summer in Amsterdam). |
| Date | Not shown, the weekday with the day and the month, DD-MM-YYYY, MM/DD/YYYY or YYYY-MM-DD, under the time. |

## Weather

The weather comes from [Open-Meteo](https://open-meteo.com/), free and without an account. **A** on the **Place** row
opens a page to type a city or a town; the places found are listed under it, and **A** on one uses it and puts the
Weather tile on the screen. **No weather** forgets the place.

What is sent: the name you search for, and then the place's coordinates every 30 minutes, only while the Weather
tile is on the screen. Nothing else about you. Without a place nothing goes over the network.

## Start

| Row | What it does |
|---|---|
| Start with Windows, minimized | A shortcut in your Startup folder (nothing in the registry): the app starts minimized when you sign in, and the screen shows the values from then on. Only the app installed from the portal starts so. |
| When the app closes | The screen goes dark, or keeps the last picture it had. |
| Run in the background now | Minimizes the app. The screen goes on showing the values, and the controller belongs to your games again: the app acts only while its window is in front. It comes back from the taskbar or from the portal. |
| The app's log | Read in the pane: the d-pad scrolls it, **B** goes back. |

## Install it on its own

The portal installs it. To install it on its own, download `wp-smart-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-smart-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-smart-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-smart-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings and the log stay |
| `--uninstall --purge` | also remove the settings and the log |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-smart\app\` | The program, `Smart-Screen.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-smart\windows-portable-smart.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-smart.ini` | The settings |
| `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Smart Screen.lnk` | Start with Windows, while it is on |
| `Pictures\Smart Screen\`, `Documents\Smart Screen\` | The pictures and reports you saved; never removed by the app |
