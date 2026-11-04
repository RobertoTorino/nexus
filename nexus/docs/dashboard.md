<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Dashboard

The **Nexus Dashboard** (`dev/dash/` in the repository) is the one door to the tools for working on the suites.
Its tiles start the Nexus apps of the checkout, each in a window of its own, and open the tools of the suite
chosen in its header; below them, Test local apps starts the suite's own apps and wikis from the checkout. Like every Nexus app it runs from the checkout it lives in, takes Nexus's design and icon,
and has no releases of its own: nothing of it is in a portal.

The suites' own scripts stay in their folders (each suite stands apart): the dashboard runs them there. A tile is
greyed out where it does not run on this system or for this suite, and says why in its tooltip.

## Start it

From the repository's root, with the checkout's venv for the system (`.venv-linux` or `.venv-windows`, see
[Development](development.md#set-up-and-test)). Nothing is copied when you install it: the menu entry always
starts the app of the checkout you installed it from. After moving the checkout, install it again.

On Linux:

```bash
dev/dash/run.sh                             # open it; --suite bc250-bazzite opens it on that suite
dev/dash/install.sh                         # app menu entry and Desktop icon
dev/dash/install.sh --no-desktop-shortcut   # app menu entry only
dev/dash/install.sh --uninstall             # remove them; the checkout stays
dev/dash/install.sh --uninstall --purge     # also remove the settings
```

On Windows (PowerShell), `dev\dash\run.ps1` and `dev\dash\install.ps1` with the same options: a Start-menu entry
and a Desktop shortcut.

## The window

The header: Nexus's icon, the name and the version, and the **Suite** box: the suite the tours and the icons work
on (the Nexus apps are every suite's). The choice is remembered. Below it the tiles, then
[Test local apps](#test-local-apps), and under them a line for each click: which app started and where its log is,
or why a tile is off.

The first tiles are the Nexus apps of the checkout. A click starts the app with its run script, in a window of its
own that keeps running when the dashboard closes; the suite goes along where the app takes one.

| Tile | What it opens |
|---|---|
| **Nexus Release Tool** | The release front end: a release's versions, CHANGELOG entries, pins and portal bump, and the board checks ([Releases](releases.md)). |
| **Nexus Demo Recorder** | A portal installation recorded with OBS ([below](#demo-recorder)). Linux only: on Windows the tile is off. |
| **Nexus Installer Tests** | A suite's installer tests, one at a time ([below](#installer-tests)). |
| **Nexus Sound Lab** | Short sound effects for the suites' windows, made from sliders ([below](#sound-lab)). |

The other tiles work on the chosen suite:

| Tile | What it opens |
|---|---|
| **Portal video tour** | Records the suite's portal tour ([below](#video-tours)). |
| **Apps video tour** | Records a short tour of each app you tick ([below](#video-tours)). |
| **Convert icons** | Makes a category's icons from your images ([below](#convert-icons)). |
| **Close issues** | Closes the open issues on GitHub you tick; the repository's, whatever the suite ([below](#close-issues)). |

## Test local apps

Under **Test local apps** are the chosen suite's portal and every app window of it in the checkout, as an icon
(the portal first; the Windows Portable Suite's portal too, which starts full screen as on the handheld: View
exits it). A click starts that app from the checkout, to try a change before its release: `python -m <package>`
with the checkout's venv and its `core`, as `run.sh` starts a Nexus app. When the portal is already open, its icon
warns instead of starting: a second portal never opens (starting it only brings the open window to the front), so
close it first. An app that changes how the board runs (an orange **!** on its icon) asks first, as in the portal;
started from the checkout it uses the scripts in the checkout. Each app writes its output to
`~/.cache/nexus-dashboard/local/<package>.log`. When an app stops with an error, the end of its log shows below.
The apps keep running when you close the dashboard. The round **i** beside the title says the same.

The last icons are the chosen suite's wiki and the Nexus page (another suite's wiki shows when that suite is
chosen; each keeps its port): **BC250 Bazzite Suite wiki (local)** serves that wiki from the checkout with
`mkdocs serve` (the development venv has MkDocs) and opens it in the browser at
`http://127.0.0.1:8765/nexus/bc250-bazzite-suite/`, with its design panel open; **Nexus wiki (local)** does the same
for the Nexus page, at port 8766, and **Windows Portable Suite wiki (local)** for that suite's wiki, at port 8767.
Each rebuilds on every save; its log is `mkdocs-<wiki>-local.log` there. When one is already running, a click only
opens the page again. The wikis, like the apps, keep running when you close the dashboard, which has no button that
stops them. A wiki started before the checkout changed (after a pull, or a change to its `mkdocs.yml` or the design
panel) can still show the old setup: stop it, then click its icon again. `pkill -f "mkdocs serve"` stops every
wiki on Linux; on Windows, in PowerShell:
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*mkdocs serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`.

With **Wikis on the network** ticked, the icons serve the wikis on every address of the computer, at ports 8785
and 8786, so a handheld, a laptop or the TV opens them too: the addresses for those devices show below once a wiki
started. The computer's firewall has to let them in (see the [Design](design.md) chapter).

## Close issues

**Close issues** lists the open issues on GitHub, such as the weekly Upstream review and Backlog review, each with a
tick box. **Run** closes the ticked ones with `gh issue close`, one after the other, with a comment when you write
one; their output shows below, and when one fails the ones after it stay open. It needs the GitHub CLI with a login
(`gh auth login`). A double click opens an issue on GitHub.

## Video tours

The tours are recorded from the checkout as it is now, from the real windows, offscreen: nothing shows on the
screen while they record. They go to your Videos folder, with music under them that fades out over the last two
seconds (untick **Music** for a video without sound). **Size** is 1080p (1920 × 1080) by default, the wiki's;
choose 2160p (4K, 3840 × 2160) for a video for YouTube, which shows a 4K upload far sharper than a 1080p one: the
same tour, drawn at twice the scale so the text stays crisp, about four times the time, and `-2160p` before `.mp4`
in its name (1440p is the step between). A recording runs in the background; its output shows in the dialog,
**Stop** ends it, and **Play** opens the video in your video player.

- **Portal video tour** records the portal's tour, about two minutes: `bc250-portal-tour-v<portal version>.mp4`
  (`wp-portal-tour-...` for the Windows Portable Suite: its videos start with its tag prefix).
  Tick **Also write the copy on the wiki's Portal Tour page** to write the suite's `docs/videos/portal-tour.mp4` and
  its poster in the checkout too, for you to review and commit.
- **Apps video tour** lists every app of the suite, each of the two programs of CU Bisect and Cores Bisect apart.
  Tick the apps (**All**, **None**), set the **Length** (40 seconds by default) and choose **Record**: each tour
  takes a few seconds, `bc250-<app>-tour-v<version>.mp4` (`wp-...`). Double-click an app to play its video. What an app reads
  from the board is real, so watch a video before you publish it.

The dialogs run the suite's `tools/record-tour.sh` and `tools/record-app-tour.sh` (the BC250 Bazzite Suite's;
the Windows Portable Suite has its `tools/record-tour.sh`, run on the handheld from Git Bash, and its apps' tours
through the Nexus app tour) with the checkout's development environment; they need ffmpeg. The same scripts run
from a terminal: [the BC250 suite's Development chapter](bc250-bazzite-suite/development/) says how. The music
under every tour is the Nexus tools' `tools/sounds/`, every suite's.

## Convert icons

Every app in a category of a suite shares the category's icon, kept in the suite's `icons/<category>/` at 1024,
512, 256 and 128 px. **Convert icons** makes a category's icons from your images: one image for every size, or an
image for a single size. They are scaled, saved as WebP (the 128 px icon as PNG) under the category's names, and
copied to every app of the category, the portal's tiles and the wiki. Images must be square. The dialog shows the
current icons of the chosen category; **Convert and copy to the apps** runs `tools/sync_icons.py` on the suite,
whose output shows in the dialog; the icons and their copies are changed in the checkout, for you to review and
commit. A suite whose apps take no category icons (the Windows Portable Suite: its apps' icons are written by
`tools/make_icons.py`) has the tile off.

## Demo Recorder

The **Nexus Demo Recorder** (`dev/demo/`) records a demo of a portal installation with OBS: a portal release
extracted in Downloads (found by itself; **Find in Downloads** looks again, **Choose folder…** takes another, or a
suite's folder in a checkout), or, without one, the BC250 Bazzite Suite in this checkout, whose `portal/install.sh`
installs the released apps from the checkout's source. It runs on Linux (OBS and the desktop portal's global
shortcut); `dev/demo/run.sh` and `dev/demo/install.sh` start and install it on their own.

1. **OBS setup:** OBS needs a scene with a screen-capture source (on Wayland, Screen Capture through PipeWire) and
   its WebSocket server enabled (Tools, WebSocket Server Settings); **Setup instructions** has the steps. Enter the
   port and the password and **Test connection**: the recordings go to `~/Videos/demos`.
2. **Portal release and app:** the release and the optional app to show; the portal and that app must not be
   installed yet, since the demo is a fresh install.
3. **Record:** **Start recording and install portal** starts the OBS recording and the portal's installer in a
   terminal, for its output and its password prompts; the window hides. Once the installer is done the portal
   opens: show BC-250 Bazzite Test, install the chosen app and open it. The global shortcut the window named
   (Ctrl+Alt+F12 by default) stops the recording and brings the window back; **Recent recordings…** lists the
   videos and plays one.

## Installer tests

**Nexus Installer Tests** (`dev/itests/`) runs a suite's installer tests one at a time, with their live output on
the right and each one's result at the end of its row: a Bazzite suite's `tools/installer-tests/*.sh` on Linux
(bash, with fakeroot), a Windows suite's `*.ps1` on Windows (PowerShell). The **Suite** box in the header lists
the suites of the checkout with tests that run on this system, and remembers the choice; the dashboard's tile
opens it on the suite chosen there. Tick the tests and **Run selected**, or **Run all**;
**Stop** ends the one that runs and skips the rest. Each test installs an app from the checkout as its installer
does on a device and removes it again, in a temporary home: nothing of yours is touched. The tests use fixed
temporary folders under `/tmp`, so the same test is never run twice at once. `dev/itests/run.sh` (`--suite NAME`)
and `dev/itests/install.sh` start and install it on their own.

## Sound Lab

**Nexus Sound Lab** (`dev/sounds/`) makes and tries the short sound effects a window plays, such as the tick when
the controller moves the focus in a portal. Choose a **Preset** to start from (Tick, High tick, Blip, Thock, Click,
Select, Back, Error, Tick after silence) and a **Waveform** (sine, triangle, square, saw or noise), then shape the
sound with the sliders: the pitch at the start and the end of a tone (a sweep when they differ), the length of a
tone, the attack (the rise to full volume) and the decay (how fast it dies away, per second), the number of tones
and the interval between them in semitones (two tones a fifth apart make a blip), the noise over the tone and its
own decay, the silence before the sound, and the volume (its peak). The sound is drawn beside the sliders and plays
each time a slider is let go, with **Play**, or when the focus moves between the buttons of **Try it** (Tab, the
arrow keys or a controller's d-pad; A plays it again), the way a window plays it while you navigate. Once a slider
has left the preset the box says Custom. **Save as WAV…** writes the sound as 16-bit mono at 44.1 kHz, for a
suite's sounds folder (the BC250 portal's `portal/bc250_portal/sounds/`, where it plays a sound by its file name).
The last sound, the preset and the save folder are remembered.

**Keep the audio link awake**, on by default, plays a silent loop while the window is open. Without it a short
sound can stay silent on a TV: PipeWire pauses the output when nothing plays, and an HDMI TV mutes a moment after
the stream stops and needs time to unmute when it starts again, so a 50 ms tick is over before it is heard. The
preset Tick after silence shows the same from the other side: with the link asleep, only its tick comes through. A
window that plays such sounds needs the same loop while it is open. `dev/sounds/run.sh` and
`dev/sounds/install.sh` start and install it on their own; on Windows (PowerShell) `dev\sounds\run.ps1` starts it,
and the dashboard's tile does the same.
