<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Fan Control](../assets/fan/bc250-fan-control.webp){ .app-logo }

# BC-250 Fan Control

Shows the temperatures and fans of the **AMD BC-250** on **Bazzite**, and runs a **thermal guard**: a system
service that watches the GPU and the CPU, also when no app is open, and warns, cools and at a critical temperature
shuts the board down cleanly.

While the guard is on, it can turn the fans to full speed, turn performance mode off and power the board off, so
this app **changes the board**. It is software-only. Turn the guard off and everything is as before.

## Using it

The top row shows the **GPU** temperature (amdgpu's `edge`), the **CPU** temperature (k10temp's `Tctl`), the
**fan** and the **thermal guard**. A temperature box turns orange at the warning limit and red at the cooling
limit.

- **Warn at, cool at, shut down at, after:** the guard's limits, in °C, and how many seconds the temperature must
  stay at the shutdown limit before the board shuts down.
- **Turn on…:** installs the guard as a system service with these limits. The app asks first, then asks for your
  password. The guard starts at once and at every boot.
- **Apply…:** once the guard is on, gives it new limits (or the guard of this version of the app).
- **Turn off…:** stops and removes the guard. The fans go back as they were.
- **Defaults:** puts 85, 90 and 95 °C and 10 seconds back in the fields.

Under **Fans** is every fan that reports its speed, with the header it is on and whether it follows the firmware's
curve or a manual value. **What the guard did** lists the guard's recent warnings and actions, newest first.

## The thermal guard

Every two seconds the guard takes the hotter of the GPU and the CPU temperature, and acts at three limits:

| Limit | Default | What the guard does |
|---|---|---|
| Warning | 85 °C | A desktop notification, and a line in the journal. |
| Cooling | 90 °C | Every fan to full speed, and the GPU governor's performance mode off. |
| Shutdown | 95 °C, held for 10 s | A clean shutdown (`systemctl poweroff`), to protect the board. |

- **Back to normal:** 5 °C below the warning (80 °C with the defaults) the warning re-arms and the fans go back to
  what they were: the firmware's curve, or the manual value they had. **Performance mode stays off**: turn it on
  again in the GPU Governor Manager when you want it.
- **The shutdown waits.** Only a temperature that stays at the shutdown limit for the whole time shuts the board
  down; one that drops below it in time stops the countdown. The guard says when the countdown starts.
- **A broken sensor never shuts the board down.** A reading below 1 °C or above 150 °C counts as no reading. With
  no GPU or CPU temperature at all, the guard says so and does nothing.
- **A fan that stops** is reported: one that turned and then reads 0 RPM for 10 seconds, while it should turn.
- **When the guard stops** (turned off, or the app uninstalled), it puts the fans back as they were.

AMD publishes no thermal limits for the BC-250. The defaults follow what is known from the boards: GPU throttling
from about 85 °C, instability from 90 to 95 °C, and the GPU governor's own throttling default of 85 °C. Lower them if
your board runs hotter than that in a closed case.

## Fans

The board's fans are driven by its sensor chip, a Nuvoton NCT6686, through the `nct6687` driver that Bazzite ships.
Bazzite Test (test 22) checks that the driver is loaded and says how to load it.

- **CPU_FAN1** is the board's 4-pin PWM fan header, near the end of the board. The board can read a fan there and
  set its speed.
- **J4003**, the long two-row header beside it, carries the speed signal and the PWM control of four more fans,
  **without power**: a fan there takes its 12 V from the power supply. The app shows those channels as J4003 fan 2
  to 5.
- **A fan powered straight from the power supply** runs on its own: it reports nothing, and the guard can neither
  see nor drive it. The temperatures still count, so the guard still warns and shuts down.
- **A Y splitter** on one header drives both fans, but only one of them reports its speed. The app cannot tell when
  the other one stops. For a second fan, use J4003.

On another board the app shows the fan channels with the driver's own labels.

## Files

- `/etc/bc250-fan-control/guard.py` and `guard.json`: the guard and its limits, while it is on.
- `/etc/systemd/system/bc250-fan-control-guard.service`: the service that starts it at boot.
- `/run/bc250-fan-control/state.json`: what the guard saw last and did lately, which the app shows.
- `~/.config/bc250-fan-control/bc250-fan-control.ini`: the window's size and place.

The guard's log: `journalctl -u bc250-fan-control-guard`.

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app and the thermal guard; keeps its settings
./install.sh --uninstall --purge     # also remove its settings
```

Turning the guard on and off needs `pkexec` and the system `python3`; Bazzite has both. Uninstalling the app also
stops and removes the guard (with `sudo`).

## License

GPL-3.0-or-later. See [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/fan/LICENSE).
Where the fan headers are comes from [mothenjoyer69/bc250-documentation](https://github.com/mothenjoyer69/bc250-documentation).
