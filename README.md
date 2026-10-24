<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# BC250 Bazzite Suite

Tools for the AMD BC-250 running Bazzite, in one repository. The **[portal](portal)** installs, opens, updates
and removes them: BC-250 Bazzite Test is always installed, every other app is optional.

**Beta:** The suite is in active development: features and layout may still change between releases.

![wiki.png](portal/images/wiki.png)

## Install

**Install the portal, not the apps one by one.** It installs, updates and removes every app below for you, and
checks each download against its checksum.

1. Open the **[latest portal release](https://github.com/RobertoTorino/nexus/releases/latest)** and
   download `portal-v<version>.tar.gz` and `SHA256SUMS`.
2. In a terminal, in the folder you downloaded them to:

   ```bash
   sha256sum --check --ignore-missing SHA256SUMS
   tar -xzf portal-v*.tar.gz && cd portal-v*/ && ./install.sh
   ```

3. Start **BC250 Bazzite Suite** from the app menu or the Desktop, and install the apps you want from there.

The other releases on the Releases page (`gpu-v…`, `upscaler-v…` and so on) are the app downloads the portal
uses. You do not need them.

## The apps

By category, as the portal's tabs list them.

**Sustainable**: the board itself: test it, tune it, unlock it, cool it, and keep it running well.

- <img src="portal/images/apps/check.webp" width="20" height="20" alt=""/> **[BC-250 Bazzite Test](apps/check)**: Read-only diagnostics, stress test and benchmarks. Always installed.
- <img src="portal/images/apps/gpu.webp" width="20" height="20" alt=""/> **[BC-250 GPU Governor Manager](apps/gpu)**: Manage the cyan-skillfish GPU governor: tuning, safe points, profiles, backups.
- <img src="portal/images/apps/compute.webp" width="20" height="20" alt=""/> **[BC-250 CU Bisect](apps/compute)**: Tell bad CUs apart from an unstable CU unlock, and apply a tested unlock.
- <img src="portal/images/apps/cores.webp" width="20" height="20" alt=""/> **[BC-250 Cores Bisect](apps/cores)**: Tell bad CPU cores apart from an unstable core unlock, before you persist the 8C/16T unlock.
- <img src="portal/images/apps/oc.webp" width="20" height="20" alt=""/> **[BC-250 GPU OC Bisect](apps/oc)**: Find your board's safe GPU overclock and undervolt, one step at a time.
- <img src="portal/images/apps/acpi.webp" width="20" height="20" alt=""/> **[BC-250 Persistent ACPI](apps/acpi)**: CPU C-states and frequency scaling through a persistent ACPI override (GRUB early initrd).
- <img src="portal/images/apps/vram.webp" width="20" height="20" alt=""/> **[BC-250 Memory Manager](apps/vram)**: The VRAM split in CMOS, with the GTT, TTM limit and swap layout that go with it.
- <img src="portal/images/apps/fan.webp" width="20" height="20" alt=""/> **[BC-250 Fan Control](apps/fan)**: A thermal guard that warns, cools and shuts down cleanly at a critical temperature, and the fans.

**Graphics**: graphics features for games.

- <img src="portal/images/apps/upscaler.webp" width="20" height="20" alt=""/> **[BC-250 Upscaler Manager](apps/upscaler)**: Deploy HelixSR (FSR 3.1 drop-in upscaler with DLSS-style networks) into games.
- <img src="portal/images/apps/ace.webp" width="20" height="20" alt=""/> **[BC-250 ACE Queues](apps/ace)**: Async compute for games: a patched RADV beside the system Mesa, built on the board and tested before use.
- <img src="portal/images/apps/mesh.webp" width="20" height="20" alt=""/> **[BC-250 Mesh Shaders](apps/mesh)**: Mesh shaders for games: RADV with DirectMesh beside the system Mesa, built on the board and tested before use.

**Gaming**: apps for playing.

- <img src="portal/images/apps/consoles.webp" width="20" height="20" alt=""/> **[Console Link](apps/consoles)**: Find, wake and register PS4 and PS5 consoles on the network, and start a Remote Play session.
- <img src="portal/images/apps/clb.webp" width="20" height="20" alt=""/> **[Console LinkB](apps/clb)**: Stream your Xbox (Remote Play) or games from Xbox Cloud Gaming to the board, signed in with your Microsoft account.
- <img src="portal/images/apps/shadps4.webp" width="20" height="20" alt=""/> **[shadPS4 Manager](apps/shadps4)**: PS4 games with the shadPS4 emulator: a tested shadPS4 release, your games found (or unpacked from .pkg files) and added to Game Mode.
- <img src="portal/images/apps/decky.webp" width="20" height="20" alt=""/> **[Decky Loader Manager](apps/decky)**: Plugins in Game Mode with Decky Loader: a tested Decky release as a system service, its state and its plugins.
- <img src="portal/images/apps/rpcs3.webp" width="20" height="20" alt=""/> **[RPCS3 Manager](apps/rpcs3)**: PS3 games with the RPCS3 emulator: a tested RPCS3 build, the firmware, your games found and added to Game Mode.
- <img src="portal/images/apps/datstation.webp" width="20" height="20" alt=""/> **[Bazzite DatStation](apps/datstation)**: PlayStation quiz, console history, system versions, region codes, user guides and news, with your scores.
- <img src="portal/images/apps/ppsspp.webp" width="20" height="20" alt=""/> **[PPSSPP Manager](apps/ppsspp)**: PSP games with the PPSSPP emulator: a tested PPSSPP release, your games found and added to Game Mode.
- <img src="portal/images/apps/pcsx2.webp" width="20" height="20" alt=""/> **[PCSX2 Manager](apps/pcsx2)**: PS2 games with the PCSX2 emulator: a tested PCSX2 release, your PS2 BIOS, your games found and added to Game Mode.
- <img src="portal/images/apps/vita3k.webp" width="20" height="20" alt=""/> **[Vita3K Manager](apps/vita3k)**: PS Vita games with the Vita3K emulator: a tested Vita3K build, the firmware and your games installed through it, added to Game Mode.
- <img src="portal/images/apps/xenia.webp" width="20" height="20" alt=""/> **[Xenia Manager](apps/xenia)**: Xbox 360 games with the Xenia emulator (experimental on Linux): a tested Xenia build, your games found and added to Game Mode.

**Utilities**: handy tools around the board.

- <img src="portal/images/apps/overlay.webp" width="20" height="20" alt=""/> **[System Overlay](apps/overlay)**: CPU, GPU, refresh rate, fan and temperatures in a small window that stays on top.
- <img src="portal/images/apps/ips35.webp" width="20" height="20" alt=""/> **[USB IPS3.5](apps/ips35)**: CPU, GPU, memory, fan and temperatures on a Turzx USB IPS screen (Turing Smart Screen 3.5"), with the time, the date and the weather, in your own theme and colours.
- <img src="portal/images/apps/hdcam.webp" width="20" height="20" alt=""/> **[USB HD Cam](apps/hdcam)**: the PS5 HD Camera (CFI-ZEY1) as a webcam: loads its firmware at every plug-in and shows its picture, one camera or both side by side.
- <img src="portal/images/apps/hdcontrol.webp" width="20" height="20" alt=""/> **[USB HD Control](apps/hdcontrol)**: the DualSense and DualSense Edge: battery, firmware updates from the official server over USB, and the Edge's profiles with a backup.
- <img src="portal/images/apps/bios.webp" width="20" height="20" alt=""/> **[BC-250 BIOS Reader](apps/bios)**: The BIOS settings as the setup screen shows them, hidden menus included. Stock or modded BIOS. Read-only.
- <img src="portal/images/apps/wdriver.webp" width="20" height="20" alt=""/> **[BC-250 USB Wi-Fi](apps/wdriver)**: The driver for AIC8800D80 USB Wi-Fi sticks: built for the running kernel, loaded at boot, rebuilt after a kernel update.
- <img src="portal/images/apps/cec.webp" width="20" height="20" alt=""/> **[HDMI CEC Manager](apps/cec)**: Turn the TV on and off with the board, switch its input and use its remote, over HDMI-CEC.
- <img src="portal/images/apps/sftp.webp" width="20" height="20" alt=""/> **[Bazzite SFTP Tools](apps/sftp)**: Move files between computers over SFTP, and manage the SSH server of a Bazzite host.

**Development**: tools for working on the suite. You do not need them to use the board.

- <img src="portal/images/apps/mtool.webp" width="20" height="20" alt=""/> **[Media Tool](apps/mtool)**: Record a BC250 Bazzite Suite installation demo with OBS, and convert the suite's icons.
- <img src="portal/images/apps/package.webp" width="20" height="20" alt=""/> **[Dependency Checker](apps/package)**: The suite's Python packages and external tools, which apps use them, and whether newer ones exist; and whether a Bazzite update waits for a reboot.
- <img src="portal/images/apps/ncgui.webp" width="20" height="20" alt=""/> **[Bazzite NetcatGUI](apps/ncgui)**: A graphical netcat: connect to a host or listen on a port, TCP, UDP or TLS, one session per tab.
- <img src="portal/images/apps/suite.webp" width="20" height="20" alt=""/> **[BC250 Suite Releases](apps/suite)**: The release front end: versions, pins and the board checks of a release. Runs from a checkout of this repository.
- <img src="portal/images/apps/installer-tests.webp" width="20" height="20" alt=""/> **[BC-250 Installer Tests](tools/installer-tests/gui)**: Run the suite's installer tests one at a time, with their output live in the window. Runs from a checkout of this repository.

How to install and use them: **[the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/)**.

## License

GPL-3.0-or-later ([LICENSE](LICENSE)), except BC-250 Persistent ACPI, which is MIT, Console Link, which is
AGPL-3.0 (its protocol code comes from chiaki-ng), and Bazzite NetcatGUI, which is GPL-2.0 (a port of NetcatGUI).
Each app keeps its own `LICENSE`. The icons were made with generative AI tools and edited by hand in Photoshop, the
sounds and the music of the video tours with generative AI tools; all are under the license of the folder they are in,
like the code beside them.

## Disclaimer

The BC250 Bazzite Suite is an independent community project. It is not affiliated with or endorsed by AMD, ASRock,
the Bazzite / Universal Blue project, Sony, Nintendo, Microsoft, or the makers of the emulators the apps work with.
BC-250 is AMD's product name, Bazzite is the name of the Universal Blue project, and PlayStation, the names of
Nintendo's and Microsoft's consoles and the names of the emulators belong to their owners; the suite uses them only
to say what it works with.
