<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![PCSX2 Manager](../images/apps/pcsx2.webp){ .app-logo }

# PCSX2 Manager

Installs PCSX2, the PlayStation 2 emulator, on the device and opens it: one tested release, for your own user,
in portable mode.

PCSX2 Manager is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **PCSX2 Manager**). It opens full
screen; **B** closes it.

## The screen

Two cards on the left, **PCSX2** and **Settings**; the right side shows what the focused card does. The d-pad or the
left stick moves the amber focus, **A** acts, **B** closes the app. Every card and pill also works by touch.

## PCSX2

**A** on the PCSX2 card does what its main pill says (Install or Open PCSX2). The pane shows the PCSX2 that is installed, the one this version of the app installs, and its folder.

- **A** on **Install** downloads PCSX2 2.8.2 for Windows from PCSX2's own release on GitHub (26 MB), checks it against
  the checksum this version of the app was tested with, and unpacks it. The page counts the megabytes while it
  downloads. Nothing is downloaded before you press A.
- **A** on **Open PCSX2** starts PCSX2, in its Big Picture mode, full screen, made for a controller (see Settings). It
  runs on its own: closing PCSX2 Manager leaves it open.
- **Remove** removes PCSX2's program. Press it twice: the first press only changes the pill to **Press again to
  remove** for five seconds. Your BIOS, memory cards, save states and settings stay in the folder, so a new install
  finds them again.

**B** during the download asks first: a second **B** within five seconds closes the app and stops the download.

PCSX2 runs in **portable mode** (an empty `portable.txt` beside `pcsx2-qt.exe`): it keeps its settings, the BIOS, the
memory cards and the save states in its own folder, not in Documents. Put your PS2 BIOS in its `bios` folder: the
app tells PCSX2 to use it.

PCSX2 can update itself from its own window. When it has replaced its program with another build, the page says so
and **Y Reinstall** puts the tested release back; what you made stays. A newer PCSX2 comes with a newer version of
PCSX2 Manager, which offers **Y Update to x.y.z**.

## Settings

PCSX2 opens ready to play: right after the install, and each time before it opens, the app sets in PCSX2's settings
(`inis\PCSX2.ini` in its folder):

- its first-start setup skipped (it would ask for what the app already did);
- its own updates off (they would replace the tested release);
- the mouse pointer hidden over a game;
- the BIOS: the dump in its `bios` folder, unless the settings already name one that is there;
- player 1 on the device's controller (PCSX2 maps only the keyboard by itself), the buttons by their place: A is
  Cross, B Circle, X Square, Y Triangle, View Select and Menu Start. Once you map a controller in PCSX2's own window,
  the app leaves player 1 alone;
- View and Menu together end a game, without a question;
- Big Picture mode, full screen.

The last two stay as you set them below: turned off, the app does not turn them on again. Everything else in the file
stays as PCSX2 wrote it. Without a settings file the app starts from PCSX2's own defaults, as PCSX2 2.8.2 writes them
at its first start.

The Settings card's pane has a pill per setting with its value; **A** on one steps to the next value and saves it at
once. PCSX2 reads it the next time it opens; while PCSX2 is open, the pane asks you to close it first, since PCSX2
writes its own settings back when it closes. The **information icon** at the pane's top right says what each one does.

| Setting | Values |
|---|---|
| Renderer | Automatic (PCSX2 chooses), Direct3D 12, Direct3D 11, Vulkan, OpenGL, Software (on the CPU: exact but slow) |
| Resolution | Native (the PS2's), 2x (720p), 3x (1080p, the device's screen), 4x (1440p) |
| VSync | On or Off: no tearing, a little more delay |
| Show FPS | On or Off: the frames a second in a corner |
| Fast boot | On or Off: skips the PS2's start-up screen |
| Vibration | On or Off: the controller's rumble |
| Player 2 | On or Off: a second controller is player 2, with the same buttons |
| Quit with Select + Start | On or Off: View and Menu together end the game |
| Big Picture | On or Off: PCSX2 opens full screen for a controller, or in its desktop window |

The pills show once PCSX2 is installed. A value set in PCSX2's own window that the app does not offer is shown as it
is, and **A** goes on from the first value.

## Install it on its own

The portal installs it. To install it on its own, download `wp-pcsx2-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-pcsx2-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-pcsx2-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-pcsx2-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and PCSX2 with your BIOS and memory cards stay |
| `--uninstall --purge` | also remove the settings, the log and PCSX2's folder, with the BIOS, the memory cards and the save states in it |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\app\` | The program, `PCSX2-Manager.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\emulator\` | PCSX2 (`pcsx2-qt.exe`), its settings, BIOS, memory cards and save states, and `installed.json` (the version and the files the app installed) |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-pcsx2\windows-portable-pcsx2.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-pcsx2.ini` | The settings |
