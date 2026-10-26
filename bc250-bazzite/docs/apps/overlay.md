<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![System Overlay](../assets/overlay/bc250-system-overlay.webp){ .app-logo }

# System Overlay

A small window that stays on top of your desktop and shows the **AMD BC-250**'s live system values on
**Bazzite**. It only reads sensors: nothing on the board changes and it needs no root.

| Row | What it shows | Source |
|---|---|---|
| CPU | load over the last second and the average core clock | `/proc/stat`, cpufreq |
| GPU | load, clock and power | the GPU governor's `gpu_metrics`, `amdgpu` |
| Governor | the GPU governor's current clock range | the governor, over D-Bus |
| GPU volt | core voltage (vddgfx) | `amdgpu` |
| VRAM | used / total of the GPU's share of the memory | `amdgpu` |
| RAM | used / total | `/proc/meminfo` |
| Refresh | the refresh rate of the screen the window is on | Qt |
| Fan | the fastest spinning fan; hover it to see every fan | `nct6686` (and any other fan sensor) |
| CPU temp | Tctl | `k10temp` |
| GPU temp | edge | `amdgpu` |
| VRM temp | the voltage regulators | `nct6686` ("VRM MOS") |
| NVMe temp | the SSD | `nvme` |
| Network | download and upload, all interfaces except loopback | `/proc/net/dev` |
| Disk | read and write, all disks | `/proc/diskstats` |

The BC-250's GPU has no load sensor of its own (`gpu_busy_percent` is not supported). The GPU governor measures
the load and, with its **fix-metrics** setting on (the default), publishes it in the `gpu_metrics` table; the GPU
row reads it from there. Without it the row shows clock and power only, and hovering it says why. The Governor row
shows "—" when the governor does not run.

A row shows "—" when the board or kernel does not offer its value. Temperatures turn orange from 80 °C and red
from 90 °C. The values update every second.

## Using it

- **Move it:** drag it with the left mouse button. It opens where you left it.
- **Options:** right-click it.
  - **Rows:** tick the rows you want to see; the window resizes to fit.
  - **Background:** from solid to very see-through. The text stays fully visible.
  - **Always on top:** on by default.
  - **Quit.**

The window is frameless and see-through, with rounded corners and a thin border in the theme's accent.

### Where it shows

- **Desktop mode:** on top of the desktop and of windowed or borderless games. A game in exclusive fullscreen can
  still cover it.
- **Game Mode (gamescope):** not visible; gamescope only shows the running game. Use MangoHud there.

On Wayland a window cannot keep itself on top or choose where it opens, so the overlay runs through XWayland.
`bc250-system-overlay --native-wayland` runs it as a Wayland window instead: sharper on a scaled screen, but KDE
decides whether it stays on top (a KWin window rule can keep it there).

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app; keeps its settings
./install.sh --uninstall --purge     # also remove its settings
```

It installs:

- the app in `~/.local/share/bc250-system-overlay/app`, with the `bc250_core` it was tested with;
- PyQt6 in the suite's shared venv `~/.local/share/bc250-bazzite-suite/venv`;
- the launcher `~/.local/bin/bc250-system-overlay`, an app menu entry and a Desktop icon.

Settings are kept in `~/.config/bc250-system-overlay/bc250-system-overlay.ini`.

## License

GPL-3.0-or-later — see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/overlay/LICENSE).
