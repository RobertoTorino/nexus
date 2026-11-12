<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Fan Control](../assets/fan/bc250-fan-control.webp){ .app-logo }

# BC-250 Fan Control

!!! warning "Changes the board"
    The thermal guard is a root system service, bc250-fan-control-guard.service with its files in
    /etc/bc250-fan-control, that reads the temperatures every two seconds. At the cool limit it sets every fan
    to full speed in sysfs and switches the GPU governor's performance mode off; at the shutdown limit, held for
    the set number of seconds, it powers the board off cleanly with systemctl poweroff. The service stays
    enabled across reboots and power offs. The fan settings are written in memory only, and the guard puts the
    saved values back when it re-arms or stops. Nothing is written to the BIOS, the firmware, the CMOS or the
    kernel's arguments. Turn off disables the service and removes its files; the fans are back on their previous
    setting, and performance mode, once the guard switched it off, stays off until you switch it on again.

BC-250 Fan Control shows the temperatures and fan speeds of the **AMD BC-250** on **Bazzite**. It can also turn on
a **thermal guard**, a background service that protects the board from overheating. The guard keeps watching when
no app is open. When the board gets too hot it warns you. If it gets hotter still, it runs the fans at full speed.
As a last resort it shuts the board down cleanly.

## Using it

The top row has four boxes: the **GPU** temperature, the **CPU** temperature, the **fan** speed and the state of
the **thermal guard**. A temperature box turns orange at the warning limit and red at the cooling limit. The names
in brackets are the sensors the readings come from: `edge` is amdgpu's and `Tctl` is k10temp's.

Under **Thermal guard** you set the limits and turn the guard on or off.

- **Warn at, cool at, shut down at:** the guard's three temperature limits, in °C.
- **after:** how many seconds the temperature must stay at the shutdown limit before the guard shuts the board
  down.
- **Turn on…:** turns the guard on with these limits. The app asks you to confirm, then asks for your password.
  The guard starts at once, and again every time the board starts.
- **Apply…:** takes the place of Turn on… while the guard is on. It gives the guard the limits you changed. After
  an update of the app it also replaces the guard with the new version's.
- **Turn off…:** stops the guard and removes it. The fans go back to how they were.
- **Defaults:** puts 85, 90 and 95 °C and 10 seconds back in the fields.

**Fans** lists every fan that reports its speed. For each fan it shows the header the fan is on, and whether the
firmware's curve or a manual value sets its speed. **What the guard did** lists the guard's recent warnings and
actions, newest first.

## The thermal guard

Every two seconds the guard reads the GPU and the CPU temperature and takes the hotter of the two. It acts at three
limits:

| Limit | Default | What the guard does |
|---|---|---|
| Warning | 85 °C | It sends a desktop notification and writes a line in the journal. |
| Cooling | 90 °C | It runs every fan at full speed and switches the GPU governor's performance mode off. |
| Shutdown | 95 °C, held for 10 s | It shuts the board down cleanly (`systemctl poweroff`), to protect it. |

- **When the board has cooled down.** At 5 °C below the warning limit the guard puts the fans back to how they
  were: the firmware's curve, or the manual value they had. With the defaults that is at 80 °C. From then on the
  guard can warn again.
  **Performance mode stays off.** Switch it on again in the GPU Manager when you want it.
- **The shutdown waits.** The guard shuts the board down only when the temperature stays at the shutdown limit for
  the whole time you set. If the temperature drops below the limit before that, the countdown stops. The guard
  tells you when a countdown starts.
- **A broken sensor never shuts the board down.** The guard ignores a reading below 1 °C or above 150 °C. If it can
  read neither the GPU nor the CPU temperature, it says so and does nothing.
- **A fan that stops is reported.** That is a fan that was turning, should still turn, and has read 0 RPM for
  10 seconds.
- **When the guard stops,** because you turned it off or uninstalled the app, it puts the fans back to how they
  were.

AMD publishes no thermal limits for the BC-250. The defaults follow what is known from these boards. The GPU slows
itself down from about 85 °C, and the board becomes unstable between 90 and 95 °C. The GPU governor's own
throttling default is also 85 °C. If your board runs hotter than that in a closed case, lower the limits.

## Fans

The board's sensor chip, a Nuvoton NCT6686, drives the fans. Bazzite comes with its driver, `nct6687`. Test 22 of
Bazzite Test checks that the driver is loaded and tells you how to load it.

Where a fan is connected decides what the app can do with it:

- **CPU_FAN1** is the board's 4-pin PWM fan header, near the end of the board. The board reads the speed of a fan
  there and sets it.
- **J4003** is the long two-row header beside it. It reads the speed of four more fans and controls them, but it
  gives them **no power**. A fan there needs 12 V from the power supply. The app shows these fans as J4003 fan 2
  to 5.
- **A fan connected only to the power supply** runs by itself. It reports nothing, so the guard cannot see it or
  change its speed. The guard still reads the temperatures, so it still warns and shuts down.
- **A Y splitter** lets two fans share one header. Both run, but only one of them reports its speed, so the app
  cannot tell when the other one stops. For a second fan, use J4003.

On another board the app shows the fan channels under the names the driver gives them.

## Files

- `/etc/bc250-fan-control/guard.py` and `guard.json`: the guard and its limits, while it is on.
- `/etc/systemd/system/bc250-fan-control-guard.service`: the service that starts the guard when the board starts.
- `/run/bc250-fan-control/state.json`: what the guard last read and recently did. The app shows it.
- `~/.config/bc250-fan-control/bc250-fan-control.ini`: the size and position of the window.

To read the guard's log, run `journalctl -u bc250-fan-control-guard`.

## Install

Install the app from the BC250 Bazzite Suite portal. You can also install it from a clone or a release folder, as
your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app and the thermal guard; keeps its settings
./install.sh --uninstall --purge     # also remove its settings
```

Turning the guard on and off needs `pkexec` and the system `python3`. Bazzite has both. Uninstalling the app also
stops and removes the guard, which needs `sudo`.

## License

GPL-3.0-or-later. See [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/fan/LICENSE).
The information on the fan headers comes from
[mothenjoyer69/bc250-documentation](https://github.com/mothenjoyer69/bc250-documentation).
