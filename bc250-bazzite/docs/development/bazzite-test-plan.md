<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Basic tests and additional requirements to streamline the Qt GUI version

### Start the GUI: 
With new requirements:
```bash
python3 -m venv python && python/bin/pip install -r requirements.txt && python/bin/python -m bazzite_check  
```    
Without new requirements:
```bash
python3 -m venv python && python/bin/python -m bazzite_check  
```       

---

### Vulkan Memtest
memtest_vulkan isn't packaged with Bazzite, download it on the BC-250 board.            
Get the Linux x86_64 build from: [https://github.com/GpuZelenograd/memtest_vulkan/releases](https://github.com/GpuZelenograd/memtest_vulkan/releases)
Extract it then run:
```bash
chmod +x memtest_vulkan && mv memtest_vulkan ~/.local/bin/         
```

#### Example stress tests
```bash
sudo ./test-bazzite.sh --only=41 --stress=120
sudo ./test-bazzite.sh --only=18,19,22,35,41 --stress=30
```

### Stress test with max CU's
At max CU's, run the stress test (41) for at least 300s with memtest_vulkan.
```bash
sudo ./test-bazzite.sh --only=41 --stress=600
``` 
This 10-minute run with no stall would fully confirm that 36 CUs (or 40 if your board can handle that) is stable.              
It reports the following:               
* Whether the clock holds.
* When the board is hot.
* How much power it draws.
* Whether the extra CUs produce VRAM errors.

---

### Measure your baseline
1. Install the tools: `rpm-ostree install stress-ng` then reboot. 
2. Put the vkpeak binary from [https://github.com/nihui/vkpeak/releases](https://github.com/nihui/vkpeak/releases) in `~/.local/bin`
3. `chmod +x vkpeak && mv vkpeak ~/.local/bin/`
4. Undo any CU unlock (reboot, so 24 CUs) and close games and applications.
5. On the Performance page, tick "Save as baseline" and run test 42. 
6. It saves the benchmark results as `bench-baseline.json`.
7. Unlock your CU's and run test 42 again for the comparison.

---

### Game detection
FPS needs MangoHud logging, set this once in `~/.config/MangoHud/MangoHud.conf`
```
output_folder=/home/admin/mangohud-logs
autostart_log=1
log_interval=500
```
* Create that log folder, and make sure MangoHud is on for the game.
* It writes one log file per session, so delete old ones now and then.
* Without logging, you still get the game name and its CPU/GPU %.

#### Limits to check on the board
* It only works in Desktop Mode, because the GUI isn't visible in Game Mode.
* With fix-metrics on, the GPU % comes from the governor's patched GPU sensor file.
* I assumed where the load value sits in that file, so please compare the status bar's GPU % with MangoHud's while a game runs.
* The Hz shown in the status bar is for the screen the GUI window is on.

#### Here's how to check that the app can read mangohud:         
1. Start the game and check that the overlay appears. Right Shift + F12 shows or hides it.
2. Check that a log is being written while you play: `ls -lt ~/mangohud-logs | head -3`
3. The newest .csv file should be growing. If no file appears, press Left Shift + F2 to start logging, or check that autostart_log=1 is in the config MangoHud actually uses: `grep -E "output_folder|autostart_log" ~/.config/MangoHud/MangoHud.conf`
4. Open the app and tick Live in the status bar. It should show the game title, its CPU and GPU share, and the FPS.
5. If the overlay shows but the app doesn't show any FPS, output_folder probably points somewhere other than where the app looks.

---

### The buttons
* Next to the stress settings (test 41), plots the latest stress CSV.
* There are panels for clocks, temperatures, GPU busy, GPU power, GPU memory, fan, GPU voltage and load average.
* A line above them lists the peaks, and older stress runs can be picked from a list.
* Performance page (test 42): shows the benchmark history as bar charts per run.
* There are panels for the score against your stock baseline, GPU FP32, CPU multi- and single-thread, VRAM bandwidth and GPU clock.
* Bars are labeled like "#2 40CU 12T", so CU and core unlocks sit side by side.

#### Show Logs
* A Show graph button appears whenever the selected file is a CSV.
* A CSV the app doesn't know gets one panel per number column.

#### Behavior
In the graph window:
* Drag to zoom in.
* Right-click to zoom out.
* Hover to see values. 
* "Save as PNG" saves all panels as one image. 

---

### NVMe tests (10)

#### PCIe link: 
* the speed and width it runs at, against what the drive and the slot support. 
* It warns if the link is slower than both (usually a poor contact), notes when the slot is the limit, and shows the maximum MB/s the link allows.

#### DRAM cache: 
* DRAM-less drives ask to borrow system RAM (a "host memory buffer"), which the kernel logs when it grants it. 
* The test reads both. 
* If neither shows up, the drive has its own DRAM. 
* It warns if a buffer was requested but never given.

#### SMART health: 
* Critical warnings.
* Media errors.
* Spare blocks.
* Wear %.
* Data written.
* Temperature against the drive's own limit.
* Time spent throttling.
* Unsafe shutdowns (every hard lockup counts).

### NVMe tests (43)
`disk speed (--disk-bench, or --disk-write=GiB)`
* Read (default, nothing written): reads 4 GiB from the system disk and compares the result with the link maximum. 
* With fio installed it also measures random 4K reads.
* Write (tick "also test writes" and set a size):
* It writes a temporary file in /var/tmp 256 MiB at a time, logs the speed and drive temperature for each chunk, and deletes the file afterward.
* Where the speed drops sharply, it reports that as the fast SLC cache size, or as throttling if the drive was hot at that moment.
* It checks for enough free space first and stops if the drive reaches its critical temperature.
* The file is created with `btrfs` compression turned off, so the result is real.
* Show graph plots write speed and temperature against GiB written.
* Safeguards: you confirm before it starts, and it is never part of Run all.

To get the SMART, DRAM and random-read results on the board, install the tools first:               
`rpm-ostree install nvme-cli fio` then reboot.          

Then run the test with this flag:           
```bash
sudo ./test-bazzite.sh --only=10,43 --disk-write=16
```

---

### Internet speed test (test 44)
* It's opt-in with `--speedtest` and sits on the Network page.
* It uses Ookla's speedtest and falls back to speedtest-cli if Ookla's tool isn't installed.

It reports:         
* Download and upload speed, idle latency and jitter.
* Latency while downloading and uploading. 
* A rise of more than 100 ms is a warning (bufferbloat), with a hint to turn on SQM in the router. 
* Your run would trigger it: upload latency went up by about 136 ms.
* Packet loss above 1% is a warning.
* Which connection is used (Ethernet or Wi-Fi) and its link speed. 
* A 100 Mbit link warns about the cable, and a download close to the link speed says the port is the limit.
* A note when a VPN is in the path.
* It's never part of Run all and asks for confirmation first, because it uses about 1 GB of data.
* Each run is added to bc250-speedtest-history.csv. 
* Show graph compares all runs: speeds, idle vs loaded latency, jitter and packet loss.

To try it on the board, download the `Linux x86_64 .tgz` from `speedtest.net/apps/cli`, put `speedtest` in `~/.local/bin`
```bash
chmod +x speedtest && mv speedtest ~/.local/bin/  
```
Then run `--only=44 --speedtest`    

---

Do a CLI run with the benchmark, plus --speedtest, to confirm stress-ng, vkpeak and speedtest still give results when they run as your user.

```bash
sudo ./test-bazzite.sh --bench --speedtest
```
