<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![USB IPS3.5](../assets/ips35/bc250-usb-ips35.webp){ .app-logo }

# USB IPS3.5

Shows the **AMD BC-250**'s live system values on a small **Turzx USB IPS screen** on **Bazzite**: CPU, GPU, memory,
fan, temperatures, network and disk, and the weather if you want it. It reads the same sensors as
[System Overlay](overlay.md), without root, and changes nothing on the board.

## Screens

The app works with the Turzx screens that report USB ID `1a86:5722`:

| Screen | Size | How the app knows it |
|---|---|---|
| Turing Smart Screen 3.5" | 320 × 480 | it does not answer the app's hello |
| UsbMonitor 3.5" | 320 × 480 | answers 1 |
| UsbMonitor 5" | 480 × 800 | answers 2 |
| UsbMonitor 7" | 600 × 1024 | answers 3 |

The header shows which one it found. To check what is plugged in:

```bash
lsusb | grep 1a86:5722          # ... QinHeng Electronics UsbMonitor
```

These screens need **no driver** on Linux. They are USB serial devices: the kernel's `cdc_acm` driver makes them
`/dev/ttyACM0` (or the next free number) as soon as they are plugged in. The "driver" in the Windows download is
only Microsoft's USB serial setup file.

## Access to the screen

The port belongs to root and the `dialout` group, and Bazzite's users are not in that group. The first time, the
window shows **Access to the screen**: **Allow access…** asks for your password and adds a udev rule that gives the
user at the board the screen's port, for this USB ID only. It takes effect at once; there is no need to unplug the
screen or log out.

The rule is `/etc/udev/rules.d/70-bc250-usb-ips35.rules`:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", TAG+="uaccess"
```

`install.sh --uninstall` removes it again (with sudo).

## What it shows

Each value is a tile; tick the ones you want on the **Values** tab. The tiles fill the screen in one column standing
up and two lying down. The header shows your own text (the **Look** tab) and the time, with the time zone and the
date if you want them (the **Clock** tab). Hover a value on the Values tab to see what it shows.

| Tile | What it shows |
|---|---|
| CPU | load, with a bar; clock and temperature |
| GPU | load, with a bar; clock, power and temperature. Without the GPU governor's fix-metrics the BC-250 reports no GPU load, and the tile shows the clock instead |
| CPU temp | the CPU's temperature in large, with a bar from 0 to 100 °C |
| GPU temp | the GPU's temperature in large, with a bar from 0 to 100 °C |
| VRAM | used / total of the GPU's share of the memory, with a bar |
| RAM | used / total, with a bar |
| Fan | the fastest spinning fan and its name |
| VRM temp | the temperature of the VRM (voltage regulator module): the regulators beside the chip that feed it its power |
| NVMe temp | the SSD's temperature |
| Network | download, and upload beside it: all network interfaces, or the one chosen on the Values tab |
| Disk | read, and write beside it |
| Weather | the temperature, the sky in words and an icon for it (a moon at night), at the place chosen on the Weather tab |

A temperature turns the tile orange from 80 °C and red from 90 °C. A tile shows "—" when the board does not offer
its value. The values update every second.

The link to the screen is slow: a whole 3.5" picture takes almost two seconds. The app sends only the parts that
changed, usually a few KB a second; hover **Connected** in the header to see how much the last update sent.

## Settings

The window shows the screen's picture at its own size (the 5" and 7" scaled down to fit), with the settings on
six tabs beside it, or under it when the screen lies down. Every change shows on the screen at once.

Under the picture:

- **Save picture…** saves what the screen shows, at the screen's own size, as a PNG.
- **Save report…** saves every value at that moment as a text file, all of them, also those not on the screen,
  with the date, the time and its time zone.

**Screen**

- **Brightness:** 0 to 100 %. **Screen off** in the header switches the screen dark while the app keeps running.
- **Orientation:** portrait or landscape, each either way up. Choose the one that matches how the screen stands
  (where its USB cable is).

**Values**

- The tiles to show.
- **Network tile:** the network interface the Network tile measures. Each one says what it is: Ethernet (a cable),
  Wi-Fi, or Virtual (a bridge, VPN or container network). All interfaces, the default, adds them up.

**Look**

- **Theme:** Dark (with the suite's accent colour), Light, Midnight, Ember, Forest or Mono. Moving through the
  list shows each theme in the window's picture; the screen changes only when you choose one.
- **Colours:** your own colour for the **Text**, the **Tiles**, the **Accent** (the tiles' edge and bars) or the
  **Background**, over the theme. The window's picture shows each colour you try in the colour dialog; the screen
  changes when you choose OK. A button with your own colour shows it; **Theme's** puts back the theme's colours.
  The warm and hot temperatures stay orange and red.
- **Header text:** your own text, up to 24 characters: the board's name, its CPU, anything. Empty leaves only the
  time.
- **Background:** a picture of your own behind the tiles, cut to the screen's shape; the tiles let it show through
  a little. The app remembers where the picture is and does not copy it: if you move or remove it, the theme's
  colour comes back, and the tab says so.

**Clock**

- **Time:** 24-hour, or 12-hour with AM or PM.
- **Time zone:** not shown, its name (CEST) or its offset from UTC (UTC+2). The choices show the zone the system is
  in now.
- **Date:** not shown, or under the time: Thu 22 Oct, 22-10-2026, 10/22/2026 or 2026-10-22.

The time is the system's, in its time zone. Summer and winter time follow by themselves: in Amsterdam the header
says CEST (UTC+2) in summer and CET (UTC+1) in winter.

**Weather**

- Type a city or town and **Search**, pick the right one from the list (the region and country tell same-named
  places apart) and **Use this place**; the Weather tile is switched on with it. **No weather** forgets the place.
- The tab shows the current weather in more detail: temperature, sky, wind and humidity.
- The weather comes from [Open-Meteo](https://open-meteo.com/), free and without an account or key. Search sends
  the name you typed; after that, the place's coordinates go to Open-Meteo every 30 minutes, and only while the
  Weather tile is on the screen. Without a place nothing is sent. If Open-Meteo cannot be reached, the screen keeps
  the last weather it had. See [Privacy](../privacy.md).

**Start**

- **Start with the desktop, minimized:** the screen shows the values from the moment you log in. The window may stay
  minimized; the screen keeps being updated.
- **Switch the screen off when the app quits:** on by default, so the screen does not keep showing values that no
  longer change.

Each time the app connects to the screen, it restarts the screen once (it is gone from USB for about two seconds).
That also clears a picture that was cut off halfway, by an app that was killed or a cable that was pulled; without
it, everything after would land shifted. If the screen is unplugged, the app finds it again when it is plugged back
in.

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app, its udev rule and its autostart entry; keeps its settings
./install.sh --uninstall --purge     # also remove its settings
```

It installs:

- the app in `~/.local/share/bc250-usb-ips35/app`, with the `bc250_core` it was tested with;
- PyQt6 in the suite's shared venv `~/.local/share/bc250-bazzite-suite/venv`;
- the launcher `~/.local/bin/bc250-usb-ips35`, an app menu entry and a Desktop icon.

`bc250-usb-ips35 --minimized` starts it minimized, as Start with the desktop does. Settings are kept in
`~/.config/bc250-usb-ips35/bc250-usb-ips35.ini`.

## License

GPL-3.0-or-later — see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/apps/ips35/LICENSE).
