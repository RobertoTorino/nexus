<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Bazzite Test](../assets/check/bc250-bazzite-test.webp){ .app-logo }

# BC-250 Bazzite Test

Read-only diagnostics, stress test and benchmarks for an **AMD BC-250** board (Cyan Skillfish APU,
`gfx1013`, PCI `1002:13fe`) running **Bazzite** (Fedora Atomic / rpm-ostree).

Nothing is installed, enabled, disabled or reconfigured. The only exceptions are the opt-in stress test,
which deliberately puts the board under load, and the optional write part of the disk speed test, which
writes one temporary file and removes it.

---

## Download and install

BC-250 Bazzite Test is part of the [BC250 Bazzite Suite](https://github.com/RobertoTorino/nexus) and is always installed with it: install
the suite's **portal** (see [Install](../install.md)), and this app comes along. It can also be installed on its own from
its release on the suite's [Releases](https://github.com/RobertoTorino/nexus/releases) page: `check-v<version>.tar.gz` with a
`SHA256SUMS` file. To be notified of new releases, click **Watch → Custom → Releases** on the suite page.

Nothing is layered with `rpm-ostree` for the app itself: the test engine goes to `/opt`, the GUI's
Python packages go into the suite's shared venv in your home directory.

**1. Download and verify.** Get both files from the Releases page, then in the download folder:

```shell
sha256sum --check --ignore-missing SHA256SUMS
```

**2. Extract and run the installer** as your own user (not with `sudo`; it asks for the password
only to copy the app to `/opt`):

```shell
tar -xzf check-v*.tar.gz
cd check-v*/
./install.sh
```

**3. Start** *BC-250 Bazzite Test* from the app menu or the icon on your Desktop, or run
`bc250-bazzite-test` in a terminal. The extracted download folder can be deleted.

What `install.sh` does:

* copies the app, with the `bc250_core` it was released with, to `/opt/bc250-check-v<version>`
  (root-owned), points `/opt/bc250-bazzite-test` at it and removes older versions;
* uses the suite's shared venv `~/.local/share/bc250-bazzite-suite/venv` with PyQt6 (created on first use;
  the wheels bundle Qt, nothing else is needed; ~100 MB download the first time). The venv is removed with
  the last suite app that uses it;
* adds the launcher `~/.local/bin/bc250-bazzite-test`, an app menu entry and a Desktop icon
  (`./install.sh --no-desktop-shortcut` skips the Desktop icon).

**Optional tools** some tests use (stress-ng, vkpeak, memtest_vulkan, fio, speedtest, …) can be
installed interactively with `/opt/bc250-bazzite-test/development/tools/install-requirements.sh` —
it says what each group is for and asks per group.

> **Why `/opt`?** The test engine runs as root through sudo. A release build therefore refuses to
> run `test-bazzite.sh` unless the file and every folder above it are owned by root and writable by
> root only, and the file matches the SHA-256 recorded when the release was built. A copy in your
> home directory fails that check on purpose.

**Update:** from the portal, or download, verify and extract the new release and run its `./install.sh` again.
It replaces the old version; your settings and the history are kept — they live in your home directory.

**Uninstall:** uninstalling the portal removes this app too. On its own:

```shell
/opt/bc250-bazzite-test/install.sh --uninstall           # keeps settings, history and reports
/opt/bc250-bazzite-test/install.sh --uninstall --purge   # removes those too
```

## Reporting problems

Open an [issue](https://github.com/RobertoTorino/nexus/issues/new/choose) (app: check) and add the
app version (*Settings → About*) and the full report of the run (*Show Logs*). The report contains details
about your system: read it before you post it. Security problems: see [SECURITY.md](../SECURITY.md).

---

## Using the app

* **Run all tests** runs the passive diagnostics (tests 00–40), plus the stress test when
  *Include stress test (41) in run* is ticked. Or open a category on the left and run one test, or all
  tests of that category.
* A test button turns **yellow** while it runs, then **green** (passed), **orange** (warning),
  **red** (failure) or **blue** (information only).
* The output appears in the terminal of the page, fix suggestions in the **Hints** panel next to it.
* The boxes at the top count the latest result of every test and give a **health score**. Click
  *Warnings*, *Failures* or *Info / hints* to see what is behind the number.
* The **Base System** and **Extended System** boxes (light), at the end of the row, rate the hardware and its setup: a
  stock BC-250 on BIOS 5.00 with 24 CUs, 6 cores/12 threads, a 512 GB NVMe reading 850 MB/s, a 1 Gbit/s link,
  the ACPI fix, a 6 GB VRAM split, mitigations off, the IOMMU disabled, zswap with a disk swapfile and a 100% health score is exactly 100. Anything below a default costs points; upgrades (more CUs or cores, a
  bigger or faster drive, a faster link) only raise the Extended score, so the Base score never exceeds 100.
  Click either one for the breakdown; see [System score](#system-score) for how it is calculated.
* Most checks need administrator rights. When a password is needed, a masked prompt appears; the password
  is never shown, saved or logged.
* **History** lists every run by date (pick a date range). Select a run to see its results and
  measurements; select two (Ctrl-click) to compare them side by side, for example before and after a CU
  unlock: what got better or worse, and by how much.
* The run button shows the progress, and the time left during the stress test. Closing the window
  during a run asks first and stops the tests cleanly. A run of a minute or more that finishes while
  you're in another window gives a desktop notification (*Settings → General*).
* The app remembers its window size, the last page, the panel sizes and the stress settings.
* **Show Logs** lists earlier runs, colored like the live output; **Settings** has privacy options, a
  system overview, log cleanup, version information and **Print results**: it saves the Base and
  Extended System scores and the other header boxes as a compact "BC-250 Bazzite Test Results" card
  (results.png), easy to share and compare with other users.
* **Game details** records a game while you play, like MangoHud's logging: copy its launch line into the
  game's *Properties → Launch options* in Steam (it works alongside `mangohud %command%`). Every session
  becomes a graph of FPS, the game's CPU/GPU share, total load, GPU and CPU clocks and temperatures,
  power, voltage, VRAM and GTT, the fan and the free system memory. When the game ends the page also
  shows **Checks for the last session**: the real 1%/0.1% lows and stutter share from MangoHud's
  per-frame log, whether the session was GPU- or CPU-bound, whether the VRAM carve-out, GTT or RAM ran
  out, whether the board was power-capped or lost clocks to heat, and any amdgpu errors the kernel
  logged while the game ran. Per game you can turn recording on or off and set the sample interval; a
  screenshot of the game is taken once during the first recorded session and shown on the page. FPS and
  the frametime checks need MangoHud with logging on (see [A game's FPS](#a-games-fps)). The page also
  reads the launch options in Steam: a game whose line starts the game monitor from a folder or python
  that is gone would not start at all, so it is listed with the line to put in its place. Copy the
  launch line from the installed app, not from a checkout: a line from a checkout stops working when
  that folder moves.
* **In-game overlay:** the app has its own overlay in its own style (*Show overlay* / *Test overlay* on
  the Game details page). With *Test overlay* it can be dragged anywhere on the screen; the position is
  saved and the in-game overlay (click-through, so it never steals a click from the game) appears
  there. But it is a separate window, and games that run in exclusive fullscreen
  bypass the compositor (direct scanout) — no external window can appear above them. Only something
  drawn inside the game's own frames can, which is how MangoHud works (a Vulkan/OpenGL layer injected
  into the game). So for fullscreen games use *Set MangoHud overlay style*: it writes an
  app-owned MangoHud config that the launch-line wrapper passes to MangoHud, approximating the app's
  overlay look. The app's own overlay does work over games in windowed or borderless-fullscreen mode.
* The benchmark (42), the disk speed test (43) and the internet speed test (44) are never part of
  *Run all tests*: start them from their own buttons, on an idle system.

### System score

A stock BC-250 on the latest BIOS, set up as recommended and with every default below met, scores exactly **100**.

| Item | Points | Default (full points) | Above the default (Extended score only) |
|---|---|---|---|
| **Hardware** | **55** | | |
| GPU compute units | 20 | 24 CUs, evenly distributed (see below) | In proportion: 32 CUs = 26.7, 40 CUs = 33.3 |
| CPU cores / threads | 15 | 6 cores / 12 threads (cores 75%, threads 25%) | In proportion: 8C/16T = 20 |
| NVMe read speed (test 43) | 10 | 850 MB/s (the PCIe 2.0 slot tops out at ~1000 MB/s) | +25% of the points per doubling |
| NVMe capacity | 5 | 512 GB (480 GB and up count) | +25% of the points per doubling: 1 TB = 6.25, 8 TB = 10 |
| Wired network link | 5 | 1 Gbit/s (the onboard port's maximum) | +25% of the points per doubling: a 2.5 GbE USB adapter = 6.7 |
| **Configuration** | **45** | | |
| BIOS | 5 | 5.00 (3.00 = 3, 1.00 = 1; a modded BIOS counts as current) | None |
| ACPI fix (test 26) | 10 | Applied: cpufreq scaling and CPU idle states exist | None |
| VRAM split (test 37) | 10 | 6 GB (`bc250memcfg UMA_SIZE 6144`); any other split gets 5 | None |
| CPU mitigations (test 24) | 5 | Off (`mitigations=off`) | None |
| IOMMU (test 23) | 5 | Disabled (no IOMMU groups) | None |
| Swap (test 14) | 5 | zswap in front of a disk swapfile; zram + disk or disk only gets 3, zram only or zram + zswap 2, no usable swap 0 | None |
| Health score | 5 | 100% | None |

* **Base System Score**: below a default costs points in proportion, above it earns nothing, so the
  maximum is 100. It is rounded down, so a board on an older BIOS can never reach 100.
* **Extended System Score**: the Base score plus what goes beyond the defaults. On a stock board it is
  equal to the Base score.
* An item that is not measured yet scores 0; the pop-up lists the test to run for it.
* **CU balance**: the CUs sit in 4 shader arrays of 5 WGPs (2 CUs each), and the array with the fewest CUs
  sets the pace. An uneven unlock is scored as the evenly distributed count below it (4 x the smallest
  array, so 10/8/6/8 = 32 CUs counts as 24) and the pop-up warns that the CUs are not evenly assigned.
  The per-array counts come from test 21, which needs root and `umr`; without them the total is rounded
  down to a multiple of 8 (24, 32 or 40).

## The window in detail

**The left pane:** the Overview, one page per test category, History, Game details, Help (this chapter) and
Settings.

**The boxes at the top** count the latest result of every test over all runs, also after a restart: *Tests*
available, *Finished* (tests with a result in the history), *Passed*, *Warnings*, *Failures* and *Info / hints*.
The test buttons show that result too; their tooltip has its date. Behind *Warnings*, *Failures* and
*Info / hints* are, per test, the WARNING, ERROR or INFO lines and the hints from the log of that result: click a
test name to open its page, or *Show in log* to open the run log at that test.

* **Health score:** passed and info tests count 100%, warnings 50% and failures 0%, averaged over the tests
  that ran. Green from 90%, orange from 70%, red below.
* **CPU score** (purple) and **GPU score** (blue): the last performance benchmark (test 42), where 100 is your
  board in its stock configuration. Hover for details.

**The status bar** (bottom right) shows live values, every 2 s:

* **CPU / GPU:** whole-system load. The GPU load comes from the kernel sensor, the governor's patched
  `gpu_metrics` (fix-metrics on) or the GPU time of your processes; hover to see which, and what a sample costs.
* **🎮 Game:** while a game runs, its name (from Steam, or the game's .exe), the share of the CPU and GPU it
  uses and, with MangoHud logging on, its FPS.
* **↓ / ↑:** download and upload traffic over the wired and Wi-Fi interfaces, from `/proc/net/dev`.
* **Hz:** the refresh rate of the display the app is on.
* **Live:** switch it off to stop sampling. It also pauses while the window is minimized.

It only reads a few files from `/proc` and `/sys` (about 1 ms per sample, a full process scan every 10 s) and
slows down by itself if sampling gets expensive, so it is safe to keep running while you play.

**Settings** opens a panel over the window (close it with ✕, Esc or a click outside): *Privacy* (what is stored
and sent, history and log masking, administrator rights), *General* (notifications, copying the reports
to the Desktop), *System overview* (BIOS version, CUs, cores, threads, speed test, NVMe size, free space and package
count at a glance), *Logs & history* (clean up logs), *About* (version, build date, repository) and *Print
results*.

### Running and stopping

* **Run all tests** never includes the benchmark (42), the disk speed test (43) or the internet speed test
  (44); **Run all &lt;category&gt; tests** runs every test on that page.
* Only one run happens at a time; the buttons are off while it runs.
* **Stop** stops the current run: the tests first end their CPU and GPU load and remove their temporary files.
  The test that was running goes back to not run.
* A test takes the color of the worst line it logged (error over warning over success over info). Its output
  also streams into the terminal of the test's own category page. The **Hints** panel collects suggested fixes
  (⚠) and background notes (ℹ).

### Administrator password

Most checks read root-only logs and sysfs, so the tests run through `sudo`. When sudo needs a password, a masked
prompt appears; the password goes straight to sudo and is never stored or logged. sudo remembers it for its
usual timeout, so you are not asked for every test. *Settings › Privacy* can turn sudo off (fewer checks, never
a password) or make sudo forget the password right away.

### Logs

Every run is saved as `~/.local/share/bc250-bazzite-test/logs/<YYYYmmdd-HHMMSS>_<scope>.log`. **Show Logs** on a
page lists that page's runs; *Show all logs* lists every run. With *Mask personal data in saved GUI logs* on
(the default, *Settings › Privacy*), host and user name, home folder, serial numbers, MAC and IP addresses and
the speed test's ISP and result URL are replaced by placeholders in these files; the terminal shows everything.

Below the list of runs, **Files mentioned in this run** lists every log, CSV and config file the selected run
refers to (the full report, the stress CSV, the GPU load tool log, the governor config, and so on). Click one to
read it. A warning icon means the file is not on this machine; very large files show their last 2 MiB;
root-only files show the `sudo less` command to use instead. For a CSV, **Show graph** plots it.

**Clean up logs** (*Settings › Logs & history*) removes the run logs older than N days (default 30), or all logs.
The dialog shows what goes before anything happens. Removing old logs keeps the results in the history; *Remove
ALL* also empties the history. The full reports are owned by root, so removing them asks for your password.
`bench-baseline.json` and the benchmark and speed test history CSVs are always kept.

### History

Every result is stored in a small SQLite database, `~/.local/share/bc250-bazzite-test/history.db`: per run the
date, scope, active CUs and cores/threads (kernel version and mitigation state only when turned on in
*Settings › Privacy*); per test the status and the number of hints; and the numbers worth comparing (benchmark
scores, stress clocks, temperatures and power, disk and internet speeds). Full reports that are not in the
history yet (in `/var/log/bc250-bazzite-test` and the Desktop folder) are imported once, at startup. The
database grows by a few KB per run. The history and the logs are readable by your user only. The app checks the
history at every start: when it is damaged or was changed outside the app, it is kept aside as
`history.db.damaged-<date>` and a new, empty history starts.

On the **History** page, **From** / **to** pick the dates and **All dates** shows everything again.

* **One run selected:** its results per category, its measurements and the files it wrote. **Show logs** opens
  its log and full report; click a test name to open its page.
* **Two runs selected** (Ctrl-click or Shift-click): side by side, the older run on the left: the counts and
  configuration, the tests whose result changed and every measurement with the difference. Green is better, red
  is worse; differences under 2% count as the same (measurement noise). Untick *Only differences* to see every
  test.

Typical use: run everything and the benchmark, change something (CU unlock, BIOS, kernel, governor), run them
again, and compare the two runs.

### Integrity of the tests

Before every run the app checks that the test files are exactly the ones that came with this version and that
only an administrator can change them (see *Why `/opt`?* above). If not, no tests run, since they would run with
administrator rights, and a red bar at the top says so: reinstall the app.

### Graphs

**Show graph** opens a chart window for the CSV files the tests write:

* **Stress telemetry** (next to the stress settings): the latest stress run as panels for clocks, temperatures,
  GPU busy, GPU power, GPU memory, fan, GPU voltage and load average, with the peaks on top. Pick older runs from
  the *File* list. A clock that drops while the temperature climbs is thermal throttling; a line that simply
  stops is the moment the board froze.
* **Benchmark history** (Performance page): bar charts per run of the scores against the baseline, GPU FP32, CPU
  multi- and single-thread, VRAM bandwidth and GPU clock. Bars are labeled *#run CUs threads*; hover for the
  date, mitigations and kernel.
* **Any CSV** in Show Logs: one panel per numeric column.

Drag a rectangle to zoom in, right-click to zoom out, hover a line for its value. *Save as PNG* saves all panels
as one image. Graphs need the `PyQt6-Charts` package, which the installer puts in the venv.

### Stress test and benchmark settings

* **Stress test (41):** *Stress duration* is how long the load runs (10–3600 s, default 120), *Sample interval*
  the seconds between telemetry samples (default 2). It loads all CPU threads (`stress-ng`, or shell
  busy-loops) and the GPU (`memtest_vulkan`, which also checks the VRAM for errors and is recommended, or
  `vkpeak`, `vkmark`, `glmark2`, `vkcube`). This is a deliberate attempt to reproduce lockups under load: the
  system is sluggish while it runs and may freeze. If it does, the last telemetry line is the board's final
  operating point. The app asks before it starts.
* **Benchmark (42):** *CPU time per phase* is the seconds per `stress-ng` phase (default 20); keep it the same
  between runs you compare. The log also shows the theoretical FP32 peak for the detected CU count and clock: a
  result far below it means unlocked CUs are not doing work. Close games and other heavy apps first. How to save
  the baseline: [Performance score](#performance-score-comparing-cu-and-core-unlocks).

### A game's FPS

The FPS comes from MangoHud's log, which it writes while the game runs. Turn it on once in
`~/.config/MangoHud/MangoHud.conf`:

```ini
output_folder=/home/<you>/mangohud-logs
autostart_log=1
log_interval=500
```

Create the folder, and make sure MangoHud is active for the game (for example the Steam launch option
`mangohud %command%`). A log file is written per game session; delete old ones now and then. Without logging,
the game's name and its CPU and GPU share are still shown.

The **Game details** launch line does not work with the **Flatpak** version of Steam: the game would not start.
Use the Steam that comes with Bazzite. The **Checks for the last session** always describe the newest session;
older sessions keep their graphs.

## Output files

All files go to `/var/log/bc250-bazzite-test/`:

| File                                       | Contents                                                                               |
|--------------------------------------------|----------------------------------------------------------------------------------------|
| `bc250-test-results-<YYYYmmdd-HHMMSS>.log` | Full report.                                                                           |
| `bc250-stress-<YYYYmmdd-HHMMSS>.csv`       | Stress telemetry, written only by a stress run.                                        |
| `bc250-gpuload-<YYYYmmdd-HHMMSS>.log`      | Output of the GPU load tool, written only by a stress run.                             |
| `bc250-memtest-<YYYYmmdd-HHMMSS>.log`      | memtest_vulkan's own log, when it was the GPU load tool.                               |
| `bc250-bench-<YYYYmmdd-HHMMSS>.json`       | Benchmark result, written only by the benchmark.                                       |
| `bc250-bench-vkpeak-<YYYYmmdd-HHMMSS>.log` | vkpeak output of the benchmark.                                                        |
| `bc250-bench-history.csv`                  | One line per benchmark run, to compare configurations over time.                       |
| `bc250-disk-<YYYYmmdd-HHMMSS>.csv`         | Write speed and drive temperature per 256 MiB, only when writes are tested.            |
| `bc250-speedtest-<YYYYmmdd-HHMMSS>.json`   | Raw speed test result, only by the internet speed test.                                |
| `bc250-speedtest-history.csv`              | One line per speed test: interface, server, speeds, idle/loaded latency, jitter, loss. |

They are copied to `~/Desktop/bc250-bazzite-test/` of the desktop user at the end of the run for easy
sharing (GUI: *Settings > General > Copy the full reports to Desktop*, on by default; command line:
skipped with `--no-desktop`).
During a stress run the files are flushed to disk after every sample, so they survive a hard lockup.

The GUI additionally keeps its own captured output of every run as
`~/.local/share/bc250-bazzite-test/logs/<YYYYmmdd-HHMMSS>_<scope>.log` — these are not the files above,
just what the script printed during that run.

In-game monitoring writes one CSV per gameplay session to
`~/.local/share/bc250-bazzite-test/game-logs/bc250-game-<game>-<YYYYmmdd-HHMMSS>.csv`
(columns `elapsed_s, fps, game_cpu_pct, game_gpu_pct, cpu_pct, gpu_pct, sclk_mhz, mclk_mhz,
gpu_temp_c, gpu_power_w, vram_used_mib, gtt_used_mib, vddgfx_mv, fan_rpm, cpu_temp_c, cpu_mhz_avg,
mem_avail_mib`); the **Game details** page opens them as graphs. Next to each CSV is a small `.json`
with what is only measured once per session — the VRAM/GTT budget, the GPU power cap, the real
1%/0.1% lows and stutter share from MangoHud's per-frame log, and the amdgpu errors the kernel logged
while the game ran. The **Game details** page turns both into the pass/warn/fail *Checks for the last
session*.

The CSV columns are `elapsed_s, sclk_mhz, mclk_mhz, gpu_busy_pct, vram_used_mib, gtt_used_mib,
gpu_temp_c, gpu_power_w, vddgfx_mv, cpu_tctl_c, cpu_mhz_avg, fan_rpm, load1` — open it directly in
LibreOffice Calc to plot clocks, memory and power against temperature.

`gpu_busy_pct` comes from the kernel's `gpu_busy_percent` when it works. Stock kernels have no GPU-load
sensor for Cyan Skillfish (the read fails, which is also why MangoHud / the Steam overlay show 0% unless
the governor's `fix-metrics` is enabled), so the app then measures the gfx and compute engine time of every GPU
client from `/proc/*/fdinfo` — the same method nvtop uses. The log states which
source was used.

The summary reports peak VRAM and GTT use as a percentage of each budget, warning at 90% VRAM (allocations spilling into
GTT) and 85% GTT (the GPU is close to running out of memory).

Every line is tagged `SUCCESS`, `INFO`, `WARNING` or `ERROR`, and a `[SUMMARY]` block at the end
reports the overall verdict. In the app these become the button colors, the counters and the hints panel.

---

## Tests

### System

| #  | Test                         | Checks                                                                          |
|----|------------------------------|---------------------------------------------------------------------------------|
| 00 | Platform Identification      | Confirms the board really is a BC-250 and reports the BIOS (stock vs modded; latest stock 5.00 scores a pass, older stock BIOSes a warning with an update hint), Bazzite image and kernel. |
| 01 | Running Services             | Lists every active systemd service.                                             |
| 02 | Failed Units                 | Errors on any unit in a failed state.                                           |
| 03 | System Uptime                | Reports uptime and load average.                                                |
| 11 | Resource Consumption         | Top CPU and memory consumers.                                                   |
| 12 | Boot Time                    | `systemd-analyze` breakdown, warns on units taking over a minute.               |
| 31 | File and Directory Integrity | Verifies `/var/log` exists and is writable.                                     |

### Network

| #  | Test                   | Checks                                                                    |
|----|------------------------|---------------------------------------------------------------------------|
| 04 | Network Connectivity   | Pings an external host.                                                   |
| 05 | DNS Resolution         | Resolves a known hostname.                                                |
| 06 | Public Internet Access | Fetches a URL over HTTPS.                                                 |
| 07 | Open Ports             | Lists listening TCP/UDP sockets.                                          |
| 08 | NTP Synchronization    | Confirms the clock is synchronized.                                       |
| 30 | SSH Service            | Reports `sshd.service` / `sshd.socket` state (off by default on Bazzite). |
| 53 | Wi-Fi Adapter          | Every Wi-Fi adapter and whether the kernel has a driver for it. See below. |
| 44 | Internet Speed         | **Opt-in**: run it from its button on the Network page. See below.       |

**How test 44 measures the connection** (Ookla's `speedtest`, or `speedtest-cli` as a fallback; about 30 s):

* **Download and upload** in Mbps, plus the data used (roughly 1 GB on a gigabit line).
* **Idle latency and jitter**, and the **latency while downloading/uploading**. When the loaded latency is more
  than 100 ms above idle the line suffers from *bufferbloat*: games lag whenever something else uses the
  connection. The fix is SQM (fq_codel/CAKE) in the router. Only Ookla's CLI measures loaded latency.
* **Packet loss** (Ookla only): over 1% is a warning.
* **The local link**: the interface the traffic uses (Ethernet or Wi-Fi) and its link speed. A 10/100 Mbit/s
  Ethernet link is a warning (bad or 2-pair cable); a download near the link speed means the port is the limit.
* A VPN in the path is noted, because then the VPN is measured, not the line.
* Every run is appended to `bc250-speedtest-history.csv`; **Show graph** compares all runs.
* Install Ookla's CLI: download the Linux x86_64 `.tgz` from <https://www.speedtest.net/apps/cli> and put the
  `speedtest` binary in `~/.local/bin`. Running it accepts Ookla's license and GDPR terms.

**What test 53 says about Wi-Fi.** The BC-250 has no Wi-Fi of its own; a USB stick (or a PCIe card) adds it. The
test lists every Wi-Fi adapter it finds, with its USB or PCI ID and its driver, and says for each one:

* **connected** (a success): the band, the signal in dBm and the link speed. The network's name stays out of the
  report;
* **works, not connected**: connect it in the network settings;
* **switched off** by rfkill, in software or by a hardware switch (a warning);
* **the driver is there but not loaded**: the running kernel has a module for the stick's ID that is not loaded;
  the test gives the `modprobe` command;
* **firmware missing**: the driver took the adapter but did not get its firmware file at this boot;
* **no driver**: the running kernel has no driver for the stick's ID, so it does not work on Bazzite as it is;
* **storage mode**: the stick shows up as a small disk with the Windows driver. An AIC8800D80 stick (the UGREEN
  AX900 and others) needs [BC-250 USB Wi-Fi](wdriver.md), which builds its driver; another stick switches when
  its disk is ejected.

With BC-250 USB Wi-Fi's driver installed, the test also checks its service: enabled, its last run without an
error, the driver built for the running kernel and loaded. The test only reads: it loads no module and switches no
stick. No adapter at all is reported, not a warning: the network cable needs nothing.

### Storage and memory

| #  | Test                             | Checks                                                                                 |
|----|----------------------------------|----------------------------------------------------------------------------------------|
| 09 | Disk Configuration               | Filesystem usage and mount points.                                                     |
| 10 | NVMe Devices                     | Detection; PCIe link speed/width vs. what the drive and the slot support; DRAM cache or host memory buffer (DRAM-less); SMART health: wear, media errors, spare, temperature and time spent throttling, unsafe shutdowns. |
| 14 | Memory and Swap                  | RAM usage and the full swap topology: zram, zswap, disk swap, overlaps and swappiness. |
| 37 | Unified Memory and VRAM Pressure | VRAM/GTT usage, OOM-kill history, `vm.max_map_count`, swappiness.                      |
| 49 | CPU Memory Bandwidth             | `stress-ng` STREAM-like bandwidth on 1 thread and all threads; shows the GDDR6 latency cost the CPU pays for the GPU's console-class bandwidth. |
| 43 | Disk Speed (read, write, SLC cache) | **Opt-in**: run it from its button on the Storage page. See below.                   |

**How test 43 measures the system disk** (the disk that holds `/var/tmp`):

* **Sequential read**: `dd` reads 4 GiB straight from the partition with direct I/O. Nothing is
  written. The result is compared with the PCIe link ceiling from test 10.
* **Random 4K read** at queue depth 1 and 32: `fio --readonly` over the whole partition, 10 s each.
  This part is skipped without a system-wide `fio` (a Homebrew fio is not run as root). A high QD1 latency (over ~150 µs) is typical of a DRAM-less drive
  without a host memory buffer.
* **Sequential write and SLC cache**, only with *Disk speed test (43): also test writes* ticked:
  * Writes a temporary file in `/var/tmp` in 256 MiB chunks (direct I/O, flushed) and deletes it
    afterwards. The file is created with `chattr +C`, so btrfs doesn't compress it (compression would
    fake the result).
  * Each chunk's speed and the drive temperature go to `bc250-disk-<timestamp>.csv`; **Show graph**
    plots it.
  * The point where the speed falls below 60% of the starting speed is reported as the SLC cache
    size. If the drive was at its warning temperature at that moment, it is reported as thermal
    throttling instead.
  * Pick a size larger than the expected cache: a few GiB on cheap/QLC drives, tens of GiB on
    large TLC drives. Needs that size plus 5 GiB free. The run stops early if the drive reaches its
    critical temperature.

**DRAM cache detection (test 10)**:
* No drive reports "has DRAM" directly.
* DRAM-less NVMe drives ask the host for a *Host Memory Buffer* (the `HMPRE` field of
  `nvme id-ctrl`). The kernel logs it as `allocated N MiB host memory buffer`.
* The test reads both. If neither is present, the drive has its own DRAM.
* On the BC-250 the HMB comes out of the RAM that is shared with the GPU (usually 32–64 MiB).

### System logs

| #  | Test           | Checks                                                                   |
|----|----------------|--------------------------------------------------------------------------|
| 15 | Boot Logs      | Current-boot kernel errors, with known-benign BC-250 noise filtered out. |
| 16 | System Journal | Journal errors from the last 7 days, same filtering.                     |

Tests 15, 16 and 17 follow the log lines with a hint per kind of line: what it means and what to do about it,
with the number of lines it covers. Real faults (GPU hangs, disk errors, crashes) come first, known harmless
messages after them. A service that failed gets the commands to read why and to turn it off. Lines without a known
explanation are grouped per program, with the command to read them.

### GPU and graphics

| #  | Test                  | Checks                                                                     |
|----|-----------------------|----------------------------------------------------------------------------|
| 17 | amdgpu Driver         | Confirms `amdgpu` is bound to the Cyan Skillfish APU.                      |
| 18 | GPU Governor          | Verifies a governor is running; without one the GPU is pinned at 1500 MHz. |
| 19 | GPU Frequency Scaling | Reads `pp_dpm_sclk` / `pp_dpm_mclk` to confirm the clock actually moves.   |
| 20 | Vulkan / Mesa         | Confirms RADV reports GFX1013 and not the llvmpipe software fallback.      |
| 21 | Compute Unit Count    | Active CUs from the live GPU registers (needs admin rights and umr), else the kernel value (24 stock, up to 40 unlocked); explains why kernel and RADV keep reporting the probe-time value. |
| 29 | Display Session       | Identifies the display manager, session type and compositor.               |
| 47 | Vulkan Futureproof Matrix | Vulkan API level and the feature set modern games need: ray tracing, mesh shaders, VRS, pipeline libraries and the VRAM carveout vs today's 8 GiB recommendation. Hard evidence of which current and upcoming titles can run at all. |
| 50 | Video Decode and Encode (VCN) | `vainfo` codec matrix: H.264/HEVC/VP9/AV1 decode and encode. Matters for streaming, OBS recording and video playback while gaming. |
| 51 | HDMI-CEC | The CEC adapter of the DisplayPort output (only when the DP-to-HDMI converter tunnels CEC), whether the TV answers a poll, and Bazzite's CEC mode. Whether the board can turn the TV on and off; see [HDMI CEC Manager](cec.md). |
| 52 | HDMI-CEC Services | Whether the services behind the TV control run: Valve's CEC daemon (`cecd`), HDMI CEC Manager's background and boot services when installed, and Bazzite's dGPU CEC services when enabled. A service that is installed but not running is a warning; one that is not installed is only reported. |

### CPU and firmware

| #  | Test                      | Checks                                                                          |
|----|---------------------------|---------------------------------------------------------------------------------|
| 23 | IOMMU Disabled            | Counts IOMMU groups; IOMMU is broken on the BC-250 and must be off — via BIOS or the `amd_iommu=off` kernel arg. |
| 24 | CPU Mitigations           | Passes when `mitigations=off` is set (worth roughly +18 FPS on this board).     |
| 25 | CPU Core and Thread Count | Reports cores/threads — 6C/12T stock, 8C/16T after the unlock.                  |
| 26 | CPU Power Management      | Checks cpufreq scaling and C-states; both need the BC-250 ACPI fix.             |
| 46 | CPU Voltage               | CPU/SoC voltage rails from hwmon (amdgpu `vddgfx`/`vddnb`) plus the voltage each core requests (current P-state VID via MSR, one line per core). |

### Stability and thermals

| #  | Test                          | Checks                                                                        |
|----|-------------------------------|-------------------------------------------------------------------------------|
| 22 | Hardware Sensors              | nct6683/nct6687 SuperIO, GPU and CPU temperatures, fan RPM sanity.            |
| 27 | Handheld Daemon               | Confirms `hhd.service` is masked; it causes constant micro-stuttering.        |
| 28 | Suspend Targets               | Confirms sleep/suspend/hibernate targets are masked; s2idle resume is broken. |
| 40 | Power Delivery and Throttling | GPU power cap and draw, governor frequency ceiling, throttle messages.        |

### Crash forensics

| #  | Test                                | Checks                                                                                      |
|----|-------------------------------------|---------------------------------------------------------------------------------------------|
| 34 | Previous Boot Shutdown Integrity    | Flags previous boots that ended with no shutdown sequence — the signature of a hard lockup. |
| 35 | GPU Hang and Reset History          | Ring timeouts, GPU resets, VM faults and soft recoveries across retained boots.             |
| 36 | Kernel Panic, Lockup and Crash Dump | Oopses, soft/hard lockups, call traces, `coredumpctl` records and NMI watchdog state.       |

### Gaming

| #  | Test                           | Checks                                                                                  |
|----|--------------------------------|-----------------------------------------------------------------------------------------|
| 38 | Steam and Gaming Stack         | Steam, gamescope, gamemode, MangoHud, umu; library paths and free space.                |
| 39 | Audio Stack                    | PipeWire/WirePlumber state, default sink and ALSA cards.                                |
| 48 | Real-Game Frametime (MangoHud logs) | Reads the most recent MangoHud logs from real play sessions: average FPS, 1% and 0.1% lows and stutter share — evidence from actual games, which synthetic benchmarks cannot give. |
| 41 | CPU + GPU Stress and Telemetry | **Opt-in.** Loads the board and records clocks, temperature, power and fans throughout; includes a sustained-performance verdict (first minute vs last minute). |

### Performance

| #  | Test                                    | Checks                                                                                              |
|----|-----------------------------------------|-----------------------------------------------------------------------------------------------------|
| 42 | Performance Benchmark (CPU / GPU score) | **Opt-in**: run it from its button. CPU single/multi-thread and GPU FP32 compute, scored against a stock board, plus a comparison ladder against known systems (Steam Deck, Series S, Steam Machine, PS5, desktop GPUs). |

See [Performance score](#performance-score-comparing-cu-and-core-unlocks) below.

### Updates

| #  | Test                   | Checks                                                                           |
|----|------------------------|----------------------------------------------------------------------------------|
| 13 | Security Configuration | firewalld zones and SELinux enforcement mode.                                    |
| 32 | OSTree Deployment      | Lists deployments and warns when a newer one is staged and waiting for a reboot. |
| 33 | Update and Patch       | Checks for available rpm-ostree updates and lists Flatpak remotes.               |
| 45 | Installed Packages     | Counts installed software per source: image RPMs, layered/overridden packages, Flatpak apps, Homebrew, AppImages, Distrobox containers. Names and versions only. |

---

## Performance score: comparing CU and core unlocks

Test 42 runs fixed workloads and scores them against a **baseline: your own board in its stock
configuration** (6 cores / 12 threads, 24 CUs, governor max 1850 MHz) = 100. A score of 132 means 32%
faster than stock.

| Score     | Workload                                                              | Changes with                                |
|-----------|-----------------------------------------------------------------------|---------------------------------------------|
| CPU score | `stress-ng --cpu-method matrixprod`, all threads, bogo ops/s          | Core/thread unlock, mitigations, CPU clock  |
| (CPU 1T)  | Same on one thread, reported in the log and history                   | Mitigations, CPU clock                      |
| GPU score | `vkpeak` FP32 GFLOPS (best of fp32-scalar / fp32-vec4)                | CU unlock, GPU clock / governor maximum     |

FP32 throughput scales with CUs × clock, so it shows exactly what a CU unlock adds. The benchmark also
samples the GPU clock and prints the theoretical peak (CUs × 128 × MHz); a result far below it means
unlocked CUs are not doing work, or the clock dropped. vkpeak's `copy-d2d` VRAM bandwidth is recorded
too (memory-bound, so it does not change with CUs).

1. Put the board in its stock configuration (undo any CU unlock and reboot, so 24 CUs), close games, tick
   *Save as baseline (stock board only)* and run test 42 once. This writes
   `/var/log/bc250-bazzite-test/bench-baseline.json`, the 100 mark for the whole system.
2. Apply an unlock and run test 42 again (without *Save as baseline*). The CPU and GPU score boxes at the
   top show the result; *Benchmark history* compares all runs.

Needs `stress-ng` (`rpm-ostree install stress-ng`) and `vkpeak`
([releases](https://github.com/nihui/vkpeak/releases), put the binary in `~/.local/bin`). Keep the
CPU phase length the same between runs you compare.

### Example: 24 → 36 CU unlock

Measured on a BC-250 (6C/12T, governor max 1850 MHz, mitigations off, kernel 7.2.7-ogc1.1, Mesa 26.2.2),
October 2026. The 36-CU run scores **149** on the GPU; the ideal is 150 (36 ÷ 24).

|                              | 24 CU (baseline) | 36 CU          | Change              |
|------------------------------|------------------|----------------|---------------------|
| GPU FP32                     | 5689 GFLOPS      | 8504 GFLOPS    | **+49%**            |
| Share of theoretical maximum | 100%             | 100%           | holds 1850 MHz      |
| VRAM copy                    | 187 GB/s         | 185 GB/s       | same                |
| CPU multi / single (ops/s)   | 6646 / 1094      | 6633 / 1086    | same (within noise) |

* All 36 CUs are active and the GPU keeps its full clock during the benchmark.
* Memory bandwidth does not grow with the CUs, so games limited by memory bandwidth (high resolutions,
  large textures) gain less than the FP32 figure suggests. Expect roughly +15–35% FPS in real games.
* The CPU is unchanged: a CU unlock adds GPU units only.
* The benchmark is short. Check the unlock with a long stress test (test 41 with a duration of 300 s and
  memtest_vulkan): it shows whether the clock holds when the board is hot, how much power it draws,
  and whether the extra CUs cause VRAM errors.

Stress test at 36 CUs (300 s and 600 s runs, memtest_vulkan + stress-ng on 12 threads):

| Metric                 | Result                                                    |
|------------------------|-----------------------------------------------------------|
| GPU clock under load   | 1850 MHz throughout (at 912 mV)                           |
| GPU busy               | ~90%                                                      |
| GPU power              | 121 W average, 132 W peak                                 |
| Temperatures           | GPU 59 °C max, CPU (Tctl) 71 °C max, fan 2603 RPM max     |
| VRAM errors            | none (about 27,000 memtest_vulkan passes in 10 min, ~374 GB/s) |
| Kernel faults          | no GPU hangs, panics, throttling or OOM events            |

The 36-CU unlock is stable under sustained load and runs cool. Both runs show one ~12 s pause at
t≈275 s: that is memtest_vulkan itself, switching from its standard 5-minute test to its endless
test ("Standard 5-minute test PASSed!" in the gpuload log). Test 41 reports that pause as INFO; any
other stall is a WARNING with the system journal around it.

---

## Diagnosing a hard lockup

A freeze with a continuous screeching tone is a total kernel stall: the sound card keeps replaying
the same DMA buffer because nothing is left running to refill it. That rules out an application
crash and points at the kernel or the SoC itself.

Enable crash capture first, because a freeze this abrupt never reaches the disk:

```bash
sudo mkdir -p /var/log/journal && sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo sysctl -w kernel.nmi_watchdog=1
```

Then reproduce it under observation: on the *Stability and thermals* page set *Stress duration* to 300 s
and *Sample interval* to 1 s, and run the stress test (41).

The telemetry line prints to the page's terminal every 10 seconds, so if the board dies the last values on
screen are its final operating point. Note the `sclk` and `vddgfx` at that moment.

Most likely causes, in order:

1. **Governor ceiling too high.** Many boards hard-lock above roughly 1850 MHz. Lower the maximum in
   `/etc/cyan-skillfish-governor-smu/config.toml`, then
   `sudo systemctl restart cyan-skillfish-governor-smu` and retest.
2. **Power supply sag.** A marginal 12 V rail browns out the SoC and leaves no log evidence. Suspect
   this if the stress run survives cleanly but games still crash.
3. **Unified memory exhaustion.** CPU and GPU share one 16 GB pool — see test 37.
4. **Missing ACPI fix.** No C-states and no cpufreq scaling — see test 26.

## Useful follow-up commands

```bash
journalctl --list-boots                  # which boots are still retained
journalctl -b -1 -n 50                   # last entries before the previous boot ended
sudo cat /sys/fs/pstore/dmesg-*          # firmware-captured panic, if any
coredumpctl list --since "-14 days"      # crashed applications
watch -n1 cat /sys/class/drm/card0/device/pp_dpm_sclk    # live GPU clock
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

## Fix: GPU load shows 0% in the Steam overlay / MangoHud

The stock kernel has no GPU-load sensor for Cyan Skillfish. Reading `gpu_busy_percent` fails, and the
`gpu_metrics` table the overlays read carries no valid load value either. Depending on the tool, the
GPU load then shows as **0%** or as an impossible **655%** (the raw `0xFFFF` in that table).

`cyan-skillfish-governor-smu` already measures the real load to drive the clock. With `fix-metrics`
enabled it also writes that load into a patched copy of `gpu_metrics` and bind-mounts it over the
sysfs file, so the Steam performance overlay, MangoHud and radeontop show a real GPU %.

Enable it in `/etc/cyan-skillfish-governor-smu/config.toml`:

```toml
[gpu-usage]
fix-metrics = true
method = "busy-flag"   # "busy-flag", "process" or "kernel"
```

```bash
sudo sed -i 's/^fix-metrics *= *false/fix-metrics = true/' /etc/cyan-skillfish-governor-smu/config.toml
sudo systemctl restart cyan-skillfish-governor-smu
mount | grep gpu_metrics                 # the patched copy should be mounted over the sysfs file
```

Then start a game with the Steam overlay (performance level 3 or higher) and check that the GPU % moves.

Notes:

* `fix-metrics` also enables the load calculation used by the governor's performance mode.
* Test 40 reports `fix-metrics`, the load method and the clock control method. When `fix-metrics` is on it also
  checks that the patched `gpu_metrics` is really mounted; when it is off it gives the hint to enable it.
* `[gpu] set-method` sets how the governor changes the clock:
  * `smu` talks to the SMU (the GPU's power-management firmware) directly. It's the default and the usual
    choice on a stock kernel.
  * `kernel` goes through the amdgpu driver, which a stock driver caps at 2000 MHz. Use it only on a patched
    BC-250 kernel.
* `method` sets how the governor measures load:
  * `busy-flag` samples the GPU's busy bit and is the default.
  * `process` sums per-program GPU time from `/proc/*/fdinfo`, but costs more CPU and can stall on Proton
    games with very many open files.
  * `kernel` only works on patched kernels where `gpu_busy_percent` is readable.
* On some kernels the metrics patching misbehaves. If the overlay or governor acts up after enabling it,
  set `fix-metrics = false` again and restart the governor.
* Kernels with the BC-250 telemetry fixed in-kernel (e.g. MastaG's linux-cachyos-bc250) report the load
  natively, and `fix-metrics` is not needed there.
* A newly unlocked CU count or a kernel update can make the overlay drop back to 0%. Reinstalling or
  restarting the governor usually restores it.
* The stress test (41) does not depend on this setting. It measures GPU load itself, from
  `/proc/*/fdinfo`.

Source: the unofficial BC-250 community guide (troubleshooting and GPU governor chapters) and the
cyan-skillfish-governor-smu README.

## Requirements

The app never installs anything — it only detects what is already on
`PATH`. Layer the optional load tools once, and they are picked up automatically on every later run:

```bash
rpm-ostree install stress-ng glmark2
systemctl reboot
```

Or use the optional helper shipped with the app, which installs everything below in one go — it layers
the RPM packages and downloads `vkpeak`, `memtest_vulkan` and the Ookla `speedtest` CLI into
`~/.local/bin` (interactive: each group is asked for separately):

```bash
./development/tools/install-requirements.sh          # interactive
./development/tools/install-requirements.sh --all    # everything, no questions
```

Also recommended: zswap in front of a disk swapfile instead of Bazzite's zram-only swap, so memory pressure
does not go straight to the OOM killer (on the BC-250 that can present as a hard freeze). See
*Swap file recommendation* in [Bazzite Test script](../development/bazzite-test.md#swap-file-recommendation) for the Btrfs-safe commands; tests 14 and 37
check and report the swap layout.

`vulkan-tools` (which provides `vkcube`) is usually present on Bazzite already. Note that **Flatpak
versions are not detected** — the binary has to be on `PATH`, so layering is the right route here.

| Tool                                 | Used by           | Fallback if missing                                                                 |
|--------------------------------------|-------------------|-------------------------------------------------------------------------------------|
| `stress-ng` or `stress`              | Test 41 CPU load  | Shell busy-loops, one per thread. Still saturates the CPU.                          |
| `stress-ng`                          | Test 42 CPU score | No CPU score (warning).                                                             |
| `vkpeak`                             | Test 42 GPU score | No GPU score (warning).                                                             |
| `memtest_vulkan` or `vkpeak`         | Test 41 GPU load  | vkmark, glmark2 or vkcube (much lighter, see below).                                |
| `vkmark`, `glmark2` or `vkcube`      | Test 41 GPU load  | CPU-only stress plus a warning.                                                     |
| `lm_sensors`                         | Test 22           | Falls back to reading hwmon sysfs directly.                                         |
| `vulkan-tools`                       | Tests 20, 21      | Those checks are skipped.                                                           |
| `nvme-cli` or `smartmontools`        | Test 10           | DRAM/HMB guessed from the kernel log; no SMART health.                              |
| `fio`                                | Test 43           | Random 4K read skipped (sequential read/write use `dd`).                            |
| Ookla `speedtest` or `speedtest-cli` | Test 44           | Test 44 warns and is skipped. `speedtest-cli` has no loaded latency or packet loss. |

* Preference order for GPU load is memtest_vulkan → vkpeak → vkmark → glmark2 → vkcube.
* **memtest_vulkan is recommended.** It's a headless compute load that keeps the GPU fully busy, and it also
  checks the VRAM for errors; any error found is reported as an ERROR. It isn't packaged: download the Linux
  build from [its releases](https://github.com/GpuZelenograd/memtest_vulkan/releases) and put the
  `memtest_vulkan` binary in `/usr/local/bin` or `~/.local/bin` (the app also finds it there).
* **User-installed tools never run as root.** The app finds tools in `~/.local/bin` and Homebrew itself
  instead of adding those folders to root's PATH. Anything writable by your user (those folders, or any
  tool not owned by root) is run as your user, not as root. `fio` needs root to read the raw partition,
  so a Homebrew/`~/.local/bin` fio is not used: install it with `rpm-ostree install fio` for the random 4K test.
* memtest_vulkan is limited to ¾ of the VRAM and at most half of the available RAM. Left alone it fills
  all free RAM on this APU, and the OOM killer then kills the desktop (kwin_wayland).
* Memory safety during the stress run: the GPU load tool is the OOM killer's first victim (`oom_score_adj`
  1000), the test protects itself so it can always stop the load, the tool is wrapped in `timeout` so it
  never outlives the test, and a memory guard stops the run when available RAM drops below 5% (min 512 MiB).
* vkmark and glmark2 render one light frame at a time. On the BC-250 vkmark ran ~2000 FPS in every scene and
  left the GPU only ~20% busy at 1000 MHz, so test 41 will warn that the GPU was never meaningfully loaded.
  As a fallback they run in a 2560x1440 window, and vkmark only runs `effect2d` blur and the `desktop` scene
  with 16 large windows.
* The CPU load runs as `SCHED_IDLE` (`chrt -i 0`, or `nice 19` without `chrt`), and its autogroup is set to nice 19,
  so it only uses cycles nothing else wants and never slows the GPU load tool or the desktop.
* vkcube is a spinning cube — it'll register, but it won't push the GPU hard enough to be a real stability test.

### Install commands

```bash
sudo rpm-ostree install lm_sensors
systemctl reboot
```

```bash
rpm-ostree install vkmark
systemctl reboot
```

```bash
rpm-ostree install nvme-cli fio      # test 10 SMART/DRAM detection, test 43 random reads
systemctl reboot
```

**INFO: glmark2, vkcube, vulkan-tools and smartctl are already available on Bazzite.**

## Advice to set the VRAM size

The split sets a minimum, not a reservation.
The GPU grows past it dynamically.
512 MB is genuinely the RAM-efficient choice, because unused VRAM returns to the regular pool when the game exits.
With an 8 GB split that memory is permanently unavailable even when a game uses 2 GB.
But 512 MB has two documented crash mechanisms

1. Dynamic ceiling. Linux allows dynamic VRAM up to half the remaining RAM, so:

   | Split  | Max total VRAM before the display driver crashes |
   |--------|--------------------------------------------------|
   | 512 MB | 8.25 GB                                          |
   | 4 GB   | 10 GB                                            |
   | 6 GB   | 11 GB                                            |
   | 8 GB   | 12 GB                                            |

   Fixed with ttm.pages_limit — we don't need a bigger split for this one.
2. Framebuffer pinning - Scatter-gather display is disabled on Cyan Skillfish, so every framebuffer the compositor
   displays must be pinned inside the real minimum carve. When a game fills that 512 MB, the next flip can't be pinned
   and the session dies:
   ```bash
   amdgpu: ... pin failed
   Failed to pin framebuffer with error -12
   gamescope: drm: fatal flip error, aborting
   ```
   No GPU hang, no OOM-kill — nothing the tests were looking for. ttm.pages_limit does not help, because it only raises
   the dynamic ceiling. The documented fix is a larger minimum split; 6 GB resolved it for the reporter and never
   recurred.
   6 GB is the value with a documented fix-report behind it for exactly this failure.
   We can use fanoush/bc250_memcfg, which writes to CMOS and survives reflashes. This also makes
   the "P3.00 Chipset Menu" modded BIOS obsolete for VRAM purposes: its only draw was exposing
   the hidden UMA setting in the setup menu, and bc250_memcfg sets the same CMOS value from Linux
   on any BIOS:

   ```bash
   git clone https://github.com/fanoush/bc250_memcfg
   cd bc250_memcfg
   make
   sudo ./bc250memcfg UMA_SIZE 6144
   systemctl reboot
      
   # drop the pages limit if set, not needed when applying this
   rpm-ostree kargs --delete-if-present=ttm.pages_limit
      
   # verify after reboot:
   cat /sys/class/drm/card*/device/mem_info_vram_total   # 6442450944 = 6 GB
   free -h                                               # ~9.4 GB system RAM
   ```

## Disabling the IOMMU without a modded BIOS

The IOMMU is broken on the BC-250 and leaving it active creates an unstable system. The modded
3.00 BIOS unlocks the Advanced Chipset menu where it can be switched off — but you don't need
that BIOS for this. The kernel can be told to never initialize the AMD IOMMU (AMD-Vi) via a
boot parameter, which is the standard BC-250 community workaround.

On Bazzite (ostree-based):

```bash
rpm-ostree kargs --append=amd_iommu=off
systemctl reboot

# verify after reboot (this is exactly what test 23 checks):
find /sys/kernel/iommu_groups -maxdepth 1 -mindepth 1 -type d | wc -l   # should be 0
```

Nuances:

- `amd_iommu=off` stops the kernel's AMD-Vi driver from initializing — no IOMMU groups, no DMA
  remapping, no interrupt remapping via IOMMU. From Linux's perspective this is functionally
  equivalent to the BIOS toggle, and it resolves the instability.
- It is *not* a hardware-level disable: the silicon is still powered/configured by firmware, but
  since nothing programs or uses it, the broken behavior isn't triggered. In practice BC-250
  users on the stock 5.00 BIOS run stable with this karg.
- `iommu=pt` (passthrough) is a softer alternative but not sufficient here — on the BC-250 you
  want it fully off.
- Downside: no VFIO/PCI passthrough for VMs, which is irrelevant on this board anyway.

Test 23 validates either route the same way: it counts IOMMU groups, so it goes green whether
the IOMMU was disabled in the BIOS or via the kernel arg.

## Optional: ACPI fix without the P3.00 MeiMeiDXE v3 BIOS

[e-tho/bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix) (maintained fork of
[bc250-collective/bc250-acpi-fix](https://github.com/bc250-collective/bc250-acpi-fix)) is a
pure-software fix: three SSDT overrides loaded from initrd via the kernel's ACPI table upgrade.
No flashing, fully reversible (delete the file + GRUB line), works on all stock BIOS versions,
and covers both stock 6-core and unlocked 8-core setups. Bazzite install:

```bash
sudo cp acpi_override.cpio /boot/
echo 'GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"' | sudo tee -a /etc/default/grub
ujust regenerate-grub   # then reboot
```

Or use the guided installer from
[acpi](https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/acpi) (a suite app, installed from the portal):
it bundles the tables, checks for a BC-250 and a modded BIOS, installs idempotently and has an
uninstaller. The fix is persistent — the blscfg GRUB module applies the early initrd to every
BLS boot entry, so it survives kernel and rpm-ostree image updates.

Verify with `sudo dmesg | grep -iE 'ACPI.*(SSDT|Table Upgrade)'` — or just rerun test 26
(it reports whether the ACPI tables came from the initrd override or the BIOS).

**For the 2 extra cores without flashing:**
[rw-r-r-0644/bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) unlocks
8C/16T at runtime via the SMU. Caveats:

- Survives warm reboots only — redo after every cold boot.
- Refuses boards whose core mask isn't the usual `0x77` (a different mask suggests genuinely
  defective cores).
- Stress-test for MCEs before trusting the new cores (test 25 checks for machine-check events).
- Known side effect: `pp_dpm_sclk` reports nonsense clocks afterwards — tests 19/40 would
  flag that.

Or use [BC-250 Cores Bisect](https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/cores) (a suite app),
which does its own unlock and also makes it **persistent**:

1. **Test first:** `bc250-cores-bisect.sh` runs a control on the stock cores, unlocks, then tests each
   new core on its own and both combined over several rounds (verified `stress-ng` + MCE check,
   crash-safe across reboots) — the unlock is all-or-nothing, so you want this verdict before
   trusting it.
2. **Make it persistent:** after a clean verdict, `sudo ./bc250-cores-unlock.sh --install` (or
   **Install** in its GUI, gated on the bisect verdict) enables a root service that re-applies the
   unlock after every cold boot and warm-reboots once. Survives reboots, cold boots and Bazzite updates.
3. **Undo:** `sudo ./bc250-cores-unlock.sh --uninstall`, then a full power off: stock 6C/12T returns.

**For the extra CUs without flashing:**
[BC-250 CU Bisect](https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/compute) (a suite app) unlocks CUs at runtime
by writing the GPU's WGP mask registers with `umr`, and keeps a validated unlock across reboots:

1. **Test first:** `bc250-cu-bisect.sh` tests every locked WGP (2 CUs) on its own over several rounds and
   tells bad WGPs apart from an unstable unlock, power or heat. Then retest the combined mask on its own.
2. **Make it persistent:** `bc250-cu-unlock.sh --install <masks>`, or **Install** in its BC Unlock GUI,
   saves the mask and reapplies it at every boot through a root systemd service that starts before the
   desktop. It survives reboots, cold boots and Bazzite updates. The GUI only allows **Install** once the
   bisect results show the combined mask passed every round with the same number of WGPs on all 4 rows.
3. **Undo:** `sudo ./bc250-cu-unlock.sh --uninstall` or **Uninstall** in the GUI, then reboot: stock 24 CUs.

Caveats:

- Keep the 4 shader arrays even (for example 4/4/4/4 WGPs = 32 CUs): the GPU splits work across them in
  lockstep, so an uneven mask uses more power without being faster.
- Check the result here: test 21 shows the live CU count, test 41 (stress) and test 42 (benchmark) show
  whether it's stable and what it adds. See [Example: 24 → 36 CU unlock](#example-24--36-cu-unlock).
- A WGP that passed can still fail under other conditions (heat, a game). After a hang, uninstall and
  reboot, then test again.

With these tools every reason for a modded BIOS now has a software-only, reversible alternative,
so you can stay on the regular stock BIOS (up to and including 5.00) without losing any
performance benefit:

| Modded-BIOS benefit                | Stock-BIOS equivalent                                      |
|------------------------------------|------------------------------------------------------------|
| UMA/VRAM split menu                | `bc250_memcfg` (writes the same CMOS value)                |
| ACPI fix (C-states + freq scaling) | `bc250-persistent-acpi` (works on 1.00–5.00, same DSDT)    |
| Chipset menu → IOMMU disable       | `rpm-ostree kargs --append=amd_iommu=off`                  |
| 8C/16T unlock                      | `bc250-cores-unlock.sh --install`                          |
| Extra CUs                          | `bc250-cu-unlock.sh --install`                             |

Minor caveats, not performance losses:

- Cores: after a cold boot the service re-applies the unlock and does **one extra warm reboot**
  (slightly slower power-on, same runtime performance).
- A CMOS reset/battery pull would revert the `bc250_memcfg` split — just rerun it.
- Validate cores/CUs with the bisect tools first; silicon quality is per board, independent of BIOS.

Going beyond stock: [BC-250 GPU OC Bisect](https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/oc) (a suite app)
sweeps the governor's top GPU safe-point (clock up, voltage down) the same bisect way, to find the
safe overclock or undervolt for your specific board — no BIOS involved either.

And the stock BIOS is actually safer: zero bricking risk, and no duplicate-ACPI-table conflicts
with the override. The BIOS route remains an alternative, not a requirement.

> **Note** (from e-tho's README): if you ever do install a modded BIOS, remove the ACPI
> override first — modded BIOSes may ship their own ACPI fixes, and duplicate tables fail
> to load.

---

## License

Copyright © 2026 Philip.

BC-250 Bazzite Test is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.html), version 3 or (at your option) any
later version. It is distributed in the hope that it will be useful, but **without any warranty**; without
even the implied warranty of merchantability or fitness for a particular purpose.

The release tarball `check-v<version>.tar.gz` is the complete source of that release (Python and shell,
nothing is compiled); GitHub also attaches the source of the whole suite at that tag.

Third-party components: Qt 6 (LGPL v3), PyQt6 (GPL v3), the Inter font (SIL Open Font License 1.1).
