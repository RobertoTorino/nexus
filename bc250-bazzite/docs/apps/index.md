<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The apps

The portal installs, opens, updates and removes these apps. BC-250 Bazzite Test is always installed, every
other app is optional. They are listed by category, as the portal's tabs list them; what the icons stand for is in
[App categories](categories.md).

**Sustainable**: the board itself: test it, tune it, unlock it, cool it, and keep it running well.

| App | What it does |
|---|---|
| ![](../assets/apps/check.webp){ .app-icon } [BC-250 Bazzite Test](check.md) | Read-only diagnostics, stress test and benchmarks. Always installed. |
| ![](../assets/apps/gpu.webp){ .app-icon } [BC-250 GPU Governor Manager](gpu.md) | Manage the cyan-skillfish GPU governor: tuning, safe points, profiles, backups. **Changes the board.** |
| ![](../assets/apps/compute.webp){ .app-icon } [BC-250 CU Bisect](compute.md) | Tell bad CUs apart from an unstable CU unlock, and apply a tested unlock. **Changes the board.** |
| ![](../assets/apps/cores.webp){ .app-icon } [BC-250 Cores Bisect](cores.md) | Tell bad CPU cores apart from an unstable core unlock, before you persist the 8C/16T unlock. **Changes the board.** |
| ![](../assets/apps/oc.webp){ .app-icon } [BC-250 GPU OC Bisect](oc.md) | Find your board's safe GPU overclock and undervolt, one step at a time. **Changes the board.** |
| ![](../assets/apps/acpi.webp){ .app-icon } [BC-250 Persistent ACPI](acpi.md) | CPU C-states and frequency scaling through a persistent ACPI override (GRUB early initrd). **Changes the board.** |
| ![](../assets/apps/vram.webp){ .app-icon } [BC-250 Memory Manager](vram.md) | The VRAM split in CMOS, with the GTT, TTM limit and swap layout that go with it. **Changes the board.** |
| ![](../assets/apps/fan.webp){ .app-icon } [BC-250 Fan Control](fan.md) | A thermal guard that warns, cools and shuts down cleanly at a critical temperature, and the fans. **Changes the board.** |

**Graphics**: graphics features for games.

| App | What it does |
|---|---|
| ![](../assets/apps/upscaler.webp){ .app-icon } [BC-250 Upscaler Manager](upscaler.md) | Deploy HelixSR (FSR 3.1 drop-in upscaler with DLSS-style networks) into games. |
| ![](../assets/apps/ace.webp){ .app-icon } [BC-250 ACE Queues](ace.md) | Async compute for games: a patched RADV beside the system Mesa, built on the board and tested before use. **Changes the board.** |
| ![](../assets/apps/mesh.webp){ .app-icon } [BC-250 Mesh Shaders](mesh.md) | Mesh shaders for games: RADV with DirectMesh beside the system Mesa, built on the board and tested before use. **Changes the board.** |

**Gaming**: apps for playing.

| App | What it does |
|---|---|
| ![](../assets/apps/consoles.webp){ .app-icon } [Console Link](consoles.md) | Find, wake and register PS4 and PS5 consoles on the network, and start a Remote Play session. |
| ![](../assets/apps/clb.webp){ .app-icon } [Console LinkB](clb.md) | Stream your Xbox (Remote Play) or games from Xbox Cloud Gaming to the board, signed in with your Microsoft account. |
| ![](../assets/apps/shadps4.webp){ .app-icon } [shadPS4 Manager](shadps4.md) | PS4 games with the shadPS4 emulator: a tested shadPS4 release, your games found (or unpacked from .pkg files) and added to Game Mode. |
| ![](../assets/apps/decky.webp){ .app-icon } [Decky Loader Manager](decky.md) | Plugins in Game Mode with Decky Loader: a tested Decky release as a system service, its state and its plugins. |
| ![](../assets/apps/rpcs3.webp){ .app-icon } [RPCS3 Manager](rpcs3.md) | PS3 games with the RPCS3 emulator: a tested RPCS3 build, the firmware, your games found and added to Steam. |
| ![](../assets/apps/ppsspp.webp){ .app-icon } [PPSSPP Manager](ppsspp.md) | PSP games with the PPSSPP emulator: a tested PPSSPP release, your games found and added to Game Mode. |
| ![](../assets/apps/pcsx2.webp){ .app-icon } [PCSX2 Manager](pcsx2.md) | PS2 games with the PCSX2 emulator: a tested PCSX2 release, your PS2 BIOS, your games found and added to Game Mode. |
| ![](../assets/apps/vita3k.webp){ .app-icon } [Vita3K Manager](vita3k.md) | PS Vita games with the Vita3K emulator: a tested Vita3K build, the firmware and your games installed through it, added to Game Mode. |
| ![](../assets/apps/xenia.webp){ .app-icon } [Xenia Manager](xenia.md) | Xbox 360 games with the Xenia emulator (experimental on Linux): a tested Xenia build, your games found and added to Game Mode. |
| ![](../assets/apps/datstation.webp){ .app-icon } [Bazzite DatStation](datstation.md) | PlayStation quiz, console history, system versions, region codes, user guides and news, with your scores. |

**Utilities**: handy tools around the board.

| App | What it does |
|---|---|
| ![](../assets/apps/overlay.webp){ .app-icon } [System Overlay](overlay.md) | CPU, GPU, refresh rate, fan and temperatures in a small window that stays on top. |
| ![](../assets/apps/ips35.webp){ .app-icon } [USB IPS3.5](ips35.md) | CPU, GPU, memory, fan and temperatures on a Turzx USB IPS screen (Turing Smart Screen 3.5"), with the time, the date and the weather, in your own theme and colors. |
| ![](../assets/apps/hdcam.webp){ .app-icon } [USB HD Cam](hdcam.md) | The PS5 HD Camera (CFI-ZEY1) as a webcam: loads its firmware at every plug-in and shows its picture, one camera or both side by side. |
| ![](../assets/apps/hdcontrol.webp){ .app-icon } [USB HD Control](hdcontrol.md) | The DualSense and DualSense Edge: battery, firmware updates from the official server over USB, and the Edge's profiles with a backup. |
| ![](../assets/apps/bios.webp){ .app-icon } [BC-250 BIOS Reader](bios.md) | The BIOS settings as the setup screen shows them, hidden menus included. Stock or modded BIOS. Read-only. |
| ![](../assets/apps/wdriver.webp){ .app-icon } [BC-250 USB Wi-Fi](wdriver.md) | The driver for AIC8800D80 USB Wi-Fi sticks: built for the running kernel, loaded at boot, rebuilt after a kernel update. **Changes the board.** |
| ![](../assets/apps/cec.webp){ .app-icon } [HDMI CEC Manager](cec.md) | Turn the TV on and off with the board, switch its input and use its remote, over HDMI-CEC. |
| ![](../assets/apps/sftp.webp){ .app-icon } [Bazzite SFTP Tools](sftp.md) | Move files between computers over SFTP, and manage the SSH server of a Bazzite host. |

**Development**: tools for working on the suite. You do not need them to use the board.

| App | What it does |
|---|---|
| ![](../assets/apps/mtool.webp){ .app-icon } [Media Tool](../other-tools/media-tool.md) | Record a BC250 Bazzite Suite installation demo with OBS, and convert the suite's icons. |
| ![](../assets/apps/package.webp){ .app-icon } [Dependency Checker](package.md) | The suite's Python packages and external tools, which apps use them, and whether newer ones exist; and whether a Bazzite update waits for a reboot. |
| ![](../assets/apps/ncgui.webp){ .app-icon } [Bazzite NetcatGUI](ncgui.md) | A graphical netcat: connect to a host or listen on a port, TCP, UDP or TLS, one session per tab. |
| ![](../assets/apps/suite.webp){ .app-icon } [BC250 Suite Releases](../portal.md#the-release-front-end) | The release front end: versions, pins and the board checks of a release. Runs from a checkout of this repository. |
| ![](../assets/apps/installer-tests.webp){ .app-icon } [BC-250 Installer Tests](../development/architecture.md#tests) | Run the suite's installer tests one at a time, with their output live in the window. Runs from a checkout of this repository. |

Apps that **change the board** (unlocks, the GPU governor, GPU overclocking, the ACPI override, the VRAM split,
a patched GPU driver) change how the BC-250 runs. They are software-only and can be undone; the portal asks before it installs or opens them. Read an
app's chapter before you use it.
