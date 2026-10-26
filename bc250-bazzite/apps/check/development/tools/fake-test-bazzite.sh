#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Development stand-in for test-bazzite.sh: same options and output format, no system access.
# Lets the GUI be developed on machines that are not a BC-250 (e.g. macOS).
#   python -m bazzite_check --script development/tools/fake-test-bazzite.sh --no-sudo
# Replay a real report (/var/log/bc250-bazzite-test/bc250-test-results-*.log) instead of simulated output:
#   BC250_REPLAY=path/to/report.log python -m bazzite_check --script development/tools/fake-test-bazzite.sh --no-sudo

ONLY=""
STRESS_MODE=false
STRESS_DURATION=120
BENCH_MODE=false
SAVE_BASELINE=false
DISK_MODE=false
DISK_WRITE=0
SPEEDTEST_MODE=false
while [ $# -gt 0 ]; do
    case "$1" in
        --only=*)    ONLY=",${1#*=}," ;;
        --stress)    STRESS_MODE=true ;;
        --stress=*)  STRESS_MODE=true; STRESS_DURATION="${1#*=}" ;;
        --bench|--bench=*) BENCH_MODE=true ;;
        --save-baseline) SAVE_BASELINE=true ;;
        --disk-bench) DISK_MODE=true ;;
        --disk-write=*) DISK_MODE=true; DISK_WRITE="${1#*=}" ;;
        --speedtest) SPEEDTEST_MODE=true ;;
        --interval=*|--no-prompt|--no-desktop|--gui) ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"; }
want() { [ -z "$ONLY" ] || case "$ONLY" in *",$1,"*) true ;; *) false ;; esac; }

TESTS="00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45"
ERRORS=0
# Print the [TEST NN] block of test $1 from the replay log, up to the next test or the footer.
replay_block() {
    awk -v id="$1" '
        /^[0-9-]+ [0-9:]+ - \[TEST [0-9]+\]/ { on = ($0 ~ "\\[TEST " id "\\]") }
        /^[0-9-]+ [0-9:]+ - (All tests completed|\[SUMMARY\])/ { on = 0 }
        on
    ' "$BC250_REPLAY"
}

for t in $TESTS; do
    want "$t" || continue
    if [ -n "${BC250_REPLAY:-}" ]; then
        BLOCK=$(replay_block "$t")
        [ -z "$BLOCK" ] && continue
        echo "$BLOCK"
        grep -qE '^[0-9-]+ [0-9:]+ - (ERROR|FAILURE):' <<<"$BLOCK" && ERRORS=$((ERRORS + 1))
        sleep 0.2
        continue
    fi
    log "[TEST $t] Simulated test $t"
    sleep 0.3
    if [ "$t" = 41 ] && [ "$STRESS_MODE" != true ]; then
        log "INFO: Skipped. Re-run with --stress to load the board."
        echo; continue
    fi
    if [ "$t" = 42 ]; then
        if [ "$BENCH_MODE" != true ]; then
            log "INFO: Skipped. Re-run with --bench to measure CPU and GPU performance."
        else
            # Simulated 32-CU / 6C12T board, against a 24-CU stock baseline of 612 / 4410 / 5520.
            log "INFO: Configuration: AMD BC-250, 6C/12T, 32 CUs, governor max 1850 MHz, mitigations off"
            sleep 1
            log "INFO: CPU single-thread: 615.3 ops/s | multi-thread: 4432.8 ops/s (7.2x)"
            log "INFO: GPU FP32: 7310.4 GFLOPS | VRAM copy: 198.2 GB/s | clock under load: ~1850 MHz"
            if [ "$SAVE_BASELINE" = true ]; then
                log "SUCCESS: Saved as the baseline: $(pwd)/bench-baseline.json"
                log "BENCH: cpu_single=615.3 cpu_multi=4432.8 gpu_fp32=7310.4 gpu_copy=198.2 cores=6 threads=12 cus=32 gpu_mhz=1850"
            else
                log "SUCCESS: CPU score: 101 (multi-thread; single-thread: 101)"
                log "SUCCESS: GPU score: 132 (FP32 compute)"
                log "BENCH: cpu_single=615.3 cpu_multi=4432.8 gpu_fp32=7310.4 gpu_copy=198.2 cpu_score=101 cpu1_score=101 gpu_score=132 cores=6 threads=12 cus=32 gpu_mhz=1850"
            fi
        fi
        echo; continue
    fi
    if [ "$t" = 43 ]; then
        if [ "$DISK_MODE" != true ]; then
            log "INFO: Skipped. Re-run with --disk-bench to measure read speed (nothing is written)."
        else
            log "Testing /dev/nvme0n1 (Simulated NVMe 1TB), the disk that holds the system; reading from /dev/nvme0n1p3."
            log "SUCCESS: Sequential read: 3310 MB/s (4096 MiB, 4 MiB blocks, direct I/O)."
            log "INFO: That is 84% of the PCIe link ceiling (~3940 MB/s)."
            log "SUCCESS: Random 4K read, queue depth 1: 14200 IOPS (58 MB/s, 68 µs average latency)."
            if [ "$DISK_WRITE" -gt 0 ]; then
                sleep 1
                log "SUCCESS: Sequential write: 2950 MB/s at the start, 610 MB/s at the end, 1480 MB/s average (peak drive temperature 61 °C)."
                log "INFO: SLC cache: about 6.00 GiB. Writes run at ~2950 MB/s until it is full and at ~610 MB/s after that."
            else
                log "INFO: Write test not requested (--disk-write=GiB); nothing was written."
            fi
        fi
        echo; continue
    fi
    if [ "$t" = 44 ]; then
        if [ "$SPEEDTEST_MODE" != true ]; then
            log "INFO: Skipped. Re-run with --speedtest to measure download and upload speed and latency"
            log "INFO: (uses about 1 GB of data on a fast connection)."
        else
            log "INFO: Traffic goes through enp4s0 (Ethernet, link 1000 Mbit/s)."
            log "Running Ookla speedtest (about 30 s; by running it you accept Ookla's license and GDPR terms)"
            sleep 1
            log "INFO: Server: MIRHosting - Amsterdam; ISP: Zscaler"
            log "SUCCESS: Download: 611.16 Mbps (603.10 MB used), latency while downloading 42.38 ms"
            log "SUCCESS: Upload: 581.76 Mbps (606.00 MB used), latency while uploading 143.26 ms"
            log "INFO: Idle latency: 6.66 ms (jitter 0.70 ms)"
            log "WARNING: Latency rises by 136 ms while the line is busy (bufferbloat). Online games lag whenever something else downloads or uploads."
            log "HINT: Enable SQM / Smart Queue Management (fq_codel or CAKE) in your router, set to ~90% of these speeds."
            log "SUCCESS: Packet loss: 0%"
            log "INFO: Result URL: https://www.speedtest.net/result/c/e3aba7a5-22c5-4c8d-a27c-935e036e3ce1"
        fi
        echo; continue
    fi
    if [ "$t" = 45 ]; then
        log "INFO: RPM packages in the system image: 1873"
        log "INFO: Layered on top of the image (rpm-ostree install): 2"
        printf '    htop\n    umr\n'
        log "INFO: Flatpak apps (system): 3"
        printf '    com.valvesoftware.Steam\t1.0.0.81\n    net.lutris.Lutris\t0.5.18\n    org.mozilla.firefox\t131.0\n'
        log "INFO: Flatpak apps (user): 1"
        printf '    it.mijorus.gearlever\t3.2\n'
        log "INFO: Flatpak runtimes and extensions: 24"
        log "INFO: Homebrew formulae: 5"
        printf '    btop\n    fastfetch\n    gh\n    jq\n    ripgrep\n'
        log "INFO: Distrobox/Toolbox containers: 1 (the packages inside them are not counted)"
        log "SUCCESS: 1906 packages and apps installed, from 5 source(s)."
        echo; continue
    fi
    if [ "$t" = 10 ]; then
        log "SUCCESS: 1 NVMe controller(s) recognized."
        log "INFO: /dev/nvme0: Simulated NVMe 1TB, firmware 1.0"
        log "INFO: Link: PCIe Gen3 x4 (8.0 GT/s, ceiling ~3940 MB/s); drive supports Gen4 x4, slot supports Gen3 x4. The slot, not the drive, sets the speed limit."
        log "INFO: DRAM cache: none. /dev/nvme0 is DRAM-less and uses a Host Memory Buffer (wants 64 MiB of system RAM, minimum 32 MiB)."
        log "SUCCESS: The kernel gave it a 64 MiB host memory buffer."
        log "HINT: Fine for game loading. Expect slower sustained and random writes than a drive with DRAM; the buffer comes out of the RAM the BC-250 shares with the GPU."
        log "INFO: Wear: 3% of the rated endurance used, 12800 GB written, 1200 power-on hours."
        log "INFO: 37 unsafe shutdowns recorded (every hard lockup or power cut counts, see test 34)."
        log "SUCCESS: SMART health of /dev/nvme0 is good (source: nvme)."
        echo; continue
    fi
    echo "  raw command output for test $t"
    # Deterministic mix of outcomes so every button color shows up.
    case $((10#$t % 7)) in
        0) log "ERROR: Simulated failure in test $t."
           log "HINT: This is what a fix suggestion looks like."; ERRORS=$((ERRORS + 1)) ;;
        1|4) log "WARNING: Simulated warning in test $t."
             log "HINT: Consider checking the configuration for test $t." ;;
        2) log "INFO: Informational result only." ;;
        *) log "SUCCESS: Test $t passed." ;;
    esac
    echo
done
log "All tests completed."
log "[SUMMARY] Test Results"
if [ "$ERRORS" -gt 0 ]; then log "FAILURE: Errors were found."; else log "SUCCESS: No errors detected during the tests."; fi
