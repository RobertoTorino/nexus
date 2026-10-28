---
template: home.html
hide:
  - navigation
  - toc
---
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<section class="home-hero" markdown>
<div class="home-hero__pictures" markdown>
![A BC-250 board](images/home/bc250-board.webp){ .home-hero__board }
![A steel gray controller](images/home/controllers/ds4.webp){ .home-hero__controller }
</div>
<div class="home-hero__text" markdown>
# Tools for every part of the board. { .home-hero__lead }
<p class="home-hero__claim">Get the most out of your BC-250.</p>
<p class="home-hero__stage"><strong>Beta</strong> The suite is in active development: features and layout may still change between releases.</p>
</div>
</section>

<section class="home-section home-section--dark" markdown>
<div class="home-section__inner" markdown>
## Lots in the suite

<div class="home-grid" markdown>
<div class="home-card" markdown>
#### :material-stethoscope: Diagnostics

[Bazzite Test](apps/check.md) checks, stress-tests and benchmarks the board,
[BIOS Reader](apps/bios.md) shows every BIOS setting, hidden menus too, and
[System Overlay](apps/overlay.md) keeps CPU, GPU, fan and temperatures on top,
[USB IPS3.5](apps/ips35.md) shows them on a small USB screen,
[Fan Control](apps/fan.md) guards the board against overheating, and
[USB Wi-Fi](apps/wdriver.md) brings the driver for AIC8800D80 Wi-Fi sticks.
</div>
<div class="home-card" markdown>
#### :material-speedometer: Tuning

[GPU Governor Manager](apps/gpu.md) tunes the GPU governor, [GPU OC Bisect](apps/oc.md) finds your
board's safe overclock and undervolt, and [Persistent ACPI](apps/acpi.md) gives the CPU its C-states and
frequency scaling.
</div>
<div class="home-card" markdown>
#### :material-lock-open-variant: Unlocks

[CU Bisect](apps/compute.md) and [Cores Bisect](apps/cores.md) tell bad CUs and cores apart from an
unstable unlock, and [Memory Manager](apps/vram.md) sets the VRAM split.
</div>
<div class="home-card" markdown>
#### :material-gamepad-variant: Gaming

[BC-250 Upscaler Manager](apps/upscaler.md) deploys an FSR 3.1 drop-in upscaler into games, and
[ACE Queues](apps/ace.md) and [Mesh Shaders](apps/mesh.md) bring async compute and mesh shaders,
beside the system Mesa.
</div>
<div class="home-card" markdown>
#### :material-gamepad-variant: PlayStation

[shadPS4 Manager](apps/shadps4.md) plays PS4 games with the shadPS4 emulator,
[RPCS3 Manager](apps/rpcs3.md) PS3 games with the RPCS3 emulator, and
[Console Link](apps/consoles.md) finds, wakes and registers PS4 and PS5 consoles for Remote Play.
</div>
<div class="home-card" markdown>
#### :material-television: Living room

[HDMI CEC Manager](apps/cec.md) turns the TV on and off with the board, [SFTP Tools](apps/sftp.md) moves files
between computers, [USB HD Cam](apps/hdcam.md) makes the PS5 HD Camera a webcam,
[USB HD Control](apps/hdcontrol.md) updates the DualSense's firmware, and
[Decky Loader Manager](apps/decky.md) adds plugins to Game Mode.
</div>
</div>

[All the apps](apps/index.md){ .md-button }
</div>
</section>

<section class="home-section home-section--light" markdown>
<div class="home-section__inner home-split" markdown>
<div markdown>
## One portal for every app

The portal installs, opens, updates and removes the apps. Each app is a tile: click its icon to open it, and use
the buttons beside it to install or uninstall. A red dot shows an update. Apps that **change the board** are
marked, and the portal asks before it installs or opens them.

[About the portal](portal.md){ .md-button }
</div>
![The portal with its app tiles](images/home/portal.webp){ .home-split__picture }
</div>
</section>

<section class="home-section home-section--accent" markdown>
<div class="home-section__inner" markdown>
## Get started

Ready to set up your BC-250 board? Download the newest portal on the board (under BC250 Bazzite Suite in the Nexus
index), check it with SHA256 and run its installer. It installs BC-250 Bazzite Test with it, every other app
installs from the portal.

[:material-download: Download](https://github.com/RobertoTorino/nexus/releases/latest){ .md-button .md-button--primary }
[Install steps](install.md){ .md-button }
</div>
</section>

<section class="home-section home-faq" markdown>
<div class="home-section__inner" markdown>
## FAQ

### Do the apps change my board?

Only the apps marked **changes the board**: the unlocks, the GPU governor, GPU overclocking, the ACPI override, the
VRAM split and the patched GPU drivers. They are software-only and can be undone, and the portal asks before it
installs or opens them. BC-250 Bazzite Test and BIOS Reader only read.

### How do I undo a change?

In the app that made it: each of these apps has an Uninstall, Remove or Undo. Uninstalling an app does not undo
what it changed on the board, so undo that first. [What stays after an uninstall](portal.md#what-stays-after-an-uninstall)
lists each app and how to undo it.

### Do the apps change Bazzite's own driver?

No. ACE Queues and Mesh Shaders build their RADV beside the system Mesa, which stays as it is, and games use it
only when you say so. Bazzite's own packages and their updates are Bazzite's.

### Do I have to install the apps one by one?

No. Install the portal; it installs, updates and removes the apps, each from a tested release that it checks
before it unpacks it. See [Install](install.md).

### Does it work on other boards or systems?

The suite is made and tested for the AMD BC-250 running Bazzite.

### How do I check a download?

Every release comes with a `SHA256SUMS` file: run `sha256sum --check --ignore-missing SHA256SUMS` before you
install. See the [security policy](SECURITY.md#verifying-a-download).

### Is it open source?

Yes. The code of every app is on [GitHub](https://github.com/RobertoTorino/nexus), under the licenses
below.

### What does the suite know about me?

Nothing it sends anywhere: no accounts, statistics or crash reports. What goes over the network, and when, is on the
[Privacy](privacy.md) page.

### Where do I get help?

Open an issue on [GitHub](https://github.com/RobertoTorino/nexus/issues). For a security problem,
use **Security → Report a vulnerability** instead, as the [security policy](SECURITY.md) says.

## License

GPL-3.0-or-later, except BC-250 Persistent ACPI, which is MIT, Console Link, which is AGPL-3.0 (its
protocol code comes from chiaki-ng), and Bazzite NetcatGUI, which is GPL-2.0 (a port of NetcatGUI). Each app has
its own `LICENSE`. The icons were made with generative AI tools and edited by hand in Photoshop, the sounds and the
music of the video tours with generative AI tools; all are under the license of the app or tool they come with, like its
code.

## Disclaimer

<!-- disclaimer -->
</div>
</section>
