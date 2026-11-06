<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![USB HD Cam](../images/apps/hdcam.webp){ .app-logo }

# USB HD Cam

Makes the **PS5 HD Camera** (CFI-ZEY1) a webcam on Windows. The camera has no memory of its own: it starts as a
boot loader and needs its firmware each time it is plugged in, as a PlayStation sends it. The app gets the firmware
(a pinned, checked download, or a file of your own), gives the boot loader a driver once, and sends the firmware
when you press **A**. Then Windows sees an ordinary webcam, **USB Camera-OV580**, for OBS, a browser, Discord or any
other app. The Picture card shows it full screen in the app itself, with screenshots, recordings, zoom and black and
white. Keep the app open while you use the camera in another app: it
keeps the picture bright (see Keeping the picture bright). The camera has no microphone.

USB HD Cam is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **USB HD Cam**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **A PS5 HD Camera.** Its plug is USB 3 (USB-A): on a handheld with only USB-C ports, a USB-C hub or dock with a USB-A
  port, or an adapter.
- **A USB 3 port** (5 Gbit/s). The boot loader works on a slower one, the video does not.
- **An administrator's password, once per USB port** (or a yes, when your own user is one): see Allow access below.

## The screen

Four cards on the left, **Camera**, **Picture**, **Firmware** and **Bandwidth**; the right side shows what the
focused card does.
The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row at the bottom with
what it does on the pane that shows: **A** included. Press the button, or tap the entry. **B** goes back: from a
list to its card. **⧉** (View) exits the app. **☰** (Menu) opens the information of the pane that shows; the
**information icon** at a pane's top right does the same by touch. Nothing is grayed out: when a button cannot do its
job now, pressing it says why on the pane's status line.

## Camera

Plug the camera in, then press **A** on the Camera card. Nothing is looked for before you do. **A** always does the
next step, and the row at the bottom names it:

1. **A Look for it** finds the camera and shows what it is now: its USB speed, its driver and, once it is a webcam,
   the name apps list it by.
2. **A Allow access**, the first time on a USB port. Windows gives a device without a driver none, so the boot
   loader gets Microsoft's own **WinUSB** driver: the one that ships with Windows, signed by Microsoft, the same as
   picking **WinUsb Device** by hand in Device Manager. Installing a driver takes an administrator, so Windows asks
   once (its prompt may open behind the app). This is the app's only step as administrator, and it installs nothing
   else. Windows keeps a device for each USB port, so another port asks once more.
3. **A Load the firmware** sends the firmware to the boot loader. The camera comes back as a webcam within a second,
   and stays one until it is unplugged. After the handheld slept or restarted, unplug it and plug it in if apps no
   longer see it, then load it again.
4. **A Look again** checks it once more. Once the camera is a webcam, the app also sets its picture (below); **A Look
   again** sets it anew, for instance after you plugged the camera in again.

A **PS4 Camera** on Sony's adapter is found and named, but the app does not load its firmware.

## Picture

The **Picture** card shows the camera's picture full screen, once the Camera card has made it a webcam. **LB Mode
before** and **RB Next mode** choose the mode, named under the title: one camera's picture first, from 1920 x 1080
down to 320 x 184, then both cameras side by side, as the camera sends them for depth (5148 x 1088 is both and smaller
copies of them). Each size comes at its fastest rate that gives a picture; the modes in which the camera sends nothing
are not listed. The app remembers the mode. **A Start** starts the picture.

### Full screen

The picture fills the screen. The row at the bottom holds its buttons, and the line above it shows the mode, the
zoom and, while it records, the recording's time in amber:

| Button | What it does |
|---|---|
| **A Screenshot** | Saves what the screen shows as a PNG in your **Pictures** folder |
| **X Record**, **X Stop** | Starts a recording of what the screen shows, and stops it; it goes to your **Videos** folder |
| **Y Gray**, **Y Color** | Black and white, or color again; the app remembers it |
| **LB Mode −**, **RB Mode +** | The mode before or the next one; the picture starts again in it |
| **LT Zoom −**, **RT Zoom +** | Zooms out or in: 1x, 1.5x, 2x, 3x and 4x |
| **d-pad**, left stick | Moves the zoomed picture |
| **B Back** | Ends the full screen; a recording stops and is kept |

By touch, tap an entry in the row, drag the picture with a finger to move it, or turn the mouse wheel to zoom.
**☰** (Menu) or the information icon shows these buttons.

Screenshots and recordings show what you see: zoomed in and black and white too. Each goes in a **USB HD Cam**
folder, named with the date and the time (`USB HD Cam 2026-11-01 21-04-09.png`); after a screenshot Explorer opens on
that folder with the new file selected. A recording is an MP4 (H.264,
written by Windows' own video encoder) at the mode's size, with at most 30 frames a second. The mode does not change
while it records: stop it first. If the camera stops sending, the screen says so and stays: choose another mode with
**LB** or **RB**. **⧉** (View) asks for a second press while a recording runs, then stops it and keeps the file.

Other apps can show the camera while the picture runs; they get the camera's own picture, in color and not zoomed.

## Keeping the picture bright

Left to itself, the camera keeps a very short exposure (its own Shutter Priority mode), and its picture is close to
black, even in a lit room. So once it is a webcam, the app switches its exposure to automatic, and the Camera card's
**Picture** row
says **Auto exposure, while the app is open**.

Windows switches a camera off as soon as no app uses it, and this camera forgets the setting when it is switched off.
So the app keeps the camera's driver open while it runs, without taking its picture: OBS, a browser, Discord or
Windows' Camera app show the camera meanwhile, with the bright picture. **Leave USB HD Cam open in the background**
while you use the camera; once it closes, the picture is dark again. **⧉** (View) therefore asks for a second press
then.

## Firmware

The firmware is Sony's, so the suite does not ship it.

- **A Download** gets firmware 21.01-03.20.00.04 from
  [github.com/prosperodev/hdcamera](https://github.com/prosperodev/hdcamera), and keeps it only when its size and
  SHA-256 are the ones this version of the app knows.
- **X Pick a file** takes a firmware file of your own (a `.bin`): browse to it with the controller (**A** opens a
  folder or takes the file, **B** goes a level up). The pane says whether the app knows the file. A PS4 Camera's
  firmware is refused.

The file is kept in the suite's folder (see Files) and used for every load.

## Bandwidth

The firmware asks the USB controller for the most video bandwidth USB 3 has. Some controllers refuse it; then the
largest modes give no picture. **A** on a row picks it:

- **Full**, the default: on the ROG XBOX Ally X every mode runs at its full rate, side by side up to 5148 x 1088 at
  30 fps.
- **Reduced**: two thirds of it, for a controller that refuses full. Every one-camera mode still runs at its full rate,
  side by side up to 2560 x 800 at 30 fps; the three largest side-by-side modes give no picture.

The firmware file stays as it is; only the copy sent to the camera changes. It counts from the next load: unplug the
camera, plug it in again and load it.

## How it works

The upload is the one the PS4EYECam driver found and PS Move API uses: the file in 512-byte USB control transfers,
then one byte that starts it, through WinUSB. The camera's USB speed is what its hub reports, as Windows' USBView
reads it. The ready camera is a standard USB video camera, which Windows' own webcam driver (usbvideo) takes.

To take the WinUSB driver off the boot loader again, unplug the camera and plug it in, then in Device Manager:
**Universal Serial Bus devices**, **WinUsb Device**, **Uninstall device**.

## Install it on its own

The portal installs it. To install it on its own, download `wp-hdcam-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-hdcam-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-hdcam-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-hdcam-v<x.y.z>\install.ps1
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
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcam\app\` | The program, `USB-HD-Cam.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcam\windows-portable-hdcam.log` | The log |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-hdcam\firmware\cfi-zey1.bin` | The camera's firmware (kept by `--uninstall`, removed by `--purge`) |
| `%APPDATA%\windows-portable-suite\windows-portable-hdcam.ini` | The settings |
| `Pictures\USB HD Cam\` | The screenshots (your own Pictures folder, wherever Windows keeps it; `--uninstall --purge` leaves them) |
| `Videos\USB HD Cam\` | The recordings (your own Videos folder; `--uninstall --purge` leaves them) |
