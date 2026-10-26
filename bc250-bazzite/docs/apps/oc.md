<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 GPU OC Bisect](../assets/oc/bc250-gpu-oc-bisect.webp){ .app-logo }

# BC-250 GPU OC Bisect

Finds your **AMD BC-250's** (Cyan Skillfish, gfx1013) safe **GPU overclock and undervolt**, one step at a time.

There is no formula for the right GPU clock and voltage: the stable ceiling depends on your specific die
(silicon lottery), your cooling and your PSU rail. Two boards from the same batch can differ by 100 MHz or
more. The only honest answer is empirical: raise the clock (or lower the voltage) one step at a time, hammer
the GPU with a load that verifies its results, and see where your board stops being stable.

`bc250-gpu-oc-bisect.sh` does exactly that, in the same way its sibling projects bisect
[CUs](compute.md) and
[CPU cores](cores.md).

In plain words: an **overclock** (OC) gives more performance at the same voltage, an **undervolt**
(UV) gives the same performance with less heat and power. The script finds how far your board can
safely go in either direction, and can then make the result permanent with `--install`.

> **Warning:** this restarts the GPU governor with raised clocks or lowered voltages. An unstable step can
> freeze the system; that is the point of the test, but save your work first. The script enforces hard rails
> (2500 MHz, 1100 mV ceiling, 700 mV floor, 97 °C abort) that cannot be overridden: the community record of
> hard-locks above ~1850-2000 MHz and one bricked-board report from overvolting are the reason. Use at your
> own risk.

## Quick start

```shell
chmod +x bc250-gpu-oc-bisect.sh
./bc250-gpu-oc-bisect.sh            # run the full sweep; repeat after any freeze until it says done
./bc250-gpu-oc-bisect.sh --status   # see the results and the recommendation
./bc250-gpu-oc-bisect.sh --install  # make the recommended point permanent (backup kept)
```

That is all most people need. The rest of this chapter explains what happens under the hood and
which knobs exist.

### Or use the GUI

A PyQt6 launcher with the same look as the sibling projects' GUIs: pick load time, rounds,
overclock and/or undervolt sweep, the ladder limits and steps (capped at the hard rails), then
click **Start GPU OC Bisect** - the window closes and the real sweep continues in a terminal,
exactly as if typed by hand. Buttons for **Show status**, **Install result**, **Uninstall** and a
confirmed **Reset** are included.

```shell
pip install -r requirements.txt
python -m oc_bisect
```

Or install/update the desktop app (launcher, app-menu entry, optional Desktop shortcut) from this
repo or from an extracted release tarball:

```shell
chmod +x install.sh
./install.sh
```

## How it works

On Bazzite the BC-250 GPU is scaled by **cyan-skillfish-governor-smu** along a frequency/voltage curve
defined by the `[[safe-points]]` in `/etc/cyan-skillfish-governor-smu/config.toml` (stock top point:
2000 MHz @ 1000 mV). The script sweeps that top point:

| Step        | What changes                                                                    |
|-------------|---------------------------------------------------------------------------------|
| **control** | nothing - your own top safe-point, governor restarted. A failing control means power, heat or the load tool is at fault and no step verdict can be trusted. |
| **oc:FREQ** | top frequency raised one step at a time (default +50 MHz, up to `--max-freq`) at a fixed voltage (default: your config's top voltage). |
| **uv:VOLT** | top voltage lowered one step at a time (default -25 mV, down to `--min-volt`) at your stock top frequency. |

For every attempt the script:

1. snapshots your own governor config,
2. swaps in a temporary config whose top safe-point is the step under test (your other sections -
   `[gpu]`, `[gpu-usage]`, timings - are kept as they are),
3. restarts the governor and runs a **verified** GPU load -
   [memtest_vulkan](https://github.com/GpuZelenograd/memtest_vulkan) finds wrong results, not only
   crashes (falls back to vkpeak, vkmark or glmark2 if it is not installed),
4. watches temperature, clock and busy% the whole time (aborts the attempt at 97 °C), and flags
   **NO-REACH** if the GPU never gets near the requested clock under full load,
5. restores your own config and restarts the governor again.

Every step runs several rounds (default 3). The ladder is walked depth-first: all rounds of a step finish
before the next step is attempted, so the sweep never drives past a step that is still failing. Steps
beyond a step that **fails every time** are skipped automatically.

**Crash-safe:** a marker file records the attempt in flight. After a freeze, cold boot and run the script
again - it restores your config first, records the crash against the right step and resumes where it left
off.

### Verdicts

| Verdict             | Meaning                                                              |
|---------------------|----------------------------------------------------------------------|
| passes every round  | stable at this step                                                  |
| fails every time    | past your die's limit at this voltage - the ladder stops here        |
| random              | sometimes passes, sometimes fails: power, heat or margin noise, not a clean limit |

The final recommendation is the best step that passed every round, with the step one notch back suggested
as the **margin pick** for daily use.

## Requirements

- AMD BC-250 running Bazzite (or any distro using cyan-skillfish-governor-smu)
- `cyan-skillfish-governor-smu` installed and its config at `/etc/cyan-skillfish-governor-smu/config.toml`
- [memtest_vulkan](https://github.com/GpuZelenograd/memtest_vulkan) in `~/.local/bin` (strongly
  recommended; it verifies results instead of only loading the GPU)
- `sudo` (governor config, `systemctl`, kernel log) - run the script as your desktop user, not as root

## Usage

```shell
chmod +x bc250-gpu-oc-bisect.sh
./bc250-gpu-oc-bisect.sh                 # sweep both: OC ladder then UV ladder
./bc250-gpu-oc-bisect.sh --oc            # frequency only
./bc250-gpu-oc-bisect.sh --uv            # voltage only
./bc250-gpu-oc-bisect.sh --status        # results so far + report on the Desktop
```

```text
-t, --time SECS      GPU load per attempt (default 180, minimum 60)
-r, --rounds N       attempts per step (default 3, 2-9)
    --oc             sweep frequency up (default when neither --oc nor --uv is given: both)
    --uv             sweep voltage down
    --max-freq MHZ   highest frequency to try (default 2200, hard ceiling 2500)
    --min-volt MV    lowest voltage to try (default 850, hard floor 700)
    --oc-volt MV     voltage used for the OC ladder (default: your config's top voltage; hard ceiling 1100)
    --freq-step MHZ  OC ladder step (default 50, minimum 25)
    --volt-step MV   UV ladder step (default 25, minimum 5)
    --per-boot       one attempt per boot for strict isolation (default: same boot with a cooldown;
                     the governor restart resets its state)
    --install        write the best validated step into the governor config and exit
    --uninstall      restore the governor config from the backup made by --install and exit
    --status         show the results so far and write the report, then exit
    --reset          delete the results and start over
-V, --version        show the version
-h, --help           show this help
```

### Making it stick

When the sweep is complete, `--install` writes the recommended (margin) point into the real governor
config, after an explicit confirmation. A backup of your config is kept at
`/etc/cyan-skillfish-governor-smu/config.toml.pre-oc-bisect`; `--uninstall` restores it.

## State and report

Everything lives in `~/.local/share/bc250-gpu-oc-bisect/`: `runs.tsv` (every attempt: step, MHz, mV,
outcome, errors, faults, max temp/clock/busy), per-attempt logs in `logs/`, and the snapshot of your
governor config. `--status` (and a finished run) writes a readable report to your Desktop.

## Related projects

- [bc250-cu-bisect](compute.md) - CU unlock and bisect
- [bc250-cores-bisect](cores.md) - CPU cores unlock and bisect
- [BC-250 Bazzite Test](check.md) - health-check test suite
- The **CPU** side (voltage/frequency via SMU) is covered by
  [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc) from the BC-250 collective - this
  project deliberately sticks to the GPU curve.

## License

GPL-3.0 - see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/oc/LICENSE).
