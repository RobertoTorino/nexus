<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Bazzite Test: the script

Diagnostic script for **Bazzite** (Fedora Atomic / rpm-ostree) running on an **AMD BC-250** board (Cyan Skillfish APU,
`gfx1013`, PCI `1002:13fe`).

It is **read-only**: nothing is installed, enabled, disabled or reconfigured. The only exception is
the opt-in `--stress` mode, which deliberately puts the board under load.

---

## Usage

```bash
sudo chmod +x test-bazzite.sh

sudo ./test-bazzite.sh                        # passive diagnostics only (tests 00-40, 45)
sudo ./test-bazzite.sh --stress               # ... plus a 120s CPU+GPU stress run (test 41)
sudo ./test-bazzite.sh --stress=300           # 300s stress run
sudo ./test-bazzite.sh --stress=300 --interval=1   # sample telemetry every second
sudo ./test-bazzite.sh --only=04,05,17            # run only tests 04, 05 and 17
sudo ./test-bazzite.sh --only=42 --bench --save-baseline   # benchmark a STOCK board once (baseline = 100)
sudo ./test-bazzite.sh --only=42 --bench          # benchmark after an unlock: CPU and GPU score vs stock
sudo ./test-bazzite.sh --only=10,43 --disk-bench  # NVMe link/DRAM/health + disk read speed (read-only)
sudo ./test-bazzite.sh --only=43 --disk-write=16  # ... also write 16 GiB to find the SLC cache size
sudo ./test-bazzite.sh --only=44 --speedtest      # internet speed, latency under load, packet loss (~1 GB of data)
sudo ./test-bazzite.sh --help                 # show options
```

| Option               | Description                                                                |
|----------------------|----------------------------------------------------------------------------|
| `--stress[=SECONDS]` | Opt-in. Loads CPU + GPU and samples telemetry. Default 120s, minimum 10s.  |
| `--interval=SECONDS` | Telemetry sampling interval during the stress run. Default 2s, minimum 1s. |
| `--bench[=SECONDS]`  | Opt-in performance benchmark (test 42). SECONDS per CPU phase, default 20, minimum 5. |
| `--save-baseline`    | With `--bench`: save this run as `/var/log/bc250-bazzite-test/bench-baseline.json` (the 100 mark). |
| `--disk-bench`       | Opt-in disk speed test (test 43): sequential read, and random 4K read with `fio`. Read-only. |
| `--disk-write=GiB`   | Also write GiB (1–256) to a temporary file in `/var/tmp` for write speed and SLC cache size. Implies `--disk-bench`. |
| `--speedtest`        | Opt-in internet speed test (test 44) with Ookla `speedtest` or `speedtest-cli`. Uses ~1 GB of data on a fast line. |
| `--only=LIST`        | Run only the listed tests, e.g. `--only=04,05,17`. Test 41 also needs `--stress`, test 42 `--bench`, test 43 `--disk-bench`, test 44 `--speedtest`. |
| `--no-desktop`       | Do not copy the report to the desktop user's `Desktop`.                    |
| `--gui`              | Word the how-to-run hints for the GUI instead of these options (used by the GUI). |
| `-h`, `--help`       | Show usage and exit.                                                       |

The GUI is described in [Bazzite Test internals](bazzite-test-internals.md) (developers) and [BC-250 Bazzite Test](../apps/check.md) (users).

### Output

All files go to `/var/log/bc250-bazzite-test/`:

| File                                         | Contents                                                          |
|----------------------------------------------|-------------------------------------------------------------------|
| `bc250-test-results-<YYYYmmdd-HHMMSS>.log`   | Full report.                                                      |
| `bc250-stress-<YYYYmmdd-HHMMSS>.csv`         | Stress telemetry, written only with `--stress`.                   |
| `bc250-gpuload-<YYYYmmdd-HHMMSS>.log`        | Output of the GPU load tool, written only with `--stress`.        |
| `bc250-memtest-<YYYYmmdd-HHMMSS>.log`        | memtest_vulkan's own log, when it was the GPU load tool.          |
| `bc250-bench-<YYYYmmdd-HHMMSS>.json`         | Benchmark result, written only with `--bench`.                    |
| `bc250-bench-vkpeak-<YYYYmmdd-HHMMSS>.log`   | vkpeak output of the benchmark.                                   |
| `bc250-bench-history.csv`                    | One line per benchmark run, to compare configurations over time.  |
| `bc250-disk-<YYYYmmdd-HHMMSS>.csv`           | Write speed and drive temperature per 256 MiB, only with `--disk-write`. |
| `bc250-speedtest-<YYYYmmdd-HHMMSS>.json`     | Raw speed test result, only with `--speedtest`.                   |
| `bc250-speedtest-history.csv`                | One line per speed test: interface, server, speeds, idle/loaded latency, jitter, loss. |

They are copied to `~/Desktop/bc250-bazzite-test/` of the desktop user at the end of the run for easy
sharing (skipped with `--no-desktop`; in the GUI this is *Settings > General > Copy the full reports to
Desktop*, on by default).
During a stress run the files are flushed to disk after every sample, so they survive a hard lockup.

The GUI additionally keeps its own captured output of every run as
`~/.local/share/bc250-bazzite-test/logs/<YYYYmmdd-HHMMSS>_<scope>.log` — these are not the files above,
just what the script printed during that run.

The CSV columns are `elapsed_s, sclk_mhz, mclk_mhz, gpu_busy_pct, vram_used_mib, gtt_used_mib,
gpu_temp_c, gpu_power_w, vddgfx_mv, cpu_tctl_c, cpu_mhz_avg, fan_rpm, load1` — open it directly in
LibreOffice Calc to plot clocks, memory and power against temperature.

`gpu_busy_pct` comes from the kernel's `gpu_busy_percent` when it works. Stock kernels have no GPU-load
sensor for Cyan Skillfish (the read fails, which is also why MangoHud / the Steam overlay show 0% unless
the governor's `fix-metrics` is enabled), so the script then measures the gfx and compute engine time of every GPU
client from `/proc/*/fdinfo` — the same method nvtop uses. The log states which
source was used.

The summary reports peak VRAM and GTT use as a percentage of each budget, warning at 90% VRAM (allocations spilling into
GTT) and 85% GTT (the GPU is close to running out of memory).

Every line is tagged `SUCCESS`, `INFO`, `WARNING` or `ERROR`, and a `[SUMMARY]` block at the end
reports the overall verdict.

---

## Tests

### System

| #  | Test                         | Checks                                                                          |
|----|------------------------------|---------------------------------------------------------------------------------|
| 00 | Platform Identification      | Confirms the board really is a BC-250 and reports the BIOS (stock vs modded), Bazzite image and kernel. |
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
| 53 | Wi-Fi Adapter          | Every Wi-Fi adapter, its driver and firmware, rfkill and its connection; BC-250 USB Wi-Fi's service. |
| 44 | Internet Speed         | **Opt-in** (`--speedtest`). See below.                                    |

**How test 44 measures the connection** (Ookla's `speedtest`, or `speedtest-cli` as a fallback; about 30 s):

* **Download and upload** in Mbps, plus the data used (roughly 1 GB on a gigabit line).
* **Idle latency and jitter**, and the **latency while downloading/uploading**. When the loaded latency is more
  than 100 ms above idle the line suffers from *bufferbloat*: games lag whenever something else uses the
  connection. The fix is SQM (fq_codel/CAKE) in the router. Only Ookla's CLI measures loaded latency.
* **Packet loss** (Ookla only): over 1% is a warning.
* **The local link**: the interface the traffic uses (Ethernet or Wi-Fi) and its link speed. A 10/100 Mbit/s
  Ethernet link is a warning (bad or 2-pair cable); a download near the link speed means the port is the limit.
* A VPN in the path is noted, because then the VPN is measured, not the line.
* Every run is appended to `bc250-speedtest-history.csv`; the GUI's **Show graph** compares all runs.
* Install Ookla's CLI: download the Linux x86_64 `.tgz` from <https://www.speedtest.net/apps/cli> and put the
  `speedtest` binary in `~/.local/bin`. Running it accepts Ookla's license and GDPR terms.

Test 53 runs `bc250_core.wifi` with the system `python3 -I -B` (standard library only, no bytecode written as
root): from the `bc250_core` bundled next to the script, or `core/` in the suite checkout. It reads `/sys`, the
running kernel's `modules.dep` and `modules.alias`, this boot's kernel log and `iw dev <interface> link`, and prints
its findings as `LEVEL: text` lines, which the script logs; a `WARNING` line counts as a warning. BC-250 USB
Wi-Fi's part reads `/etc/bc250-usb-wifi/driver.json`, `/run/bc250-usb-wifi/state.json`, the built modules under
`/var/lib/bc250-usb-wifi/modules/<kernel>` and `lsmod`.

### Storage and memory

| #  | Test                             | Checks                                                                                 |
|----|----------------------------------|----------------------------------------------------------------------------------------|
| 09 | Disk Configuration               | Filesystem usage and mount points.                                                     |
| 10 | NVMe Devices                     | Detection; PCIe link speed/width vs. what the drive and the slot support; DRAM cache or host memory buffer (DRAM-less); SMART health: wear, media errors, spare, temperature and time spent throttling, unsafe shutdowns. |
| 14 | Memory and Swap                  | RAM usage and the full swap topology: zram, zswap, disk swap, overlaps and swappiness. |
| 37 | Unified Memory and VRAM Pressure | VRAM/GTT usage, OOM-kill history, `vm.max_map_count`, swappiness.                      |
| 49 | CPU Memory Bandwidth             | `stress-ng` STREAM-like bandwidth on 1 thread and all threads; shows the GDDR6 latency cost the CPU pays for the GPU's console-class bandwidth. |
| 43 | Disk Speed (read, write, SLC cache) | **Opt-in** (`--disk-bench`, `--disk-write=GiB`). See below.                         |

**How test 43 measures the system disk** (the disk that holds `/var/tmp`):

* **Sequential read**: `dd` reads 4 GiB straight from the partition with direct I/O. Nothing is
  written. The result is compared with the PCIe link ceiling from test 10.
* **Random 4K read** at queue depth 1 and 32: `fio --readonly` over the whole partition, 10 s each.
  This part is skipped without a system-wide `fio` (a Homebrew fio is not run as root). A high QD1 latency (over ~150 µs) is typical of a DRAM-less drive
  without a host memory buffer.
* **Sequential write and SLC cache**, only with `--disk-write=GiB`:
  * Writes a temporary file in `/var/tmp` in 256 MiB chunks (direct I/O, flushed) and deletes it
    afterwards. The file is created with `chattr +C`, so btrfs doesn't compress it (compression would
    fake the result).
  * Each chunk's speed and the drive temperature go to `bc250-disk-<timestamp>.csv`; **Show graph**
    in the GUI plots it.
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

### GPU and graphics

| #  | Test                  | Checks                                                                     |
|----|-----------------------|----------------------------------------------------------------------------|
| 17 | amdgpu Driver         | Confirms `amdgpu` is bound to the Cyan Skillfish APU.                      |
| 18 | GPU Governor          | Verifies a governor is running; without one the GPU is pinned at 1500 MHz. |
| 19 | GPU Frequency Scaling | Reads `pp_dpm_sclk` / `pp_dpm_mclk` to confirm the clock actually moves.   |
| 20 | Vulkan / Mesa         | Confirms RADV reports GFX1013 and not the llvmpipe software fallback.      |
| 21 | Compute Unit Count    | Active CUs from the live GPU registers (needs admin rights and umr), else the kernel value (24 stock, up to 40 unlocked); explains why kernel and RADV keep reporting the probe-time value. |
| 29 | Display Session       | Identifies the display manager, session type and compositor.               |
| 47 | Vulkan Futureproof Matrix | Vulkan API level and the feature set modern games need: ray tracing, mesh shaders, VRS, pipeline libraries and the VRAM carveout vs today's 8 GiB recommendation. |
| 50 | Video Decode and Encode (VCN) | `vainfo` codec matrix: H.264/HEVC/VP9/AV1 decode and encode. |
| 51 | HDMI-CEC | The CEC adapter of the DisplayPort output, whether the TV answers a poll, and Bazzite's CEC mode. |
| 52 | HDMI-CEC Services | Whether `cecd`, `bc250-hdmi-cec-watch` and `bc250-hdmi-cec-boot` (and Bazzite's dGPU CEC services) run. |

### CPU and firmware

| #  | Test                      | Checks                                                                          |
|----|---------------------------|---------------------------------------------------------------------------------|
| 23 | IOMMU Disabled            | Counts IOMMU groups; IOMMU is broken on the BC-250 and must be off — via BIOS or the `amd_iommu=off` kernel arg. |
| 24 | CPU Mitigations           | Passes when `mitigations=off` is set (worth roughly +18 FPS on this board).     |
| 25 | CPU Core and Thread Count | Reports cores/threads — 6C/12T stock, 8C/16T after the unlock.                  |
| 26 | CPU Power Management      | Checks cpufreq scaling and C-states; both need the BC-250 ACPI fix.             |

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
| 48 | Real-Game Frametime (MangoHud logs) | Reads the most recent MangoHud logs from real play sessions: average FPS, 1% and 0.1% lows and stutter share. |
| 41 | CPU + GPU Stress and Telemetry | **Opt-in.** Loads the board and records clocks, temperature, power and fans throughout; includes a sustained-performance verdict (first minute vs last minute). |

### Performance

| #  | Test                                    | Checks                                                                                              |
|----|-----------------------------------------|-----------------------------------------------------------------------------------------------------|
| 42 | Performance Benchmark (CPU / GPU score) | **Opt-in** (`--bench`). CPU single/multi-thread and GPU FP32 compute, scored against a stock board, plus a comparison ladder against known systems (Steam Deck, Series S, Steam Machine, PS5, desktop GPUs). |

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

1. Put the board in its stock configuration (undo any CU unlock and reboot, so 24 CUs), close games, then:
   `sudo ./test-bazzite.sh --only=42 --bench --save-baseline` (or tick *Save as baseline* in the GUI).
   This writes `/var/log/bc250-bazzite-test/bench-baseline.json`: one baseline for every copy of the script
   and for the GUI. A baseline saved by an older version next to the script is moved there on the next `--bench` run.
2. Apply an unlock, then run `sudo ./test-bazzite.sh --only=42 --bench`. Compare in
   `/var/log/bc250-bazzite-test/bc250-bench-history.csv` or the GUI's *Benchmark history*.

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
* The benchmark is short. Check the unlock with a long stress test (`--only=41 --stress=300` with
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

Then reproduce it under observation:

```bash
sudo ./test-bazzite.sh --stress=300 --interval=1
```

The telemetry line prints to the console every 10 seconds, so if the board dies the last values on
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

Runs as root on Bazzite. The script never installs anything — it only detects what is already on
`PATH`. Layer the optional load tools once, and they are picked up automatically on every later run:

```bash
rpm-ostree install stress-ng glmark2
systemctl reboot
```

Or use the optional helper, which installs everything below in one go — it layers the RPM packages
(`stress-ng`, `lm_sensors`, `vkmark`, `nvme-cli`, `fio`) and downloads `vkpeak`, `memtest_vulkan` and
the Ookla `speedtest` CLI into `~/.local/bin` (interactive: each group is asked for separately):

```bash
./development/tools/install-requirements.sh          # interactive
./development/tools/install-requirements.sh --all    # everything, no questions
```

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
  `memtest_vulkan` binary in `/usr/local/bin` or `~/.local/bin` (the script also looks there under sudo).
* **User-installed tools never run as root.** The script finds tools in `~/.local/bin` and Homebrew itself
  instead of adding those folders to root's PATH. Anything writable by your user (those folders, or any
  tool not owned by root) is run as your user, not as root. `fio` needs root to read the raw partition,
  so a Homebrew/`~/.local/bin` fio is not used: install it with `rpm-ostree install fio` for the random 4K test.
* memtest_vulkan is limited to ¾ of the VRAM and at most half of the available RAM. Left alone it fills
  all free RAM on this APU, and the OOM killer then kills the desktop (kwin_wayland).
* Memory safety during the stress run: the GPU load tool is the OOM killer's first victim (`oom_score_adj`
  1000), the script protects itself so it can always stop the load, the tool is wrapped in `timeout` so it
  never outlives the script, and a memory guard stops the run when available RAM drops below 5% (min 512 MiB).
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

**INFO: glmark2, vkcube and vulkan-tools are already available on Bazzite.**

## Swap file recommendation

Bazzite ships with **zram as the only swap**. zram is compressed RAM: when it fills there is no
overflow to disk, and the OOM killer runs — on the BC-250, with its unified memory, that can present
as a hard freeze of the whole desktop. Test 14 warns about this layout and test 37 watches the
resulting memory pressure.

The recommended layout, and the default of the System score, is **zswap in front of a disk swapfile**,
with zram disabled. zswap keeps a compressed cache in RAM like zram does, but when it fills it writes
the oldest pages to the swapfile instead of ending in the OOM killer, which is much more stable for
gaming. zram with a swapfile as a backstop works too, but scores less; zram alone scores lowest.
On Bazzite's Btrfs root a swapfile must be created NOCOW and uncompressed; the kernel refuses it otherwise:

```bash
sudo mkdir -p /var/swap
sudo btrfs filesystem mkswapfile --size 8g /var/swap/swapfile
sudo swapon /var/swap/swapfile
echo '/var/swap/swapfile none swap defaults 0 0' | sudo tee -a /etc/fstab
# Disable zram (an empty config overrides the default) and enable zswap, then reboot:
sudo touch /etc/systemd/zram-generator.conf
rpm-ostree kargs --append-if-missing=zswap.enabled=1
```

Verify with `swapon --show` (only the swapfile, no zram) and
`cat /sys/module/zswap/parameters/enabled` (`Y`). 8 GiB is a good size for the 16 GB board; halve it
for a lighter setup. Do not put a swapfile on an SD card or USB stick, and do not run zswap next to
zram (test 14 warns: compressing pages twice wastes CPU and memory).

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
   No GPU hang, no OOM-kill — nothing the script was looking for. ttm.pages_limit does not help, because it only raises
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

## Optional: ACPI fix without the P3.00 MeiMeiDXE v3 BIOS

[e-tho/bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix) (maintained fork of
[bc250-collective/bc250-acpi-fix](https://github.com/bc250-collective/bc250-acpi-fix)) is a pure-software fix.
3 SSDT overrides loaded from initrd via the kernel's ACPI table upgrade.
No flashing, fully reversible (delete the file + GRUB line), works on all stock BIOS versions,
and covers both stock 6-core and unlocked 8-core setups. Bazzite install:

```bash
sudo cp acpi_override.cpio /boot/
echo 'GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"' | sudo tee -a /etc/default/grub
ujust regenerate-grub   # then reboot
```

Or use the guided installer from
[acpi](../apps/acpi.md) (a suite app):
it bundles the tables, checks for a BC-250 and a modded BIOS, installs idempotently and has an
uninstaller. The fix is persistent — the blscfg GRUB module applies the early initrd to every
BLS boot entry, so it survives kernel and rpm-ostree image updates.

Verify with `sudo dmesg | grep -iE 'ACPI.*(SSDT|Table Upgrade)'` — or just rerun the test
script (test 26 reports whether the ACPI tables came from the initrd override or the BIOS).

**For the 2 extra cores without flashing:**
[rw-r-r-0644/bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) unlocks
8C/16T at runtime via the SMU. Caveats:

- Survives warm reboots only — redo after every cold boot.
- Refuses boards whose core mask isn't the usual `0x77` (a different mask suggests genuinely
  defective cores).
- Stress-test for MCEs before trusting the new cores (test 25 checks for machine-check events).
- Known side effect: `pp_dpm_sclk` reports nonsense clocks afterwards — tests 19/40 would
  flag that.

**For the extra CUs without flashing:**
[BC-250 CU Bisect](../apps/compute.md) (a suite app) unlocks CUs at runtime
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

If you later want persistence for the cores, that is when the BIOS mod becomes relevant — the runtime route
lets you validate the cores risk-free first. For the CUs, `bc250-cu-unlock.sh` above gives persistence
without flashing; the BIOS route is the alternative.

> **Note** (from e-tho's README): if you ever do install a modded BIOS, remove the ACPI
> override first — modded BIOSes may ship their own ACPI fixes, and duplicate tables fail
> to load.

## Optional: bad CUs or an unstable unlock?

Every BC-250 die differs: AMD fuses off WGPs that failed validation. But a crash after a CU unlock
doesn't have to mean a bad WGP: the runtime unlock itself, power or heat can cause it too.
[bc250-cu-bisect](../apps/compute.md) separates these causes: it does its
own unlock with umr, tests a control (same register writes, no extra CUs) and every locked WGP on its own
over several rounds, and tells you per WGP whether it's good, fails every time (likely bad) or fails at
random (likely the unlock, power or heat). Once a mask passes, `bc250-cu-unlock.sh` or the BC Unlock GUI
from the same repository keeps it across reboots (see *For the extra CUs without flashing* above).
