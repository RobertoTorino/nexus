<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Media Tool](../assets/mtool/media-tool.webp){ .app-logo }

# Media Tool

A standalone Qt app for recording a BC250 Bazzite Suite installation demo on Bazzite, and, in a checkout of the suite,
for recording the video tours of the portal and the apps and for converting the suite's category icons. The three
pills in its header, **Portal video tour**, **Apps video tour** and **Convert icons**, open those tools. The suite
portal lists it on its Development tab. It does not use the suite's shared Python environment.

## Install

From this folder, run:

```bash
./install.sh
```

The installer creates an app-specific Python environment under
`~/.local/share/media-tool/venv`, installs PyQt6, the OBS WebSocket client and Pillow, and adds **Media Tool**
to the desktop app menu and Desktop, using the supplied app icon. It also creates `~/MediaToolRecordings`
for recordings. It does not use `sudo` or layer packages into Bazzite. Start the app from the menu or run
`~/.local/bin/media-tool`. Python 3.11 or newer is required.

Media Tool was called Simple Demo Tool before. Installing it removes an older Simple Demo Tool (its launcher, menu
entry, Desktop icon and `~/.local/share/simple-demo-tool`). Recordings already in `~/SimpleVideoToolRecordings`
stay there; new ones go to `~/MediaToolRecordings`.

## Record a demo

1. Open OBS, configure a scene with a screen-capture source, and enable **Tools → WebSocket Server Settings**.
   For a Wayland session, use **Screen Capture (PipeWire)** and approve the desktop-sharing prompt.
2. Open Media Tool and test the OBS connection. It defaults to `127.0.0.1:4455`; enter the WebSocket
   password if OBS authentication is enabled. On a successful connection, the tool sets OBS's recording folder
   to `~/MediaToolRecordings`. This needs OBS WebSocket 5.3 or newer.
3. Download the portal tarball and `SHA256SUMS` from the suite's
   [Releases page](https://github.com/RobertoTorino/nexus/releases), verify it with
   `sha256sum --check --ignore-missing SHA256SUMS`, and extract it into your Downloads folder. Media Tool
   automatically selects the newest extracted portal release there. Use **Find in Downloads** to rescan, or
   **Choose folder…** if you extracted it elsewhere. For local development, choose the suite repository folder
   or `bc250-bazzite/apps/mtool`; the tool uses the checkout's root installer and portal manifest. The portal
   and selected app must not already be installed for a fresh-install recording.
4. Start the demo and approve the system-wide stop shortcut if your desktop asks. OBS begins recording and the
   portal installer opens in a terminal. Media Tool hides, and the portal opens automatically when its
   installer finishes successfully. The installer may ask for your password when copying files to `/opt`.
5. Show the always-included BC-250 Bazzite Test, install the selected optional app using its Install button, then
   open it using the portal's Open button. Press the shortcut shown in the desktop's shortcut configuration to
   stop the recording and bring Media Tool back. Some keyboards report the F12 key as **End**; use the
   trigger shown by the desktop. Choose **Recent recordings…** to see the newest videos from OBS's recording
   folder. Select one and choose **Play selected video** to play it inside Media Tool. Use the playback
   controls to pause or seek, and **Refresh** to update the list.

The system-wide stop shortcut uses the desktop's GlobalShortcuts portal. If your desktop does not support that
portal, Media Tool reports the error and does not start recording. The app only changes OBS's recording
folder; it does not automate other OBS settings or click through the portal. That keeps the capture source and
normal portal warnings under your control.

## Record the video tours

The tours are recorded from a checkout of the suite, from the real windows, offscreen: nothing shows on the screen
while they record. They go to your Videos folder, with music under them that fades out over the last two seconds
(untick **Music** for a video without sound). Under **Suite checkout**, check the folder: the tool finds it as for
the icons (below). A recording runs in the background; its output shows in the window, **Stop** ends it, and
**Play** plays the video in Media Tool.

- **Portal video tour** records the portal's tour, about two minutes: `bc250-portal-tour-v<portal version>.mp4`.
  Tick **Also write the copy on the wiki's Portal Tour page** to write `bc250-bazzite/docs/videos/portal-tour.mp4` and its poster
  in the checkout too, for you to review and commit.
- **Apps video tour** lists every app, each of the two programs of CU Bisect and Cores Bisect apart. Tick the apps
  (**All**, **None**), set the **Length** (40 seconds by default) and choose **Record**: each tour takes a few
  seconds, `bc250-<app>-tour-v<version>.mp4`. Double-click an app to play its video. What an app reads from the
  board is real, so watch a video before you publish it.

The tool runs the checkout's `bc250-bazzite/tools/record-tour.sh` and `bc250-bazzite/tools/record-app-tour.sh` with the checkout's development
environment (`.venv-linux`, see [Development](../development/index.md)); they need ffmpeg.

## Convert the suite's icons

Every app in a category shares the category's icon, kept in a checkout of the suite at 1024, 512, 256 and 128 px
([Icons](../development/architecture.md#icons)). The **Convert icons** pill makes them from your own images:

1. Under **Suite checkout**, check the folder. The tool finds it by itself when the chosen portal release is a
   checkout or the tool runs from one; otherwise choose it with **Choose folder…**.
2. Pick the **Category**. Its current icons show at each size.
3. Choose one image under **Every size from one image**, an image for single sizes, or both: a size picked on its
   own replaces that size of the whole set. Sizes left empty stay as they are.
4. Choose **Convert and copy to the apps**. Each image is scaled to its size and saved as WebP (the 128 px icon as
   PNG) under the category's names, and copied to every app of the category and its portal tile. Images must be
   square; any format Pillow reads works.

The changes stay in the checkout for you to review and commit. The tool runs the checkout's
`bc250-bazzite/tools/sync_icons.py`, which does the same from a terminal.

## Uninstall

`./install.sh --no-desktop-shortcut` leaves the Desktop icon out. Run `./install.sh --uninstall` from this folder. This removes the launcher, menu entry, Desktop shortcut, bundled
icons, and the tool's own files. It leaves `~/MediaToolRecordings` and its videos untouched.

## Tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests
```

## License

GPL-3.0-or-later ([GNU GPL v3](https://www.gnu.org/licenses/gpl-3.0.html)).
