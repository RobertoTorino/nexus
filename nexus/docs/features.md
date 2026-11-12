<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- Written by tools/features.py from nexus/features.toml: edit that file, then run the tool. -->

# Apps and features

Every app of every suite, and what each one does, side by side. A row is one app; a column is a suite:
**BC250** is the [BC250 Bazzite Suite](https://robertotorino.github.io/nexus/bc250-bazzite-suite/), **Console** is the [Bazzite Console Suite](https://robertotorino.github.io/nexus/bazzite-console-suite/), **Portable** is the [Windows Portable Suite](https://robertotorino.github.io/nexus/windows-portable-suite/).

## The apps per suite

| App | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| [Portal](#portal) | [Portal](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/) | [Portal](https://robertotorino.github.io/nexus/bazzite-console-suite/portal/) | [Portal](https://robertotorino.github.io/nexus/windows-portable-suite/portal/) |
| **Sustainable** | | | |
| [Test](#test) | [BC-250 Bazzite Test](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/check/) | [Bazzite Test](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/bazzite/) | [Windows Portable Test](https://robertotorino.github.io/nexus/windows-portable-suite/apps/test/) |
| [GPU Manager](#gpu-manager) | [BC-250 GPU Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/gpu/) |  |  |
| [CU Bisect](#cu-bisect) | [BC-250 CU Bisect](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/compute/) |  |  |
| [Cores Bisect](#cores-bisect) | [BC-250 Cores Bisect](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/cores/) |  |  |
| [GPU OC Bisect](#gpu-oc-bisect) | [BC-250 GPU OC Bisect](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/oc/) |  |  |
| [Persistent ACPI](#persistent-acpi) | [BC-250 Persistent ACPI](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/acpi/) |  |  |
| [Memory Manager](#memory-manager) | [BC-250 Memory Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/vram/) |  |  |
| [Fan Control](#fan-control) | [BC-250 Fan Control](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/fan/) |  |  |
| **Graphics** | | | |
| [HelixSR upscaler](#helixsr-upscaler) | [BC-250 Upscaler Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/upscaler/) |  | [Upscale Boost](https://robertotorino.github.io/nexus/windows-portable-suite/apps/upscale/) |
| [ACE Queues](#ace-queues) | [BC-250 ACE Queues](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/ace/) |  |  |
| [Mesh Shaders](#mesh-shaders) | [BC-250 Mesh Shaders](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/mesh/) |  |  |
| **Gaming** | | | |
| [PCSX2 Manager](#pcsx2-manager) | [PCSX2 Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/pcsx2/) | [PCSX2 Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/pcsx2/) | [PCSX2 Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/pcsx2/) |
| [PPSSPP Manager](#ppsspp-manager) | [PPSSPP Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/ppsspp/) | [PPSSPP Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/ppsspp/) | [PPSSPP Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/ppsspp/) |
| [RPCS3 Manager](#rpcs3-manager) | [RPCS3 Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/rpcs3/) | [RPCS3 Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/rpcs3/) | [RPCS3 Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/rpcs3/) |
| [shadPS4 Manager](#shadps4-manager) | [shadPS4 Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/shadps4/) | [shadPS4 Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/shadps4/) | [shadPS4 Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/shadps4/) |
| [Vita3K Manager](#vita3k-manager) | [Vita3K Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/vita3k/) | [Vita3K Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/vita3k/) | [Vita3K Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/vita3k/) |
| [Xenia Manager](#xenia-manager) | [Xenia Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/xenia/) | [Xenia Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/xenia/) | [Xenia Manager](https://robertotorino.github.io/nexus/windows-portable-suite/apps/xenia/) |
| [Decky Loader Manager](#decky-loader-manager) |  | [Decky Loader Manager](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/decky/) |  |
| [PS Remote Play](#ps-remote-play) | [BC-250 PS Remote Play](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/consoles/) | [Console Link](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/consoles/) | [Remote Play](https://robertotorino.github.io/nexus/windows-portable-suite/apps/rplay/) |
| [XB Remote Play](#xb-remote-play) | [BC-250 XB Remote Play](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/clb/) | [Console LinkB](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/clb/) |  |
| [DatStation](#datstation) | [Bazzite DatStation](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/datstation/) | [Bazzite DatStation](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/datstation/) | [DatStation](https://robertotorino.github.io/nexus/windows-portable-suite/apps/datstat/) |
| **Utilities** | | | |
| [SFTP Tools](#sftp-tools) | [Bazzite SFTP Tools](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/sftp/) | [SFTP Tools](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/sftp/) | [sFTP Tools](https://robertotorino.github.io/nexus/windows-portable-suite/apps/sftp/) |
| [USB HD Cam](#usb-hd-cam) | [USB HD Cam](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/hdcam/) | [USB HD Cam](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/hdcam/) | [USB HD Cam](https://robertotorino.github.io/nexus/windows-portable-suite/apps/hdcam/) |
| [USB HD Control](#usb-hd-control) | [USB HD Control](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/hdcontrol/) | [USB HD Control](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/hdcontrol/) | [HD Controller](https://robertotorino.github.io/nexus/windows-portable-suite/apps/hdcontrol/) |
| [SSD Check](#ssd-check) | [SSD Check](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/ssd/) | [SSD Check](https://robertotorino.github.io/nexus/bazzite-console-suite/apps/ssd/) | [SSD Check](https://robertotorino.github.io/nexus/windows-portable-suite/apps/ssd/) |
| [BIOS Reader](#bios-reader) | [BC-250 BIOS Reader](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/bios/) |  | [BIOS Reader](https://robertotorino.github.io/nexus/windows-portable-suite/apps/bios/) |
| [USB screen](#usb-screen) | [USB IPS3.5](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/ips35/) |  | [Smart Screen](https://robertotorino.github.io/nexus/windows-portable-suite/apps/smart/) |
| [Support Checker](#support-checker) |  |  | [Support Checker](https://robertotorino.github.io/nexus/windows-portable-suite/apps/support/) |
| [System Overlay](#system-overlay) | [System Overlay](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/overlay/) |  |  |
| [USB Wi-Fi](#usb-wi-fi) | [BC-250 USB Wi-Fi](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/wdriver/) |  |  |
| [BC-250 CEC Manager](#bc-250-cec-manager) | [BC-250 CEC Manager](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/cec/) |  |  |
| [Bluetooth Pairing](#bluetooth-pairing) | [BC-250 Bluetooth Pairing](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/btpair/) |  |  |

## Features

### Portal

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Apps: tiles by category; install, open, update, remove | ✓ | ✓ | ✓ |
| Apps: checksum-checked installs from GitHub releases | ✓ | ✓ | ✓ |
| Apps: install all missing apps or updates at once | ✓ | ✓ |  |
| Updates: flag apps needing an update or reinstall | ✓ | ✓ | ✓ |
| Updates: update the portal itself from a banner | ✓ | ✓ | ✓ |
| Updates: flag newer programs outside the suite | ✓ | ✓ |  |
| Media: open streaming sites and apps full screen |  | ✓ |  |
| Sys info: show and copy the system's details | ✓ | ✓ |  |
| Header: live CPU and GPU, date and time | ✓ | ✓ | ✓ |
| Settings: wallpaper, transparency and sound | ✓ | ✓ | ✓ |
| Settings: clock format, time zone and weather place | ✓ | ✓ | ✓ |
| Settings: theme, Desktop icons and touchpad speed | ✓ | ✓ |  |
| Settings: performance mode, screens and XBOX mode |  |  | ✓ |
| Steam: open its Big Picture library with RT |  |  | ✓ |

### Test

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| System: show the OS version, read again on demand | ✓ | ✓ | ✓ |
| Hardware: list CPU, GPU, memory, storage, screen | ✓ |  | ✓ |
| Hardware: list problem devices and USB devices |  |  | ✓ |
| Network: test the Wi-Fi link and internet speed | ✓ |  | ✓ |
| Controller: test buttons, sticks, triggers, lights |  |  | ✓ |
| Status line: live CPU, GPU and refresh rate | ✓ |  | ✓ |
| Reports: save a text report of the results | ✓ |  | ✓ |
| Tests: run 50+ board diagnostics with fix hints | ✓ |  |  |
| Stress test and benchmark: load and score CPU/GPU | ✓ |  |  |
| Disk: measure read, write and SLC cache speed | ✓ |  |  |
| History: compare two runs side by side | ✓ |  |  |
| Logs: view runs, graph CSVs, clean up | ✓ |  |  |
| Game details: record FPS and load while playing | ✓ |  |  |
| Results: share a score card as a picture | ✓ |  |  |

### GPU Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Overview: live load, clock, temperature, power chart | ✓ |  |  |
| Overview: export history to CSV, compare with an earlier run | ✓ |  |  |
| GPU Usage: fix the load readout, choose sampling method | ✓ |  |  |
| Tuning: clock range, load target, temperature, timing | ✓ |  |  |
| Profiles: save, apply, bind to a hotkey | ✓ |  |  |
| Safe points: edit the clock/voltage curve | ✓ |  |  |
| Safe points: test a point under load, abort on GPU errors | ✓ |  |  |
| Performance: runtime clocks, per-game launch options | ✓ |  |  |
| Backups: a dated copy before every write, diff, restore | ✓ |  |  |
| Service: start, stop, enable at boot, live journal | ✓ |  |  |
| Settings: tray icon, autostart, temperature alerts | ✓ |  |  |

### CU Bisect

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Bisect: test each locked WGP under verified GPU load | ✓ |  |  |
| Bisect: control round, rounds per WGP, crash-safe resume | ✓ |  |  |
| Bisect: unattended mode with auto-reboot and resume | ✓ |  |  |
| Results: good, fails every time or random per WGP | ✓ |  |  |
| Results: suggest an even 24, 32 or 40 CU mask | ✓ |  |  |
| Unlock: apply the mask at every boot as a service | ✓ |  |  |
| Unlock: install only when results justify the mask | ✓ |  |  |
| Status: read the live masks from the GPU, uninstall | ✓ |  |  |

### Cores Bisect

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Bisect: unlock the 2 extra CPU cores through the SMU | ✓ |  |  |
| Bisect: test each new core pinned under verified load | ✓ |  |  |
| Bisect: stress-ng, mprime or both; rasdaemon errors | ✓ |  |  |
| Bisect: unattended mode, crash-safe resume across boots | ✓ |  |  |
| Results: verdict per core, report on the Desktop | ✓ |  |  |
| Setup: pick load, rounds and mode, runtime estimate | ✓ |  |  |
| Unlock: keep 8 cores after a cold boot, as a service | ✓ |  |  |
| Unlock: install only after a clean verdict, uninstall | ✓ |  |  |

### GPU OC Bisect

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Sweep: raise the GPU clock step by step (overclock) | ✓ |  |  |
| Sweep: lower the GPU voltage step by step (undervolt) | ✓ |  |  |
| Test: verified GPU load, 97 °C abort, fixed hard limits | ✓ |  |  |
| Test: crash-safe, restores your governor config | ✓ |  |  |
| Results: verdict per step, best and margin pick | ✓ |  |  |
| Install: make the safe point permanent, uninstall | ✓ |  |  |
| Launcher: pick time, rounds, ladder limits and steps | ✓ |  |  |

### Persistent ACPI

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: CPU idle states and 8 clock steps, no BIOS flash | ✓ |  |  |
| Install: stays across kernel and Bazzite updates | ✓ |  |  |
| Install: warns on modded BIOS and missing kernel support | ✓ |  |  |
| Status: installed, clock steps, idle states | ✓ |  |  |
| Status with sudo: whether the kernel loaded the tables | ✓ |  |  |
| Uninstall: back to the BIOS tables after a reboot | ✓ |  |  |

### Memory Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Overview: VRAM split, GTT, TTM limit, RAM and swap | ✓ |  |  |
| Memory map: live bar of the 16 GB, preview next boot | ✓ |  |  |
| Split: set the VRAM split in CMOS, undo | ✓ |  |  |
| GTT limit: set ttm.pages_limit on the kernel line | ✓ |  |  |
| Profiles: Default or Games split and limit at once | ✓ |  |  |
| Read CMOS: show and save the memory block, read-only | ✓ |  |  |
| Safety: refuses on bad checksum, lockdown, other boards | ✓ |  |  |
| Backups: CMOS block before and after every change | ✓ |  |  |

### Fan Control

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Overview: GPU and CPU temperature, fans, guard state | ✓ |  |  |
| Fans: every fan, its header, firmware curve or manual | ✓ |  |  |
| Guard: warn, full fans, clean shutdown at set limits | ✓ |  |  |
| Guard: runs as a service, also with no app open | ✓ |  |  |
| Guard: reports a stopped fan, ignores broken sensors | ✓ |  |  |
| Limits: set, apply, back to defaults | ✓ |  |  |
| History: what the guard did, newest first | ✓ |  |  |

### HelixSR upscaler

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Setup: download and build HelixSR, checked | ✓ |  | ✓ |
| Setup: latest release or HelixSR 1.8.1 | ✓ |  | ✓ |
| Setup: NVIDIA's DLL downloaded, from Steam or a file | ✓ |  | ✓ |
| Setup: import a release you built | ✓ |  | ✓ |
| Updates: check for a newer HelixSR | ✓ |  | ✓ |
| Games: Steam games with FSR 3.1, run with HelixSR | ✓ |  | ✓ |
| Deploy: replace a game's DLL, reversibly | ✓ |  | ✓ |
| Deploy: any game folder, added by hand | ✓ |  | ✓ |
| OptiScaler: for games without FSR 3.1 | ✓ |  | ✓ |
| Deployments: status, update older games, remove | ✓ |  | ✓ |
| helixsr.ini: edit settings, apply to a game | ✓ |  | ✓ |

### ACE Queues

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Build: patched RADV for async compute, in a container | ✓ |  |  |
| Install: driver beside the system Mesa, never replaced | ✓ |  |  |
| Test: compute queues checked on the running kernel | ✓ |  |  |
| Use: copy launch options per game | ✓ |  |  |
| Use: switch on for all apps, off again after a kernel update | ✓ |  |  |
| Status: not built, test needed, ready, test failed | ✓ |  |  |
| Remove: take the driver and all-apps files away | ✓ |  |  |

### Mesh Shaders

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Build: RADV with DirectMesh mesh shaders, in a container | ✓ |  |  |
| Install: driver beside the system Mesa, never replaced | ✓ |  |  |
| Test: mesh draws and compute queues on the running kernel | ✓ |  |  |
| Use: copy launch options per game | ✓ |  |  |
| Switches: driver options per game, for comparisons | ✓ |  |  |
| Updates: says when a newer DirectMesh release is out | ✓ |  |  |
| Remove: take the driver and wrapper away | ✓ |  |  |

### PCSX2 Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ |  |
| Setup: emulator ready to play, its own updates off | ✓ | ✓ | ✓ |
| BIOS: copied in from the app's folder, removable | ✓ | ✓ | ✓ |
| Games: found in the Games folder and on SD cards and USB drives | ✓ | ✓ | ✓ |
| Games: remove a game, choosing what to keep | ✓ | ✓ | ✓ |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Steam: follows a game renamed or moved | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Controller: player 1 and 2, quit with Select + Start | ✓ | ✓ | ✓ |
| Header: controller connected or not | ✓ | ✓ |  |
| Screen: per game original, widescreen or fill | ✓ | ✓ |  |
| Settings: picture, game, sound, controller, on screen | ✓ | ✓ | ✓ |
| Sound: shows and unmutes Bazzite's volume for it | ✓ | ✓ |  |
| Memory cards: list cards and saves, make a new card | ✓ | ✓ | ✓ |
| Memory cards: copy a whole card |  |  | ✓ |
| Memory cards: import, export, copy, delete saves | ✓ | ✓ |  |
| Memory cards: slots, format, check, backups | ✓ | ✓ |  |
| Play time: the time spent in your games | ✓ | ✓ | ✓ |
| Log: what the app did, and the emulator's last run | ✓ | ✓ | ✓ |

### PPSSPP Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ |  |
| Setup: emulator ready to play, its own updates off | ✓ | ✓ | ✓ |
| Games: found in the Games folder and on SD cards and USB drives | ✓ | ✓ | ✓ |
| Games: disc images and memory stick games | ✓ | ✓ | ✓ |
| Games: remove a game, choosing what to keep | ✓ | ✓ | ✓ |
| Games: rename ISO and CSO files after the game | ✓ | ✓ |  |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Steam: follows a game renamed or moved | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Settings: picture, game, sound, controller, on screen | ✓ | ✓ | ✓ |
| Settings: show the battery on screen |  |  | ✓ |
| Settings: open the emulator's own window | ✓ | ✓ |  |
| Log: what the app did | ✓ | ✓ | ✓ |

### RPCS3 Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ |  |
| Setup: emulator ready to play, its own updates off | ✓ | ✓ | ✓ |
| Firmware: installed from the app's folder by itself | ✓ | ✓ | ✓ |
| Packages: install games, updates and licenses | ✓ | ✓ | ✓ |
| Packages: delete after install, choosing what to keep |  |  | ✓ |
| Games: found in the Games folder and on SD cards and USB drives | ✓ | ✓ | ✓ |
| Games: remove a game, choosing what to keep | ✓ | ✓ | ✓ |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Steam: follows a game renamed or moved | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Controller: player 1 set up on your controller | ✓ | ✓ | ✓ |
| Header: controller connected or not | ✓ | ✓ |  |
| Screen: per game 16:9, 4:3 or fill | ✓ | ✓ |  |
| Settings: picture, speed, sound, messages | ✓ | ✓ | ✓ |
| Sound: shows and unmutes Bazzite's volume for it | ✓ | ✓ |  |
| Settings: open the emulator's own window | ✓ | ✓ |  |
| Play time: the time spent in your games | ✓ | ✓ | ✓ |
| Log: what the app did, firmware and package results | ✓ | ✓ | ✓ |

### shadPS4 Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ |  |
| System modules: copied into shadPS4 by themselves | ✓ | ✓ | ✓ |
| Games: found in the Games folder and on SD cards and USB drives | ✓ | ✓ | ✓ |
| Packages: unpack .pkg games and updates, keep or delete | ✓ | ✓ | ✓ |
| Packages: preview, salvage, compare and rename | ✓ | ✓ |  |
| Games: remove a game with its update and mods | ✓ | ✓ | ✓ |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Settings: picture, sound, controller and language | ✓ | ✓ | ✓ |
| shadNet: create, test and save an online account | ✓ | ✓ | ✓ |
| Play time: the time spent in your games | ✓ | ✓ | ✓ |
| Log: what the app did | ✓ | ✓ | ✓ |

### Vita3K Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ | ✓ |
| Firmware: installed from the Firmware folder by itself | ✓ | ✓ | ✓ |
| Games: install .vpk, .zip, a dumped folder or .pkg with zRIF | ✓ | ✓ | ✓ |
| Games: found in the Games folder and on SD cards and USB drives |  |  | ✓ |
| Games: updates and DLC installed as a game | ✓ | ✓ | ✓ |
| Games: remove a game with its update and DLC | ✓ | ✓ | ✓ |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Settings: picture, speed, sound and system | ✓ | ✓ | ✓ |
| Settings: open the emulator's own window | ✓ | ✓ |  |
| Log: what the app did | ✓ | ✓ | ✓ |

### Xenia Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested emulator release, checksum checked | ✓ | ✓ | ✓ |
| Install: says when a newer emulator is out | ✓ | ✓ | ✓ |
| Games: found in the Games folder and on SD cards and USB drives | ✓ | ✓ | ✓ |
| Games: ISO, unpacked disc, ZAR, Games on Demand, Arcade | ✓ | ✓ | ✓ |
| Games: remove a game, keeping its add-ons if you like | ✓ | ✓ | ✓ |
| Steam: add games, with SteamGridDB artwork | ✓ | ✓ | ✓ |
| Steam: follows a game renamed or moved | ✓ | ✓ | ✓ |
| Play: quit a game by holding View, LB and RB |  |  | ✓ |
| Play: warns while the device runs hot |  |  | ✓ |
| Profile: create one, signed in for every game |  |  | ✓ |
| Settings: picture, speed, sound and console | ✓ | ✓ | ✓ |
| Settings: open the emulator's own window | ✓ | ✓ |  |
| Log: what the app did | ✓ | ✓ | ✓ |

### Decky Loader Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Install: a tested Decky release, checksum checked |  | ✓ |  |
| Install: update, or remove with or without plugins |  | ✓ |  |
| Install: says when a newer Decky release is out |  | ✓ |  |
| Install: finds a Decky installed by ujust or Decky's installer |  | ✓ |  |
| Service: shows whether Decky runs, restart it |  | ✓ |  |
| Service: Decky's log from the system journal |  | ✓ |  |
| Steam: switch Decky's remote debugging on or off |  | ✓ |  |
| Steam Deck plugins: link /home/deck for them |  | ✓ |  |
| Plugins: list with version, author and state |  | ✓ |  |
| Plugins: open the plugins folder |  | ✓ |  |

### PS Remote Play

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Find: search the network or one address | ✓ | ✓ | ✓ |
| Register: PIN pairing, account ID via PSN sign-in | ✓ | ✓ | ✓ |
| Console: wake from rest mode, or put it in rest mode | ✓ | ✓ | ✓ |
| Tests: test session and test stream | ✓ | ✓ | ✓ |
| Stream: full-screen picture and sound, controllers play | ✓ | ✓ | ✓ |
| Stream: DualShock 4 and DualSense touchpad, motion, rumble, light bar | ✓ | ✓ | ✓ |
| Stream settings: resolution, fps, bitrate, picture, delay | ✓ | ✓ | ✓ |
| Login passcode: saved per console | ✓ | ✓ | ✓ |
| History: games played and time, per console | ✓ | ✓ | ✓ |
| Steam: add a console as a game, streams on start | ✓ | ✓ | ✓ |
| Controller test: live buttons, drift, genuine or fake | ✓ | ✓ |  |
| Privacy: personal details masked, shown on request | ✓ | ✓ | ✓ |

### XB Remote Play

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Account: Microsoft sign-in with a code, stays signed in | ✓ | ✓ |  |
| Consoles: list with power state and remote play | ✓ | ✓ |  |
| Consoles: wake an XBOX from sleep | ✓ | ✓ |  |
| Stream: your own XBOX (Remote Play) | ✓ | ✓ |  |
| Cloud games: Game Pass or free-to-play, with search | ✓ | ✓ |  |
| Stream: full screen, sound, controller with rumble | ✓ | ✓ |  |
| Stream: keyboard as a controller | ✓ | ✓ |  |
| Stream: answers a game's dialogs, shows the cloud queue | ✓ | ✓ |  |
| Privacy: log masks tokens, gamertag and IDs | ✓ | ✓ |  |

### DatStation

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Quiz: PlayStation quiz against the clock, 12 categories | ✓ | ✓ | ✓ |
| Quiz: quick quiz, pause, skip, music on or off | ✓ | ✓ | ✓ |
| Scores and trophies: top ten rounds and trophies | ✓ | ✓ | ✓ |
| History: every PlayStation console since 1994 | ✓ | ✓ | ✓ |
| System versions: every system software release | ✓ | ✓ | ✓ |
| Region codes: title ID prefixes and model regions | ✓ | ✓ | ✓ |
| User guides: Sony's online manuals | ✓ | ✓ | ✓ |
| PS News: PlayStation.Blog feed and store links | ✓ | ✓ | ✓ |
| Steam: add the app to Steam, or take it out | ✓ | ✓ | ✓ |

### SFTP Tools

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Connection: password or key, host key check | ✓ | ✓ | ✓ |
| Connection: remembered servers, never a password | ✓ | ✓ | ✓ |
| Files: browse both sides, upload and download folders | ✓ | ✓ | ✓ |
| Files: delete on either side | ✓ | ✓ | ✓ |
| Files: drag and drop to upload | ✓ | ✓ |  |
| Transfers: queue with progress and speed | ✓ | ✓ | ✓ |
| Settings: speed limit, existing files, compression | ✓ | ✓ | ✓ |
| SSH server: start or stop sshd on the remote host | ✓ | ✓ | ✓ |
| SSH server: view sshd_config |  |  | ✓ |
| SSH server: edit and check sshd_config | ✓ | ✓ |  |
| SSH server: start or stop sshd on this computer | ✓ | ✓ |  |
| Windows: a build for Windows PCs | ✓ |  |  |

### USB HD Cam

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Firmware: pinned, checked download or your own file | ✓ | ✓ | ✓ |
| Camera: loads the firmware, a webcam for other apps | ✓ | ✓ | ✓ |
| Access: one-time permission for the boot loader | ✓ | ✓ | ✓ |
| Firmware: loads by itself on plug-in and login | ✓ | ✓ |  |
| Bandwidth: full or reduced USB bandwidth | ✓ | ✓ | ✓ |
| Picture: preview in every mode, side by side too | ✓ | ✓ | ✓ |
| Picture: keeps auto exposure for a bright picture | ✓ | ✓ | ✓ |
| Picture settings: brightness, white balance, exposure | ✓ | ✓ |  |
| Full screen: screenshot, record, zoom, black and white | ✓ | ✓ | ✓ |
| PS4 Camera: firmware on Sony's adapter | ✓ | ✓ |  |

### USB HD Control

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Controller: model, connection, battery, report rate | ✓ | ✓ | ✓ |
| Controller: several controllers, one at a time | ✓ | ✓ | ✓ |
| Controller: spec sheet with official sources | ✓ | ✓ | ✓ |
| Test: live drawing of buttons, sticks and triggers | ✓ | ✓ | ✓ |
| Test: vibration and light bar color | ✓ | ✓ | ✓ |
| Firmware: check Sony's server, update over USB | ✓ | ✓ | ✓ |
| Firmware: send a firmware file of your own | ✓ | ✓ | ✓ |
| Profiles: show, back up, create, edit, clear (Edge) | ✓ | ✓ | ✓ |
| Bluetooth: turn a controller off | ✓ | ✓ |  |
| Bluetooth: switch off when unused | ✓ | ✓ |  |

### SSD Check

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Health: wear, power cycles, power-on hours | ✓ | ✓ | ✓ |
| Health: problems the drive reports | ✓ | ✓ | ✓ |
| Specs: firmware, interface, host reads and writes | ✓ | ✓ | ✓ |
| Speed: link, board link and rated read and write | ✓ | ✓ | ✓ |
| Speed: a 1 GB read and write test | ✓ | ✓ | ✓ |
| Drives: NVMe, SATA and USB, one at a time | ✓ | ✓ | ✓ |
| Drives: memory cards |  |  | ✓ |
| Firmware: fwupd says whether an update exists | ✓ | ✓ |  |
| Serial: hidden, shown on a click | ✓ | ✓ |  |
| Screenshot: save the window as a PNG | ✓ | ✓ | ✓ |

### BIOS Reader

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Setup screens: every page and menu, read only | ✓ |  | ✓ |
| Setup screens: hidden settings and menus, with reasons | ✓ |  | ✓ |
| Settings: help, default, options and storage place | ✓ |  | ✓ |
| Settings: this device's own values | ✓ |  | ✓ |
| Open: a BIOS dump or the maker's BIOS file | ✓ |  | ✓ |
| BIOS chip: read and verify a flash dump | ✓ |  |  |
| Status: stock or modded BIOS | ✓ |  |  |
| This device: BIOS version, and the newest from ASUS |  |  | ✓ |
| BIOS file: this device's from Windows Update |  |  | ✓ |

### USB screen

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Screens: Turzx 3.5", 5" and 7", found by themselves | ✓ |  | ✓ |
| Values: CPU, GPU, temperatures, RAM, network, disk | ✓ |  | ✓ |
| Values: fan, VRAM, VRM and NVMe temperatures | ✓ |  |  |
| Values: power and battery |  |  | ✓ |
| Screen: brightness, orientation, screen off | ✓ |  | ✓ |
| Look: six themes, own colors, header text, background | ✓ |  | ✓ |
| Clock: 12 or 24 hours, time zone, date | ✓ |  | ✓ |
| Weather: a place's weather from Open-Meteo | ✓ |  | ✓ |
| Save: the picture as a PNG, the values as a report | ✓ |  | ✓ |
| Start: with the desktop, minimized | ✓ |  | ✓ |

### Support Checker

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Windows: show version, build and newest update |  |  | ✓ |
| Windows: flag a pending restart or late update |  |  | ✓ |
| Tools: check the runtimes and programs apps need |  |  | ✓ |
| Tools: show which app uses each, how to get it |  |  | ✓ |
| Tools: flag missing or unsupported builds |  |  | ✓ |
| Apps: compare installed versions with the portal's |  |  | ✓ |
| Check again: run every check once more |  |  | ✓ |
| Info: explain each pane with the ☰ button |  |  | ✓ |
| Read-only: installs and changes nothing |  |  | ✓ |

### System Overlay

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Overlay: CPU and GPU load, clocks, power, voltage | ✓ |  |  |
| Overlay: VRAM, RAM, refresh rate, network and disk | ✓ |  |  |
| Overlay: fan speed, CPU, GPU, VRM and NVMe temps | ✓ |  |  |
| Overlay: governor clock range, colors when hot | ✓ |  |  |
| Options: choose rows, background see-through, on top | ✓ |  |  |
| Window: drag to move, opens where you left it | ✓ |  |  |

### USB Wi-Fi

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Status: stick mode, chip, driver and Wi-Fi interface | ✓ |  |  |
| Driver: branch chosen from the chip's revision | ✓ |  |  |
| Build: AIC8800D80 driver for the running kernel | ✓ |  |  |
| Build: newest sources when a kernel breaks the pin | ✓ |  |  |
| Install: service loads it at every boot, rebuilds | ✓ |  |  |
| Install: switches a stick out of storage mode | ✓ |  |  |
| Driver: update and remove | ✓ |  |  |
| Wi-Fi adapters: check any stick's kernel support | ✓ |  |  |

### BC-250 CEC Manager

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| TV: turn on, standby, switch to the board's input | ✓ |  |  |
| TV: volume and mute, to the TV or an AV receiver | ✓ |  |  |
| TV: check, list devices on the bus, TV info | ✓ |  |  |
| Name: set the name the TV shows for the board | ✓ |  |  |
| Picture: fix a black TV after standby | ✓ |  |  |
| Media: pause players while the TV is off | ✓ |  |  |
| Boot: name the board, turn the TV on before login | ✓ |  |  |
| Daemon: wake and sleep with the TV, remote as keys | ✓ |  |  |
| Remote: map buttons to keys, show received keys | ✓ |  |  |

### Bluetooth Pairing

| Feature | BC250 | Console | Portable |
|---|:---:|:---:|:---:|
| Pairing: the listed keyboard, mouse and controllers paired after every boot, on the login screen | ✓ |  |  |
| Pairing: a device that dropped its pairing paired again; other names never | ✓ |  |  |
| Batteries: PlayStation controller batteries in the Bluetooth icon | ✓ |  |  |
| Login: Bluetooth switched on at every login (Plasma) | ✓ |  |  |
