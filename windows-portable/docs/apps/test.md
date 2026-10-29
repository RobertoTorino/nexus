<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Windows Portable Test](../images/apps/test.webp){ .app-logo }

# Windows Portable Test

Gets to know a **Windows portable device**: what Windows reports about the device, how its network does, and every
button, stick and trigger of its controller as you press them. It reads and shows; it changes nothing on the device.

Windows Portable Test is always installed with the [portal](../portal.md) and is its first tile. Open it there with
**A**, or from the Start menu (**Windows Portable Suite**, **Windows Portable Test**). It opens full screen.

## The screen

Five cards on the left: Device, Hardware, Connected, Network and Controller; the right side shows what the focused
card does.
The d-pad or the left stick moves the amber focus between the cards, **A** runs the focused card, **B** closes the
app. Every card and pill also works by touch. The amber edge shows where you are: on a card with a glow under it,
and on the pane at the right, with its card keeping only the edge, once the focus moves into it. The top right
shows the date and the time,
`Wednesday 28/10/2026 | 17:04`, and under them, live every five seconds, the CPU's and the GPU's temperature, the
power the chip draws, the refresh rate of the screen and the battery: `CPU 47° GPU 45° | 18 W | 120 Hz | 82%`. On a
device with AMD graphics the temperatures and the power come from AMD's driver; on another the GPU's temperature
comes from Windows (as Task Manager shows it), and the CPU's and the power are left out. The refresh rate is the
screen the window is on: docked to a TV, it is the TV's.

The wallpaper the portal shows is behind its cards too, unless it is switched off in the portal's Settings.

The information icon (a ring with an i) at the top right of a pane opens more about it, over the window; **A** or
**B** closes it.

## Device

What Windows reports about the device: its name, the processor with its cores and threads, the graphics
and its driver, the memory (installed and usable), the storage, the screen the window is on (its pixels, Windows'
scaling and the refresh rate), Windows' version, the firmware and the battery. No serial numbers.

Nothing is read until you ask: press **A** on the Device, Hardware or Connected card, or tap **Read**. One read
fills all three; Windows takes about four seconds to answer. **Read again** reads it once more.

**X** saves what the three cards show as one text report in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\reports\` (`device-<date>-<time>.txt`), a section per
card, with the Network card's last when it was measured; the card says where.

## Hardware

What is built in: the panel's size (Windows gives it in whole centimeters, so the inches are rounded), the touch
screen and how many touch points it takes, the Wi-Fi adapter with its driver, the Bluetooth adapter, audio, the
fingerprint reader, a camera, the sensors (such as the accelerometer) and the USB controllers (USB4 shows here). Of
Bluetooth only the adapter is listed, never a paired device, and no MAC address is read.

## Connected

What is plugged in: a dock or a hub, the screens beside the built-in one (with how they are connected, such as
DisplayPort or HDMI), network adapters on USB (a dock's Ethernet port) and drives on USB. Windows does not tell a dock
from a hub: a dock is a USB hub with ports behind it, so the card shows the hub's maker (such as Realtek, USB 3 and
USB 2) and what is behind it. With nothing plugged in, the card says so.

A screen on a dock's or a stand's HDMI port shows as **DisplayPort**: the device sends the picture as DisplayPort
over USB-C, and the dock turns it into HDMI.

## Network

How the network does at this moment, to compare a slow moment with a fast one, on mains and on battery. **A** on the
Network card, or **Test**, measures it; it takes about fifteen seconds. **Test again** measures once more.

| Row | What it shows |
|---|---|
| Wi-Fi | The band (2.4, 5 or 6 GHz) and the channel |
| Standard | Wi-Fi 6 (802.11ax), Wi-Fi 5 (802.11ac) and so on |
| Signal | The signal in percent and in dBm |
| Rate | The link's rate down and up, in Mbps: what the adapter and the access point agreed, not the download speed |
| Power | Mains or battery, and the power plan |
| Wi-Fi on mains, Wi-Fi on battery | The power plan's Wi-Fi setting: Maximum Performance to Maximum Power Saving |
| Other traffic | What the device received in the two seconds before the download |
| Also running | Delivery Optimization's downloads (Windows Update, the Microsoft Store and the Xbox app's games) and the programs that download on their own: Steam, the Xbox app, the Epic Games Launcher, Windows Update and others |
| Download | The speed of a timed download: Windows Portable Test's newest release from GitHub, as the portal downloads it, for ten seconds at most. Nothing is kept |

A slow download with a good link (a high rate and signal) points past the device: the access point, the internet
connection or GitHub at that moment. Without Wi-Fi (on a dock's Ethernet port) the card says so and still times the
download. The network's name and the access point's address are never read out.

**X** saves the measurement in the same report as the device, as its Network section.

## Controller

**A** on the Controller card starts the test. Every button lights amber while you hold it and keeps an amber label
once it answered, so a button that never answers stands out; the count under them says how many answered. The sticks
show as a dot in a circle with their position, the triggers as a bar from 0 to 100 %.

During the test every button is the test's, B too: **hold B** for a second and a half, or tap **Finish**, to end it.
On a keyboard, Escape ends it.

The buttons on the card are those Windows reports for an Xbox controller: LB, View, Xbox, ☰ (Menu), RB, the d-pad,
A, B, X, Y and the two stick presses, and on an ASUS device such as the ROG Xbox Ally X the **back buttons M1 and
M2** as one chip, **M1/M2**. They are Armoury Crate's own modifiers (held with A a screenshot, with Y a recording),
never gamepad buttons, and Armoury Crate reports either of them the same way, so Windows cannot tell M1 from M2: the
chip lights for both. To use them as two buttons, map them in Armoury Crate (Settings, Configure, M1 or M2: untick
Secondary Function and choose a button); they then light that button. A device without ASUS's channel shows no
M1/M2 chip, and the count leaves it out. The information icon at the top right of the Controller card's pane says so
on the device; it opens before or after the test, not during it.

## Stick lights

The light icon (a bulb in a ring) beside the information icon opens the stick lights' test over the window. Its
pills set the lights around the sticks: **Red**, **Green**, **Blue** or **White** on both, **Left only** or **Right
only** in white with the other stick dark, and **Off**. The d-pad moves between them, **A** presses one, and the line
under them says what it did. Above the pills is what Windows reports: the controller, its lamps (four on the ROG
Xbox Ally X, two around each stick) and whether Dynamic Lighting is on for it.

The app sets the lights through Windows' Dynamic Lighting, and Windows lets it do so only while its window is in
front. **Close** (or **B**) gives them back to the app that sets them otherwise, such as Armoury Crate; Windows does
so too when the window closes or another one comes in front. Without lights Windows can set, the popup says so: where
a controller has them, switch Dynamic Lighting on in Settings > Personalization > Dynamic Lighting and open it
again. Like the information icon, it opens before or after the button test, not during it.

## Install it on its own

The portal installs it. To install it on its own, download `wp-test-v<x.y.z>.zip` and `SHA256SUMS` from its
release, then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-test-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-test-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-test-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and the reports stay |
| `--uninstall --purge` | also remove the settings, the log and the reports |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\app\` | The program, `Windows-Portable-Test.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\reports\` | The saved reports |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\windows-portable-test.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-test.ini` | The settings |
