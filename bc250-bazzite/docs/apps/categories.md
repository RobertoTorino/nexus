<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# App categories

Every app in the suite belongs to one of five categories, and every app in a category has the same icon. The icon
tells you what kind of app it is: one that keeps the board running well, one for graphics in games, one for playing,
a utility, or a tool for working on the suite.

## Why categories

- **You see at a glance what an app is for.** In the portal, the menu, on the Desktop and in Steam, the icon shows
  its kind before you read the name.
- **The suite looks like one suite.** Twenty-odd apps with twenty-odd styles would look like a pile of separate
  tools; five icons look like one family.
- **One place to change them.** Each category's icon is kept once, in `bc250-bazzite/icons/<category>/`. A new app picks a
  category and gets its icon; a new icon for a category reaches every app in it. How that works is in
  [Architecture and consistency](../development/architecture.md#icons).

The categories are also the [portal's](../portal.md) tabs: an app's tile is on the tab of its category.

## Legend

| Icon | Category | What it stands for |
|---|---|---|
| ![](../assets/categories/sustainable.webp){ .app-icon } | **Sustainable** | The board itself: test it, tune it, unlock it, cool it, and keep it running well for a long time. Most of these apps change how the board runs. |
| ![](../assets/categories/graphics.webp){ .app-icon } | **Graphics** | Graphics features for games: upscaling, async compute and mesh shaders on the board's GPU. |
| ![](../assets/categories/gaming.webp){ .app-icon } | **Gaming** | Playing: emulators, Remote Play with your console, plugins in Game Mode, and PlayStation trivia. |
| ![](../assets/categories/utilities.webp){ .app-icon } | **Utilities** | Handy tools around the board: an overlay, a USB stats screen, the PS5 HD Camera as a webcam, the DualSense's firmware, the BIOS settings, Wi-Fi, the TV over HDMI-CEC, and file transfer. |
| ![](../assets/categories/development.webp){ .app-icon } | **Development** | Tools for working on the suite itself. You do not need them to use the board. |

## Apps by category

Every app with its icon and its category.

| App | Category |
|---|---|
| ![](../assets/apps/check.webp){ .app-icon } [BC-250 Bazzite Test](check.md) | Sustainable |
| ![](../assets/apps/gpu.webp){ .app-icon } [BC-250 GPU Governor Manager](gpu.md) | Sustainable |
| ![](../assets/apps/compute.webp){ .app-icon } [BC-250 CU Bisect](compute.md), with its Unlock window | Sustainable |
| ![](../assets/apps/cores.webp){ .app-icon } [BC-250 Cores Bisect](cores.md), with its Unlock window | Sustainable |
| ![](../assets/apps/oc.webp){ .app-icon } [BC-250 GPU OC Bisect](oc.md) | Sustainable |
| ![](../assets/apps/acpi.webp){ .app-icon } [BC-250 Persistent ACPI](acpi.md) | Sustainable |
| ![](../assets/apps/vram.webp){ .app-icon } [BC-250 Memory Manager](vram.md) | Sustainable |
| ![](../assets/apps/fan.webp){ .app-icon } [BC-250 Fan Control](fan.md) | Sustainable |
| ![](../assets/apps/upscaler.webp){ .app-icon } [BC-250 Upscaler Manager](upscaler.md) | Graphics |
| ![](../assets/apps/ace.webp){ .app-icon } [BC-250 ACE Queues](ace.md) | Graphics |
| ![](../assets/apps/mesh.webp){ .app-icon } [BC-250 Mesh Shaders](mesh.md) | Graphics |
| ![](../assets/apps/consoles.webp){ .app-icon } [Console Link](consoles.md) | Gaming |
| ![](../assets/apps/clb.webp){ .app-icon } [Console LinkB](clb.md) | Gaming |
| ![](../assets/apps/shadps4.webp){ .app-icon } [shadPS4 Manager](shadps4.md) | Gaming |
| ![](../assets/apps/rpcs3.webp){ .app-icon } [RPCS3 Manager](rpcs3.md) | Gaming |
| ![](../assets/apps/ppsspp.webp){ .app-icon } [PPSSPP Manager](ppsspp.md) | Gaming |
| ![](../assets/apps/pcsx2.webp){ .app-icon } [PCSX2 Manager](pcsx2.md) | Gaming |
| ![](../assets/apps/vita3k.webp){ .app-icon } [Vita3K Manager](vita3k.md) | Gaming |
| ![](../assets/apps/xenia.webp){ .app-icon } [Xenia Manager](xenia.md) | Gaming |
| ![](../assets/apps/decky.webp){ .app-icon } [Decky Loader Manager](decky.md) | Gaming |
| ![](../assets/apps/datstation.webp){ .app-icon } [Bazzite DatStation](datstation.md) | Gaming |
| ![](../assets/apps/overlay.webp){ .app-icon } [System Overlay](overlay.md) | Utilities |
| ![](../assets/apps/ips35.webp){ .app-icon } [USB IPS3.5](ips35.md) | Utilities |
| ![](../assets/apps/hdcam.webp){ .app-icon } [USB HD Cam](hdcam.md) | Utilities |
| ![](../assets/apps/hdcontrol.webp){ .app-icon } [USB HD Control](hdcontrol.md) | Utilities |
| ![](../assets/apps/bios.webp){ .app-icon } [BC-250 BIOS Reader](bios.md) | Utilities |
| ![](../assets/apps/wdriver.webp){ .app-icon } [BC-250 USB Wi-Fi](wdriver.md) | Utilities |
| ![](../assets/apps/cec.webp){ .app-icon } [HDMI CEC Manager](cec.md) | Utilities |
| ![](../assets/apps/sftp.webp){ .app-icon } [Bazzite SFTP Tools](sftp.md) | Utilities |
| ![](../assets/apps/mtool.webp){ .app-icon } [Media Tool](../other-tools/media-tool.md) | Development |
| ![](../assets/apps/package.webp){ .app-icon } [Dependency Checker](package.md) | Development |
| ![](../assets/apps/ncgui.webp){ .app-icon } [Bazzite NetcatGUI](ncgui.md) | Development |
| ![](../assets/apps/suite.webp){ .app-icon } [BC250 Suite Releases](../portal.md#the-release-front-end) | Development |
| ![](../assets/apps/installer-tests.webp){ .app-icon } [BC-250 Installer Tests](../development/architecture.md#tests) | Development |
