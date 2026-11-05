<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Upscale Boost](../images/apps/upscale.webp){ .app-logo }

# Upscale Boost

HelixSR, the DLSS-like upscaler for AMD graphics, in your games: its build, deployed per game and set.

[HelixSR](https://github.com/lonewolf0622/HelixSR) runs NVIDIA's DLSS upscaling network on AMD graphics. A game talks
to it as AMD FSR 3.1: HelixSR takes the place of the game's own FSR 3.1 DLL, and you choose **AMD FSR** in the game.
Upscale Boost gets HelixSR, builds its network on your handheld, puts it into your games and takes it out again, and
sets HelixSR's settings. It is the BC250 Bazzite Suite's BC-250 Upscaler Manager, made for a Windows handheld.

Upscale Boost is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Upscale Boost**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

Whether HelixSR helps a game, and how much, depends on the game and the graphics chip. Include the game's
`helixsr.log` (next to HelixSR's DLL in the game's folder) when you report a problem at
[HelixSR](https://github.com/lonewolf0622/HelixSR/issues).

## What you need

- **A game with AMD FSR 3.1** as a DLL of its own (`amd_fidelityfx_upscaler_dx12.dll` or `amd_fidelityfx_dx12.dll`).
  A game with only DLSS, XeSS or FSR 2 can use HelixSR through OptiScaler (see [OptiScaler](#optiscaler)).
- **About 1.5 GB of free space** while HelixSR is built, and an internet connection for the downloads.
- **Steam**, to find your games and start them (optional: you can add any game folder by hand).
- No administrator: everything runs as your own user. A game in Steam's folder is yours to change.

## The screen

Five cards on the left, **HelixSR**, **Games**, **Deployments**, **Settings** and **Log**; the right side shows what
the focused card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row
at the bottom with what it does on the pane that shows: **A** included (**A Get HelixSR**, **A Run with HelixSR**,
**A Change**). Press the button, or tap the entry. **B** goes back: from a list or a page to where you came from, from
a pane to its card on the left (on a card it does nothing). **⧉** (View) exits the app. **☰** (Menu) opens the
information of the pane that shows; the **information icon** at a pane's top right does the same by touch.

Nothing is ever grayed out: when a button cannot do its job now, pressing it says why on the pane's status line. What
needs care asks for a second press within five seconds: the entry says **Press again** meanwhile.

## HelixSR

The pane shows the payload (your built copy of HelixSR: its version, whether its network is built, whether it has
OptiScaler), the newest HelixSR release on GitHub, the version to get, and where NVIDIA's DLL comes from. Under the rows
are the newest lines of the build's output.

- **A Get HelixSR** (also **A** on the HelixSR card) gets the newest HelixSR 2.x release and builds it:
    1. It downloads the release from GitHub and checks it against the SHA-256 GitHub publishes for it.
    2. It reads what HelixSR's own setup (`helixsr-setup.ps1`) pins, and downloads at the same time what is not here
       yet, each checked: NVIDIA's DLSS 310.7.0 DLL (59 MB, from NVIDIA's GitHub, under NVIDIA's license), Python
       with numpy, and Microsoft's DirectX Shader Compiler.
    3. It runs HelixSR's own builder (`setup\helixsr_setup.py`, unchanged), without a console window, and keeps the
       result as the payload. NVIDIA's DLL is deleted afterwards.

    It takes a few minutes. The pane counts the megabytes and shows the builder's output; the log keeps all of it.
    **X Cancel** stops it. When the payload already has that version, **A** asks for a second press.
- **Y Check now** asks GitHub for the newest HelixSR. The app also asks at every start, unless the Settings card's
  **More** tab turns that off. A newer HelixSR shows as a red dot on the HelixSR card.
- **LB** switches the version to get: the latest release, or **HelixSR 1.8.1**, the version HelixSR's developer
  recommends when the latest one does not work for you. 1.8.1 also brings OptiScaler, which the payload keeps when you
  switch back to the latest.
- **RB NVIDIA's DLL** opens a page: **Download it from NVIDIA** (the default), a copy a game you own ships
  (**Y Find in Steam** lists only the files with the exact checksum HelixSR pins), or **Pick a file**. A local copy
  saves NVIDIA's download.
- **LT Import** takes a HelixSR release you built yourself: open its folder in the browser and press **X**, or press
  **A** on its zip. The newest release the app built is the first place listed. Only HelixSR's own files are copied.

The app sets up HelixSR 1.x and 2.x. When a later major version is out, the **Latest release** row says so, and the app
keeps getting the newest release it supports.

HelixSR's own setup would go on to install HelixSR into every game it finds, and builds frame generation too. The app
does neither: it builds the network only, and your games change only from the Games and Deployments cards.

What the builder makes contains NVIDIA's software: it is for your own device. The app never shares or uploads it.

## Games

Every Steam game on the handheld (from every Steam library, an SD card's too), and the folders you added. Each game is
looked through for an FSR 3.1 DLL; the games that have one come first, with HelixSR's state: **Not installed**,
**HelixSR 2.0.0 installed**, an older build with **is available**, or **The game put its own DLL back** (after a game
update or Steam's file check). The line at the bottom shows where the game's DLL is.

- **A Run with HelixSR** puts HelixSR in where it is missing, older, or replaced by the game's own DLL, then starts
  the game through Steam. The first time for a game, it asks for a second press. It does nothing while the game runs.
  Choose **AMD FSR** in the game's graphics settings.
- **A Put HelixSR in**, on a folder you added: the same, without starting the game. Start it as you always do.
- **Y Go back** takes HelixSR out: its files go, and the game's own DLL gets its name back. Press it twice.
- **X OptiScaler**, for a game without FSR 3.1 (see [OptiScaler](#optiscaler)).
- **LB Add a folder** opens the browser: open a place, then the game's folder, and press **X**.
- **RB Take off the list**, on a folder you added: the game itself stays as it is.
- **LT Rescan** looks through every game again.

The game's own DLL is kept beside HelixSR as `.original.dll`. A newer HelixSR never replaces that copy, so Go back
always gives you the game's own file.

## Deployments

Every place the app put HelixSR, with its state now: **In place**, **Older build** (the payload is newer), **Newer
build** (the payload went back to 1.8.1), **Original restored** (the game's own DLL is back), **Network files
missing**, **Only the backup is left**, **Removed** or **Folder gone**. The line at the bottom shows the place, the
version and when it was put there.

- **RB Update older games** puts the payload's HelixSR into every game with an older build or with its own DLL back.
  Their `helixsr.ini` stays as it is, and so does the game's backup. A game that is running is left alone. After
  **Get HelixSR** the HelixSR pane says when there are such games.
- **Y Go back** takes HelixSR out there (and OptiScaler, for an OptiScaler folder). Press it twice.
- **X Forget** drops the line from the list without touching the game. Press it twice.

## OptiScaler

For a game without FSR 3.1: a DLSS, XeSS, FSR 2 or FSR 3.0 game. [OptiScaler](https://github.com/OptiScaler/OptiScaler)
hands the game's upscaler calls to an FSR 3.1 DLL. **X** on a game in the Games list opens its page:

- **OptiScaler beside the game's .exe**: with a payload that has OptiScaler (HelixSR 1.7.0 to 1.8.1 ship it; get 1.8.1
  once and the payload keeps it), the app installs OptiScaler next to the game's `.exe`, as `dxgi.dll` (or under the
  name of an OptiScaler the game already has), with `fakenvapi`, and points its `OptiScaler.ini` at HelixSR. A file of
  the game it replaces is kept in the HelixSR folder's `backup`. Windows loads it from the game's folder by itself:
  no launch options are needed.
- **Second upscaler**: another FidelityFX upscaler DLL, for example AMD's `amd_fidelityfx_upscaler_dx12.dll` with
  FSR 4. It goes into the folder as `amd_fidelityfx_upscaler_dx12.amd.dll`, and OptiScaler's FFX Upscaler menu lists its
  upscalers after HelixSR. **A** picks the file in the browser; **A** again takes it out.
- **Write helixsr.ini**: the settings of the Settings card go with it.

**A** changes the row the focus is on. **X Put HelixSR in** writes HelixSR, under both FidelityFX names, into a folder
of its own in the game's folder (`HelixSR`); installing OptiScaler asks for a second press. Start the game and select
**DLSS**; OptiScaler's menu (Insert) shows FSR HelixSR. Without OptiScaler beside the `.exe`, install OptiScaler
yourself and paste the `OptiScaler.ini` lines **LB Copy lines** puts on the clipboard. **Y Go back** takes the folder
out, and OptiScaler with it, and puts back what it replaced.

## Settings

HelixSR reads its settings from a `helixsr.ini` next to its DLL; every setting has a default. The pane has three tabs,
**Sharpening**, **Model E** and **More**: **LB** and **RB** step through them, or tap one. **A** on a row steps to its
next value and saves it at once as the payload's `helixsr.ini`: what HelixSR gets in every game you put it in from
then on. The file keeps HelixSR's own comments. A value that would make the file invalid is skipped. Rows the
payload's HelixSR does not read are not shown.

- **Y Apply to a game** writes the settings into a game that has HelixSR already: **A** on the game. HelixSR reads
  them at the game's next start.
- **X Defaults** sets every setting to HelixSR's default. Press it twice.

| Tab | Settings |
|---|---|
| Sharpening | Mode (up to HelixSR 1.7), Sharpener (off, nvidia or rcas), Sharpness, Use the game's slider, Motion adaptive, Motion threshold, Motion limit, Motion reduction |
| Model E | Model E network, Network (up to HelixSR 1.7), Invert jitter, Invert motion vectors, Motion vector front end |
| More | helixsr.log, Forwarding DLL, Second upscaler, Look for a new HelixSR at start |

The **information icon** says what each setting of the tab does.

## Log

The pane shows where the app keeps HelixSR and the newest lines of the app's log: every download, the builder's
output, every game changed. **A View log** (or a tap on the pane) shows the whole log in the pane; the d-pad scrolls
it, and **B** goes back.

## Install it on its own

The portal installs it. To install it on its own, download `wp-upscale-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-upscale-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-upscale-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-upscale-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and HelixSR stay |
| `--uninstall --purge` | also remove the settings, the log and HelixSR |

Uninstalling never changes a game. A game that still has HelixSR keeps its `.original.dll`: install the app again and
**Y Go back** on the Games card puts the game's own DLL back.

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\app\` | The program, `Upscale-Boost.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\windows-portable-upscale.log` | The log |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\payload\` | The payload: HelixSR's DLL, its `helixsr.ini`, and OptiScaler when a release brought it |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\work\` | The downloaded releases, and the newest one built |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\HelixSR\` | Python with numpy and the shader compiler, for HelixSR's builder |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-upscale\deployments.json` | Where HelixSR was put |
| `%APPDATA%\windows-portable-suite\windows-portable-upscale.ini` | The settings: the version to get, NVIDIA's DLL, the added folders |

In a game's folder: HelixSR's DLL under the game's DLL's name, the game's own DLL as `*.original.dll`, and
`helixsr.ini` and `helixsr.log` beside them; for OptiScaler, a `HelixSR` folder.
