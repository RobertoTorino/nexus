<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# USB HD Cam

Makes the **PS5 HD Camera (CFI-ZEY1)** a webcam on **Bazzite**. The camera has no memory of its
own: it starts as a boot loader and needs its firmware each time it is plugged in, as a PlayStation sends it. The app
gets the firmware (a pinned, checked download, or a file of your own), gives your user the camera once, and sends the
firmware by itself whenever the camera is plugged in. Linux then sees an ordinary USB video camera, for OBS, a browser
or any other app. The window shows the camera's state and its picture in every mode it reports, one camera or both
side by side. A PS4 Camera on Sony's adapter works the same way, with its own firmware.

How to install and use it: [USB HD Cam in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/hdcam/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The camera's firmware is Sony's: it is not part of this app.
