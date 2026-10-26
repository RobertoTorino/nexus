<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![HDMI CEC Manager](../assets/cec/bc250-hdmi-cec.webp){ .app-logo }

# HDMI CEC Manager

HDMI-CEC lets the board and the TV talk over the HDMI cable. With it you can turn the TV on and off from the
**AMD BC-250**, switch the TV to the board's input, set the volume, and use the TV remote on the board.

The app does not change how the board runs. It sends CEC messages to the TV when you press a button, and at boot
when you switch that on. While **Restart the picture** is on, it asks the TV every 5 seconds whether it is on.

## What the board needs

The BC-250 has only DisplayPort outputs, so the TV hangs on a DP-to-HDMI cable or adapter. There is a converter
chip in it, and CEC works only when that chip passes it on:

- **The adapter appears** when the converter reports CEC tunnelling. amdgpu then makes a CEC adapter for that
  output, `/dev/cec0`, named after the connector (`DP-1`). Many converters don't report it. Then there is no
  adapter, and nothing in software can add one. A USB CEC adapter (Pulse-Eight) is the alternative.
- **The TV answers** only when the converter also connects the CEC wire, and when CEC is switched on in the TV.
  TVs give CEC a brand name in their settings: Anynet+ (Samsung), SimpLink (LG), Bravia Sync (Sony), HDMI control or
  HDMI CEC (others).

Bazzite Test checks both (test 51).

## Using it

The top row shows the **CEC adapter** (the connector it belongs to), the board's **physical address** (the HDMI
input it is on, from the TV's EDID; "None" when the board sees no display), the **display**'s name and the
**TV power** after a check. Opening the app only reads these; nothing goes to the TV. With more than one CEC
adapter (a USB one as well, for example), the app uses the one that sees a display.

**TV:**

- **Turn TV on:** wakes the TV and switches it to the BC-250 (Image View On, then Active Source).
- **Switch to BC-250:** switches the TV to the board's input when it shows something else.
- **TV standby:** puts the TV in standby.
- **Check TV:** asks the TV whether it is there and on. The status next to the title then says **TV answers** or
  **TV does not answer**.
- **Volume −**, **Volume +** and **Mute:** go to an AV receiver when one answered the last check, else to the TV.
- **Devices on the bus…:** asks every device on the HDMI bus who it is, and lists them. Read-only.
- **TV info…:** what the TV tells about itself: its CEC version, power status, name and type, vendor ID, menu
  language, its CEC 2.0 features, its volume and mute status, its lip-sync delay, and whether an AV receiver or
  soundbar is connected (with its name and volume). A CEC 1.4 TV says "not supported" to the CEC 2.0 questions; a
  CEC 2.0 TV shows what it can do, for example ARC or taking an exact volume. These are only questions: nothing on
  the TV changes.
- **Name on the TV** and **Set name:** the name the TV shows for the board in its list of inputs and devices, at
  most 14 plain characters. The app tells the TV the new name right away; with Valve's CEC daemon running, it
  restarts the daemon with it.

When the TV does not answer, the app says what to check: CEC switched on in the TV, the TV on, and a cable or
adapter that passes CEC.

The first message configures the adapter when nothing has yet, or when it carries another name (a plain
`cec-ctl --playback` names it "Playback", and the TV lists the input as that): the board then shows up on the TV as
a playback device with your name (**BC-250** until you set another), and the app tells the TV. Some TVs only update
the name in their input list after switching inputs or turning the TV off and on.

## When the TV turns off and on

### The picture

With some DP-to-HDMI converters the TV stays black after standby, although it is on and the board runs on. The
converter keeps the DisplayPort side up while the TV is off, so the board never learns that the TV went away. At
high speeds HDMI needs a handshake with the TV (scrambling, above 340 MHz: 1080p at 120 Hz with 10 or 12 bits per
color). When the TV comes back, some converters do not redo that handshake, and the TV gets no picture until the
signal changes.

Choose what the app does about it:

- **Leave it as it is:** nothing changes. Fine with most TVs and adapters. With this choice, **TV standby** asks first,
  because the picture may not come back.
- **8 bits per color:** the picture comes back by itself. 1080p at 120 Hz then stays below the speed where the
  handshake is needed. Colors are slightly less fine; nothing runs in the background and nothing flickers. Larger
  modes, such as 1440p at 120 Hz or 4K at 60 Hz, need the handshake even at 8 bits: there only the next choice
  helps.
- **Restart the picture when the TV turns on:** full color. A small background service asks the TV every 5 seconds
  whether it is on. When the TV comes back, the screen switches to another refresh rate for 4 seconds and back: one
  short flicker, and the converter handshakes again. It starts with your desktop session.

Under the choices the app says what the current mode means: whether 8 bits is enough, or whether the signal is so
slow that the handshake never happens (1080p at 60 Hz, for example), so a black TV has another cause. Both fixes use
KDE's display settings, so they work on the KDE desktop and not in Game Mode. The color depth is the
same setting as **Color resolution** in KDE's Display settings. If the TV stays black and neither fix is on, changing
the refresh rate in Display settings (when you can see it) or a restart brings the picture back.

### Videos and music

**Pause videos and music while the TV is off** pauses the media players that play when the TV goes to standby
(browsers, mpv, VLC, Spotify and other players that offer media controls), and continues them when the TV is on
again. Only the ones that were playing continue. Games are not media players: they keep running. It uses the same
background service as **Restart the picture**, and works with or without it.

The service asks the TV every 5 seconds. One missed answer does not count as "off": only three in a row do, for
example when the TV is unplugged. So a hiccup on the HDMI bus neither flickers the picture nor pauses anything.

## At boot, before you log in

### Why a service

Everything above runs in your desktop session: the buttons, the background service of **When the TV turns off and
on**, and Valve's CEC daemon. Until you log in, none of it runs. The daemon's **Turn the TV on** setting also only
acts when the board wakes from sleep, not when it starts.

Bazzite has its own boot part, but it does not help reliably here. Bazzite ships a udev rule
(`/usr/lib/udev/rules.d/99-cec-bluetooth.rules`) that runs `cec-control onboot` each time a Bluetooth adapter
appears. It runs even with Bazzite's CEC services switched off, unless the CEC mode is native. The script
configures the CEC adapter as a playback device, turns the TV on and switches it to the board. On the BC-250 this
goes wrong in three ways:

- **It depends on the Bluetooth adapter, not on the CEC adapter.** The CEC adapter only appears once the DP-to-HDMI
  converter sees the TV, and that can be later than the Bluetooth adapter, or only when you turn the TV on. The
  script then finds no CEC adapter and does nothing, so the TV stays off. Whether it works is a matter of timing,
  so it can differ from one boot to the next.
- **It gives the adapter no name.** The TV then lists the board as "Playback", also after the app named it, because
  the script runs again whenever the Bluetooth adapter appears.
- **The login screen has its own display settings.** When the TV is off while the login screen starts, and is
  turned on later, some converters give no picture (see [The picture](#the-picture)). The 8 bits per color you
  chose for your desktop do not apply to the login screen.

The service of the app starts on the CEC adapter itself, at whatever moment it appears. It uses your name for the
board, and it runs before the login screen.

### What it does

- **Give the TV the board's name at boot** installs a small system service that runs once at each boot. It starts
  when the CEC adapter appears and waits until it sees the TV. Then it gives the adapter the board's name (the one
  under **Name on the TV**) and tells the TV.
- **Also turn the TV on and switch it to the BC-250 at boot** has it send Image View On and Active Source as well.
  This happens before the login screen starts. The login screen waits at most 8 seconds for that, so the TV is on
  when the login screen sets the picture.

The service is a system service because it runs before anyone logs in. Switching it on or off, and every change,
asks for your password. When you set another name, the app updates the service too. **Update** appears when the
installed service is from another version of the app, or has another name.

For a minute after it named the adapter, the service keeps the name: when Bazzite's `cec-control` configures the
adapter as "Playback" again at boot, the service gives it the board's name again. When Valve's CEC daemon runs, the
service leaves the name to it.

With some DP-to-HDMI converters, the adapter only appears once the TV is turned on. The service then runs at that
moment: it names the board and switches the TV to it, but the login screen is already there.

### The login screen's picture

The login screen does not use the color depth you chose under **When the TV turns off and on**. **Display settings to the login screen…** copies your desktop's display settings (resolution,
refresh rate, color depth) to it, as KDE's **Apply Plasma Settings** under System Settings → Login Screen does.
With **8 bits per color** chosen, a TV turned on while the login screen shows then gets its picture too. It works
with KDE's login screens (Plasma Login and SDDM), and asks for your password.

To see what the service did at the last boot: `journalctl -b -u bc250-hdmi-cec-boot`.

## Automatic: Valve's CEC daemon

Bazzite ships Valve's CEC daemon, `cecd`, the one SteamOS uses. It runs with your desktop session and can:

- **Turn the TV on when the board wakes from sleep.**
- **Put the TV in standby when the board goes to sleep.**
- **Use the TV remote as a keyboard:** arrows, OK, back and the media keys arrive as key presses.
- **Put the board to sleep when the TV goes to standby.**

The daemon is Bazzite's **native** CEC mode. Bazzite's other mode, **dGPU**, is for USB adapters. When the app
shows another mode, **Use Valve's CEC daemon…** runs Bazzite's own `ujust cec-mode native` in a terminal; it asks
for your password. Press **Check again** when it is done.

The four switches are the daemon's settings for your account. The app writes them to
`~/.config/cecd/config.d/99-bc250-hdmi-cec.toml` and tells the daemon to read them again. They win over Bazzite's
defaults (`98-bazzite-cec-mode.toml`). Where SteamOS Manager runs, its own settings (`99-steamos-manager.toml`) win
over the app's.

**Remote buttons…** chooses the key each button of the TV remote gives. The buttons most TVs pass on come first:
OK, the arrows, back, the media buttons, the four colored buttons, info and the channel buttons. After them come all
the others the daemon knows (numbers, menus, guide, …); which of those arrive depends on the TV. Each button can
keep the daemon's **Default**, give one key (for example **F12** for a Steam screenshot, **Super** for the app
launcher, **Play/pause**), or do **Nothing**. A button gives one key, not a combination.
The daemon reads the buttons when it starts, so saving restarts it. As soon
as one button differs from the default, the app writes the daemon's whole table with your changes, in the same file.

## Remote control keys

With the daemon running, every key the board receives from the TV remote shows in the list, with its CEC name.
The TV sends the keys only while it shows the BC-250's input.

## Files

- `~/.config/bc250-hdmi-cec/bc250-hdmi-cec.ini`: the window size.
- `~/.config/cecd/config.d/99-bc250-hdmi-cec.toml`: the daemon settings, the name on the TV and the remote's
  buttons, once you change one. Uninstalling keeps
  it, so the TV keeps behaving the same; `install.sh --uninstall --purge` removes it.
- `~/.config/systemd/user/bc250-hdmi-cec-watch.service`: the background service of **Restart the picture** and
  **Pause videos and music**, only while one of them is on. Uninstalling removes it. It writes a line to the journal
  each time it restarts the picture, pauses or continues: `journalctl --user -u bc250-hdmi-cec-watch`.
- `/etc/bc250-hdmi-cec/` (`boot.py`, `boot.json`), `/etc/systemd/system/bc250-hdmi-cec-boot.service` and
  `/etc/udev/rules.d/99-bc250-hdmi-cec-boot.rules`: the service of **At boot**, only while it is on. The name and
  whether to turn the TV on are in `boot.json`. Uninstalling removes them; it asks for the sudo password then.
