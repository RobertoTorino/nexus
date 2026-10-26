#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Base script for testing Bazzite (Fedora Atomic / rpm-ostree) on an AMD BC-250 (Cyan Skillfish, gfx1013).
# Change permissions: sudo chmod +x test-bazzite.sh
# Run with: sudo ./test-bazzite.sh
# Stress mode: sudo ./test-bazzite.sh --stress=180
# Benchmark:   sudo ./test-bazzite.sh --only=42 --bench   (add --save-baseline on a stock board)
# Disk speed:  sudo ./test-bazzite.sh --only=10,43 --disk-bench   (--disk-write=8 also tests writes)
# Internet:    sudo ./test-bazzite.sh --only=44 --speedtest
# Output: /var/log/bc250-bazzite-test/bc250-test-results-YYYYmmdd-HHMMSS.log, also copied to
# ~/Desktop/bc250-bazzite-test/ of the desktop user.
# Uncomment set -x for debug
# set -x

# Initialize flags
ERROR_FOUND=false
WARN_FOUND=false

# Options
STRESS_MODE=false
STRESS_DURATION=120
STRESS_SAMPLE=2
BENCH_MODE=false
BENCH_SECONDS=20
BENCH_SAVE_BASELINE=false
DISK_MODE=false
DISK_WRITE_GIB=0
SPEEDTEST_MODE=false
ONLY=""
NO_DESKTOP=false
GUI_MODE=false

usage() {
    cat <<'USAGE'
Usage: sudo ./test-bazzite.sh [options]

  --stress[=SECONDS]   Run a combined CPU+GPU load after the passive tests and
                       sample clocks, temperatures, power and fans throughout.
                       Defaults to 120 seconds. This is a deliberate attempt to
                       reproduce an under-load lockup, so expect the box to be
                       unusable while it runs and to possibly freeze outright.
  --interval=SECONDS   Sampling interval during the stress run (default 2).
  --bench[=SECONDS]    Run the performance benchmark (test 42): CPU single- and
                       multi-thread (stress-ng, SECONDS per phase, default 20)
                       and GPU FP32 compute (vkpeak), scored against a stock
                       BC-250 baseline (/var/log/bc250-bazzite-test/bench-baseline.json).
  --save-baseline      With --bench: save this run as the baseline. Run it once
                       on a stock board (6C/12T, 24 CUs, governor max 1850 MHz).
  --disk-bench         Run the disk speed test (test 43) on the system disk:
                       sequential read, and random 4K read when fio is
                       installed. Read-only, nothing is written.
  --disk-write=GiB     Also write GiB (1-256) to a temporary file in /var/tmp
                       to measure write speed and the SLC cache size; the file
                       is removed afterwards. Implies --disk-bench.
  --speedtest          Run the internet speed test (test 44): download, upload,
                       idle and loaded latency, packet loss (Ookla speedtest or
                       speedtest-cli). Uses about 1 GB of data.
  --only=LIST          Run only the listed tests, e.g. --only=04,05,17.
                       Test 41 additionally needs --stress, test 42 --bench,
                       test 43 --disk-bench, test 44 --speedtest.
  --no-desktop         Do not copy the report to the user's Desktop.
  --gui                Word the how-to-run hints for the GUI instead of command-line options (used by the GUI).
  -h, --help           Show this help and exit.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --stress)            STRESS_MODE=true ;;
        --stress=*)          STRESS_MODE=true; STRESS_DURATION="${1#*=}" ;;
        --interval=*)        STRESS_SAMPLE="${1#*=}" ;;
        --bench)             BENCH_MODE=true ;;
        --bench=*)           BENCH_MODE=true; BENCH_SECONDS="${1#*=}" ;;
        --save-baseline)     BENCH_SAVE_BASELINE=true ;;
        --disk-bench)        DISK_MODE=true ;;
        --speedtest)         SPEEDTEST_MODE=true ;;
        --disk-write=*)      DISK_MODE=true; DISK_WRITE_GIB="${1#*=}" ;;
        --only=*)            ONLY="${1#*=}" ;;
        --no-prompt)         ;;   # skipped the reboot question at the end, which is gone; still accepted
        --no-desktop)        NO_DESKTOP=true ;;
        --gui)               GUI_MODE=true ;;
        -h|--help)           usage; exit 0 ;;
        *)                   echo "Unknown option: $1"; usage; exit 1 ;;
    esac
    shift
done
DISK_SIZE_WORD="--disk-write size"
[ "$GUI_MODE" = true ] && DISK_SIZE_WORD="write size"

if ! [[ "$STRESS_DURATION" =~ ^[0-9]+$ ]] || [ "$STRESS_DURATION" -lt 10 ]; then
    echo "--stress duration must be an integer of at least 10 seconds."
    exit 1
fi
if ! [[ "$STRESS_SAMPLE" =~ ^[0-9]+$ ]] || [ "$STRESS_SAMPLE" -lt 1 ]; then
    echo "--interval must be an integer of at least 1 second."
    exit 1
fi

if ! [[ "$BENCH_SECONDS" =~ ^[0-9]+$ ]] || [ "$BENCH_SECONDS" -lt 5 ]; then
    echo "--bench duration must be an integer of at least 5 seconds."
    exit 1
fi
if [ "$BENCH_SAVE_BASELINE" = true ] && [ "$BENCH_MODE" != true ]; then
    echo "--save-baseline only works together with --bench."
    exit 1
fi
if ! [[ "$DISK_WRITE_GIB" =~ ^[0-9]+$ ]] || [ "$DISK_WRITE_GIB" -gt 256 ]; then
    echo "--disk-write must be a whole number of GiB between 1 and 256."
    exit 1
fi
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ -n "$ONLY" ]; then
    if ! [[ "$ONLY" =~ ^[0-9]{1,2}(,[0-9]{1,2})*$ ]]; then
        echo "--only must be a comma-separated list of test numbers, e.g. --only=04,17."
        exit 1
    fi
    # Normalize to two digits (10# avoids 08/09 being read as octal).
    _norm=""
    IFS=',' read -ra _ids <<<"$ONLY"
    for _id in "${_ids[@]}"; do _norm+="$(printf '%02d' "$((10#$_id))"),"; done
    ONLY=",${_norm}"
    unset _norm _ids _id
fi

# True when test $1 is selected (always true without --only).
want() { [ -z "$ONLY" ] || [[ "$ONLY" == *",$1,"* ]]; }

TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
LOG_DIR="/var/log/bc250-bazzite-test"
mkdir -p "$LOG_DIR" || { echo "Cannot create $LOG_DIR (run with sudo)." >&2; exit 1; }
LOG_FILE="$LOG_DIR/bc250-test-results-${TIMESTAMP}.log"
# One baseline for every copy of the script (and the GUI), in the root-owned log folder. Older versions
# saved it next to the script; that copy is moved here the first time (see bench_load_legacy_baseline).
BENCH_BASELINE="$LOG_DIR/bench-baseline.json"
BENCH_BASELINE_OLD="$SCRIPT_DIR/bench-baseline.json"
echo "Starting BC-250 / Bazzite Tests - $(date '+%Y-%m-%d %H:%M:%S')" > "$LOG_FILE"

# Pre-checked false positives to exclude from the log results.
# Bazzite/BC-250 is noisy at boot; these are harmless on this hardware.
EXCLUSIONS=(
  # --- Firmware / ACPI ---
  "GRUB failed boot detection"
  "ACPI BIOS Error"
  "ACPI BIOS Warning"
  "ACPI Error"
  # The BC-250 BIOS disables pcid while a dependent feature stays set; harmless.
  "x86 CPU feature dependency check failure.*pcid"
  # --- amdgpu on Cyan Skillfish: display block reports these on every boot ---
  "dal_irq_service_dummy_(set|ack)"
  # The DC layer WARN_ONs at probe on this board, and kwin probes a format DC rejects.
  "dal_irq_service_(set|ack)\.cold"
  "display/dc/irq/irq_service\.c"
  "Unsupported screen format RA24"
  "Failed to clear hpd\(rx\) source=[0-9]+ on init"
  "Failed to add display topology, DTM TA is not initialized"
  "amdgpu: Secure display: Generic Failure"
  "psp gfx command LOAD_TA\(0x9\) failed"
  "Failed to initialize parser -125"
  "kfd kfd: amdgpu: TOPAZ not supported in kfd"
  # --- Fedora Atomic early-boot udev ordering (users/groups not yet resolvable) ---
  "Failed to resolve (group|user) '(lp|disk|kvm|tss|render|video|audio|utmp|clock|tty|kmem|input|sgx)'"
  # systemd-tmpfiles on bootc images cannot apply these shipped ACLs; cosmetic.
  "Failed to parse ACL"
  # --- rpm-ostree upstream quirk on merge commits ---
  "failed to query container image base metadata"
  # --- sudo/pam under a non-login root session ---
  "pam_systemd.*Failed to check if /run/user/[0-9]+/bus exists"
  # --- KDE Plasma desktop noise (flatpak portal sandbox detection) ---
  "Failed to register with host portal"
  "Failed to open hostWrapper directory"
  "org.kde.powerdevil.(chargethreshold|backlight)"
  "Charge thresholds are not supported by the kernel"
  "Failed to find service for Unity Launcher"
  "ToolTipDelegate.qml"
  "Failed to connect to Bolt manager DBus interface"
  "Failed to write to the pipe: Bad file descriptor"
  # --- One-off desktop session logout/login churn, not persistent problems ---
  "PipeWire remote error"
  "IPP_INTERNAL_ERROR: clearing cookies and reconnecting"
  "kded6\[[0-9]+\]: Failed to reconnect Invalid argument"
  "PreviewJob subjob had an error"
  "Transaction for (user|user-runtime-dir)@[0-9]+\.service/start is destructive"
  "Varlink call io.systemd.Login.CreateSession failed"
  "plasma-kactivitymanagerd.service: Failed with result"
  "kwin_wayland.*Applying output configuration failed"
  "setroubleshoot.*failed to retrieve rpm info"
  "Failed to subscribe to NameOwnerChanged signal"
  # powerdevil probes DDC/CI brightness over i2c; monitors without it return EREMOTEIO.
  "org_kde_powerdevil.*i2c"
  "Error in ioctl\(\) read.*EREMOTEIO"
  # NetworkManager dispatcher is not shipped activatable on Bazzite.
  "Activation request for 'org.freedesktop.nm_dispatcher' failed"
  # --- No Bluetooth radio on a stock BC-250 ---
  "Could not activate remote peer 'org.bluez'"
  "Bluetooth: hci0: (No support for|Opcode)"
  # input-remapper probes every input device at udev time; exit 1 just means "no preset for this device".
  "input-remapper-control --command autoload"
  # kwin retries output layer/modeset configs on hotplug and DPMS wakeups; harmless when the screen works.
  "kwin_wayland.*Failed to find a working output layer configuration"
  "kwin_wayland.*Atomic modeset commit failed"
  # --- Misc ---
  "sensors: no sensors found"
  "usb: port power management may be unreliable"
  "spd5118"
  "i2c_designware.*Transfer while suspended"
  "systemd-gpt-auto-generator"
  "Failed to start Load Kernel Module fuse"
  "tpm_crb|tpm_tis"
)

# Bazzite/BC-250 governor candidates, in order of preference.
GOVERNORS=(
  "cyan-skillfish-governor-smu"
  "cyan-skillfish-governor-tt"
  "oberon-governor"
)

# Always yields a number, so it is safe inside $(( )).
read_num_g() { local v; v=$(cat "$1" 2>/dev/null | tr -dc '0-9'); echo "${v:-0}"; }

# Function to log results
log_result() {
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# How to start an opt-in part: $1 for the command line, $2 for the GUI (--gui).
log_howto() {
    if [ "$GUI_MODE" = true ]; then log_result "$2"; else log_result "$1"; fi
}

# Function to filter log results with exclusions
filter_logs() {
    local log_content="$1"
    local filtered_log="$log_content"
    for exclusion in "${EXCLUSIONS[@]}"; do
        filtered_log=$(echo "$filtered_log" | grep -vE "$exclusion")
    done
    echo "$filtered_log"
}

# What journal lines mean and what to do about them (tests 15, 16 and 17): pairs of a
# pattern (grep -iE) and its advice. A line counts for the first pattern it matches, so
# real faults come first and the known noise after them.
LOG_ADVICE=(
  # --- Real faults ---
  "ring [a-z0-9_.]+ timed? ?out|amdgpu_job_timedout|GPU reset|gpu_recover|Waiting for fences timed out|MES failed"
  "GPU hang or reset: usually an unstable CU unlock, GPU overclock or governor setting. Go back to the last stable one (cu-bisect, gpu-oc-bisect, governor) and check test 35."
  "VM_L2_PROTECTION_FAULT|GPU fault detected|page fault \(src_id"
  "GPU page fault: a game or the driver used invalid GPU memory. Once is usually a game bug; if it repeats, update Bazzite (Mesa) and undo any GPU overclock."
  "flip_done timed out|commit wait timed out"
  "Display update timed out: try another cable, port or refresh rate. A GPU hang (test 35) causes it too."
  "Direct firmware load for .* failed|failed to load firmware"
  "Missing firmware file: harmless if the device it names works; otherwise update Bazzite (rpm-ostree upgrade)."
  "nvme.*(timeout|I/O error|resetting controller|controller is down)"
  "NVMe timeout or reset, often the drive's power saving (APST): sudo rpm-ostree kargs --append-if-missing=nvme_core.default_ps_max_latency_us=0, reboot, and check test 10."
  "I/O error, dev|Buffer I/O error|EXT4-fs error|BTRFS (error|critical)|critical medium error"
  "Disk read or write errors: back up your data now and check the drive health (test 10, sudo smartctl -a /dev/nvme0n1)."
  "Machine check|mce: \[Hardware Error\]"
  "CPU hardware error (MCE): usually an unstable core unlock, undervolt or overheating. Go back to stock settings and check the cooling (tests 22, 36 and 46)."
  "Out of memory: Killed process|oom-kill|invoked oom-killer"
  "Out of memory, the kernel killed a program: close programs, check the swap layout (test 14) or move RAM from VRAM to the CPU with memory-manager."
  "segfault at|dumped core|Failed with result 'core-dump'|coredump|__stack_chk_fail|__fortify_fail"
  "A program crashed: coredumpctl list shows which, coredumpctl info <name> shows why. If it repeats, update Bazzite or the app."
  "Failed at step EXEC spawning (/var)?/home/"
  "systemd cannot run a script from a home folder (SELinux blocks it), so that service never starts. Reinstall the app from the portal, or remove the old service: sudo systemctl disable <name>.service."
  "usb .*(device descriptor read|unable to enumerate|not accepting address|over-current)"
  "A USB device failed to connect: try another port or cable, or a powered hub for power-hungry devices."
  "app-.*@autostart\.service"
  "An autostart entry failed: check it in System Settings > Autostart, and remove it if the program is gone."
  # --- Known noise ---
  "Transaction for .* is destructive"
  "Logged while shutting down or rebooting; harmless."
  "kwallet"
  "KDE Wallet is off or not set up, so apps that store passwords may ask again. Harmless; set it up in System Settings > KDE Wallet if you want it."
  "org\.bluez|bluetoothd|Bluetooth:"
  "Bluetooth: the BC-250 has no radio, and with a USB dongle bluez reports profiles it cannot start. Harmless if your Bluetooth devices work."
  "Activation request for '[^']+' failed|Could not activate remote peer"
  "A D-Bus service (UDisks2, UPower, RealtimeKit, a portal) was asked for while it was stopping, usually at logout or shutdown. Harmless if disks, power and sound work."
  "pam_unix.*(auth|conversation failed)|Authentication failure|ERROR_AUTHENTICATION"
  "A wrong or canceled password at the login screen or sudo; harmless unless it was not you."
  "plasmalogin.*(Process crashed|ERROR_INTERNAL)"
  "The login screen process ended with an error, usually when it closes at login or shutdown. Look into it only if the login screen fails to appear."
  "\.qml(:[0-9]+)?:|TypeError: Cannot read property"
  "Plasma widget script messages; harmless, Plasma updates clear them."
  "wireplumber|pipewire"
  "PipeWire / WirePlumber (sound) messages; harmless if sound works. Otherwise: systemctl --user restart pipewire wireplumber."
  "kwin_wayland"
  "KWin (the desktop compositor): logged when switching to Game Mode or a TTY, or probing sensors the BC-250 lacks. Harmless if the screen works."
  "IPP_INTERNAL_ERROR|Failed to reconnect Invalid argument"
  "The printer status (CUPS) reconnecting, also without a printer; harmless."
  "xdg-desktop-portal"
  "Desktop portal messages (file dialogs and screen sharing for Flatpak apps); harmless if those work."
  "kded[0-9]*(\[[0-9]+\])?:|kioworker|dolphin"
  "KDE desktop and file manager messages; harmless."
)

# explain_log_lines LINES SCOPE: after a test's journal lines, a HINT per known kind of line,
# per failed unit and per source of the lines left unexplained. SCOPE is the journalctl
# time option to read more with ("-b" or "--since '7 days ago'").
explain_log_lines() {
    local rest="$1" scope="$2" i hits n unit units ident
    [ -n "$rest" ] || return 0
    for ((i = 0; i < ${#LOG_ADVICE[@]}; i += 2)); do
        hits=$(grep -iE -- "${LOG_ADVICE[i]}" <<<"$rest")
        [ -n "$hits" ] || continue
        n=$(grep -c '' <<<"$hits")
        log_result "HINT: [$n line$( [ "$n" = 1 ] || echo s)] ${LOG_ADVICE[i + 1]}"
        rest=$(grep -viE -- "${LOG_ADVICE[i]}" <<<"$rest")
    done
    # Units that failed to start: where to read why, and how to stop them.
    units=$(grep -iE "Failed to start |: Failed with result|: Failed at step" <<<"$rest" \
        | grep -oE "[A-Za-z0-9@_.:\\-]+\.(service|socket|mount|timer)" | sort | uniq -c | sort -rn | head -5)
    while read -r n unit; do
        [ -n "$unit" ] || continue
        log_result "HINT: [$n line$( [ "$n" = 1 ] || echo s)] ${unit} failed. Read why with: journalctl ${scope} -u ${unit}; if you no longer use it: sudo systemctl disable ${unit}."
        rest=$(grep -vF -- "$unit" <<<"$rest")
    done <<<"$units"
    # Everything else: the programs that logged it, and how to read their lines.
    while read -r n ident; do
        [ -n "$ident" ] || continue
        log_result "HINT: [$n line$( [ "$n" = 1 ] || echo s)] from ${ident}, no known explanation. Read them with: journalctl ${scope} -p warning -t ${ident}; search the message online if it repeats."
    done < <(awk '/^[A-Z][a-z][a-z] +[0-9]+ [0-9:]+ / { t = $5; sub(/\[[0-9]+\]/, "", t); sub(/:$/, "", t); if (t != "") print t }' <<<"$rest" \
        | sort | uniq -c | sort -rn | head -3)
}

# Function to check service status
check_service() {
    local SERVICE_NAME=$1
    log_result "Check service: $SERVICE_NAME"
    if ! systemctl list-unit-files "$SERVICE_NAME" >/dev/null 2>&1 || \
       [ -z "$(systemctl list-unit-files --no-legend "$SERVICE_NAME" 2>/dev/null)" ]; then
        log_result "INFO: $SERVICE_NAME is not installed on this system."
        return 2
    fi
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_result "SUCCESS: $SERVICE_NAME is active."
        return 0
    else
        log_result "ERROR: $SERVICE_NAME is not active."
        ERROR_FOUND=true
        return 1
    fi
}

# Function to check a unit is masked (used for units that MUST stay off on BC-250)
check_masked() {
    local SERVICE_NAME=$1
    local REASON=$2
    local STATE
    STATE=$(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null)
    if [ "$STATE" = "masked" ]; then
        log_result "SUCCESS: $SERVICE_NAME is masked. ($REASON)"
    elif [ -z "$(systemctl list-unit-files --no-legend "$SERVICE_NAME" 2>/dev/null)" ] && \
         ! systemctl cat "$SERVICE_NAME" >/dev/null 2>&1; then
        log_result "INFO: $SERVICE_NAME is not present on this system. ($REASON)"
    elif systemctl is-active --quiet "$SERVICE_NAME"; then
        log_result "ERROR: $SERVICE_NAME is ACTIVE but must be masked. ($REASON)"
        ERROR_FOUND=true
    else
        log_result "WARNING: $SERVICE_NAME is '${STATE:-unknown}' and not masked. ($REASON)"
        log_result "HINT: sudo systemctl mask $SERVICE_NAME"
        WARN_FOUND=true
    fi
}

# ----------------------------------------------------------------------------
# Shared discovery. Several tests read these, so they are resolved up front and
# stay valid when only a subset of tests is selected with --only.
# ----------------------------------------------------------------------------
# Installed BC-250 GPU governor (tests 18, 19).
GOV_FOUND=""
for gov in "${GOVERNORS[@]}"; do
    if [ -n "$(systemctl list-unit-files --no-legend "${gov}.service" 2>/dev/null)" ]; then
        GOV_FOUND="$gov"
        break
    fi
done
# GPU sysfs node (tests 19, 22).
GPU_DEV=""
for card in /sys/class/drm/card*/device; do
    [ -e "$card/pp_dpm_sclk" ] || continue
    if grep -qi "0x13f9\|amdgpu" "$card/uevent" 2>/dev/null; then
        GPU_DEV="$card"
        break
    fi
    GPU_DEV="$card"
done

# Desktop user, for tests that need the user session (38, 39, 41).
GAME_USER="${SUDO_USER:-$USER}"
GAME_HOME=$(getent passwd "$GAME_USER" 2>/dev/null | cut -d: -f6)

# Optional tools (stress-ng, vkpeak, memtest_vulkan, fio, speedtest, ...) may live in the desktop
# user's ~/.local/bin or in Homebrew. Those folders are writable by the user, so a tool found there is
# never run as root: anything running as the user could otherwise replace it and get root. Root's
# PATH is not extended; find_tool looks there itself and says how the tool may be run.
root_safe() {
    # True when the file and every folder above it belong to root and only root can write to them.
    local p
    p=$(readlink -f -- "$1" 2>/dev/null) || return 1
    while :; do
        [ "$(stat -c %u -- "$p" 2>/dev/null)" = 0 ] || return 1
        [ -z "$(find "$p" -maxdepth 0 -perm /022 2>/dev/null)" ] || return 1
        [ "$p" = / ] && return 0
        p=$(dirname -- "$p")
    done
}
find_tool() {
    # find_tool NAME: sets TOOL (full path), TOOL_AS_USER (true when it must not run as root) and
    # TOOL_CMD (array to run it with: the path, or sudo -u <desktop user> path). Returns 1 if missing,
    # or when it is user-writable and there is no desktop user to run it as.
    local d
    TOOL=$(command -v "$1" 2>/dev/null)
    if [ -z "$TOOL" ]; then
        for d in "$GAME_HOME/.local/bin" /home/linuxbrew/.linuxbrew/bin; do
            [ -n "$d" ] && [ -x "$d/$1" ] && [ -f "$d/$1" ] && { TOOL="$d/$1"; break; }
        done
    fi
    [ -n "$TOOL" ] || return 1
    TOOL_AS_USER=false
    TOOL_CMD=("$TOOL")
    if [ "$(id -u)" = 0 ] && ! root_safe "$TOOL"; then
        TOOL_AS_USER=true
        if [ -z "$GAME_USER" ] || [ "$GAME_USER" = root ]; then
            log_result "INFO: Not running $TOOL as root: it is writable by a non-root user."
            return 1
        fi
        TOOL_CMD=(sudo -u "$GAME_USER" -H -- "$TOOL")
    fi
    return 0
}
run_as_user() {
    # Run a command as the desktop user with a usable session bus.
    local uid
    uid=$(id -u "$GAME_USER" 2>/dev/null) || return 1
    sudo -u "$GAME_USER" XDG_RUNTIME_DIR="/run/user/$uid" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" DISPLAY="${DISPLAY:-:0}" "$@" 2>/dev/null
}
# Kernel-log signatures (tests 35, 36 and the stress run in 41).
GPU_HANG_RE="ring [a-z0-9_.]+ timed? ?out|amdgpu_job_timedout|GPU reset begin|GPU reset\(|amdgpu_device_gpu_recover|Waiting for fences timed out|VM_L2_PROTECTION_FAULT|GPU fault detected|page fault \(src_id|MES failed|Failed to evict|GPU hang|soft recovery|reset was successful|failed to write reg|SMU: I'm not done"
PANIC_RE="Kernel panic|\bOops\b|BUG: |general protection fault|soft lockup|hard LOCKUP|watchdog: (BUG|Watchdog detected)|unable to handle (kernel|page)|Call Trace:|RIP: 0010"
# The amdgpu DC layer throws a harmless WARN_ON at probe on this board, which drags a
# RIP and a Call Trace into the journal on every boot. It is never a real fault.
PANIC_BENIGN_RE="dal_irq_service_(set|ack)|irq_service\.c|NMI watchdog: Enabled|amdgpu_dm_hpd_init|traps: .*(general protection fault|trap int3)"

if want 00; then
log_result "[TEST 00] Platform Identification Test"
log_result "Verify this is a BC-250 board running Bazzite"
BOARD=$(cat /sys/class/dmi/id/board_name 2>/dev/null)
VENDOR=$(cat /sys/class/dmi/id/board_vendor 2>/dev/null)
log_result "INFO: Board: ${VENDOR:-unknown} ${BOARD:-unknown}"
if grep -qi "bc-250\|bc250" <<<"$BOARD"; then
    log_result "SUCCESS: BC-250 board detected."
else
    log_result "WARNING: Board does not identify as BC-250 (got '${BOARD:-unknown}'). BIOS may not expose it."
    WARN_FOUND=true
fi
# BIOS identification. Stock ASRock releases are 1.00 / 2.00 / 3.00 / 5.00 (all
# share the same DSDT). Anything else usually means a modded BIOS (MeiMei /
# RescueMei DXE core unlock), which matters: modded BIOSes may ship their own
# ACPI fix and conflict with the initrd ACPI override.
BIOS_VENDOR=$(cat /sys/class/dmi/id/bios_vendor 2>/dev/null)
BIOS_VERSION=$(cat /sys/class/dmi/id/bios_version 2>/dev/null)
BIOS_DATE=$(cat /sys/class/dmi/id/bios_date 2>/dev/null)
BIOS_RELEASE=$(cat /sys/class/dmi/id/bios_release 2>/dev/null)
log_result "INFO: BIOS: ${BIOS_VENDOR:-unknown} version '${BIOS_VERSION:-unknown}' (date: ${BIOS_DATE:-unknown}, release: ${BIOS_RELEASE:-unknown})"
case "$BIOS_VERSION" in
    *[Mm]ei[Mm]ei*|*[Mm]od*|*unlock*|*UNLOCK*)
        log_result "INFO: BIOS version string suggests a modded BIOS (core unlock / ACPI fix built in)."
        log_result "HINT: Do not combine a modded BIOS with the initrd ACPI override; duplicate tables fail to load."
        log_result "HINT: A modded BIOS is no longer needed: bc250_memcfg (VRAM split), bc250-persistent-acpi"
        log_result "HINT: (ACPI fix) and the cores/CU unlock tools give the same benefits on stock 5.00."
        ;;
    [LP]5.00|5.00)
        log_result "SUCCESS: Latest stock ASRock BIOS ($BIOS_VERSION)."
        log_result "NOTE: Menu-unlock mods (e.g. the P3.00 'Chipset Menu' BIOS) keep the stock"
        log_result "NOTE: version string, so DMI cannot distinguish them from a factory BIOS."
        ;;
    [LP][1-4].00|[1-4].00)
        log_result "WARNING: Older stock ASRock BIOS version string ($BIOS_VERSION); the latest is 5.00."
        log_result "HINT: Update to stock 5.00 — no performance is lost: bc250_memcfg (VRAM split),"
        log_result "HINT: bc250-persistent-acpi (ACPI fix) and the cores/CU unlock tools replace every"
        log_result "HINT: modded-BIOS benefit in software."
        log_result "NOTE: Menu-unlock mods (e.g. the P3.00 'Chipset Menu' BIOS) keep the stock"
        log_result "NOTE: version string, so DMI cannot distinguish them from a factory BIOS."
        WARN_FOUND=true
        ;;
    "")
        log_result "WARNING: BIOS version not exposed via DMI."
        WARN_FOUND=true
        ;;
    *)
        log_result "INFO: Unrecognized BIOS version string; stock releases are 1.00/2.00/3.00/5.00."
        ;;
esac
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    log_result "INFO: OS: $PRETTY_NAME"
    if grep -qi "bazzite" <<<"$ID $NAME $PRETTY_NAME"; then
        log_result "SUCCESS: Bazzite detected."
    else
        log_result "WARNING: This does not look like Bazzite. Some tests will not apply."
        WARN_FOUND=true
    fi
fi
log_result "INFO: Kernel: $(uname -r)"
# On this APU a GPU crash takes the whole system with it, because the driver cannot
# reset the GPU the CPU is part of. Two kernel ranges are known to trigger that.
KVER=$(uname -r | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+')
case "$KVER" in
    6.15.[0-6]|6.17.[89]|6.17.10)
        log_result "ERROR: Kernel $KVER is a known-bad release for the BC-250 (random GPU crashes under load)."
        log_result "HINT: Roll back with: rpm-ostree rollback, or update past the affected range."
        ERROR_FOUND=true ;;
    *)
        log_result "SUCCESS: Kernel $KVER is outside the known-bad BC-250 ranges (6.15.0-6.15.6, 6.17.8-6.17.10)." ;;
esac
echo

fi  # TEST 00
if want 01; then
log_result "[TEST 01] Check All Running Services Test"
log_result "Check running services"
systemctl list-units --type=service --state=running --no-pager | tee -a "$LOG_FILE"
echo

fi  # TEST 01
if want 02; then
log_result "[TEST 02] Failed Units Test"
log_result "Check for failed systemd units"
FAILED_UNITS=$(systemctl list-units --state=failed --no-legend --no-pager)
if [ -n "$FAILED_UNITS" ]; then
    log_result "ERROR: Failed systemd units detected:"
    echo "$FAILED_UNITS" | while read -r line; do log_result "$line"; done
    ERROR_FOUND=true
else
    log_result "SUCCESS: No failed systemd units."
fi
echo

fi  # TEST 02
if want 03; then
log_result "[TEST 03] System Uptime Test"
log_result "Check system uptime"
uptime | tee -a "$LOG_FILE"
echo

fi  # TEST 03
if want 04; then
log_result "[TEST 04] Network Connectivity Test"
log_result "Pinging Google"
if ping -c 4 google.com >/dev/null 2>&1; then
    log_result "SUCCESS: Network connectivity to the internet is working."
else
    log_result "ERROR: No network connectivity to the internet."
    ERROR_FOUND=true
fi
echo

fi  # TEST 04
if want 05; then
log_result "[TEST 05] DNS Resolution Test"
log_result "Check DNS resolution for google.com"
if command -v dig >/dev/null 2>&1; then
    if dig google.com +short >/dev/null 2>&1; then
        log_result "SUCCESS: DNS resolution is working."
        dig google.com +short | tee -a "$LOG_FILE"
    else
        log_result "ERROR: DNS resolution failed."
        ERROR_FOUND=true
    fi
else
    log_result "INFO: 'dig' not installed, falling back to resolvectl."
    resolvectl query google.com 2>&1 | tee -a "$LOG_FILE"
fi
echo

fi  # TEST 05
if want 06; then
log_result "[TEST 06] Public Internet Access Test"
log_result "Verify Public Internet Access"
if curl -sI https://www.example.com >/dev/null 2>&1; then
    log_result "SUCCESS: Internet is accessible."
    curl -sI https://www.example.com | head -1 | tee -a "$LOG_FILE"
else
    log_result "ERROR: No internet available."
    ERROR_FOUND=true
fi
echo

fi  # TEST 06
if want 07; then
log_result "[TEST 07] Open Ports Test"
log_result "Check for open ports"
OPEN_PORTS=$(ss -tuln | grep LISTEN)
if [ -n "$OPEN_PORTS" ]; then
    log_result "INFO: Open ports detected:"
    echo "$OPEN_PORTS" | while read -r line; do
        log_result "$line"
    done
else
    log_result "SUCCESS: No open ports detected."
fi
echo

fi  # TEST 07
if want 08; then
log_result "[TEST 08] System Clock NTP Synchronization Test"
log_result "NTP synchronization Test"
if timedatectl show -p NTPSynchronized --value | grep -q "yes"; then
    log_result "SUCCESS: System clock is synchronized with NTP."
else
    log_result "ERROR: System clock is not synchronized with NTP."
    ERROR_FOUND=true
fi
echo

fi  # TEST 08
if want 09; then
log_result "[TEST 09] Disk Configuration Test"
log_result "Check disk space and volumes"
df -h | tee -a "$LOG_FILE"
lsblk | tee -a "$LOG_FILE"
echo

fi  # TEST 09
if want 10; then
log_result "[TEST 10] NVMe Devices Test"
log_result "Check NVMe devices: detection, PCIe link, DRAM cache or host memory buffer, and SMART health"
NVME_CTRLS=()
for c in /sys/class/nvme/nvme*; do [ -e "$c" ] && NVME_CTRLS+=("$c"); done
if [ ${#NVME_CTRLS[@]} -eq 0 ]; then
    log_result "INFO: No NVMe devices present (BC-250 may be booting from USB/SATA)."
else
    log_result "SUCCESS: ${#NVME_CTRLS[@]} NVMe controller(s) recognized."
    ls -l /dev/nvme?n? 2>/dev/null | tee -a "$LOG_FILE"
    HAVE_NVME_CLI=false; command -v nvme >/dev/null 2>&1 && HAVE_NVME_CLI=true
    HAVE_SMARTCTL=false; command -v smartctl >/dev/null 2>&1 && HAVE_SMARTCTL=true
    [ "$HAVE_NVME_CLI" = true ] && nvme list 2>/dev/null | tee -a "$LOG_FILE"
    NVME_KLOG=$(journalctl -k -b --no-pager 2>/dev/null | grep -i "nvme"; dmesg 2>/dev/null | grep -i "nvme")
    for c in "${NVME_CTRLS[@]}"; do
        n=$(basename "$c")
        model=$(sed 's/[[:space:]]*$//' "$c/model" 2>/dev/null)
        fw=$(sed 's/[[:space:]]*$//' "$c/firmware_rev" 2>/dev/null)
        log_result "INFO: /dev/$n: ${model:-unknown model}, firmware ${fw:-?}"

        # ---- PCIe link: what it trained at vs. what the drive and the slot support ----
        pdev=$(readlink -f "$c/device" 2>/dev/null)
        cur_s=$(awk '{print $1}' "$pdev/current_link_speed" 2>/dev/null)
        cur_w=$(cat "$pdev/current_link_width" 2>/dev/null)
        dev_s=$(awk '{print $1}' "$pdev/max_link_speed" 2>/dev/null)
        dev_w=$(cat "$pdev/max_link_width" 2>/dev/null)
        slot_s=$(awk '{print $1}' "$(dirname "$pdev")/max_link_speed" 2>/dev/null)
        slot_w=$(cat "$(dirname "$pdev")/max_link_width" 2>/dev/null)
        if [ -n "$cur_s" ] && [ -n "$cur_w" ]; then
            read -r LINK_VERDICT LINK_TEXT < <(awk -v cs="$cur_s" -v cw="$cur_w" -v ds="${dev_s:-$cur_s}" -v dw="${dev_w:-$cur_w}" \
                -v ss="${slot_s:-0}" -v sw="${slot_w:-0}" '
                function gen(s) { return s >= 32 ? 5 : s >= 16 ? 4 : s >= 8 ? 3 : s >= 5 ? 2 : 1 }
                function lane(s) { return s >= 32 ? 3938 : s >= 16 ? 1969 : s >= 8 ? 985 : s >= 5 ? 500 : 250 }
                BEGIN {
                    ls = (ss > 0 && ss < ds) ? ss : ds; lw = (sw > 0 && sw < dw) ? sw : dw
                    txt = sprintf("PCIe Gen%d x%d (%s GT/s, ceiling ~%d MB/s); drive supports Gen%d x%d", gen(cs), cw, cs, lane(cs) * cw, gen(ds), dw)
                    if (ss > 0) txt = txt sprintf(", slot supports Gen%d x%d", gen(ss), sw)
                    v = (cs < ls || cw < lw) ? "LOW" : (cs < ds || cw < dw) ? "SLOT" : "OK"
                    print v, txt
                }')
            case "$LINK_VERDICT" in
                OK)   log_result "SUCCESS: Link: $LINK_TEXT." ;;
                SLOT) log_result "INFO: Link: $LINK_TEXT. The slot, not the drive, sets the speed limit." ;;
                LOW)  log_result "WARNING: Link: $LINK_TEXT. It trained below what both the drive and the slot support."
                      log_result "HINT: Reseat the drive (and check any M.2 adapter or riser); a poor contact makes the link fall back to a lower speed or width."
                      WARN_FOUND=true ;;
            esac
        else
            log_result "INFO: PCIe link speed of /dev/$n is not exposed in sysfs."
        fi

        # ---- DRAM cache: DRAM-less drives ask the host for a memory buffer (HMB) ----
        HMPRE=""; HMMIN=""; WCTEMP=""; CCTEMP=""
        if [ "$HAVE_NVME_CLI" = true ]; then
            while IFS='=' read -r k v; do
                case "$k" in hmpre) HMPRE=$v ;; hmmin) HMMIN=$v ;; wctemp) WCTEMP=$v ;; cctemp) CCTEMP=$v ;; esac
            done < <(nvme id-ctrl "/dev/$n" -o json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for k in ("hmpre", "hmmin", "wctemp", "cctemp"):
    try:
        v = int(d.get(k, ""))
    except (TypeError, ValueError):
        continue
    # hmpre/hmmin are in 4 KiB units, temperatures in Kelvin.
    if k in ("hmpre", "hmmin"):
        v = v * 4 // 1024
    elif v > 0:
        v -= 273
    print("%s=%d" % (k, v))
' 2>/dev/null)
        fi
        HMB_ALLOC=$(grep -E "\b$n\b.*allocated [0-9]+ MiB host memory buffer" <<<"$NVME_KLOG" | grep -oE "[0-9]+ MiB" | tail -1)
        if [ -n "$HMPRE" ] && [ "$HMPRE" -gt 0 ] 2>/dev/null; then
            log_result "INFO: DRAM cache: none. /dev/$n is DRAM-less and uses a Host Memory Buffer (wants ${HMPRE} MiB of system RAM, minimum ${HMMIN:-?} MiB)."
            if [ -n "$HMB_ALLOC" ]; then
                log_result "SUCCESS: The kernel gave it a ${HMB_ALLOC} host memory buffer."
                log_result "HINT: Fine for game loading. Expect slower sustained and random writes than a drive with DRAM; the buffer comes out of the RAM the BC-250 shares with the GPU."
            else
                log_result "WARNING: No host memory buffer allocation found in this boot's kernel log; the drive may be running without any mapping cache (slow random I/O)."
                log_result "HINT: Check for nvme.max_host_mem_size_mb=0 on the kernel command line: cat /proc/cmdline"
                WARN_FOUND=true
            fi
        elif [ -n "$HMPRE" ]; then
            log_result "SUCCESS: DRAM cache: /dev/$n does not ask for a host memory buffer, so it has its own DRAM cache (DRAM-less NVMe drives without HMB are rare)."
        elif [ -n "$HMB_ALLOC" ]; then
            log_result "INFO: DRAM cache: none. The kernel gave /dev/$n a ${HMB_ALLOC} host memory buffer, so it is a DRAM-less drive."
        else
            log_result "INFO: DRAM cache: probably yes. No host memory buffer was allocated for /dev/$n in this boot (install nvme-cli to confirm)."
            log_result "HINT: rpm-ostree install nvme-cli   (then reboot)"
        fi

        # ---- SMART / health log ----
        SMART_JSON=""; SMART_SRC=""
        if [ "$HAVE_NVME_CLI" = true ]; then
            SMART_JSON=$(nvme smart-log "/dev/$n" -o json 2>/dev/null); SMART_SRC=nvme
        fi
        if [ -z "$SMART_JSON" ] && [ "$HAVE_SMARTCTL" = true ]; then
            SMART_JSON=$(smartctl -j -a "/dev/$n" 2>/dev/null); SMART_SRC=smartctl
        fi
        unset SM; declare -A SM=()
        if [ -n "$SMART_JSON" ]; then
            while IFS='=' read -r k v; do [ -n "$k" ] && SM[$k]=$v; done < <(python3 -c '
import json, sys
src = sys.argv[1]
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if src == "smartctl":
    d = d.get("nvme_smart_health_information_log", {})
def num(v):
    if isinstance(v, dict):     # newer nvme-cli nests some fields
        v = v.get("value", next((x for x in v.values() if isinstance(x, (int, float, str))), None))
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
keys = {
    "warn": ["critical_warning"], "temp": ["temperature"], "spare": ["avail_spare", "available_spare"],
    "thresh": ["spare_thresh", "available_spare_threshold"], "used": ["percent_used", "percentage_used"],
    "media": ["media_errors"], "errlog": ["num_err_log_entries"], "wtime": ["warning_temp_time"],
    "ctime": ["critical_comp_time"], "hours": ["power_on_hours"], "unsafe": ["unsafe_shutdowns"],
    "written": ["data_units_written"],
}
for out, names in keys.items():
    for name in names:
        v = num(d.get(name))
        if v is not None:
            if out == "temp" and v > 200:
                v -= 273
            if out == "written":
                v = v * 512000 // 10**9          # data units of 512,000 bytes -> GB
            print(f"{out}={v}")
            break
' "$SMART_SRC" <<<"$SMART_JSON" 2>/dev/null)
        fi
        if [ -z "${SM[temp]:-}" ]; then
            for h in "$c"/hwmon*/temp1_input "$c"/device/hwmon/hwmon*/temp1_input; do
                [ -r "$h" ] && SM[temp]=$(( $(read_num_g "$h") / 1000 )) && break
            done
        fi
        if [ ${#SM[@]} -eq 0 ]; then
            log_result "INFO: No SMART data for /dev/$n (needs nvme-cli or smartctl)."
            log_result "HINT: rpm-ostree install nvme-cli   (then reboot)"
        else
            HEALTH_OK=true
            if [ -n "${SM[warn]:-}" ] && [ "${SM[warn]}" -ne 0 ]; then
                W=${SM[warn]}; WHY=""
                (( W & 1 ))  && WHY+=" spare-below-threshold"
                (( W & 2 ))  && WHY+=" temperature"
                (( W & 4 ))  && WHY+=" reliability-degraded"
                (( W & 8 ))  && WHY+=" read-only"
                (( W & 16 )) && WHY+=" backup-failed"
                log_result "ERROR: /dev/$n reports a critical warning ($(printf '0x%02x' "$W"):${WHY:- unknown}). Back up your data."
                ERROR_FOUND=true; HEALTH_OK=false
            fi
            if [ "${SM[media]:-0}" -gt 0 ]; then
                log_result "ERROR: /dev/$n has ${SM[media]} media/data integrity errors. Back up your data and consider replacing it."
                ERROR_FOUND=true; HEALTH_OK=false
            fi
            if [ -n "${SM[spare]:-}" ] && [ -n "${SM[thresh]:-}" ] && [ "${SM[spare]}" -lt "${SM[thresh]}" ]; then
                log_result "ERROR: Spare blocks at ${SM[spare]}%, below the ${SM[thresh]}% threshold."
                ERROR_FOUND=true; HEALTH_OK=false
            fi
            if [ -n "${SM[used]:-}" ]; then
                if [ "${SM[used]}" -ge 100 ]; then
                    log_result "ERROR: Wear: ${SM[used]}% of the rated endurance used."; ERROR_FOUND=true; HEALTH_OK=false
                elif [ "${SM[used]}" -ge 80 ]; then
                    log_result "WARNING: Wear: ${SM[used]}% of the rated endurance used."; WARN_FOUND=true; HEALTH_OK=false
                else
                    log_result "INFO: Wear: ${SM[used]}% of the rated endurance used${SM[written]:+, ${SM[written]} GB written}${SM[hours]:+, ${SM[hours]} power-on hours}."
                fi
            fi
            if [ -n "${SM[temp]:-}" ]; then
                T_WARN=${WCTEMP:-70}; [ "$T_WARN" -gt 0 ] 2>/dev/null || T_WARN=70
                if [ "${SM[temp]}" -ge "$T_WARN" ]; then
                    log_result "WARNING: /dev/$n is at ${SM[temp]} °C (its warning threshold is ${T_WARN} °C)."
                    log_result "HINT: Fit an M.2 heatsink or add airflow over the drive; hot NVMe drives throttle hard."
                    WARN_FOUND=true; HEALTH_OK=false
                else
                    log_result "INFO: Temperature: ${SM[temp]} °C (warning threshold ${T_WARN} °C${CCTEMP:+, critical ${CCTEMP} °C})."
                fi
            fi
            if [ "${SM[wtime]:-0}" -gt 0 ] || [ "${SM[ctime]:-0}" -gt 0 ]; then
                log_result "WARNING: /dev/$n has spent ${SM[wtime]:-0} min above its warning and ${SM[ctime]:-0} min above its critical temperature (it throttles there)."
                log_result "HINT: Fit an M.2 heatsink or add airflow over the drive."
                WARN_FOUND=true; HEALTH_OK=false
            fi
            [ -n "${SM[unsafe]:-}" ] && log_result "INFO: ${SM[unsafe]} unsafe shutdowns recorded (every hard lockup or power cut counts, see test 34)."
            [ "${SM[errlog]:-0}" -gt 0 ] && log_result "INFO: ${SM[errlog]} entries in the drive's error log (usually harmless command errors, not data loss)."
            [ "$HEALTH_OK" = true ] && [ -n "${SM[warn]:-}" ] && log_result "SUCCESS: SMART health of /dev/$n is good (source: $SMART_SRC)."
        fi
    done
    log_howto "INFO: Measure read/write speed and the SLC cache size with the disk speed test (43): --disk-bench" \
              "INFO: Measure read/write speed and the SLC cache size with the disk speed test (43, Storage and memory page)."
fi
echo

fi  # TEST 10
if want 11; then
log_result "[TEST 11] Resource Consumption Test"
log_result "Check resource usage"
top -bn1 | head -10 | tee -a "$LOG_FILE"
echo

fi  # TEST 11
if want 12; then
log_result "[TEST 12] Boot Time Test"
log_result "Analyzing boot time"
systemd-analyze 2>&1 | tee -a "$LOG_FILE"
systemd-analyze blame 2>/dev/null | head -10 | tee -a "$LOG_FILE"
SLOW_UNITS=$(systemd-analyze blame --no-pager 2>/dev/null | awk '$1 ~ /min/ {print}')
if [ -n "$SLOW_UNITS" ]; then
    log_result "WARNING: Units taking over a minute at boot:"
    echo "$SLOW_UNITS" | while read -r line; do log_result "  $line"; done
    log_result "INFO: uupd.service is the Bazzite updater and is expected to be slow; it does not block the desktop."
    WARN_FOUND=true
fi
echo

fi  # TEST 12
if want 13; then
log_result "[TEST 13] Security Configuration Test"
log_result "Check firewall status (firewalld)"
if command -v firewall-cmd >/dev/null 2>&1; then
    if systemctl is-active --quiet firewalld; then
        log_result "SUCCESS: firewalld is active."
        firewall-cmd --list-all 2>&1 | tee -a "$LOG_FILE"
    else
        log_result "WARNING: firewalld is installed but not active."
        WARN_FOUND=true
    fi
else
    log_result "INFO: firewalld is not installed."
fi
log_result "Check SELinux status"
if command -v getenforce >/dev/null 2>&1; then
    log_result "INFO: SELinux is $(getenforce)."
else
    log_result "INFO: SELinux tools not available."
fi
echo

fi  # TEST 13
if want 14; then
log_result "[TEST 14] Memory and Swap Test"
log_result "Check memory and swap usage"
MEMORY_USAGE=$(free -h)
log_result "INFO: Memory and swap usage:\n$MEMORY_USAGE"
log_result "Check the full swap topology"
SWAP_TABLE=$(swapon --show --bytes 2>/dev/null)
if [ -n "$SWAP_TABLE" ]; then
    swapon --show 2>/dev/null | tee -a "$LOG_FILE"
else
    log_result "WARNING: No swap is active at all."
    log_result "HINT: On this board an OOM can present as a hard freeze. Configure a disk swapfile with zswap in front of it."
    WARN_FOUND=true
fi

ZRAM_ACTIVE=false
ZSWAP_ACTIVE=false
DISK_SWAP_ACTIVE=false

log_result "Check zram (Bazzite default swap backend)"
if command -v zramctl >/dev/null 2>&1 && [ -n "$(zramctl --noheadings 2>/dev/null)" ]; then
    zramctl | tee -a "$LOG_FILE"
    ZRAM_ACTIVE=true
    # zram lives in the same GDDR6 pool the GPU allocates from on the BC-250.
    ZRAM_BYTES=$(zramctl --noheadings --bytes --output DISKSIZE 2>/dev/null | awk '{s+=$1} END {print s+0}')
    MEM_BYTES=$(awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo)
    if [ "${MEM_BYTES:-0}" -gt 0 ] && [ "${ZRAM_BYTES:-0}" -gt 0 ]; then
        ZRAM_PCT=$((ZRAM_BYTES * 100 / MEM_BYTES))
        log_result "INFO: zram is sized at $((ZRAM_BYTES / 1048576)) MiB, ${ZRAM_PCT}% of total memory."
        if [ "$ZRAM_PCT" -ge 50 ]; then
            log_result "WARNING: zram may claim up to ${ZRAM_PCT}% of the unified pool the GPU also allocates from."
            WARN_FOUND=true
        fi
    fi
else
    log_result "INFO: No zram device configured."
fi

log_result "Check zswap"
if [ -r /sys/module/zswap/parameters/enabled ]; then
    ZSWAP_EN=$(cat /sys/module/zswap/parameters/enabled 2>/dev/null)
    if [ "$ZSWAP_EN" = "Y" ] || [ "$ZSWAP_EN" = "1" ]; then
        ZSWAP_ACTIVE=true
        log_result "SUCCESS: zswap is enabled."
        for prm in max_pool_percent compressor zpool shrinker_enabled; do
            [ -r "/sys/module/zswap/parameters/$prm" ] && \
                log_result "INFO: zswap.$prm = $(cat "/sys/module/zswap/parameters/$prm" 2>/dev/null)"
        done
        [ -r /sys/kernel/debug/zswap/stored_pages ] && \
            log_result "INFO: zswap stored pages: $(cat /sys/kernel/debug/zswap/stored_pages 2>/dev/null)"
    else
        log_result "INFO: zswap is present but disabled."
    fi
else
    log_result "INFO: zswap is not available in this kernel."
fi

log_result "Check disk-backed swap"
if [ -n "$SWAP_TABLE" ]; then
    while read -r name type size used prio; do
        # zram devices are listed as type "partition"; they are RAM, not disk.
        case "$name" in /dev/zram*) continue ;; esac
        case "$type" in
            partition|file)
                DISK_SWAP_ACTIVE=true
                log_result "INFO: Disk swap $name ($type) $((size / 1048576)) MiB, priority $prio."
                # A Btrfs swapfile must be NOCOW and uncompressed or the kernel refuses it.
                if [ "$type" = "file" ] && [ -f "$name" ]; then
                    FSTYPE=$(findmnt -no FSTYPE -T "$name" 2>/dev/null)
                    log_result "INFO: $name lives on $FSTYPE."
                    if [ "$FSTYPE" = "btrfs" ] && command -v lsattr >/dev/null 2>&1; then
                        ATTRS=$(lsattr "$name" 2>/dev/null | awk '{print $1}')
                        case "$ATTRS" in
                            *C*) log_result "SUCCESS: The swapfile is NOCOW as Btrfs requires." ;;
                            *)   log_result "WARNING: The Btrfs swapfile does not look NOCOW (attrs '$ATTRS')."
                                 WARN_FOUND=true ;;
                        esac
                    fi
                fi
                ;;
        esac
    done <<<"$SWAP_TABLE"
fi
[ "$DISK_SWAP_ACTIVE" = false ] && log_result "INFO: No disk-backed swap is configured."

log_result "Evaluate the swap configuration"
if [ "$ZRAM_ACTIVE" = true ] && [ "$ZSWAP_ACTIVE" = true ]; then
    log_result "WARNING: zram AND zswap are both active. Compressing pages twice wastes CPU and memory."
    log_result "HINT: Pick one: zswap plus a disk swapfile (recommended), or zram alone."
    WARN_FOUND=true
elif [ "$ZSWAP_ACTIVE" = true ] && [ "$DISK_SWAP_ACTIVE" = false ]; then
    log_result "WARNING: zswap is enabled but there is no disk swap behind it, so it does nothing."
    log_result "HINT: zswap is a cache in front of real swap; add a swapfile."
    WARN_FOUND=true
elif [ "$ZSWAP_ACTIVE" = true ] && [ "$DISK_SWAP_ACTIVE" = true ]; then
    log_result "SUCCESS: zswap is backed by disk swap, which is the recommended layout for this board."
elif [ "$ZRAM_ACTIVE" = true ] && [ "$DISK_SWAP_ACTIVE" = true ]; then
    log_result "SUCCESS: zram has a disk swap backstop, so memory pressure will not go straight to OOM."
    log_result "HINT: zswap in front of the swapfile (zram disabled) is more stable for gaming and is the System score default."
    # The disk swap is only an emergency backstop if zram has the higher priority (used first).
    ZRAM_PRIO=$(awk 'NR > 1 && $1 ~ /zram/ {print $NF}' <<<"$SWAP_TABLE" | sort -n | head -1)
    DISK_PRIO=$(awk 'NR > 1 && $1 !~ /zram/ {print $NF}' <<<"$SWAP_TABLE" | sort -n | tail -1)
    if [ -n "$ZRAM_PRIO" ] && [ -n "$DISK_PRIO" ]; then
        if [ "$ZRAM_PRIO" -gt "$DISK_PRIO" ]; then
            log_result "SUCCESS: zram (priority $ZRAM_PRIO) is used before disk swap (priority $DISK_PRIO)."
        else
            log_result "WARNING: Disk swap (priority $DISK_PRIO) is not below zram (priority $ZRAM_PRIO), so the NVMe is used before zram."
            log_result "HINT: Give the swapfile a lower priority, e.g. pri=10 in its /etc/fstab line (zram defaults to 100)."
            WARN_FOUND=true
        fi
    fi
elif [ "$ZRAM_ACTIVE" = true ]; then
    log_result "WARNING: zram is the only swap. When it fills there is no overflow and the OOM killer runs."
    log_result "HINT: On the BC-250 that can present as a hard freeze. Use zswap with a disk swapfile instead."
    WARN_FOUND=true
fi

SWAPPINESS=$(sysctl -n vm.swappiness 2>/dev/null)
log_result "INFO: vm.swappiness = ${SWAPPINESS:-unknown}"
if [ "$ZRAM_ACTIVE" = true ] && [ "$DISK_SWAP_ACTIVE" = false ] && [ -n "$SWAPPINESS" ] && [ "$SWAPPINESS" -lt 100 ]; then
    log_result "INFO: A zram-only setup usually wants a higher swappiness (150-180); swapping to RAM is cheap."
elif [ "$DISK_SWAP_ACTIVE" = true ] && [ -n "$SWAPPINESS" ] && [ "$SWAPPINESS" -gt 100 ]; then
    log_result "WARNING: swappiness ${SWAPPINESS} is tuned for zram-only but this system swaps to disk."
    log_result "HINT: Around 60 avoids unnecessary NVMe writes."
    WARN_FOUND=true
fi
echo

fi  # TEST 14
if want 15; then
log_result "[TEST 15] Boot Logs Test"
log_result "Check boot logs for warnings or errors from the current boot"
JOURNAL_OUTPUT=$(journalctl -b -p err --no-pager 2>/dev/null)
FILTERED_OUTPUT=$(filter_logs "$JOURNAL_OUTPUT")
if echo "$FILTERED_OUTPUT" | grep -iE "error|fail" >/dev/null 2>&1; then
    log_result "WARNING: Issues detected in boot logs. Displaying matching entries below:"
    echo "$FILTERED_OUTPUT" | grep -iE "error|fail" | tail -n 50 | tee -a "$LOG_FILE"
    explain_log_lines "$(grep -iE "error|fail" <<<"$FILTERED_OUTPUT")" "-b"
    WARN_FOUND=true
else
    log_result "SUCCESS: No issues detected in boot logs."
fi
echo

fi  # TEST 15
if want 16; then
log_result "[TEST 16] System Journal Test"
log_result "Check the journal for errors from the last 7 days (Fedora Atomic has no /var/log/syslog)"
if [ ! -d /var/log/journal ]; then
    log_result "WARNING: Persistent journal storage (/var/log/journal) is not enabled."
    WARN_FOUND=true
fi
RAW_JOURNAL_WARNINGS=$(journalctl --since "7 days ago" -p warning --no-pager 2>/dev/null)
JOURNAL_WARNINGS=$(filter_logs "$RAW_JOURNAL_WARNINGS" | grep -iE "warning|error|fail")
if [ -n "$JOURNAL_WARNINGS" ]; then
    log_result "WARNING: Warnings or errors found in the system journal (last 50):"
    echo "$JOURNAL_WARNINGS" | tail -n 50 | while read -r line; do
        log_result "$line"
    done
    explain_log_lines "$JOURNAL_WARNINGS" "--since '7 days ago'"
    WARN_FOUND=true
else
    log_result "SUCCESS: No issues detected in the system journal."
fi
echo

fi  # TEST 16
if want 17; then
log_result "[TEST 17] amdgpu Driver Test"
log_result "Verify the amdgpu kernel driver bound to the Cyan Skillfish APU"
if lsmod | grep -q "^amdgpu"; then
    log_result "SUCCESS: amdgpu module is loaded."
else
    log_result "ERROR: amdgpu module is NOT loaded."
    ERROR_FOUND=true
fi
lspci -nnk | grep -A3 -iE "VGA|Display" | tee -a "$LOG_FILE"
AMDGPU_ERRS=$(filter_logs "$(journalctl -b -k --no-pager 2>/dev/null | grep -iE 'amdgpu|drm' | grep -iE 'error|fail')")
if [ -n "$AMDGPU_ERRS" ]; then
    log_result "WARNING: amdgpu/drm errors in the kernel log (last 20):"
    echo "$AMDGPU_ERRS" | tail -20 | tee -a "$LOG_FILE"
    explain_log_lines "$AMDGPU_ERRS" "-b -k"
    WARN_FOUND=true
else
    log_result "SUCCESS: No amdgpu/drm errors in the kernel log."
fi
echo

fi  # TEST 17
if want 18; then
log_result "[TEST 18] GPU Governor Test (SMU / Oberon)"
log_result "The BC-250 GPU is locked at 1500MHz without a governor"
if [ -z "$GOV_FOUND" ]; then
    log_result "ERROR: No BC-250 GPU governor installed (looked for: ${GOVERNORS[*]})."
    log_result "HINT: sudo dnf copr enable filippor/bazzite && rpm-ostree install cyan-skillfish-governor-smu"
    ERROR_FOUND=true
else
    log_result "INFO: Governor found: $GOV_FOUND"
    if [ "$GOV_FOUND" = "oberon-governor" ]; then
        log_result "WARNING: oberon-governor is legacy. Migrate to cyan-skillfish-governor-smu."
        WARN_FOUND=true
    fi
    check_service "${GOV_FOUND}.service"
    GOV_SVC_RC=$?
    if [ "$GOV_SVC_RC" -eq 1 ]; then
        log_result "INFO: Service state details:"
        systemctl show "${GOV_FOUND}.service" \
            -p UnitFileState,ActiveState,SubState,Result,ExecMainStatus,ExecMainCode,ConditionResult,LoadError \
            --no-pager 2>/dev/null | tee -a "$LOG_FILE"
        systemctl status "${GOV_FOUND}.service" --no-pager -l 2>/dev/null | tail -15 | tee -a "$LOG_FILE"
        if [ "$(systemctl show "${GOV_FOUND}.service" -p ConditionResult --value 2>/dev/null)" = "no" ]; then
            log_result "HINT: A start condition failed; the service never ran, so 'enable --now' has no effect."
            log_result "HINT: Check the Condition*= lines: systemctl cat ${GOV_FOUND}.service"
        elif [ "$(systemctl show "${GOV_FOUND}.service" -p UnitFileState --value 2>/dev/null)" != "enabled" ]; then
            log_result "HINT: The service is not enabled: sudo systemctl enable --now ${GOV_FOUND}"
        else
            log_result "HINT: The service is enabled but failed; see the status output above and:"
            log_result "HINT: journalctl -u ${GOV_FOUND}.service -b --no-pager"
        fi
    fi
    log_result "Recent governor log output:"
    journalctl -u "${GOV_FOUND}.service" -b --no-pager 2>/dev/null | tail -10 | tee -a "$LOG_FILE"
    for cfg in "/etc/cyan-skillfish-governor-smu/config.toml" \
               "/etc/cyan-skillfish-governor-tt/config.toml" \
               "/etc/oberon-config.yaml"; do
        if [ -f "$cfg" ]; then
            log_result "INFO: Governor config $cfg:"
            cat "$cfg" | tee -a "$LOG_FILE"
        fi
    done
fi
echo

fi  # TEST 18
if want 19; then
log_result "[TEST 19] GPU Frequency Scaling Test"
log_result "Check that the GPU actually scales (pp_dpm_sclk / pp_dpm_mclk)"
if [ -n "$GPU_DEV" ]; then
    log_result "INFO: Using GPU sysfs node: $GPU_DEV"
    log_result "INFO: GPU core clock states (pp_dpm_sclk):"
    cat "$GPU_DEV/pp_dpm_sclk" | tee -a "$LOG_FILE"
    if [ -r "$GPU_DEV/pp_dpm_mclk" ]; then
        log_result "INFO: GPU memory clock states (pp_dpm_mclk):"
        cat "$GPU_DEV/pp_dpm_mclk" | tee -a "$LOG_FILE"
    fi
    CUR_SCLK=$(grep '\*' "$GPU_DEV/pp_dpm_sclk" | grep -oE '[0-9]+Mhz' | head -1 | tr -d 'Mhz')
    if [ -n "$CUR_SCLK" ]; then
        log_result "INFO: Current GPU clock: ${CUR_SCLK}MHz"
        if [ "$CUR_SCLK" = "1500" ] && [ -z "$GOV_FOUND" ]; then
            log_result "WARNING: GPU pinned at 1500MHz, which is the no-governor default."
            WARN_FOUND=true
        fi
    fi
    if [ -r "$GPU_DEV/power_dpm_force_performance_level" ]; then
        log_result "INFO: Performance level: $(cat "$GPU_DEV/power_dpm_force_performance_level")"
    fi
else
    log_result "ERROR: No amdgpu pp_dpm_sclk node found. GPU power management is unavailable."
    ERROR_FOUND=true
fi
echo

fi  # TEST 19
if want 20; then
log_result "[TEST 20] Vulkan / Mesa Test"
log_result "Verify RADV sees GFX1013 and not llvmpipe"
if command -v vulkaninfo >/dev/null 2>&1; then
    VK_DEVICE=$(vulkaninfo --summary 2>/dev/null | grep -i "deviceName" | head -3)
    log_result "INFO: Vulkan devices:\n$VK_DEVICE"
    if grep -qi "GFX1013" <<<"$VK_DEVICE"; then
        log_result "SUCCESS: RADV GFX1013 detected."
    elif grep -qi "llvmpipe" <<<"$VK_DEVICE"; then
        log_result "ERROR: Vulkan is falling back to llvmpipe (software rendering)."
        ERROR_FOUND=true
    else
        log_result "WARNING: Unexpected Vulkan device. Verify GPU driver."
        WARN_FOUND=true
    fi
else
    log_result "INFO: vulkaninfo not installed (vulkan-tools)."
fi
if command -v glxinfo >/dev/null 2>&1; then
    glxinfo -B 2>/dev/null | grep -iE "OpenGL renderer|OpenGL version" | tee -a "$LOG_FILE"
fi
log_result "INFO: Mesa packages:"
rpm -qa 2>/dev/null | grep -i "^mesa" | sort | tee -a "$LOG_FILE"
echo

fi  # TEST 20
# A runtime CU unlock writes the WGP masks after the driver has probed. The kernel keeps its probe-time
# topology (active_cu_number; RADV reads the same snapshot), so it never sees the change. The live value
# is in the GPU registers, which umr reads (read-only, needs root). Per shader array (4 rows, 5 WGPs of
# 2 CUs): SPI_PG_ENABLE_STATIC_WGP_MASK = WGPs that get work, CC_GC_SHADER_ARRAY_CONFIG bits 16-20 =
# WGPs marked inactive. A WGP is active when its SPI bit is set and its CC bit is clear.
# Defined outside test 21 so that test 42 can read the live count when test 21 did not run.
CU_UMR=""
for p in /usr/bin/umr /usr/sbin/umr /usr/local/bin/umr; do [ -x "$p" ] && { CU_UMR=$p; break; }; done

# read_live_cus: sets CU_LIVE (active CUs), CU_ARRAYS (CUs per shader array) and CU_ROWS (per-array text)
# from the WGP mask registers; false, with CU_LIVE empty, when umr cannot read them. The caller checks first
# that it runs as root and that $CU_UMR is set and root_safe.
read_live_cus() {
    CU_ASIC="cyan_skillfish.gfx1013"
    CU_UMR_I=()
    CU_BDF=$(lspci -Dn -d 1002:13fe 2>/dev/null | awk 'NR==1{print $1}')
    CU_INST=$(grep -l -s -F "${CU_BDF:-none}" /sys/kernel/debug/dri/[0-9]*/name 2>/dev/null | head -1 | awk -F/ '{print $(NF-1)}')
    [[ "$CU_INST" =~ ^[0-9]+$ ]] && CU_UMR_I=(-i "$CU_INST")
    cu_reg() { # cu_reg REGISTER SE SH: the register's value for one shader array
        "$CU_UMR" "${CU_UMR_I[@]}" -r "$CU_ASIC.$1" -b "$2" "$3" 0xffffffff 2>/dev/null \
            | awk '{for (i = NF; i >= 1; i--) if ($i ~ /^0x[0-9a-fA-F]+$/) {print $i; exit}}'
    }
    CU_LIVE=0 CU_ROWS="" CU_ARRAYS=()
    for r in 0 1 2 3; do
        spi=$(cu_reg mmSPI_PG_ENABLE_STATIC_WGP_MASK $((r / 2)) $((r % 2)))
        [ -n "$spi" ] || { CU_LIVE=""; break; }
        cc=$(cu_reg mmCC_GC_SHADER_ARRAY_CONFIG $((r / 2)) $((r % 2)))
        act=$(( spi & ~(${cc:-0} >> 16) & 31 ))
        n=0; for b in 0 1 2 3 4; do (( act >> b & 1 )) && n=$((n + 2)); done
        CU_LIVE=$((CU_LIVE + n))
        CU_ARRAYS+=("$n")
        CU_ROWS+="SE$((r / 2)).SH$((r % 2)) $(printf '0x%02x' "$act") = $n, "
    done
    [ -n "$CU_LIVE" ]
}

if want 21; then
log_result "[TEST 21] Compute Unit (CU) Count Test"
log_result "BC-250 ships with 24 of 40 RDNA2 CUs active; the 40CU unlock re-enables the rest"
CU_COUNT=""
CU_SOURCE=""
CU_LIVE=""

if [ "$(id -u)" != 0 ]; then
    log_howto "INFO: Live CU masks not read: reading the GPU registers needs root (sudo)." \
              "INFO: Live CU masks not read: this needs admin privileges (Settings › Privacy)."
elif [ -z "$CU_UMR" ]; then
    log_result "INFO: umr is not installed, so the live CU masks can't be read."
    log_result "HINT: sudo rpm-ostree install umr (then reboot) to see a CU unlock made at runtime."
elif ! root_safe "$CU_UMR"; then
    log_result "WARNING: $CU_UMR is not owned by root or is writable by others; not running it as root."
    WARN_FOUND=true
else
    if read_live_cus; then
        CU_COUNT="$CU_LIVE"
        CU_SOURCE="GPU registers (live WGP masks via umr)"
        log_result "INFO: Live WGP masks per shader array: ${CU_ROWS%, } CUs."
        CU_MIN=$(printf '%s\n' "${CU_ARRAYS[@]}" | sort -n | head -1)
        CU_MAX=$(printf '%s\n' "${CU_ARRAYS[@]}" | sort -n | tail -1)
        if [ "$CU_MIN" != "$CU_MAX" ]; then
            log_result "WARNING: CUs are not evenly distributed over the shader arrays (${CU_ARRAYS[*]} CUs per array)."
            log_result "HINT: The slowest shader array sets the pace; this behaves like $((CU_MIN * 4)) CUs. Redo the CU unlock so every array has the same count."
            WARN_FOUND=true
        fi
    else
        CU_LIVE=""
        log_result "WARNING: umr could not read the WGP mask registers."
        WARN_FOUND=true
    fi
fi

# The kernel log reflects the state at driver probe, not any later live change.
CU_KERNEL=$(journalctl -b -k --no-pager 2>/dev/null | grep -oE "active_cu_number [0-9]+" | tail -1 | grep -oE "[0-9]+")
if [ -n "$CU_KERNEL" ]; then
    log_result "INFO: Kernel reported $CU_KERNEL CUs at driver probe (active_cu_number)."
    journalctl -b -k --no-pager 2>/dev/null | grep -E "active_cu_number|bc250-40cu" | tail -6 | tee -a "$LOG_FILE"
    if [ -z "$CU_COUNT" ]; then
        CU_COUNT="$CU_KERNEL"
        CU_SOURCE="kernel log (active_cu_number, probe-time value)"
    elif [ "$CU_KERNEL" != "$CU_COUNT" ]; then
        log_result "INFO: Probe value $CU_KERNEL differs from the live value $CU_COUNT. This is expected:"
        log_result "INFO: amdgpu snapshots the CU topology at driver probe, and a runtime unlock changes the"
        log_result "INFO: WGP masks after that, so the kernel value never updates. The live registers show"
        log_result "INFO: the CUs that actually get work."
    fi
fi

# Cross-check via RADV.
if command -v vulkaninfo >/dev/null 2>&1; then
    CU_RADV=$(RADV_DEBUG=info vulkaninfo --summary 2>/dev/null | grep -oE "num_cu = [0-9]+" | head -1 | grep -oE "[0-9]+")
    if [ -n "$CU_RADV" ]; then
        log_result "INFO: RADV reports num_cu = $CU_RADV"
        if [ -z "$CU_COUNT" ]; then
            CU_COUNT="$CU_RADV"
            CU_SOURCE="RADV (num_cu)"
        elif [ "$CU_RADV" != "$CU_COUNT" ]; then
            log_result "INFO: RADV sees $CU_RADV while $CU_COUNT CUs are active. This is expected and harmless:"
            log_result "INFO: RADV queries the kernel's probe-time CU snapshot, which the runtime WGP unlock"
            log_result "INFO: does not update. Shaders still dispatch across all $CU_COUNT active CUs; only the"
            log_result "INFO: reported number is stale. It stays $CU_RADV until amdgpu itself probes more CUs."
        fi
    fi
fi

# Last resort: ROCm / OpenCL.
if [ -z "$CU_COUNT" ] && command -v rocminfo >/dev/null 2>&1; then
    CU_COUNT=$(rocminfo 2>/dev/null | grep -A20 "gfx1013" | grep -oE "Compute Unit: *[0-9]+" | head -1 | grep -oE "[0-9]+")
    [ -n "$CU_COUNT" ] && CU_SOURCE="rocminfo"
fi
if [ -z "$CU_COUNT" ] && command -v clinfo >/dev/null 2>&1; then
    CU_COUNT=$(clinfo 2>/dev/null | grep -iE "Max compute units" | grep -oE "[0-9]+" | head -1)
    [ -n "$CU_COUNT" ] && CU_SOURCE="clinfo"
fi

if [ -z "$CU_COUNT" ]; then
    log_result "WARNING: Could not determine the active CU count."
    log_result "HINT: sudo dmesg | grep active_cu_number  (or install vulkan-tools for RADV_DEBUG=info vulkaninfo)"
    WARN_FOUND=true
else
    log_result "INFO: Active Compute Units: $CU_COUNT of 40 (source: $CU_SOURCE)"
    if [ "$CU_COUNT" -eq 40 ]; then
        log_result "SUCCESS: All 40 CUs are unlocked."
        log_result "REMINDER: 40 CU at 2GHz throttles on stock cooling. Cap the governor at 1500MHz."
    elif [ "$CU_COUNT" -eq 24 ]; then
        log_result "SUCCESS: 24 CUs active (stock BC-250 configuration, not unlocked)."
        if [ -z "$CU_LIVE" ]; then
            log_result "NOTE: This is the driver's probe-time value. A CU unlock made at runtime changes"
            log_result "NOTE: the WGP masks after the driver probes, so the kernel and RADV keep reporting 24."
            log_howto "HINT: Run this script as root with umr installed to read the live masks." \
                      "HINT: Run the tests with admin privileges (Settings › Privacy) and umr installed to read the live masks."
        fi
    elif [ "$CU_COUNT" -gt 24 ] && [ "$CU_COUNT" -lt 40 ]; then
        log_result "SUCCESS: $CU_COUNT CUs active: a partial CU unlock."
        log_result "INFO: Partial unlocks are normal; WGPs that fail routing or stability are left"
        log_result "INFO: masked, and fewer CUs also means less heat on stock cooling."
    elif [ "$CU_COUNT" -lt 24 ]; then
        log_result "ERROR: Only $CU_COUNT CUs active, below the stock 24. CUs may be masked or failing."
        ERROR_FOUND=true
    else
        log_result "WARNING: Unexpected CU count $CU_COUNT (expected 24-40)."
        WARN_FOUND=true
    fi
fi

# Report the unlock module parameter when the patched amdgpu is installed.
if [ -r /sys/module/amdgpu/parameters/bc250_cc_write_mode ]; then
    log_result "INFO: Patched amdgpu present, bc250_cc_write_mode = $(cat /sys/module/amdgpu/parameters/bc250_cc_write_mode)"
else
    log_result "INFO: Stock amdgpu module (no bc250_cc_write_mode parameter)."
fi
if [ -f /etc/modprobe.d/bc250-40cu.conf ]; then
    log_result "INFO: /etc/modprobe.d/bc250-40cu.conf:"
    cat /etc/modprobe.d/bc250-40cu.conf | tee -a "$LOG_FILE"
fi
echo

fi  # TEST 21
if want 22; then
log_result "[TEST 22] Hardware Sensors Test"
log_result "Check nct6683/nct6687 SuperIO sensors, GPU and CPU temperatures"
if lsmod | grep -qE "nct668[37]"; then
    log_result "SUCCESS: Nuvoton NCT6686D sensor module is loaded."
else
    log_result "WARNING: nct6683/nct6687 not loaded, board sensors will be missing."
    log_result "HINT: echo 'options nct6683 force=true' | sudo tee /etc/modprobe.d/sensors.conf"
    WARN_FOUND=true
fi
if lsmod | grep -q "^k10temp"; then
    log_result "SUCCESS: k10temp (CPU temperature) is loaded."
else
    log_result "WARNING: k10temp is not loaded, CPU temperature unavailable."
    WARN_FOUND=true
fi
if command -v sensors >/dev/null 2>&1; then
    sensors 2>&1 | tee -a "$LOG_FILE"
else
    log_result "INFO: lm_sensors not installed."
fi
log_result "Check GPU hwmon readings"
for hw in "$GPU_DEV"/hwmon/hwmon*; do
    [ -d "$hw" ] || continue
    if [ -r "$hw/temp1_input" ]; then
        GPU_TEMP=$(( $(cat "$hw/temp1_input") / 1000 ))
        log_result "INFO: GPU edge temp: ${GPU_TEMP}C"
        if [ "$GPU_TEMP" -ge 95 ]; then
            log_result "ERROR: GPU is at ${GPU_TEMP}C. Check cooling and lower the governor ceiling."
            ERROR_FOUND=true
        elif [ "$GPU_TEMP" -ge 85 ]; then
            log_result "WARNING: GPU is at ${GPU_TEMP}C, at or above the governor throttle point."
            WARN_FOUND=true
        fi
    fi
    [ -r "$hw/power1_average" ] && log_result "INFO: GPU average power: $(( $(cat "$hw/power1_average") / 1000000 ))W"
    [ -r "$hw/in0_input" ] && log_result "INFO: GPU voltage: $(cat "$hw/in0_input")mV"
    [ -r "$hw/fan1_input" ] && log_result "INFO: GPU fan: $(cat "$hw/fan1_input") RPM"
done

log_result "Check CPU temperature (k10temp Tctl)"
for h in /sys/class/hwmon/hwmon*; do
    if [ "$(cat "$h/name" 2>/dev/null)" = "k10temp" ] && [ -r "$h/temp1_input" ]; then
        CPU_TEMP=$(( $(cat "$h/temp1_input") / 1000 ))
        log_result "INFO: CPU Tctl: ${CPU_TEMP}C"
        if [ "$CPU_TEMP" -ge 95 ]; then
            log_result "ERROR: CPU is at ${CPU_TEMP}C, at or near TJmax."
            ERROR_FOUND=true
        elif [ "$CPU_TEMP" -ge 85 ]; then
            log_result "WARNING: CPU is at ${CPU_TEMP}C."
            WARN_FOUND=true
        fi
        break
    fi
done

log_result "Check that at least one chassis fan is spinning"
FAN_MAX=0
for f in /sys/class/hwmon/hwmon*/fan?_input; do
    [ -r "$f" ] || continue
    RPM=$(cat "$f" 2>/dev/null)
    [ -n "$RPM" ] && [ "$RPM" -gt "$FAN_MAX" ] && FAN_MAX="$RPM"
done
if [ "$FAN_MAX" -gt 0 ]; then
    log_result "SUCCESS: Highest fan reading is ${FAN_MAX} RPM."
    log_result "NOTE: On the BC-250 the main fan usually reports on the 'Pump Fan' header; a 0 RPM 'CPU Fan' is normal."
else
    log_result "ERROR: No fan is reporting any RPM. Verify cooling before applying load."
    ERROR_FOUND=true
fi
log_result "NOTE: The read-only nct6683 driver reports most voltage rails as 0.00V on this board. That is a driver limitation, not a fault."
echo

fi  # TEST 22
if want 23; then
log_result "[TEST 23] IOMMU Disabled Test"
log_result "IOMMU is broken on the BC-250 and MUST be disabled — in the BIOS or via the amd_iommu=off kernel arg"
# Authoritative: with the IOMMU off (BIOS toggle or amd_iommu=off) the kernel creates no IOMMU groups.
IOMMU_GROUPS=$(find /sys/kernel/iommu_groups -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
IOMMU_EVIDENCE=$(journalctl -b -k --no-pager 2>/dev/null \
    | grep -iE "AMD-Vi: (Interrupt remapping enabled|Virtual APIC enabled)|iommu: Default domain type:|AMD-Vi: Found IOMMU")
if [ "${IOMMU_GROUPS:-0}" -gt 0 ]; then
    log_result "ERROR: IOMMU is ENABLED ($IOMMU_GROUPS IOMMU groups). Disable it in the BIOS or run: rpm-ostree kargs --append=amd_iommu=off"
    ERROR_FOUND=true
else
    log_result "SUCCESS: IOMMU is not active (no IOMMU groups)."
fi
if [ -n "$IOMMU_EVIDENCE" ]; then
    log_result "INFO: IOMMU-related kernel messages:"
    echo "$IOMMU_EVIDENCE" | tail -5 | tee -a "$LOG_FILE"
fi
log_result "INFO: Kernel command line: $(cat /proc/cmdline)"
if command -v rpm-ostree >/dev/null 2>&1; then
    log_result "INFO: rpm-ostree kargs: $(rpm-ostree kargs 2>/dev/null)"
fi
echo

fi  # TEST 23
if want 24; then
log_result "[TEST 24] CPU Mitigations Test"
log_result "Mitigations must be OFF on the BC-250 gaming box (approx +18 FPS)"
MITIGATIONS_OFF=false
if grep -qw "mitigations=off" /proc/cmdline; then
    log_result "SUCCESS: 'mitigations=off' is present on the kernel command line."
    MITIGATIONS_OFF=true
else
    log_result "ERROR: 'mitigations=off' is NOT on the kernel command line."
    log_result "HINT: rpm-ostree kargs --append-if-missing=\"mitigations=off\" && systemctl reboot"
    ERROR_FOUND=true
fi
log_result "Cross-check /sys/devices/system/cpu/vulnerabilities"
VULN_DIR="/sys/devices/system/cpu/vulnerabilities"
if [ -d "$VULN_DIR" ]; then
    STILL_MITIGATED=""
    for v in "$VULN_DIR"/*; do
        [ -r "$v" ] || continue
        VAL=$(cat "$v")
        log_result "INFO: $(basename "$v"): $VAL"
        if grep -qiE "^Mitigation" <<<"$VAL"; then
            STILL_MITIGATED="$STILL_MITIGATED $(basename "$v")"
        fi
    done
    if [ -n "$STILL_MITIGATED" ]; then
        log_result "WARNING: Active mitigations remain for:$STILL_MITIGATED"
        [ "$MITIGATIONS_OFF" = true ] && log_result "INFO: Some mitigations cannot be disabled via mitigations=off."
        WARN_FOUND=true
    else
        log_result "SUCCESS: No active CPU mitigations reported."
    fi
else
    log_result "INFO: $VULN_DIR not available on this kernel."
fi
echo

fi  # TEST 24
if want 25; then
log_result "[TEST 25] CPU Core and Thread Count Test"
log_result "BC-250 ships down-cored to 6C/12T; the 8-core unlock enables the full 8C/16T die"
THREADS_ONLINE=$(nproc 2>/dev/null)
THREADS_TOTAL=$(nproc --all 2>/dev/null)
PHYS_CORES=""
if command -v lscpu >/dev/null 2>&1; then
    CORES_PER_SOCKET=$(lscpu 2>/dev/null | awk -F: '/^Core\(s\) per socket/{gsub(/ /,"",$2); print $2}')
    SOCKETS=$(lscpu 2>/dev/null | awk -F: '/^Socket\(s\)/{gsub(/ /,"",$2); print $2}')
    if [ -n "$CORES_PER_SOCKET" ] && [ -n "$SOCKETS" ]; then
        PHYS_CORES=$(( CORES_PER_SOCKET * SOCKETS ))
    fi
    log_result "INFO: CPU topology:"
    lscpu 2>/dev/null | grep -E "^(Model name|Socket|Core\(s\)|Thread\(s\)|CPU\(s\)|NUMA node\(s\))" | tee -a "$LOG_FILE"
fi
if [ -z "$PHYS_CORES" ]; then
    PHYS_CORES=$(awk -F: '/^physical id/{p=$2} /^core id/{print p"-"$2}' /proc/cpuinfo 2>/dev/null | sort -u | wc -l | tr -d ' ')
fi
log_result "INFO: Physical cores: ${PHYS_CORES:-unknown}, online threads: ${THREADS_ONLINE:-unknown} (total: ${THREADS_TOTAL:-unknown})"

OFFLINE_CPUS=$(cat /sys/devices/system/cpu/offline 2>/dev/null)
if [ -n "$OFFLINE_CPUS" ]; then
    log_result "WARNING: CPUs currently offline: $OFFLINE_CPUS"
    WARN_FOUND=true
fi

if [ -z "$PHYS_CORES" ] || [ "$PHYS_CORES" -eq 0 ] 2>/dev/null; then
    log_result "WARNING: Could not determine the physical core count."
    WARN_FOUND=true
else
    case "$PHYS_CORES" in
        8)
            log_result "SUCCESS: 8 cores active. The 8-core unlock is applied (full die)."
            log_result "REMINDER: The Linux unlock is cleared by a cold boot and must be re-applied."
            log_result "REMINDER: Known side effect of the core unlock: pp_dpm_sclk and hwmon freq1_input report nonsense values."
            ;;
        6)
            log_result "SUCCESS: 6 cores active (stock BC-250 down-cored configuration)."
            ;;
        7)
            log_result "INFO: 7 cores active: partial unlock, or one core is offline/masked."
            ;;
        *)
            if [ "$PHYS_CORES" -lt 6 ]; then
                log_result "ERROR: Only $PHYS_CORES cores active, below the stock 6."
                ERROR_FOUND=true
            else
                log_result "WARNING: Unexpected core count $PHYS_CORES (expected 6 or 8)."
                WARN_FOUND=true
            fi
            ;;
    esac
fi

if [ -n "$PHYS_CORES" ] && [ -n "$THREADS_ONLINE" ]; then
    EXPECTED_THREADS=$(( PHYS_CORES * 2 ))
    if [ "$THREADS_ONLINE" -eq "$EXPECTED_THREADS" ]; then
        log_result "SUCCESS: SMT is enabled ($THREADS_ONLINE threads for $PHYS_CORES cores)."
    else
        log_result "WARNING: Expected $EXPECTED_THREADS threads for $PHYS_CORES cores but found $THREADS_ONLINE. SMT may be disabled."
        WARN_FOUND=true
    fi
fi
if [ -r /sys/devices/system/cpu/smt/control ]; then
    log_result "INFO: SMT control: $(cat /sys/devices/system/cpu/smt/control)"
fi

log_result "Check for machine-check events on the CPU cores"
# "MCE: In-kernel MCE decoding enabled." is an informational banner, not an event.
MCE_LOG=$(journalctl -b -k --no-pager 2>/dev/null \
    | grep -iE "mce: \[Hardware Error\]|Machine check events logged|mce: CPU[0-9]+: Machine Check|Uncorrected hardware memory error" )
if [ -n "$MCE_LOG" ]; then
    log_result "ERROR: Machine-check events detected. A CPU core may be unstable:"
    echo "$MCE_LOG" | tail -10 | tee -a "$LOG_FILE"
    ERROR_FOUND=true
else
    log_result "SUCCESS: No machine-check events in the kernel log."
fi
echo

fi  # TEST 25
if want 26; then
log_result "[TEST 26] CPU Power Management Test (ACPI fix)"
log_result "Without the ACPI fix the BC-250 has no C-states or frequency scaling"
if [ -d /sys/devices/system/cpu/cpu0/cpufreq ]; then
    log_result "SUCCESS: cpufreq scaling is available."
    log_result "INFO: Driver: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver 2>/dev/null)"
    log_result "INFO: Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
else
    log_result "WARNING: No cpufreq scaling. Apply the BC-250 ACPI fix (rpm-ostree variant)."
    WARN_FOUND=true
fi
# Report where the ACPI tables came from: initrd override (bc250-acpi-fix) or a
# (possibly modded) BIOS. Helps distinguish "fix not applied" from "fix failed".
ACPI_UPGRADE=$(journalctl -b -k --no-pager -q 2>/dev/null | grep -iE "ACPI: Table Upgrade|ACPI:.*SSDT.*\(bootloader\)" | head -4)
if [ -n "$ACPI_UPGRADE" ]; then
    log_result "INFO: ACPI table override loaded from initrd (bc250-acpi-fix):"
    echo "$ACPI_UPGRADE" | tee -a "$LOG_FILE"
else
    log_result "INFO: No initrd ACPI table override detected; ACPI tables come from the BIOS."
fi
if [ -d /sys/devices/system/cpu/cpu0/cpuidle ]; then
    log_result "SUCCESS: CPU idle states are available."
    for st in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
        [ -r "$st/name" ] && log_result "INFO: C-state $(cat "$st/name") usage=$(cat "$st/usage" 2>/dev/null)"
    done
else
    log_result "WARNING: No CPU idle states exposed. Apply the BC-250 ACPI fix."
    WARN_FOUND=true
fi
log_result "INFO: CPU model: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs)"
echo

fi  # TEST 26
if want 46; then
log_result "[TEST 46] CPU Voltage Test"
log_result "Report the CPU/SoC voltage rails and the per-core requested voltage (P-state VID)"
# Rails first: on this APU the amdgpu hwmon exposes vddgfx (GPU) and vddnb (SoC/northbridge,
# the CPU side of the package). zenpower (out-of-tree) would add vcore/vsoc if installed.
RAILS_FOUND=false
for h in /sys/class/hwmon/hwmon*; do
    HW_NAME=$(cat "$h/name" 2>/dev/null)
    case "$HW_NAME" in amdgpu|zenpower|k10temp) ;; *) continue ;; esac
    for v in "$h"/in*_input; do
        [ -r "$v" ] || continue
        V_LABEL=$(cat "${v%_input}_label" 2>/dev/null)
        V_MV=$(cat "$v" 2>/dev/null)
        [[ "$V_MV" =~ ^[0-9]+$ ]] || continue
        log_result "INFO: $HW_NAME ${V_LABEL:-$(basename "${v%_input}")}: ${V_MV} mV"
        RAILS_FOUND=true
        if [ "$V_MV" -gt 1450 ]; then
            log_result "WARNING: ${V_LABEL:-$(basename "${v%_input}")} reads above 1.45 V — unusually high for this APU."
            WARN_FOUND=true
        fi
    done
done
[ "$RAILS_FOUND" = true ] || log_result "INFO: No voltage rails found in hwmon (amdgpu/zenpower)."
log_result "NOTE: k10temp no longer reports Vcore/Vsoc on modern kernels, and the read-only nct6683"
log_result "NOTE: shows most board rails as 0.00V, so the amdgpu rails above are the usable readings."

log_result "Check the voltage each core requests (current P-state VID via MSR)"
modprobe msr 2>/dev/null
# read_msr <cpu> <reg>: 64-bit MSR value as hex, empty on failure.
read_msr() { dd if=/dev/cpu/"$1"/msr bs=8 count=1 skip="$2" iflag=skip_bytes 2>/dev/null | od -An -tx8 | tr -d ' \n'; }
if [ -r /dev/cpu/0/msr ] && [ -n "$(read_msr 0 $((0xC0010063)))" ]; then
    MAX_REQ_MV=0
    declare -A VID_SEEN_CORE=()
    for CPUDIR in /sys/devices/system/cpu/cpu[0-9]*; do
        CPU=${CPUDIR##*/cpu}
        CORE=$(cat "$CPUDIR/topology/core_id" 2>/dev/null) || continue
        [ -n "${VID_SEEN_CORE[$CORE]:-}" ] && continue   # one SMT thread per core is enough
        VID_SEEN_CORE[$CORE]=1
        PS_HEX=$(read_msr "$CPU" $((0xC0010063)))
        [ -n "$PS_HEX" ] || continue
        PS_IDX=$(( 16#$PS_HEX & 0x7 ))
        DEF_HEX=$(read_msr "$CPU" $(( 0xC0010064 + PS_IDX )))
        [ -n "$DEF_HEX" ] || continue
        PS_DEF=$(( 16#$DEF_HEX ))
        CPU_VID=$(( (PS_DEF >> 14) & 0xFF ))
        CPU_FID=$(( PS_DEF & 0xFF ))
        CPU_DID=$(( (PS_DEF >> 8) & 0x3F ))
        CORE_MHZ=0; [ "$CPU_DID" -gt 0 ] && CORE_MHZ=$(( CPU_FID * 200 / CPU_DID ))
        if [ "$CPU_VID" -eq 0 ]; then
            log_result "INFO: core $CORE (cpu$CPU): P$PS_IDX, no VID request (idle)"
            continue
        fi
        # Zen 2 SVI2: V = 1.55 V - VID * 6.25 mV
        REQ_MV=$(awk -v v="$CPU_VID" 'BEGIN{printf "%.0f", 1550 - v * 6.25}')
        [ "$REQ_MV" -gt "$MAX_REQ_MV" ] && MAX_REQ_MV=$REQ_MV
        log_result "INFO: core $CORE (cpu$CPU): P$PS_IDX, VID $CPU_VID = ${REQ_MV} mV (~${CORE_MHZ} MHz)"
    done
    unset VID_SEEN_CORE
    if [ "$MAX_REQ_MV" -gt 0 ]; then
        if [ "$MAX_REQ_MV" -gt 1450 ]; then
            log_result "WARNING: Highest core request is ${MAX_REQ_MV} mV — above the usual Zen 2 range."
            WARN_FOUND=true
        else
            log_result "SUCCESS: Highest core request is ${MAX_REQ_MV} mV, within the usual Zen 2 range."
        fi
    else
        log_result "INFO: All cores were idle during the read; rerun under load for the boost voltage."
    fi
    log_result "NOTE: All Zen 2 cores share one VDDCR_CPU rail — the rail follows the highest request,"
    log_result "NOTE: so these are per-core requests, not separate supplies. Values move with load;"
    log_result "NOTE: an idle core parked in a low P-state reporting ~700-900 mV is normal."
else
    log_result "INFO: Cannot read MSRs (/dev/cpu/*/msr); per-core VID skipped."
    log_result "HINT: The msr module could not be loaded, or kernel lockdown (secure boot) blocks MSR access."
fi
echo

fi  # TEST 46
if want 27; then
log_result "[TEST 27] Handheld Daemon Test"
log_result "hhd is not supported on BC-250 and causes constant micro-stuttering"
check_masked "hhd.service" "BC-250 has no handheld controls"
echo

fi  # TEST 27
if want 28; then
log_result "[TEST 28] Suspend Targets Test"
log_result "Resume from s2idle is broken on BC-250, suspend targets should be masked"
for tgt in sleep.target suspend.target hibernate.target hybrid-sleep.target; do
    check_masked "$tgt" "s2idle resume is broken on BC-250"
done
echo

fi  # TEST 28
if want 29; then
log_result "[TEST 29] Display Session Test"
log_result "Check display manager and graphical session"
if systemctl cat display-manager.service >/dev/null 2>&1; then
    DM_UNIT=$(basename "$(readlink -f /etc/systemd/system/display-manager.service 2>/dev/null)" 2>/dev/null)
    log_result "INFO: display-manager.service -> ${DM_UNIT:-unknown}, state: $(systemctl is-active display-manager.service 2>/dev/null)"
else
    log_result "INFO: No display-manager.service (Deck/Game Mode images use an autologin session instead)."
fi
for dm in sddm.service gdm.service greetd.service; do
    if systemctl cat "$dm" >/dev/null 2>&1; then
        log_result "INFO: $dm is $(systemctl is-active "$dm" 2>/dev/null) / $(systemctl is-enabled "$dm" 2>/dev/null)."
    fi
done
log_result "INFO: Graphical target: $(systemctl get-default 2>/dev/null), reached: $(systemctl is-active graphical.target 2>/dev/null)"
if systemctl --all --no-legend list-units 'gamescope-session*' 2>/dev/null | grep -q gamescope; then
    log_result "INFO: Gamescope (Deck UI) session units present:"
    systemctl --all --no-legend --no-pager list-units 'gamescope-session*' | tee -a "$LOG_FILE"
fi
if [ -n "$(ls /sys/class/drm/card*/status 2>/dev/null)" ]; then
    log_result "INFO: Connector status:"
    for c in /sys/class/drm/card*-*/status; do
        [ -r "$c" ] && log_result "  $(basename "$(dirname "$c")"): $(cat "$c")"
    done
fi
echo

fi  # TEST 29
if want 30; then
log_result "[TEST 30] SSH Service Test"
log_result "On Fedora/Bazzite the unit is sshd.service, not ssh.service. Bazzite ships it disabled."
if systemctl is-active --quiet sshd.service; then
    log_result "SUCCESS: sshd.service is active."
elif systemctl is-active --quiet sshd.socket; then
    log_result "SUCCESS: sshd.socket is active (socket-activated SSH)."
else
    log_result "INFO: SSH is not running. This is the Bazzite default; enable it only if you need remote access."
    log_result "NOTE: To enable remote access: sudo systemctl enable --now sshd"
fi
echo

fi  # TEST 30
if want 31; then
log_result "[TEST 31] File and Directory Integrity Test"
TEST_PATH="/var/log/"
log_result "Checking integrity of $TEST_PATH"
if [ -e "$TEST_PATH" ]; then
    find "$TEST_PATH" -maxdepth 1 -exec ls -ld {} + | tee -a "$LOG_FILE"
    log_result "SUCCESS: $TEST_PATH exists."
else
    log_result "ERROR: $TEST_PATH does not exist."
    ERROR_FOUND=true
fi
echo

fi  # TEST 31
if want 32; then
log_result "[TEST 32] OSTree Deployment Test"
log_result "Check rpm-ostree deployments and layered packages"
if command -v rpm-ostree >/dev/null 2>&1; then
    OSTREE_STATUS=$(rpm-ostree status 2>&1)
    echo "$OSTREE_STATUS" | tee -a "$LOG_FILE"
    if grep -q "LocalPackages\|InactiveBaseReplacements" <<<"$OSTREE_STATUS"; then
        log_result "INFO: Layered or local packages are present. These can block or slow updates."
    fi
    # The booted deployment is the one marked with a bullet. If it is not the first
    # entry, a newer deployment is already staged and only needs a reboot.
    BOOTED_INDEX=$(grep -nE "^●" <<<"$OSTREE_STATUS" | head -1 | cut -d: -f1)
    FIRST_INDEX=$(grep -nE "^[●[:space:]]+ostree-" <<<"$OSTREE_STATUS" | head -1 | cut -d: -f1)
    if [ -n "$BOOTED_INDEX" ] && [ -n "$FIRST_INDEX" ] && [ "$BOOTED_INDEX" -gt "$FIRST_INDEX" ]; then
        PENDING_VERSION=$(grep -E "Version:" <<<"$OSTREE_STATUS" | head -1 | xargs)
        log_result "WARNING: A newer deployment is staged and pending a reboot ($PENDING_VERSION)."
        log_result "HINT: systemctl reboot"
        WARN_FOUND=true
    else
        log_result "SUCCESS: The booted deployment is the newest one."
    fi
else
    log_result "ERROR: rpm-ostree not found. This is not a Fedora Atomic system."
    ERROR_FOUND=true
fi
echo

fi  # TEST 32
if want 33; then
log_result "[TEST 33] Update and Patch Test"
log_result "Check for available updates (read-only, nothing is installed)"
if command -v rpm-ostree >/dev/null 2>&1; then
    UPDATE_OUTPUT=$(rpm-ostree upgrade --check 2>&1)
    echo "$UPDATE_OUTPUT" | tee -a "$LOG_FILE"
    if grep -qi "No updates available" <<<"$UPDATE_OUTPUT"; then
        log_result "SUCCESS: System is up to date."
    else
        log_result "INFO: An update is available. Apply with: ujust update"
    fi
fi
for t in uupd.timer ublue-update.timer rpm-ostreed-automatic.timer; do
    if [ -n "$(systemctl list-unit-files --no-legend "$t" 2>/dev/null)" ]; then
        log_result "INFO: $t is $(systemctl is-enabled "$t" 2>/dev/null) / $(systemctl is-active "$t" 2>/dev/null)."
    fi
done
if command -v flatpak >/dev/null 2>&1; then
    log_result "INFO: Flatpak remotes:"
    flatpak remotes 2>&1 | tee -a "$LOG_FILE"
    log_result "INFO: Installed flatpaks: $(flatpak list --app --columns=application 2>/dev/null | wc -l)"
fi
echo

fi  # TEST 33

# ----------------------------------------------------------------------------
# Test 45: what is installed, counted per source. Only package names, versions and
# counts are reported: no paths, user names, container names or settings.
if want 45; then
log_result "[TEST 45] Installed Packages Test"
log_result "Count installed software per source (names and versions only, nothing personal)"
PKG_TOTAL=0
PKG_SOURCES=0
pkg_count() { # pkg_count LABEL COUNT [LIST]: one source line, LIST (one name per line) goes to the log only
    [ "${2:-0}" -gt 0 ] 2>/dev/null || return 0
    log_result "INFO: $1: $2"
    [ -n "$3" ] && echo "$3" | sed 's/^/    /' | tee -a "$LOG_FILE"
    PKG_TOTAL=$((PKG_TOTAL + $2)); PKG_SOURCES=$((PKG_SOURCES + 1))
}
if command -v rpm >/dev/null 2>&1; then
    pkg_count "RPM packages in the system image" "$(rpm -qa 2>/dev/null | grep -c .)"
fi
LAYERED_N=0; OVERRIDE_N=0
if command -v rpm-ostree >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    # Booted deployment only: what is running now, not a staged update.
    OSTREE_PKGS=$(rpm-ostree status --booted --json 2>/dev/null | python3 -c '
import json, sys
try:
    d = next(x for x in json.load(sys.stdin)["deployments"] if x.get("booted"))
except Exception:
    sys.exit(0)
for key, tag in (("requested-packages", "L"), ("requested-local-packages", "L"),
                 ("requested-base-removals", "R"), ("requested-base-local-replacements", "O")):
    for p in d.get(key) or []:
        print(tag, p if isinstance(p, str) else p[0])
' 2>/dev/null)
    LAYERED=$(awk '$1 == "L" {print $2}' <<<"$OSTREE_PKGS" | sort)
    OVERRIDES=$(awk '$1 == "R" {print "removed:  " $2} $1 == "O" {print "replaced: " $2}' <<<"$OSTREE_PKGS")
    [ -n "$LAYERED" ] && LAYERED_N=$(grep -c . <<<"$LAYERED")
    [ -n "$OVERRIDES" ] && OVERRIDE_N=$(grep -c . <<<"$OVERRIDES")
    if [ "$LAYERED_N" -gt 0 ]; then
        log_result "INFO: Layered on top of the image (rpm-ostree install): $LAYERED_N"
        echo "$LAYERED" | sed 's/^/    /' | tee -a "$LOG_FILE"
    else
        log_result "SUCCESS: No packages layered on top of the image."
    fi
    if [ "$OVERRIDE_N" -gt 0 ]; then
        log_result "INFO: Image packages removed or replaced (rpm-ostree override): $OVERRIDE_N"
        echo "$OVERRIDES" | sed 's/^/    /' | tee -a "$LOG_FILE"
    fi
    if [ $((LAYERED_N + OVERRIDE_N)) -ge 10 ]; then
        log_result "HINT: Every layered or overridden package is re-applied on each update, makes updates slower and can block one when it conflicts with a new image. Prefer Flatpak, Homebrew or Distrobox where possible."
    fi
fi
if command -v flatpak >/dev/null 2>&1; then
    FP_SYS=$(flatpak list --system --app --columns=application,version 2>/dev/null | sort)
    FP_USR=$(run_as_user flatpak list --user --app --columns=application,version 2>/dev/null | sort)
    FP_RT=$( { flatpak list --system --runtime --columns=application; \
               run_as_user flatpak list --user --runtime --columns=application; } 2>/dev/null | grep -c .)
    pkg_count "Flatpak apps (system)" "$(grep -c . <<<"$FP_SYS")" "$FP_SYS"
    pkg_count "Flatpak apps (user)" "$(grep -c . <<<"$FP_USR")" "$FP_USR"
    pkg_count "Flatpak runtimes and extensions" "$FP_RT"
fi
BREW_PREFIX=/home/linuxbrew/.linuxbrew
if [ -d "$BREW_PREFIX/Cellar" ] || [ -d "$BREW_PREFIX/Caskroom" ]; then
    BREW_F=$(ls -1 "$BREW_PREFIX/Cellar" 2>/dev/null)
    BREW_C=$(ls -1 "$BREW_PREFIX/Caskroom" 2>/dev/null)
    pkg_count "Homebrew formulae" "$(grep -c . <<<"$BREW_F")" "$BREW_F"
    pkg_count "Homebrew casks" "$(grep -c . <<<"$BREW_C")" "$BREW_C"
fi
GAME_HOME=$(getent passwd "$GAME_USER" | cut -d: -f6)
if [ -n "$GAME_HOME" ]; then
    APPIMAGES=$(find "$GAME_HOME/AppImages" "$GAME_HOME/Applications" -maxdepth 1 -iname '*.appimage' 2>/dev/null | grep -c .)
    pkg_count "AppImages (~/AppImages, ~/Applications)" "$APPIMAGES"
fi
if command -v podman >/dev/null 2>&1; then
    # Count only: container names are chosen by the user.
    BOXES=$(run_as_user podman ps -a --filter label=manager=distrobox --format '{{.ID}}' 2>/dev/null | grep -c .)
    TOOLBOXES=$(run_as_user podman ps -a --filter label=com.github.containers.toolbox=true --format '{{.ID}}' 2>/dev/null | grep -c .)
    [ $((BOXES + TOOLBOXES)) -gt 0 ] && \
        log_result "INFO: Distrobox/Toolbox containers: $((BOXES + TOOLBOXES)) (the packages inside them are not counted)"
fi
log_result "SUCCESS: $PKG_TOTAL packages and apps installed, from $PKG_SOURCES source(s)."
echo

fi  # TEST 45

# ----------------------------------------------------------------------------
# Gaming / stability tests. The BC-250 is mainly used as a Steam box, so these
# focus on crash forensics and the things that actually take this board down
# mid-game: GPU hangs, unified-memory exhaustion and power delivery.
# ----------------------------------------------------------------------------
if want 34; then
log_result "[TEST 34] Previous Boot Shutdown Integrity Test"
log_result "A hard lockup leaves no shutdown record; this finds boots that ended abnormally"
BOOT_COUNT=$(journalctl --list-boots --no-pager -q 2>/dev/null | grep -cE "^\s*-?[0-9]+")
log_result "INFO: Journal holds $BOOT_COUNT boot(s). Persistent journal: $( [ -d /var/log/journal ] && echo yes || echo NO )"
if [ ! -d /var/log/journal ]; then
    log_result "ERROR: The journal is volatile, so crash evidence is lost on every reboot."
    log_result "HINT: sudo mkdir -p /var/log/journal && sudo systemd-tmpfiles --create --prefix /var/log/journal"
    ERROR_FOUND=true
fi
UNCLEAN=0
for off in -1 -2 -3 -4 -5 -6 -7 -8 -9 -10; do
    journalctl -b "$off" -n 1 -q --no-pager >/dev/null 2>&1 || continue
    BOOT_TAIL=$(journalctl -b "$off" -n 60 -q --no-pager 2>/dev/null)
    BOOT_WHEN=$(journalctl -b "$off" -n 1 -q --no-pager -o short-full 2>/dev/null | awk '{print $1" "$2" "$3}')
    # journald is torn down before the final "Powering off" line is ever written to
    # disk, so the reliable evidence of a clean exit is that the shutdown *began*:
    # targets stopping, filesystems unmounting, the journal being flushed.
    if grep -qiE "systemd-shutdown|Reached target (Power-Off|Reboot|Shutdown|Halt|Final Step|Unmount)|Powering off|Rebooting|Shutting down|Journal stopped|Stopped target |Unmounting |Deactivated successfully" <<<"$BOOT_TAIL"; then
        log_result "SUCCESS: Boot $off (ended $BOOT_WHEN) shut down cleanly."
    else
        log_result "ERROR: Boot $off (ended $BOOT_WHEN) ended WITHOUT a shutdown sequence - hard lockup, panic or power cut."
        log_result "INFO: Last entries of boot $off:"
        echo "$BOOT_TAIL" | tail -15 | tee -a "$LOG_FILE"
        ERROR_FOUND=true
        UNCLEAN=$((UNCLEAN + 1))
    fi
done
if [ "$UNCLEAN" -gt 0 ]; then
    log_result "HINT: $UNCLEAN abnormal boot end(s) found. If the tail above shows nothing useful the"
    log_result "HINT: freeze was too abrupt to flush the journal. Capture it with pstore or netconsole."
fi
log_result "Check pstore for a panic captured by firmware"
if [ -d /sys/fs/pstore ]; then
    PSTORE_FILES=$(ls -1 /sys/fs/pstore 2>/dev/null)
    if [ -n "$PSTORE_FILES" ]; then
        log_result "ERROR: pstore contains crash records from a previous panic:"
        echo "$PSTORE_FILES" | tee -a "$LOG_FILE"
        log_result "HINT: sudo cat /sys/fs/pstore/dmesg-* to read them, then delete them to re-arm pstore."
        ERROR_FOUND=true
    else
        log_result "INFO: pstore is mounted and empty (no firmware-captured panic)."
    fi
else
    log_result "INFO: /sys/fs/pstore is not mounted; firmware crash capture is unavailable."
fi
echo

fi  # TEST 34
if want 35; then
log_result "[TEST 35] GPU Hang and Reset History Test"
log_result "Look for amdgpu ring timeouts, resets and VM faults across the retained boots"
GPU_HANGS=""
for off in 0 -1 -2 -3 -4 -5 -6 -7 -8 -9 -10; do
    journalctl -b "$off" -n 1 -q --no-pager >/dev/null 2>&1 || continue
    HITS=$(journalctl -b "$off" -k --no-pager -q 2>/dev/null | grep -EI "$GPU_HANG_RE")
    [ -n "$HITS" ] && GPU_HANGS+="--- boot $off ---"$'\n'"$HITS"$'\n'
done
if [ -n "$GPU_HANGS" ]; then
    log_result "ERROR: GPU hang or reset activity detected:"
    echo "$GPU_HANGS" | tee -a "$LOG_FILE"
    log_result "HINT: On the BC-250 this is almost always the SMU governor pushing an unstable"
    log_result "HINT: sclk/voltage pair. Lower the ceiling in /etc/cyan-skillfish-governor-smu/config.toml."
    ERROR_FOUND=true
else
    log_result "SUCCESS: No GPU hangs or resets recorded in the retained boots."
fi
log_result "Check amdgpu recovery tunables"
for p in gpu_recovery lockup_timeout noretry ppfeaturemask; do
    [ -r "/sys/module/amdgpu/parameters/$p" ] && \
        log_result "INFO: amdgpu.$p = $(cat "/sys/module/amdgpu/parameters/$p")"
done
echo

fi  # TEST 35
if want 36; then
log_result "[TEST 36] Kernel Panic, Lockup and Crash Dump Test"
log_result "Scan retained boots for oopses, soft/hard lockups and collected coredumps"
# Line-based filtering used to strip the RIP/dal_irq lines but leave the orphaned
# "Call Trace:" lines of the same benign WARN, raising a false ERROR every run.
# Group each hit with its surrounding context instead, and drop the whole block
# when it carries a known-benign signature. Surviving blocks keep their context,
# so a real trace is actually diagnosable from the log.
scan_kernel_faults() {
    awk -v panic="$PANIC_RE" -v benign="$PANIC_BENIGN_RE" '
        BEGIN { IGNORECASE=1; tail=0; block="" }
        function flush() { if (block != "" && block !~ benign) printf "%s\n", block; block="" }
        {
            if ($0 ~ panic) {
                if (tail == 0) {
                    flush()
                    start = NR - 8; if (start < 1) start = 1
                    for (i = start; i < NR; i++) block = block buf[i % 9] "\n"
                }
                block = block $0 "\n"
                tail = 6
            } else if (tail > 0) {
                block = block $0 "\n"
                if (--tail == 0) flush()
            }
            buf[NR % 9] = $0
        }
        END { flush() }
    '
}
PANICS=""
for off in 0 -1 -2 -3 -4 -5 -6 -7 -8 -9 -10; do
    journalctl -b "$off" -n 1 -q --no-pager >/dev/null 2>&1 || continue
    HITS=$(journalctl -b "$off" -k --no-pager -q 2>/dev/null | scan_kernel_faults)
    [ -n "$HITS" ] && PANICS+="--- boot $off ---"$'\n'"$HITS"$'\n'
done
if [ -n "$PANICS" ]; then
    log_result "ERROR: Kernel fault traces found:"
    echo "$PANICS" | tee -a "$LOG_FILE"
    ERROR_FOUND=true
else
    log_result "SUCCESS: No kernel panics or lockup traces in the retained boots."
fi
log_result "Check the NMI watchdog (it can turn a silent freeze into a logged panic)"
NMI_WD=$(sysctl -n kernel.nmi_watchdog 2>/dev/null)
if [ "$NMI_WD" = "1" ]; then
    log_result "SUCCESS: kernel.nmi_watchdog is enabled, hard lockups will be logged."
else
    log_result "WARNING: kernel.nmi_watchdog is '${NMI_WD:-unavailable}', so a hard freeze leaves no trace."
    log_result "HINT: sudo sysctl -w kernel.nmi_watchdog=1 (add nowatchdog removal to kargs to persist)."
    WARN_FOUND=true
fi
log_result "Check recent application coredumps (crashed games leave records here)"
if command -v coredumpctl >/dev/null 2>&1; then
    DUMPS=$(coredumpctl list --since "-14 days" --no-pager 2>/dev/null | tail -20)
    if [ -n "$DUMPS" ] && ! grep -qi "no coredumps" <<<"$DUMPS"; then
        log_result "INFO: Coredumps in the last 14 days:"
        echo "$DUMPS" | tee -a "$LOG_FILE"
    else
        log_result "SUCCESS: No coredumps recorded in the last 14 days."
    fi
fi
echo

fi  # TEST 36
if want 37; then
log_result "[TEST 37] Unified Memory and VRAM Pressure Test"
log_result "The BC-250 shares one 16GB GDDR6 pool between CPU and GPU, so exhaustion freezes the box"
for card in /sys/class/drm/card*/device; do
    [ -r "$card/mem_info_vram_total" ] || continue
    VRAM_T=$(cat "$card/mem_info_vram_total" 2>/dev/null)
    VRAM_U=$(cat "$card/mem_info_vram_used" 2>/dev/null)
    GTT_T=$(cat "$card/mem_info_gtt_total" 2>/dev/null)
    GTT_U=$(cat "$card/mem_info_gtt_used" 2>/dev/null)
    log_result "INFO: VRAM $((VRAM_U / 1048576)) MiB used of $((VRAM_T / 1048576)) MiB"
    log_result "INFO: GTT  $((GTT_U / 1048576)) MiB used of $((GTT_T / 1048576)) MiB"
done
log_result "Check for out-of-memory kills across the retained boots"
OOM=""
for off in 0 -1 -2 -3 -4 -5 -6 -7 -8 -9 -10; do
    journalctl -b "$off" -n 1 -q --no-pager >/dev/null 2>&1 || continue
    HITS=$(journalctl -b "$off" --no-pager -q 2>/dev/null | grep -EI "Out of memory: Killed process|oom-kill:|invoked oom-killer|systemd-oomd.*Killed")
    [ -n "$HITS" ] && OOM+="--- boot $off ---"$'\n'"$HITS"$'\n'
done
if [ -n "$OOM" ]; then
    log_result "ERROR: Out-of-memory kills detected:"
    echo "$OOM" | tee -a "$LOG_FILE"
    log_result "HINT: Cap in-game texture/resolution settings, or use zswap with a disk swapfile instead of zram."
    ERROR_FOUND=true
else
    log_result "SUCCESS: No out-of-memory kills in the retained boots."
fi
log_result "Check for scanout framebuffer pin failures (the 512MB-split killer)"
# Scatter-gather display is disabled on Cyan Skillfish, so every framebuffer the
# compositor shows must be pinned inside the *minimum* VRAM carve. If a game fills
# that carve the next flip cannot be pinned and the session dies. There is no GPU
# hang and no OOM-kill, so nothing else in this script would catch it.
PIN_RE="Failed to pin framebuffer|pin failed|fatal flip error|Failed to pin new rbo buffer"
PINFAIL=""
for off in 0 -1 -2 -3 -4 -5 -6 -7 -8 -9 -10; do
    journalctl -b "$off" -n 1 -q --no-pager >/dev/null 2>&1 || continue
    HITS=$(journalctl -b "$off" --no-pager -q 2>/dev/null | grep -EI "$PIN_RE")
    [ -n "$HITS" ] && PINFAIL+="--- boot $off ---"$'\n'"$HITS"$'\n'
done
if [ -n "$PINFAIL" ]; then
    log_result "ERROR: Framebuffer pin failures detected - the VRAM carve is too small for your games:"
    echo "$PINFAIL" | tee -a "$LOG_FILE"
    log_result "HINT: ttm.pages_limit does NOT fix this; only a larger minimum split does."
    log_result "HINT: sudo ./bc250memcfg UMA_SIZE 6144   (from fanoush/bc250_memcfg), then reboot."
    ERROR_FOUND=true
else
    log_result "SUCCESS: No framebuffer pin failures in the retained boots."
fi
log_result "Report the VRAM split and its dynamic ceiling"
VRAM_SPLIT_MIB=$(( $(read_num_g "/sys/class/drm/card1/device/mem_info_vram_total") / 1048576 ))
GTT_MIB=$(( $(read_num_g "/sys/class/drm/card1/device/mem_info_gtt_total") / 1048576 ))
for card in /sys/class/drm/card*/device; do
    [ -r "$card/mem_info_vram_total" ] || continue
    VRAM_SPLIT_MIB=$(( $(read_num_g "$card/mem_info_vram_total") / 1048576 ))
    GTT_MIB=$(( $(read_num_g "$card/mem_info_gtt_total") / 1048576 ))
done
# amdgpu sizes GTT from ttm.pages_limit (4 KiB pages, default half the RAM) and caps it at the RAM on this APU,
# so the GTT total is the real dynamic ceiling, not the parameter.
TTM_LIMIT=$(cat /sys/module/ttm/parameters/pages_limit 2>/dev/null)
if [ "$GTT_MIB" -gt 0 ]; then
    log_result "INFO: VRAM split is ${VRAM_SPLIT_MIB} MiB; the GPU can borrow up to ${GTT_MIB} MiB of system RAM on top (GTT)."
fi
if [ -n "$TTM_LIMIT" ] && [ "$TTM_LIMIT" -gt 0 ] && [ "$GTT_MIB" -gt 0 ] && [ $((TTM_LIMIT / 256)) -gt "$GTT_MIB" ]; then
    log_result "INFO: ttm.pages_limit is $((TTM_LIMIT / 256)) MiB, more than the RAM: amdgpu caps GTT at the RAM, so a higher limit has no effect."
fi
if [ "$VRAM_SPLIT_MIB" -le 1024 ]; then
    log_result "INFO: This is a small (dynamic-friendly) split, which maximizes regular RAM."
    if ! grep -q "ttm.pages_limit" /proc/cmdline 2>/dev/null; then
        log_result "WARNING: A small split without ttm.pages_limit caps total VRAM at $((VRAM_SPLIT_MIB + GTT_MIB)) MiB (the split plus half the RAM)."
        log_result "HINT: rpm-ostree kargs --append-if-missing=ttm.pages_limit=3014656   # ~11.5 GiB"
        WARN_FOUND=true
    fi
fi
log_result "Check vm.max_map_count (several modern games need a very high value)"
MMC=$(sysctl -n vm.max_map_count 2>/dev/null)
if [ -n "$MMC" ] && [ "$MMC" -ge 1048576 ]; then
    log_result "SUCCESS: vm.max_map_count is $MMC."
else
    log_result "WARNING: vm.max_map_count is ${MMC:-unknown}, which is low for modern titles."
    log_result "HINT: echo 'vm.max_map_count=2147483642' | sudo tee /etc/sysctl.d/99-gaming.conf"
    WARN_FOUND=true
fi
log_result "INFO: vm.swappiness = $(sysctl -n vm.swappiness 2>/dev/null)"
echo

fi  # TEST 37
if want 38; then
log_result "[TEST 38] Steam and Gaming Stack Test"
log_result "Verify Steam, Proton, gamescope, gamemode and MangoHud are present"
if run_as_user flatpak list --app --columns=application 2>/dev/null | grep -qx "com.valvesoftware.Steam"; then
    log_result "SUCCESS: Steam is installed as a Flatpak."
elif command -v steam >/dev/null 2>&1; then
    log_result "SUCCESS: Steam is installed natively ($(command -v steam))."
else
    log_result "WARNING: Steam was not found for user $GAME_USER."
    WARN_FOUND=true
fi
for tool in gamescope mangohud gamemoded umu-run vkbasalt; do
    if command -v "$tool" >/dev/null 2>&1; then
        log_result "INFO: $tool is available."
    else
        log_result "INFO: $tool is not installed."
    fi
done
if command -v gamemoded >/dev/null 2>&1; then
    GM=$(run_as_user gamemoded -s 2>/dev/null)
    log_result "INFO: gamemode status: ${GM:-unavailable}"
fi
log_result "Check Steam library locations and free space"
GAME_HOME=$(getent passwd "$GAME_USER" | cut -d: -f6)
for lib in "$GAME_HOME/.local/share/Steam/steamapps" \
           "$GAME_HOME/.steam/steam/steamapps" \
           "$GAME_HOME/.var/app/com.valvesoftware.Steam/data/Steam/steamapps"; do
    [ -d "$lib" ] || continue
    log_result "INFO: Library $lib -> $(df -h "$lib" | awk 'NR==2 {print $4" free of "$2" ("$5" used)"}')"
    VDF="$(dirname "$lib")/steamapps/libraryfolders.vdf"
    [ -r "$VDF" ] && grep -E '"path"' "$VDF" 2>/dev/null | tee -a "$LOG_FILE"
done
echo

fi  # TEST 38
if want 39; then
log_result "[TEST 39] Audio Stack Test"
log_result "A continuous screech during a freeze is a looping DMA buffer, not an audio fault"
for u in pipewire.service pipewire-pulse.service wireplumber.service; do
    STATE=$(run_as_user systemctl --user is-active "$u" 2>/dev/null)
    if [ "$STATE" = "active" ]; then
        log_result "SUCCESS: $u is active for $GAME_USER."
    else
        log_result "WARNING: $u is '${STATE:-unknown}' for $GAME_USER."
        WARN_FOUND=true
    fi
done
if command -v wpctl >/dev/null 2>&1; then
    log_result "INFO: Default audio sink:"
    run_as_user wpctl status 2>/dev/null | sed -n '/Sinks:/,/^$/p' | tee -a "$LOG_FILE"
fi
log_result "INFO: ALSA cards:"
cat /proc/asound/cards 2>/dev/null | tee -a "$LOG_FILE"
echo

fi  # TEST 39
if want 40; then
log_result "[TEST 40] Power Delivery and Throttling Test"
log_result "Brownouts and an over-aggressive governor ceiling are the top BC-250 lockup causes"
for hw in /sys/class/drm/card*/device/hwmon/hwmon*; do
    [ -r "$hw/power1_cap" ] || continue
    log_result "INFO: GPU power cap: $(( $(cat "$hw/power1_cap") / 1000000 )) W (max $(( $(cat "$hw/power1_cap_max" 2>/dev/null || echo 0) / 1000000 )) W)"
    [ -r "$hw/power1_average" ] && log_result "INFO: GPU power now: $(( $(cat "$hw/power1_average") / 1000000 )) W"
done
log_result "Review the SMU governor frequency ceiling"
GOV_CONF="/etc/cyan-skillfish-governor-smu/config.toml"
if [ -r "$GOV_CONF" ]; then
    grep -vE "^\s*(#|$)" "$GOV_CONF" | tee -a "$LOG_FILE"
    GOV_MAX=$(grep -oE "max[_a-z]*\s*=\s*[0-9]+" "$GOV_CONF" | grep -oE "[0-9]+" | sort -rn | head -1)
    if [ -n "$GOV_MAX" ] && [ "$GOV_MAX" -gt 1900 ]; then
        log_result "WARNING: The governor may drive the GPU up to ${GOV_MAX} MHz."
        log_result "HINT: Many BC-250 boards are unstable above ~1850 MHz and hard-lock under load."
        log_result "HINT: Lower the maximum in $GOV_CONF, then: sudo systemctl restart cyan-skillfish-governor-smu"
        WARN_FOUND=true
    elif [ -n "$GOV_MAX" ]; then
        log_result "SUCCESS: The governor ceiling (${GOV_MAX} MHz) is within the commonly stable range."
    fi

    # toml_get SECTION KEY: the value of KEY inside [SECTION], quotes stripped.
    toml_get() {
        awk -v sec="[$1]" -v key="$2" '
            /^[[:space:]]*\[/ { insec = ($1 == sec); next }
            insec && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
                sub(/^[^=]*=[[:space:]]*/, ""); sub(/[[:space:]]*#.*$/, ""); gsub(/"/, ""); print; exit
            }' "$GOV_CONF"
    }
    GOV_SET_METHOD=$(toml_get gpu set-method);         GOV_SET_METHOD=${GOV_SET_METHOD:-smu}
    GOV_USAGE_METHOD=$(toml_get gpu-usage method);     GOV_USAGE_METHOD=${GOV_USAGE_METHOD:-busy-flag}
    GOV_FIX_METRICS=$(toml_get gpu-usage fix-metrics); GOV_FIX_METRICS=${GOV_FIX_METRICS:-true}
    log_result "INFO: Governor clock control (gpu.set-method): $GOV_SET_METHOD | load measurement (gpu-usage.method): $GOV_USAGE_METHOD | fix-metrics: $GOV_FIX_METRICS"
    if [ "$GOV_SET_METHOD" = "kernel" ]; then
        log_result "NOTE: set-method \"kernel\" goes through the amdgpu driver, which a stock driver caps at 2000 MHz."
        log_result "NOTE: \"smu\" talks to the SMU directly and is the usual choice on a stock kernel."
    fi
    if [ "$GOV_FIX_METRICS" = "true" ]; then
        if grep -q 'gpu_metrics' /proc/self/mountinfo 2>/dev/null; then
            log_result "SUCCESS: fix-metrics is on and the patched gpu_metrics is mounted; overlays show a real GPU load."
        else
            log_result "WARNING: fix-metrics is on, but no patched gpu_metrics is mounted. Overlays will show 0% or 655% GPU load."
            log_result "HINT: sudo systemctl restart $GOV_FOUND   # then check: mount | grep gpu_metrics"
            WARN_FOUND=true
        fi
    else
        log_result "INFO: fix-metrics is off, so MangoHud / the Steam overlay show 0% (or 655%) GPU load."
        log_result "NOTE: To show the real load, set fix-metrics = true under [gpu-usage] in $GOV_CONF,"
        log_result "NOTE: then: sudo systemctl restart $GOV_FOUND   (see the manual: \"Fix: GPU load shows 0%\")."
    fi
else
    log_result "INFO: $GOV_CONF not present."
fi
log_result "Check for thermal or power throttling messages"
THROTTLE=$(journalctl -k --no-pager -q 2>/dev/null | grep -EI "throttl|thermal trip|critical temperature|Power limit|over-current|PSU" | tail -20)
if [ -n "$THROTTLE" ]; then
    log_result "WARNING: Throttling or power messages found:"
    echo "$THROTTLE" | tee -a "$LOG_FILE"
    WARN_FOUND=true
else
    log_result "SUCCESS: No throttling or power-limit messages recorded."
fi
echo
fi  # TEST 40
if want 41; then
log_result "[TEST 41] Combined CPU + GPU Stress and Telemetry Test"
if [ "$STRESS_MODE" != true ]; then
    log_howto "INFO: Skipped. Re-run with --stress (or --stress=SECONDS) to load the board and" \
              "INFO: Skipped. Start test 41 (Stability and thermals page) to load the board and"
    log_result "INFO: sample clocks, temperatures, power and fans while it is under load."
    echo
else
log_result "Loading CPU and GPU for ${STRESS_DURATION}s while sampling telemetry every ${STRESS_SAMPLE}s"
log_result "NOTE: This is a deliberate attempt to reproduce an under-load lockup."

STRESS_CSV="$LOG_DIR/bc250-stress-${TIMESTAMP}.csv"
STRESS_PIDS=()
STRESS_ABORT=false

# ---- sysfs discovery -------------------------------------------------------
GPU_DEV=""
for d in /sys/class/drm/card*/device; do
    [ -r "$d/pp_dpm_sclk" ] && { GPU_DEV="$d"; break; }
done
GPU_HWMON=""
[ -n "$GPU_DEV" ] && for h in "$GPU_DEV"/hwmon/hwmon*; do [ -d "$h" ] && { GPU_HWMON="$h"; break; }; done
CPU_HWMON=""
SIO_HWMON=""
for h in /sys/class/hwmon/hwmon*; do
    case "$(cat "$h/name" 2>/dev/null)" in
        k10temp)   CPU_HWMON="$h" ;;
        nct668*)   SIO_HWMON="$h" ;;
    esac
done
log_result "INFO: GPU sysfs: ${GPU_DEV:-not found} | GPU hwmon: ${GPU_HWMON:-none} | CPU hwmon: ${CPU_HWMON:-none} | SuperIO: ${SIO_HWMON:-none}"

read_sysfs() { [ -r "$1" ] && cat "$1" 2>/dev/null || echo ""; }
read_dpm()   { grep '\*' "$1" 2>/dev/null | head -1 | awk '{print $2}' | tr -dc '0-9'; }
# Always yields a number so it is safe inside $(( )).
read_num()   { local v; v=$(cat "$1" 2>/dev/null | tr -dc '0-9'); echo "${v:-0}"; }

# Stock kernels have no GPU-load sensor for Cyan Skillfish: gpu_busy_percent fails with
# EOPNOTSUPP, and overlays only show a load when the governor's fix-metrics patches it in.
# Fall back to per-client gfx engine time from /proc/*/fdinfo, the method nvtop and the
# governor's "process" mode use. Prints "<client-id> <ns>" lines.
gfx_engine_clients() {
    find /proc/[0-9]*/fd -lname '/dev/dri/*' 2>/dev/null | sed 's#/fd/#/fdinfo/#' |
        xargs -r awk '
            FNR == 1 { amd = 0; cid = "" }
            /^drm-driver:/ { amd = ($2 == "amdgpu") }
            /^drm-client-id:/ { cid = $2 }
            /^drm-engine-(gfx|compute):/ && amd && cid != "" {
                eng = substr($1, 12, length($1) - 12); key = eng ":" cid
                if (!(key in seen)) { seen[key] = 1; print key, $2 }
            }
        ' 2>/dev/null
}

# ---- workers ---------------------------------------------------------------
cleanup_stress() {
    for p in "${STRESS_PIDS[@]}"; do
        kill "$p" 2>/dev/null
        pgid=$(ps -o pgid= "$p" 2>/dev/null | tr -d ' ')
        [ -n "$pgid" ] && kill -- "-$pgid" 2>/dev/null
    done
    STRESS_PIDS=()
}
trap 'cleanup_stress' INT TERM

NPROC=$(nproc)
CPU_WORKER="none"
# The CPU load must never starve the GPU load tool's render thread or the compositor: with 12
# busy threads at normal priority the GPU sat at ~10% busy until the CPU load stopped.
# nice alone is not enough. With sched_autogroup (enabled on Fedora/Bazzite kernels) every
# setsid session is its own scheduling group and the groups share the CPU equally, whatever their
# nice values. So each CPU worker lowers its own autogroup to nice 19 (inside the new session, so
# the script's own group is untouched) and runs as SCHED_IDLE (chrt -i 0) where available. It still
# takes every idle cycle, so the CPU stays at 100%.
run_low_prio() {
    setsid bash -c '
        echo 19 > /proc/self/autogroup 2>/dev/null
        if command -v chrt >/dev/null 2>&1; then exec chrt -i 0 "$@"; else exec nice -n 19 "$@"; fi
    ' _ "$@" >/dev/null 2>&1 &
    STRESS_PIDS+=($!)
}
if command -v chrt >/dev/null 2>&1; then CPU_PRIO="SCHED_IDLE"; else CPU_PRIO="nice 19"; fi
if [ "$(cat /proc/sys/kernel/sched_autogroup_enabled 2>/dev/null)" = "1" ]; then
    CPU_PRIO="$CPU_PRIO, autogroup nice 19"
fi
# The timeout covers the GPU start-up wait as well; cleanup_stress stops it after sampling.
CPU_TIMEOUT=$((STRESS_DURATION + 30))
if find_tool stress-ng; then
    CPU_WORKER="stress-ng"
    run_low_prio "${TOOL_CMD[@]}" --cpu "$NPROC" --timeout "${CPU_TIMEOUT}s"
elif find_tool stress; then
    CPU_WORKER="stress"
    run_low_prio "${TOOL_CMD[@]}" --cpu "$NPROC" --timeout "${CPU_TIMEOUT}s"
else
    CPU_WORKER="shell busy-loops"
    for _ in $(seq 1 "$NPROC"); do
        run_low_prio bash -c 'while :; do :; done'
    done
fi
log_result "INFO: CPU load: $CPU_WORKER across $NPROC threads ($CPU_PRIO, so the GPU load is not starved)."

GPU_WORKER="none"
GPU_WORKER_PID=""
# Not /tmp: /tmp is lost on the reboot after a lockup, and so was the evidence.
GPU_WORKER_LOG="$LOG_DIR/bc250-gpuload-${TIMESTAMP}.log"

# Inherit the real graphical session environment from the running compositor.
# Guessing WAYLAND_DISPLAY=wayland-0 is unreliable and makes the load tool exit
# instantly, which silently turns this into a CPU-only test.
grab_session_env() {
    local pid envfile
    for comm in kwin_wayland gamescope plasmashell gnome-shell Xwayland; do
        pid=$(pgrep -u "$GAME_USER" -x "$comm" 2>/dev/null | head -1)
        [ -n "$pid" ] || continue
        envfile="/proc/$pid/environ"
        [ -r "$envfile" ] || continue
        SESSION_ENV=()
        while IFS= read -r -d '' kv; do
            case "$kv" in
                WAYLAND_DISPLAY=*|DISPLAY=*|XDG_RUNTIME_DIR=*|XDG_SESSION_TYPE=*|\
                DBUS_SESSION_BUS_ADDRESS=*|XAUTHORITY=*|HOME=*)
                    SESSION_ENV+=("$kv") ;;
            esac
        done < "$envfile"
        if [ "${#SESSION_ENV[@]}" -gt 0 ]; then
            log_result "INFO: Session environment taken from $comm (pid $pid)."
            return 0
        fi
    done
    log_result "WARNING: No running compositor found; falling back to guessed session variables."
    SESSION_ENV=("XDG_RUNTIME_DIR=/run/user/$(id -u "$GAME_USER")"
                 "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}"
                 "DISPLAY=${DISPLAY:-:0}")
    WARN_FOUND=true
    return 1
}
SESSION_ENV=()
grab_session_env

# Keep the screen from locking or blanking and the system from sleeping during the run: KDE locked
# the screen mid-run even with locking turned off in its settings. The inhibitor holds only while
# the process lives; cleanup_stress kills it.
INHIBIT_SECS=$((CPU_TIMEOUT + 60))
if command -v kde-inhibit >/dev/null 2>&1; then
    setsid sudo -u "$GAME_USER" env "${SESSION_ENV[@]}" \
        kde-inhibit --power --screenSaver sleep "$INHIBIT_SECS" >/dev/null 2>&1 &
    STRESS_PIDS+=($!)
    log_result "INFO: Screen locking, blanking and sleep are inhibited for the run (kde-inhibit)."
elif command -v systemd-inhibit >/dev/null 2>&1; then
    setsid systemd-inhibit --what=idle:sleep --who="bc250-bazzite-test" --why="stress test running" \
        sleep "$INHIBIT_SECS" >/dev/null 2>&1 &
    STRESS_PIDS+=($!)
    log_result "INFO: Idle and sleep are inhibited for the run (systemd-inhibit); some desktops still lock the screen."
fi

start_gpu_worker() {
    # sudo -u resets PATH again, so pass the full path of the tool (find_tool also looks in ~/.local/bin).
    # oom_score_adj 1000: if memory runs out, the kernel kills the load tool first, not the desktop
    # (memtest_vulkan once filled the RAM and the OOM killer took kwin_wayland). timeout stops the tool
    # even if this script is killed, so it can never keep running on its own.
    local bin
    if [ "$1" != bash ] && find_tool "$1"; then bin="$TOOL"; set -- "$bin" "${@:2}"; fi
    setsid sudo -u "$GAME_USER" env "${SESSION_ENV[@]}" BC250_WORKER_CWD="${GPU_WORKER_CWD:-}" \
        timeout -k 10 "$((CPU_TIMEOUT + 30))" \
        bash -c 'echo 1000 > /proc/self/oom_score_adj 2>/dev/null
                 [ -n "$BC250_WORKER_CWD" ] && cd "$BC250_WORKER_CWD" 2>/dev/null
                 exec "$@"' _ "$@" >"$GPU_WORKER_LOG" 2>&1 &
    GPU_WORKER_PID=$!
    STRESS_PIDS+=("$GPU_WORKER_PID")
}

# Preference: headless compute tools first. They queue GPU work back to back, while the benchmark
# tools render one light frame at a time: vkmark ran ~2000 FPS in every scene on the BC-250 and
# left the GPU ~20% busy at 1000 MHz. memtest_vulkan also checks the VRAM for errors.
# vkmark/glmark2 fall back to a 2560x1440 window with only the heaviest work: effect2d blur (the one
# scene that reached ~60% busy at 1080p) and the desktop scene with 16 large overlapping windows.
GPU_LOAD_SIZE="2560x1440"
# The load tool always runs as the desktop user (start_gpu_worker), never as root.
if find_tool memtest_vulkan; then
    GPU_WORKER="memtest_vulkan"
    # By default memtest_vulkan takes all free RAM minus 400 MB on an APU (it allocated 9.6 GB of GTT
    # here and the OOM killer took the desktop). Limit it to 3/4 of the VRAM carve-out and at most
    # half of the RAM that is available now. Arguments: <device> <max bytes>; device 0 = autoselect.
    # Passing them also skips the interactive prompt; the endless test loop runs the same way.
    MEM_AVAIL_MIB=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
    VRAM_MIB=$(( $(read_num "$GPU_DEV/mem_info_vram_total") / 1048576 ))
    MEMTEST_MIB=$((VRAM_MIB * 3 / 4))
    [ "$MEMTEST_MIB" -le 0 ] || [ "$MEMTEST_MIB" -gt "$((MEM_AVAIL_MIB / 2))" ] && MEMTEST_MIB=$((MEM_AVAIL_MIB / 2))
    log_result "INFO: memtest_vulkan limited to ${MEMTEST_MIB} MiB (RAM available: ${MEM_AVAIL_MIB} MiB)."
    # memtest_vulkan always writes its own memtest_vulkan.log into the current directory; run it in a
    # work dir of its own so that log can be collected afterwards instead of littering wherever the
    # script was started.
    MEMTEST_WORKDIR=$(sudo -u "$GAME_USER" mktemp -d /tmp/bc250-memtest.XXXXXX 2>/dev/null) || MEMTEST_WORKDIR=""
    GPU_WORKER_CWD="$MEMTEST_WORKDIR"
    start_gpu_worker memtest_vulkan 0 "$((MEMTEST_MIB * 1048576))" </dev/null
    GPU_WORKER_CWD=""
elif find_tool vkpeak; then
    GPU_WORKER="vkpeak"
    start_gpu_worker bash -c 'while :; do "$0" 0; done' "$TOOL" </dev/null
elif find_tool vkmark; then
    GPU_WORKER="vkmark"
    start_gpu_worker vkmark --run-forever -s "$GPU_LOAD_SIZE" \
        -b effect2d:kernel=blur -b desktop:windows=16:window-size=0.8
elif find_tool glmark2; then
    GPU_WORKER="glmark2"
    start_gpu_worker glmark2 --run-forever -s "$GPU_LOAD_SIZE"
elif command -v vkcube >/dev/null 2>&1; then
    GPU_WORKER="vkcube (light load)"
    start_gpu_worker vkcube
else
    log_result "WARNING: No GPU load tool found; only the CPU will be stressed."
    log_result "HINT: Layer one with: rpm-ostree install glmark2 (vulkan-tools provides vkcube)."
    log_result "HINT: A Flatpak will NOT be detected here; the tool must be on PATH."
    WARN_FOUND=true
fi

# Confirm the GPU load actually survived startup instead of exiting immediately.
if [ -n "$GPU_WORKER_PID" ]; then
    sleep 5
    if kill -0 "$GPU_WORKER_PID" 2>/dev/null; then
        log_result "INFO: GPU load: $GPU_WORKER running as $GAME_USER (pid $GPU_WORKER_PID)."
    else
        log_result "ERROR: The GPU load tool ($GPU_WORKER) exited immediately; this run is CPU-only."
        [ -s "$GPU_WORKER_LOG" ] && { log_result "INFO: Its output was:"; head -20 "$GPU_WORKER_LOG" | tee -a "$LOG_FILE"; }
        log_result "HINT: Run it by hand from the desktop session first: $GPU_WORKER"
        ERROR_FOUND=true
        GPU_WORKER="none (failed to start)"
    fi
fi

# ---- sampling loop ---------------------------------------------------------
echo "elapsed_s,sclk_mhz,mclk_mhz,gpu_busy_pct,vram_used_mib,gtt_used_mib,gpu_temp_c,gpu_power_w,vddgfx_mv,cpu_tctl_c,cpu_mhz_avg,fan_rpm,load1" > "$STRESS_CSV"
MAX_SCLK=0; MAX_GTEMP=0; MAX_POWER=0; MAX_CTEMP=0; MAX_FAN=0; MAX_BUSY=0
MAX_VRAM=0; MAX_GTT=0
MIN_SCLK=999999; SAMPLES=0; SUM_SCLK=0; SUM_POWER=0; SUM_BUSY=0
VRAM_TOTAL_MIB=$(( $(read_num "$GPU_DEV/mem_info_vram_total") / 1048576 ))
GTT_TOTAL_MIB=$(( $(read_num "$GPU_DEV/mem_info_gtt_total") / 1048576 ))
[ "${VRAM_TOTAL_MIB:-0}" -eq 0 ] && VRAM_TOTAL_MIB=1
[ "${GTT_TOTAL_MIB:-0}" -eq 0 ] && GTT_TOTAL_MIB=1
log_result "INFO: Memory budget: ${VRAM_TOTAL_MIB} MiB VRAM + ${GTT_TOTAL_MIB} MiB GTT"
# Keep this script out of the OOM killer's reach during the run so it can always stop the load.
OLD_OOM_ADJ=$(cat /proc/$$/oom_score_adj 2>/dev/null)
echo -500 > /proc/$$/oom_score_adj 2>/dev/null
MEM_TOTAL_MIB=$(( $(awk '/^MemTotal:/ {print $2}' /proc/meminfo) / 1024 ))
MEM_GUARD_MIB=$((MEM_TOTAL_MIB / 20)); [ "$MEM_GUARD_MIB" -lt 512 ] && MEM_GUARD_MIB=512
STRESS_ABORT_REASON=""

declare -A GFX_PREV GFX_CUR
GFX_PREV_NS=0
# Sets GFX_BUSY to the gfx busy % since the previous call. Only clients seen in both samples
# count, so a client starting or exiting between samples does not skew the result. Must run in
# the current shell (not inside $(...)) so the previous sample survives.
sample_gfx_busy() {
    # Keys are "gfx:<client>" / "compute:<client>". Compute tools (vkpeak) may use the compute
    # ring, so both engines are summed separately and the busier one is reported.
    local now key ns gfx=0 compute=0 delta busy=0
    now=$(date +%s%N)
    GFX_CUR=()
    while read -r key ns; do GFX_CUR[$key]=$ns; done < <(gfx_engine_clients)
    for key in "${!GFX_CUR[@]}"; do
        [ -n "${GFX_PREV[$key]:-}" ] && [ "${GFX_CUR[$key]}" -ge "${GFX_PREV[$key]}" ] || continue
        case "$key" in
            gfx:*)     gfx=$((gfx + GFX_CUR[$key] - GFX_PREV[$key])) ;;
            compute:*) compute=$((compute + GFX_CUR[$key] - GFX_PREV[$key])) ;;
        esac
    done
    delta=$gfx; [ "$compute" -gt "$delta" ] && delta=$compute
    [ "$GFX_PREV_NS" -gt 0 ] && [ "$now" -gt "$GFX_PREV_NS" ] && busy=$((delta * 100 / (now - GFX_PREV_NS)))
    [ "$busy" -gt 100 ] && busy=100
    GFX_PREV=()
    for key in "${!GFX_CUR[@]}"; do GFX_PREV[$key]=${GFX_CUR[$key]}; done
    GFX_PREV_NS=$now
    GFX_BUSY=$busy
}
if cat "$GPU_DEV/gpu_busy_percent" >/dev/null 2>&1; then
    BUSY_SRC="gpu_busy_percent"
else
    BUSY_SRC="fdinfo"
    sample_gfx_busy                # baseline for the first sample
    if [ "${#GFX_CUR[@]}" -eq 0 ]; then
        BUSY_SRC="none"
    fi
fi
case "$BUSY_SRC" in
    gpu_busy_percent) log_result "INFO: GPU busy source: gpu_busy_percent (kernel load sensor)." ;;
    fdinfo)           log_result "INFO: GPU busy source: gfx/compute engine time from /proc/*/fdinfo (this kernel has no GPU load sensor)." ;;
    none)             log_result "WARNING: GPU busy cannot be measured: no load sensor and no amdgpu clients in fdinfo."
                      WARN_FOUND=true ;;
esac

START=$(date +%s)
END=$((START + STRESS_DURATION))
while [ "$(date +%s)" -lt "$END" ]; do
    ELAPSED=$(( $(date +%s) - START ))
    SCLK=$(read_dpm "$GPU_DEV/pp_dpm_sclk"); SCLK=${SCLK:-0}
    MCLK=$(read_dpm "$GPU_DEV/pp_dpm_mclk"); MCLK=${MCLK:-0}
    GTEMP_RAW=$(read_sysfs "$GPU_HWMON/temp1_input"); GTEMP=$(( ${GTEMP_RAW:-0} / 1000 ))
    GPOW_RAW=$(read_sysfs "$GPU_HWMON/power1_average"); GPOW=$(( ${GPOW_RAW:-0} / 1000000 ))
    VDD=$(read_sysfs "$GPU_HWMON/in0_input"); VDD=${VDD:-0}
    CTEMP_RAW=$(read_sysfs "$CPU_HWMON/temp1_input"); CTEMP=$(( ${CTEMP_RAW:-0} / 1000 ))
    CMHZ=$(awk -F: '/cpu MHz/ {s+=$2; n++} END {if (n) printf "%.0f", s/n; else print 0}' /proc/cpuinfo)
    FAN=0
    for f in "$SIO_HWMON"/fan*_input "$GPU_HWMON"/fan1_input; do
        [ -r "$f" ] || continue
        v=$(cat "$f" 2>/dev/null); [ -n "$v" ] && [ "$v" -gt "$FAN" ] && FAN=$v
    done
    LOAD1=$(awk '{print $1}' /proc/loadavg)
    case "$BUSY_SRC" in
        gpu_busy_percent) BUSY=$(read_num "$GPU_DEV/gpu_busy_percent") ;;
        fdinfo)           sample_gfx_busy; BUSY=$GFX_BUSY ;;
        *)                BUSY=0 ;;
    esac
    VRAM_U=$(( $(read_num "$GPU_DEV/mem_info_vram_used") / 1048576 ))
    GTT_U=$(( $(read_num "$GPU_DEV/mem_info_gtt_used") / 1048576 ))

    echo "$ELAPSED,$SCLK,$MCLK,$BUSY,$VRAM_U,$GTT_U,$GTEMP,$GPOW,$VDD,$CTEMP,$CMHZ,$FAN,$LOAD1" >> "$STRESS_CSV"
    # Flush every sample so the last seconds before a hard lockup survive the reboot.
    sync "$STRESS_CSV" "$LOG_FILE" "$GPU_WORKER_LOG" 2>/dev/null

    SAMPLES=$((SAMPLES + 1))
    SUM_SCLK=$((SUM_SCLK + SCLK)); SUM_POWER=$((SUM_POWER + GPOW)); SUM_BUSY=$((SUM_BUSY + BUSY))
    [ "$BUSY" -gt "$MAX_BUSY" ] && MAX_BUSY=$BUSY
    [ "$VRAM_U" -gt "$MAX_VRAM" ] && MAX_VRAM=$VRAM_U
    [ "$GTT_U" -gt "$MAX_GTT" ] && MAX_GTT=$GTT_U
    [ "$SCLK" -gt "$MAX_SCLK" ] && MAX_SCLK=$SCLK
    [ "$SCLK" -lt "$MIN_SCLK" ] && [ "$SCLK" -gt 0 ] && MIN_SCLK=$SCLK
    [ "$GTEMP" -gt "$MAX_GTEMP" ] && MAX_GTEMP=$GTEMP
    [ "$GPOW"  -gt "$MAX_POWER" ] && MAX_POWER=$GPOW
    [ "$CTEMP" -gt "$MAX_CTEMP" ] && MAX_CTEMP=$CTEMP
    [ "$FAN"   -gt "$MAX_FAN"   ] && MAX_FAN=$FAN

    # Live progress every ~10s so a freeze is visible on screen.
    if [ $((ELAPSED % 10)) -lt "$STRESS_SAMPLE" ]; then
        log_result "INFO: t=${ELAPSED}s sclk=${SCLK}MHz busy=${BUSY}% vram=${VRAM_U}M gtt=${GTT_U}M gpu=${GTEMP}C ${GPOW}W vddgfx=${VDD}mV cpu=${CTEMP}C fan=${FAN}rpm load=${LOAD1}"
    fi

    if [ "$GTEMP" -ge 95 ] || [ "$CTEMP" -ge 95 ]; then
        log_result "ERROR: Thermal abort at ${ELAPSED}s (GPU ${GTEMP}C / CPU ${CTEMP}C). Stopping the load."
        ERROR_FOUND=true
        STRESS_ABORT=true
        STRESS_ABORT_REASON="thermal guard"
        break
    fi
    MEM_AVAIL_NOW=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
    if [ "$MEM_AVAIL_NOW" -lt "$MEM_GUARD_MIB" ]; then
        log_result "WARNING: Memory guard at ${ELAPSED}s: only ${MEM_AVAIL_NOW} MiB RAM left (gtt=${GTT_U}M). Stopping the load before the OOM killer hits the desktop."
        WARN_FOUND=true
        STRESS_ABORT=true
        STRESS_ABORT_REASON="memory guard"
        break
    fi
    sleep "$STRESS_SAMPLE"
done

cleanup_stress
trap - INT TERM
[ -n "$OLD_OOM_ADJ" ] && echo "$OLD_OOM_ADJ" > /proc/$$/oom_score_adj 2>/dev/null
sleep 3

# ---- results ---------------------------------------------------------------
log_result "Stress run finished, $SAMPLES samples written to $STRESS_CSV"
if [ "$SAMPLES" -gt 0 ]; then
    AVG_SCLK=$((SUM_SCLK / SAMPLES)); AVG_POWER=$((SUM_POWER / SAMPLES)); AVG_BUSY=$((SUM_BUSY / SAMPLES))
    [ "$MIN_SCLK" -eq 999999 ] && MIN_SCLK=0
    log_result "INFO: sclk      min ${MIN_SCLK} / avg ${AVG_SCLK} / max ${MAX_SCLK} MHz"
    log_result "INFO: GPU busy  avg ${AVG_BUSY} / max ${MAX_BUSY} %"
    log_result "INFO: GPU temp  max ${MAX_GTEMP} C"
    log_result "INFO: GPU power avg ${AVG_POWER} / max ${MAX_POWER} W"
    log_result "INFO: CPU Tctl  max ${MAX_CTEMP} C"
    log_result "INFO: Fan       max ${MAX_FAN} RPM"
    log_result "INFO: VRAM peak ${MAX_VRAM} MiB of ${VRAM_TOTAL_MIB} MiB ($((MAX_VRAM * 100 / VRAM_TOTAL_MIB))%)"
    log_result "INFO: GTT  peak ${MAX_GTT} MiB of ${GTT_TOTAL_MIB} MiB ($((MAX_GTT * 100 / GTT_TOTAL_MIB))%)"
    if [ "$((MAX_VRAM * 100 / VRAM_TOTAL_MIB))" -ge 90 ]; then
        log_result "WARNING: The VRAM carveout was saturated; allocations are spilling into GTT."
        log_result "HINT: Raise the VRAM split with bc250_memcfg (UMA_SIZE, see test 37), then reboot."
        WARN_FOUND=true
    fi
    if [ "$((MAX_GTT * 100 / GTT_TOTAL_MIB))" -ge 85 ]; then
        log_result "WARNING: GTT peaked at $((MAX_GTT * 100 / GTT_TOTAL_MIB))% of its limit; the GPU is close to running out of memory."
        # GTT is capped at the RAM (test 37): once it is there, or the limit is already the recommended one,
        # a higher ttm.pages_limit only takes RAM away from the system.
        RAM_MIB=$(( $(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 ))
        TTM_NOW=$(read_num /sys/module/ttm/parameters/pages_limit)
        if [ "$GTT_TOTAL_MIB" -ge $((RAM_MIB * 95 / 100)) ] || [ "$TTM_NOW" -ge 3014656 ]; then
            log_result "HINT: GTT is already at its practical maximum (${GTT_TOTAL_MIB} MiB, RAM ${RAM_MIB} MiB); a higher ttm.pages_limit will not help."
            log_result "HINT: Lower texture/resolution settings, close other programs, or check the swap layout (test 14)."
        elif grep -q "ttm.pages_limit=" /proc/cmdline 2>/dev/null; then
            log_result "HINT: rpm-ostree kargs --replace=ttm.pages_limit=3014656   # ~11.5 GiB, capped at the RAM"
        else
            log_result "HINT: rpm-ostree kargs --append=ttm.pages_limit=3014656   # ~11.5 GiB, capped at the RAM"
        fi
        WARN_FOUND=true
    fi

    if [ "$MAX_GTEMP" -ge 85 ]; then
        log_result "WARNING: The GPU reached ${MAX_GTEMP} C under load. Check airflow and the heatsink mount."
        WARN_FOUND=true
    fi
    if [ "$MAX_FAN" -eq 0 ]; then
        log_result "ERROR: No fan reported any RPM during the whole run."
        ERROR_FOUND=true
    fi
    # Governor ceiling, to tell "stuck at the top" (correct under load) from "stuck low".
    GOV_TOP=$(grep -oE "max[_a-z]*\s*=\s*[0-9]+" /etc/cyan-skillfish-governor-smu/config.toml 2>/dev/null | grep -oE "[0-9]+" | sort -rn | head -1)
    # Validate the GPU was genuinely loaded before judging the governor at all.
    if [ "$BUSY_SRC" = "none" ]; then
        if [ "$MAX_SCLK" -le "$((MIN_SCLK + 100))" ]; then
            log_result "WARNING: GPU load is unknown and the clock stayed at ~${MAX_SCLK} MHz; the GPU may not have been loaded."
            WARN_FOUND=true
        else
            log_result "SUCCESS: The GPU clock responded to the load (${MIN_SCLK} -> ${MAX_SCLK} MHz)."
        fi
    elif [ "$AVG_BUSY" -lt 50 ]; then
        log_result "WARNING: The GPU averaged only ${AVG_BUSY}% busy, so it was never meaningfully loaded."
        log_result "HINT: Check that $GPU_WORKER was rendering (output in $GPU_WORKER_LOG) and not"
        log_result "HINT: frame-capped by vsync. Start it by hand in the desktop session and re-run."
        case "$GPU_WORKER" in memtest_vulkan|vkpeak) ;; *)
            log_result "HINT: $GPU_WORKER renders one light frame at a time and can't keep this GPU busy."
            log_result "HINT: Put memtest_vulkan (github.com/GpuZelenograd/memtest_vulkan) on PATH, e.g. in ~/.local/bin;"
            log_result "HINT: it is preferred automatically and also checks the VRAM for errors." ;;
        esac
        log_result "HINT: The CPU results above are still valid; the GPU verdict is not."
        WARN_FOUND=true
    elif [ "$MAX_SCLK" -le "$((MIN_SCLK + 100))" ] && [ -n "$GOV_TOP" ] && [ "$MAX_SCLK" -ge "$((GOV_TOP - 100))" ]; then
        # A clock pinned at the governor's ceiling for the whole run is the right response to full load.
        log_result "SUCCESS: The GPU was ${AVG_BUSY}% busy and held the governor maximum (~${MAX_SCLK} of ${GOV_TOP} MHz) throughout."
    elif [ "$MAX_SCLK" -le "$((MIN_SCLK + 100))" ]; then
        log_result "WARNING: The GPU was ${AVG_BUSY}% busy but the clock stayed at ~${MAX_SCLK} MHz."
        log_result "HINT: The governor is not reacting to load. Check cyan-skillfish-governor-smu."
        WARN_FOUND=true
    else
        log_result "SUCCESS: The GPU was loaded to ${MAX_BUSY}% and the clock responded (${MIN_SCLK} -> ${MAX_SCLK} MHz)."
    fi
    # Sustained performance: the average clock over the first loaded minute vs the last minute.
    # A clock that sags as heat builds up is throttling the stress run's averages would hide.
    if [ "${ELAPSED:-0}" -ge 120 ] && { [ "$BUSY_SRC" = "none" ] || [ "$AVG_BUSY" -ge 50 ]; }; then
        read -r SUST_EARLY SUST_LATE <<<"$(awk -F, -v end="$ELAPSED" '
            NR > 1 && $2 > 0 && $1 >= 10 && $1 < 60     { es += $2; en++ }
            NR > 1 && $2 > 0 && $1 >= end - 50          { ls += $2; lc++ }
            END { printf "%d %d", (en ? es / en : 0), (lc ? ls / lc : 0) }' "$STRESS_CSV")"
        if [ "${SUST_EARLY:-0}" -gt 0 ] && [ "${SUST_LATE:-0}" -gt 0 ]; then
            SUST_PCT=$((SUST_LATE * 100 / SUST_EARLY))
            if [ "$SUST_PCT" -ge 97 ]; then
                log_result "SUCCESS: Sustained performance: the clock held ${SUST_PCT}% of its first-minute average (${SUST_EARLY} -> ${SUST_LATE} MHz); no thermal sag."
            elif [ "$SUST_PCT" -ge 90 ]; then
                log_result "NOTE: Sustained performance: the clock sagged to ${SUST_PCT}% of its first-minute average (${SUST_EARLY} -> ${SUST_LATE} MHz) as heat built up."
            else
                log_result "WARNING: Sustained performance: the clock dropped to ${SUST_PCT}% of its first-minute average (${SUST_EARLY} -> ${SUST_LATE} MHz)."
                log_result "HINT: That is thermal or power throttling under sustained load: long game sessions will run slower"
                log_result "HINT: than benchmarks suggest. Check airflow, the heatsink mount and the fan curve (tests 22, 40)."
                WARN_FOUND=true
            fi
        fi
    fi
    # Stalls: the load stopped mid-run (GPU <10% busy for 3+ samples in a row, after the first 10 s).
    # A short pause hides in the averages, so list each one with what the system logged around it.
    if [ "$BUSY_SRC" != "none" ] && [ "$AVG_BUSY" -ge 50 ]; then
        STALLS=$(awk -F, 'NR > 1 && $1 >= 10 {
                if ($4 != "" && $4 < 10) { if (!n) s = $1; n++; e = $1 }
                else { if (n >= 3) print s, e; n = 0 } }
            END { if (n >= 3) print s, e }' "$STRESS_CSV")
        if [ -n "$STALLS" ]; then
            S_REAL=false
            while read -r S_FROM S_TO; do
                # memtest_vulkan pauses ~12 s when its standard 5-minute test passes and it re-allocates
                # for the endless test; seen at t=274-286 s in every 36-CU run. Not a fault.
                if [ "$GPU_WORKER" = "memtest_vulkan" ] && [ "$S_FROM" -ge 250 ] && [ "$S_FROM" -le 320 ] \
                   && [ $((S_TO - S_FROM)) -le 30 ]; then
                    log_result "INFO: The GPU load paused from t=${S_FROM}s to t=${S_TO}s: memtest_vulkan switching from its standard 5-minute test to its extended test (expected, not a fault)."
                    continue
                fi
                S_REAL=true
                log_result "WARNING: The GPU load stopped from t=${S_FROM}s to t=${S_TO}s ($(date -d "@$((START + S_FROM))" '+%H:%M:%S')-$(date -d "@$((START + S_TO))" '+%H:%M:%S')): the GPU went idle and the clock dropped, but nothing hung."
                S_LOG=$(journalctl --no-pager -q -o short-precise --since "@$((START + S_FROM - 10))" --until "@$((START + S_TO + 5))" 2>/dev/null | \
                    grep -Ev "sudo|pam_unix|bc250|test-bazzite" | tail -15)
                if [ -n "$S_LOG" ]; then
                    log_result "INFO: System journal around the stall:"
                    echo "$S_LOG" | tee -a "$LOG_FILE"
                fi
            done <<< "$STALLS"
            if [ "$S_REAL" = true ]; then
                log_result "HINT: Common causes are the screen locking or blanking, the GPU load tool pausing, or a GPU stall that recovered. Check $GPU_WORKER_LOG and the journal lines above."
                WARN_FOUND=true
            fi
        fi
    fi
    if [ "$MAX_SCLK" -ge 1900 ]; then
        log_result "WARNING: The GPU hit ${MAX_SCLK} MHz. Many BC-250 boards hard-lock above ~1850 MHz."
        log_result "HINT: Lower the maximum in /etc/cyan-skillfish-governor-smu/config.toml and retest."
        WARN_FOUND=true
    fi
else
    log_result "ERROR: No telemetry samples were collected."
    ERROR_FOUND=true
fi

if [ "$GPU_WORKER" = "memtest_vulkan" ]; then
    if grep -q 'Error found' "$GPU_WORKER_LOG" 2>/dev/null; then
        log_result "ERROR: memtest_vulkan found VRAM errors under load:"
        grep -A1 'Error found' "$GPU_WORKER_LOG" | head -10 | tee -a "$LOG_FILE"
        log_result "HINT: Lower the GPU maximum clock (and any CU unlock) and retest; see $GPU_WORKER_LOG."
        ERROR_FOUND=true
    else
        log_result "SUCCESS: memtest_vulkan found no VRAM errors during the run."
    fi
    # Collect memtest_vulkan's own log (more detail than its stdout). Read it as the user, never as
    # root: the work dir belongs to the user and a symlink there must not let root read other files.
    MEMTEST_LOG=""
    if [ -n "${MEMTEST_WORKDIR:-}" ]; then
        if sudo -u "$GAME_USER" test -s "$MEMTEST_WORKDIR/memtest_vulkan.log"; then
            MEMTEST_LOG="$LOG_DIR/bc250-memtest-${TIMESTAMP}.log"
            if sudo -u "$GAME_USER" cat -- "$MEMTEST_WORKDIR/memtest_vulkan.log" > "$MEMTEST_LOG"; then
                chmod 644 "$MEMTEST_LOG" 2>/dev/null
                log_result "INFO: memtest_vulkan's own log saved to $MEMTEST_LOG"
            else
                rm -f -- "$MEMTEST_LOG"; MEMTEST_LOG=""
            fi
        fi
        sudo -u "$GAME_USER" rm -rf -- "$MEMTEST_WORKDIR" 2>/dev/null
    fi
fi
log_result "Check for faults logged during the stress run"
POST=$(journalctl -k --no-pager -q --since "@$START" 2>/dev/null | \
    grep -EI "$GPU_HANG_RE|$PANIC_RE|throttl|Out of memory|oom-kill" | head -40)
if [ -n "$POST" ]; then
    log_result "ERROR: Faults were logged while the board was under load:"
    echo "$POST" | tee -a "$LOG_FILE"
    ERROR_FOUND=true
else
    log_result "SUCCESS: No GPU hangs, panics, throttling or OOM events during the stress run."
fi
[ "$STRESS_ABORT" = true ] && log_result "WARNING: The run was cut short by the $STRESS_ABORT_REASON."
echo
fi
fi  # TEST 41
if want 42; then
log_result "[TEST 42] Performance Benchmark (CPU and GPU score)"
if [ "$BENCH_MODE" != true ]; then
    log_howto "INFO: Skipped. Re-run with --bench to measure CPU and GPU performance and score it" \
              "INFO: Skipped. Start test 42 (Performance page) to measure CPU and GPU performance and score it"
    log_result "INFO: against a stock BC-250 (6C/12T, 24 CUs)."
    echo
else
log_result "Measuring fixed CPU and GPU workloads; compare runs before and after a CU or core unlock"
log_result "NOTE: Close games and other heavy apps first; background load lowers the scores."
BENCH_JSON="$LOG_DIR/bc250-bench-${TIMESTAMP}.json"
BENCH_HISTORY="$LOG_DIR/bc250-bench-history.csv"
BENCH_VKPEAK_LOG="$LOG_DIR/bc250-bench-vkpeak-${TIMESTAMP}.log"
BENCH_TMP=$(mktemp -d)

# ---- configuration ---------------------------------------------------------
B_THREADS=$(nproc)
B_CORES=$(lscpu 2>/dev/null | awk -F: '/^Core\(s\) per socket/ {c=$2} /^Socket\(s\)/ {s=$2} END {gsub(/ /,"",c); gsub(/ /,"",s); if (c && s) print c*s}')
B_CORES=${B_CORES:-$B_THREADS}
B_CPU_MODEL=$(awk -F: '/^model name/ {sub(/^ +/, "", $2); print $2; exit}' /proc/cpuinfo)
# CU count: the value test 21 found (live registers when it could read them). Without test 21 (a
# benchmark-only run), the live registers are read here, so a runtime CU unlock is scored as such; the
# kernel's probe value is the last resort, as it stays at 24 after a runtime unlock.
B_CUS="${CU_COUNT:-}"
if [ -z "$B_CUS" ] && ! want 21 && [ "$(id -u)" = 0 ] && [ -n "$CU_UMR" ] && root_safe "$CU_UMR" && read_live_cus; then
    B_CUS="$CU_LIVE"
    log_result "INFO: CU count from the live WGP masks (umr): $CU_LIVE (${CU_ROWS%, } CUs)."
fi
[ -z "$B_CUS" ] && B_CUS=$(journalctl -b -k --no-pager 2>/dev/null | grep -oE "active_cu_number [0-9]+" | tail -1 | grep -oE "[0-9]+")
B_GOV_MAX=""
[ -r /etc/cyan-skillfish-governor-smu/config.toml ] && \
    B_GOV_MAX=$(grep -oE "max[_a-z]*\s*=\s*[0-9]+" /etc/cyan-skillfish-governor-smu/config.toml | grep -oE "[0-9]+" | sort -rn | head -1)
B_MITIGATIONS="on"
grep -qw "mitigations=off" /proc/cmdline && B_MITIGATIONS="off"
log_result "INFO: Configuration: $B_CPU_MODEL, ${B_CORES}C/${B_THREADS}T, ${B_CUS:-unknown} CUs, governor max ${B_GOV_MAX:-unknown} MHz, mitigations $B_MITIGATIONS, kernel $(uname -r)"
B_LOAD=$(awk '{print $1}' /proc/loadavg)
if awk -v l="$B_LOAD" 'BEGIN {exit !(l > 1.5)}'; then
    log_result "WARNING: The system is not idle (load average $B_LOAD); scores will be lower than they should be."
    WARN_FOUND=true
fi

# ---- CPU: stress-ng matrixprod, 1 thread, then every thread ---------------
# A fixed method keeps runs comparable. bogo ops/s (real time) from the YAML report.
bench_cpu() {
    local yaml="$BENCH_TMP/cpu-$1.yaml" out="$BENCH_TMP/cpu-$1.txt" v
    # A user-installed stress-ng runs as the desktop user (find_tool), which cannot write into root's
    # temp folder: give it a YAML file of its own.
    if $STRESSNG_AS_USER; then
        yaml=$(sudo -u "$GAME_USER" mktemp 2>/dev/null) || yaml=/nonexistent
    fi
    "${STRESSNG[@]}" --cpu "$1" --cpu-method matrixprod --timeout "${BENCH_SECONDS}s" \
        --metrics-brief --yaml "$yaml" >"$out" 2>&1
    v=$(awk '/bogo-ops-per-second-real-time:/ {printf "%.1f", $2; exit}' "$yaml" 2>/dev/null)
    $STRESSNG_AS_USER && [ "$yaml" != /nonexistent ] && sudo -u "$GAME_USER" rm -f -- "$yaml"
    # Fallback, the metrics table: "... cpu <bogo ops> <real s> <usr s> <sys s> <ops/s real> <ops/s usr+sys>"
    [ -z "$v" ] && v=$(awk '{for (i = 1; i <= NF; i++) if ($i == "cpu" && $(i+1) ~ /^[0-9]+$/) {printf "%.1f", $(i+5); exit}}' "$out")
    echo "$v"
}
B_CPU_SINGLE=""; B_CPU_MULTI=""
if find_tool stress-ng; then
    STRESSNG=("${TOOL_CMD[@]}"); STRESSNG_AS_USER=$TOOL_AS_USER
    log_result "CPU: stress-ng matrixprod on 1 thread for ${BENCH_SECONDS}s"
    B_CPU_SINGLE=$(bench_cpu 1)
    log_result "CPU: stress-ng matrixprod on $B_THREADS threads for ${BENCH_SECONDS}s"
    B_CPU_MULTI=$(bench_cpu "$B_THREADS")
    if [ -n "$B_CPU_SINGLE" ] && [ -n "$B_CPU_MULTI" ]; then
        log_result "INFO: CPU single-thread: $B_CPU_SINGLE ops/s | multi-thread: $B_CPU_MULTI ops/s ($(awk -v m="$B_CPU_MULTI" -v s="$B_CPU_SINGLE" 'BEGIN {printf "%.1f", m/s}')x)"
    else
        log_result "WARNING: stress-ng ran but reported no metrics; no CPU score."
        WARN_FOUND=true
    fi
else
    log_result "WARNING: stress-ng is not installed; no CPU score."
    log_result "HINT: rpm-ostree install stress-ng   (then reboot), or: brew install stress-ng"
    WARN_FOUND=true
fi

# ---- GPU: vkpeak FP32 compute + device-to-device copy ---------------------
# FP32 throughput scales with CUs x clock, so it shows exactly what a CU unlock adds.
# The clock is sampled during the run, so a throttled or capped clock is visible in the result.
B_GPU_FP32=""; B_GPU_BW=""; B_GPU_MHZ=""
if find_tool vkpeak; then
    VKPEAK=("${TOOL_CMD[@]}")
    log_result "GPU: vkpeak fp32-scalar, fp32-vec4 and copy-d2d"
    ( while :; do grep '\*' "$GPU_DEV/pp_dpm_sclk" 2>/dev/null | head -1 | awk '{print $2}' | tr -dc '0-9'; echo; sleep 1; done ) \
        >"$BENCH_TMP/sclk" 2>/dev/null &
    SCLK_PID=$!
    # Newer vkpeak takes a scenario list; older builds ignore it or reject it, so fall back to all.
    timeout 300 "${VKPEAK[@]}" 0 fp32-scalar,fp32-vec4,copy-d2d >"$BENCH_VKPEAK_LOG" 2>&1
    if ! grep -qE '^fp32-(scalar|vec4) *= *[0-9.]+' "$BENCH_VKPEAK_LOG"; then
        timeout 600 "${VKPEAK[@]}" 0 >"$BENCH_VKPEAK_LOG" 2>&1
    fi
    kill "$SCLK_PID" 2>/dev/null; wait "$SCLK_PID" 2>/dev/null
    B_GPU_FP32=$(awk -F= '/^fp32-(scalar|vec4)/ {v=$2+0; if (v > m) m = v} END {if (m > 0) printf "%.1f", m}' "$BENCH_VKPEAK_LOG")
    B_GPU_BW=$(awk -F= '/^copy-d2d/ {v=$2+0; if (v > 0) printf "%.1f", v}' "$BENCH_VKPEAK_LOG")
    # Average of the samples above the idle floor, i.e. while vkpeak was actually working.
    B_GPU_MHZ=$(awk 'NF && $1 > 0 {a[NR]=$1; if ($1 > m) m = $1} END {for (i in a) if (a[i] >= m*0.8) {s+=a[i]; n++} if (n) printf "%.0f", s/n}' "$BENCH_TMP/sclk")
    if [ -n "$B_GPU_FP32" ]; then
        log_result "INFO: GPU FP32: $B_GPU_FP32 GFLOPS${B_GPU_BW:+ | VRAM copy: $B_GPU_BW GB/s}${B_GPU_MHZ:+ | clock under load: ~$B_GPU_MHZ MHz}"
        if [ -n "$B_CUS" ] && [ -n "$B_GPU_MHZ" ]; then
            # RDNA: 64 lanes x 2 FLOP (FMA) per CU per clock.
            B_GPU_PEAK=$(awk -v c="$B_CUS" -v f="$B_GPU_MHZ" 'BEGIN {printf "%.0f", c * 128 * f / 1000}')
            B_GPU_EFF=$(awk -v m="$B_GPU_FP32" -v p="$B_GPU_PEAK" 'BEGIN {printf "%.0f", 100 * m / p}')
            log_result "INFO: Theoretical FP32 for $B_CUS CUs at $B_GPU_MHZ MHz: $B_GPU_PEAK GFLOPS; measured $B_GPU_EFF% of it."
            if [ "$B_GPU_EFF" -lt 75 ]; then
                log_result "NOTE: Well below the theoretical peak: unlocked CUs that are not routed do no work,"
                log_result "NOTE: and a clock that drops during the run lowers the result too."
            fi
        fi
    else
        log_result "WARNING: vkpeak ran but reported no FP32 result; no GPU score. See $BENCH_VKPEAK_LOG."
        head -10 "$BENCH_VKPEAK_LOG" | tee -a "$LOG_FILE"
        WARN_FOUND=true
    fi
else
    log_result "WARNING: vkpeak is not installed; no GPU score."
    log_result "HINT: Download the Linux build from https://github.com/nihui/vkpeak/releases,"
    log_result "HINT: unzip it and copy vkpeak to ~/.local/bin (chmod +x ~/.local/bin/vkpeak)."
    WARN_FOUND=true
fi

# ---- score against the baseline --------------------------------------------
# A baseline saved by an older version next to the script: move it to $BENCH_BASELINE. That folder may
# belong to the user, so the file is read as the user (a symlink to a root-only file then fails instead
# of being copied into a world-readable file) and only a JSON object with numeric results is accepted.
bench_load_legacy_baseline() {
    [ -e "$BENCH_BASELINE" ] && return
    [ -f "$BENCH_BASELINE_OLD" ] || return
    local raw clean
    if [ "$(id -u)" = 0 ] && [ -n "$GAME_USER" ] && [ "$GAME_USER" != root ]; then
        raw=$(sudo -u "$GAME_USER" cat -- "$BENCH_BASELINE_OLD" 2>/dev/null | head -c 65536)
    else
        raw=$(head -c 65536 -- "$BENCH_BASELINE_OLD" 2>/dev/null)
    fi
    clean=$(python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except ValueError:
    sys.exit(1)
if not isinstance(d, dict):
    sys.exit(1)
d = {str(k)[:40]: v for k, v in d.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool)}
d = {k: (v[:120] if isinstance(v, str) else v) for k, v in d.items()}
if not all(isinstance(d.get(k), (int, float)) and d[k] > 0 for k in ("cpu_multi", "gpu_fp32")):
    sys.exit(1)
print(json.dumps(d, indent=2))' <<<"$raw" 2>/dev/null) || {
        log_result "WARNING: $BENCH_BASELINE_OLD is not a valid benchmark baseline; ignored."
        WARN_FOUND=true
        return
    }
    if (umask 022; printf '%s\n' "$clean" > "$BENCH_BASELINE"); then
        log_howto "INFO: Baseline moved to $BENCH_BASELINE (was $BENCH_BASELINE_OLD); every copy of the script now uses it." \
                  "INFO: Baseline moved to $BENCH_BASELINE (was $BENCH_BASELINE_OLD); every run now uses it."
    fi
}
bench_load_legacy_baseline
json_num() { grep -oE "\"$1\"[[:space:]]*:[[:space:]]*[0-9.]+" "$BENCH_BASELINE" 2>/dev/null | head -1 | grep -oE '[0-9.]+$'; }
ratio() { [ -n "$1" ] && [ -n "$2" ] && awk -v a="$1" -v b="$2" 'BEGIN {if (b > 0) printf "%.0f", 100 * a / b}'; }
B_CPU_SCORE=""; B_CPU1_SCORE=""; B_GPU_SCORE=""
if [ "$BENCH_SAVE_BASELINE" != true ] && [ -r "$BENCH_BASELINE" ]; then
    B_CPU1_SCORE=$(ratio "$B_CPU_SINGLE" "$(json_num cpu_single)")
    B_CPU_SCORE=$(ratio "$B_CPU_MULTI" "$(json_num cpu_multi)")
    B_GPU_SCORE=$(ratio "$B_GPU_FP32" "$(json_num gpu_fp32)")
    BASE_DESC="$(json_num cores)C/$(json_num threads)T, $(json_num cus) CUs, $(json_num gpu_mhz) MHz"
    log_result "INFO: Baseline: $BASE_DESC ($BENCH_BASELINE = 100)"
    [ -n "$B_CPU_SCORE" ] && log_result "SUCCESS: CPU score: $B_CPU_SCORE (multi-thread; single-thread: ${B_CPU1_SCORE:-n/a})"
    [ -n "$B_GPU_SCORE" ] && log_result "SUCCESS: GPU score: $B_GPU_SCORE (FP32 compute)"
elif [ "$BENCH_SAVE_BASELINE" != true ]; then
    log_result "INFO: No baseline yet ($BENCH_BASELINE), so no scores; the raw results are saved."
    log_howto "NOTE: Run the benchmark once with --save-baseline on a stock board (24 CUs, 6C/12T," \
              "NOTE: Tick 'Save as baseline' and run the benchmark once on a stock board (24 CUs, 6C/12T,"
    log_result "NOTE: governor max 1850 MHz). Every later run is then scored against it (stock = 100)."
fi

# ---- comparison ladder ------------------------------------------------------
# Where this board sits next to known gaming systems. The references are published THEORETICAL
# FP32 peaks; vkpeak measures real achievable FP32, which lands somewhat below a chip's theoretical
# number, so the percentages are approximate positioning, not FPS predictions: memory bandwidth,
# drivers, the Vulkan feature set (test 47) and the CPU decide actual game performance.
if [ -n "$B_GPU_FP32" ]; then
    B_GPU_TF=$(awk -v g="$B_GPU_FP32" 'BEGIN {printf "%.2f", g / 1000}')
    log_result "INFO: GPU compute ladder: this board measured $B_GPU_FP32 GFLOPS (${B_GPU_TF} TFLOPS) FP32."
    while IFS='|' read -r REF_NAME REF_GF; do
        [ -n "$REF_GF" ] || continue
        PCT=$(awk -v m="$B_GPU_FP32" -v r="$REF_GF" 'BEGIN {printf "%.0f", 100 * m / r}')
        log_result "INFO:   ~${PCT}% of a $REF_NAME ($(awk -v r="$REF_GF" 'BEGIN {printf "%.1f", r / 1000}') TFLOPS theoretical)"
    done <<'LADDER'
Steam Deck (RDNA2, 8 CU)|1600
Xbox Series S (RDNA2, 20 CU)|4000
stock BC-250 ceiling (24 CU at 1850 MHz)|5680
Steam Machine (announced, RDNA3 semi-custom, 28 CU)|8600
PS5 (RDNA2, 36 CU)|10300
GeForce RTX 4060 (desktop)|15100
GeForce RTX 4090 (desktop)|82600
LADDER
    log_result "NOTE: FP32 ranks raw shader compute only. The BC-250 is a cut-down PS5 SoC with console-class"
    log_result "NOTE: GDDR6 bandwidth; the Vulkan feature matrix (test 47) and the UMA memory split set the real"
    log_result "NOTE: game limit. RDNA3 dual-issue peaks (Steam Machine, RTX-class marketing numbers) overstate"
    log_result "NOTE: per-CU game performance, so treat those rungs as optimistic for the reference system."
fi

# ---- save ------------------------------------------------------------------
B_DATE=$(date '+%Y-%m-%d %H:%M:%S')
B_KERNEL=$(uname -r)
cat >"$BENCH_JSON" <<JSON
{
  "date": "$B_DATE",
  "cpu_model": "$B_CPU_MODEL",
  "cores": ${B_CORES:-0},
  "threads": ${B_THREADS:-0},
  "cus": ${B_CUS:-0},
  "gpu_max_mhz": ${B_GOV_MAX:-0},
  "gpu_mhz": ${B_GPU_MHZ:-0},
  "mitigations": "$B_MITIGATIONS",
  "kernel": "$B_KERNEL",
  "bench_seconds": $BENCH_SECONDS,
  "cpu_single": ${B_CPU_SINGLE:-0},
  "cpu_multi": ${B_CPU_MULTI:-0},
  "gpu_fp32": ${B_GPU_FP32:-0},
  "gpu_copy_gbps": ${B_GPU_BW:-0}
}
JSON
[ -f "$BENCH_HISTORY" ] || echo "date,cores,threads,cus,gpu_max_mhz,gpu_mhz,mitigations,cpu_single,cpu_multi,gpu_fp32,gpu_copy_gbps,cpu_score,gpu_score,kernel" >"$BENCH_HISTORY"
echo "$B_DATE,${B_CORES},${B_THREADS},${B_CUS},${B_GOV_MAX},${B_GPU_MHZ},$B_MITIGATIONS,${B_CPU_SINGLE},${B_CPU_MULTI},${B_GPU_FP32},${B_GPU_BW},${B_CPU_SCORE},${B_GPU_SCORE},$B_KERNEL" >>"$BENCH_HISTORY"
chmod 644 "$BENCH_JSON" "$BENCH_HISTORY" "$BENCH_VKPEAK_LOG" 2>/dev/null
log_result "INFO: Result saved to $BENCH_JSON; all runs are listed in $BENCH_HISTORY."
# One machine-readable line for the GUI.
log_result "BENCH: cpu_single=${B_CPU_SINGLE} cpu_multi=${B_CPU_MULTI} gpu_fp32=${B_GPU_FP32} gpu_copy=${B_GPU_BW} cpu_score=${B_CPU_SCORE} cpu1_score=${B_CPU1_SCORE} gpu_score=${B_GPU_SCORE} cores=${B_CORES} threads=${B_THREADS} cus=${B_CUS} gpu_mhz=${B_GPU_MHZ}"

if [ "$BENCH_SAVE_BASELINE" = true ]; then
    if [ -z "$B_CPU_MULTI" ] || [ -z "$B_GPU_FP32" ]; then
        log_result "ERROR: Baseline NOT saved: both a CPU and a GPU result are needed."
        ERROR_FOUND=true
    else
        if [ "$B_CUS" != 24 ] || [ "$B_THREADS" != 12 ]; then
            log_result "WARNING: This board is not in the stock configuration (${B_CUS:-?} CUs, $B_THREADS threads);"
            log_result "WARNING: the baseline is saved anyway, but scores will be relative to this setup."
            WARN_FOUND=true
        fi
        # Root-owned log folder: no chown, and nothing is written into the user's folders as root.
        rm -f -- "$BENCH_BASELINE"
        (umask 022; cp -- "$BENCH_JSON" "$BENCH_BASELINE")
        log_result "SUCCESS: Saved as the baseline: $BENCH_BASELINE (scores of later runs are relative to this = 100)."
    fi
fi
rm -rf "$BENCH_TMP"
echo
fi
fi  # TEST 42
if want 43; then
log_result "[TEST 43] Disk Speed Test (read, write, SLC cache)"
if [ "$DISK_MODE" != true ]; then
    log_howto "INFO: Skipped. Re-run with --disk-bench to measure read speed (nothing is written), or with" \
              "INFO: Skipped. Start test 43 (Storage and memory page) to measure read speed (nothing is written); tick"
    log_howto "INFO: --disk-write=GiB to also write GiB to a temporary file and measure write speed and the SLC cache." \
              "INFO: 'also test writes' to also write a temporary file and measure write speed and the SLC cache."
    echo
else
DISK_TMPDIR=/var/tmp
D_SRC=$(findmnt -no SOURCE -T "$DISK_TMPDIR" 2>/dev/null | sed 's/\[.*\]$//')
D_FSTYPE=$(findmnt -no FSTYPE -T "$DISK_TMPDIR" 2>/dev/null)
# Walk from the filesystem (possibly LUKS/LVM) down to its partition and disk.
D_PARTNAME=$(lsblk -snlo NAME,TYPE "$D_SRC" 2>/dev/null | awk '$2=="part" {print $1; exit}')
D_NAME=$(lsblk -snlo NAME,TYPE "$D_SRC" 2>/dev/null | awk '$2=="disk" {print $1; exit}')
if [ -z "$D_NAME" ]; then
    log_result "ERROR: Could not find the disk that holds $DISK_TMPDIR (source: ${D_SRC:-unknown})."
    ERROR_FOUND=true
    echo
else
D_DISK="/dev/$D_NAME"
D_PART="/dev/${D_PARTNAME:-$D_NAME}"
D_MODEL=$(lsblk -dno MODEL "$D_DISK" 2>/dev/null | sed 's/[[:space:]]*$//')
D_CTRL=""; [[ "$D_NAME" == nvme* ]] && D_CTRL="${D_NAME%n[0-9]*}"
log_result "Testing $D_DISK (${D_MODEL:-unknown model}), the disk that holds the system; reading from $D_PART."

disk_temp() {
    local h
    for h in /sys/class/nvme/"$D_CTRL"/hwmon*/temp1_input /sys/class/nvme/"$D_CTRL"/device/hwmon/hwmon*/temp1_input \
             /sys/block/"$D_NAME"/device/hwmon/hwmon*/temp1_input; do
        [ -n "$D_CTRL" ] || [[ "$h" == /sys/block/* ]] || continue
        [ -r "$h" ] && { echo $(( $(read_num_g "$h") / 1000 )); return; }
    done
}
D_WARN_T=70; D_CRIT_T=80
if [ -n "$D_CTRL" ] && command -v nvme >/dev/null 2>&1; then
    read -r _w _c < <(nvme id-ctrl "/dev/$D_CTRL" -o json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(int(d["wctemp"]) - 273, int(d["cctemp"]) - 273)
except Exception:
    pass' 2>/dev/null)
    [ "${_w:-0}" -gt 0 ] 2>/dev/null && D_WARN_T=$_w
    [ "${_c:-0}" -gt 0 ] 2>/dev/null && D_CRIT_T=$_c
fi
LINK_MBPS=""
if [ -n "$D_CTRL" ]; then
    _pdev=$(readlink -f "/sys/class/nvme/$D_CTRL/device" 2>/dev/null)
    LINK_MBPS=$(awk -v s="$(awk '{print $1}' "$_pdev/current_link_speed" 2>/dev/null)" -v w="$(cat "$_pdev/current_link_width" 2>/dev/null)" \
        'BEGIN { if (s > 0 && w > 0) print int((s >= 32 ? 3938 : s >= 16 ? 1969 : s >= 8 ? 985 : s >= 5 ? 500 : 250) * w) }')
fi
T0=$(disk_temp)
[ -n "$T0" ] && log_result "INFO: Drive temperature before the test: ${T0} °C (warning ${D_WARN_T} °C)."

# ---- sequential read: raw partition, direct I/O, nothing is written --------
D_SIZE_MIB=$(( $(blockdev --getsize64 "$D_PART" 2>/dev/null || echo 0) / 1048576 ))
READ_MIB=4096; [ "$D_SIZE_MIB" -gt 64 ] && [ "$READ_MIB" -gt $((D_SIZE_MIB - 32)) ] && READ_MIB=$(( (D_SIZE_MIB - 32) / 4 * 4 ))
t0=$(date +%s%N)
if dd if="$D_PART" of=/dev/null bs=4M count=$((READ_MIB / 4)) iflag=direct status=none 2>>"$LOG_FILE"; then
    t1=$(date +%s%N)
    READ_MBPS=$(awk -v b=$((READ_MIB * 1048576)) -v ns=$((t1 - t0)) 'BEGIN { printf "%d", b / (ns / 1e9) / 1e6 }')
    log_result "SUCCESS: Sequential read: ${READ_MBPS} MB/s (${READ_MIB} MiB, 4 MiB blocks, direct I/O)."
    if [ -n "$LINK_MBPS" ]; then
        log_result "INFO: That is $(( READ_MBPS * 100 / LINK_MBPS ))% of the PCIe link ceiling (~${LINK_MBPS} MB/s)."
    fi
    if [ -n "$D_CTRL" ] && [ "$READ_MBPS" -lt 300 ]; then
        log_result "WARNING: Very slow for an NVMe drive. Check the PCIe link in test 10 and the drive temperature."
        WARN_FOUND=true
    fi
else
    log_result "ERROR: Reading $D_PART failed (see the dd error above)."
    ERROR_FOUND=true
fi

# ---- random 4K read (fio, read-only) ----------------------------------------
# fio reads the raw partition, which needs root. A fio in ~/.local/bin or Homebrew is writable by the
# user and is never run as root (see find_tool), and as the user it cannot open the partition.
FIO_FOUND=false; find_tool fio && FIO_FOUND=true
if $FIO_FOUND && $TOOL_AS_USER; then
    log_result "INFO: Random 4K read skipped: $TOOL is user-installed, and it is never run as root."
    log_result "HINT: For this test install fio system-wide: rpm-ostree install fio   (then reboot)"
elif $FIO_FOUND; then
    FIO_BIN=$TOOL
    for qd in 1 32; do
        read -r R_IOPS R_LAT < <("$FIO_BIN" --name=rand4k --filename="$D_PART" --readonly --direct=1 --rw=randread --bs=4k \
            --iodepth=$qd --ioengine=libaio --runtime=10 --time_based --output-format=json 2>/dev/null | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)["jobs"][0]["read"]
    lat = r.get("clat_ns", r.get("lat_ns", {})).get("mean", 0) / 1000
    print(int(r["iops"]), int(lat))
except Exception:
    pass' 2>/dev/null)
        if [ -n "$R_IOPS" ]; then
            log_result "SUCCESS: Random 4K read, queue depth $qd: ${R_IOPS} IOPS ($(( R_IOPS * 4096 / 1000000 )) MB/s, ${R_LAT} µs average latency)."
            [ "$qd" = 1 ] && RAND_QD1_LAT=$R_LAT
        else
            log_result "WARNING: fio random read (queue depth $qd) failed."
            WARN_FOUND=true
        fi
    done
    if [ -n "${RAND_QD1_LAT:-}" ] && [ "$RAND_QD1_LAT" -gt 150 ]; then
        log_result "NOTE: Random reads across the whole partition average ${RAND_QD1_LAT} µs; DRAM-less drives without a host memory buffer are typically this slow (drives with DRAM or HMB: ~50-100 µs)."
    fi
else
    log_result "INFO: Random 4K read skipped: fio is not installed."
    log_result "HINT: rpm-ostree install fio   (then reboot). A Homebrew fio is not used: it would have to run as root."
fi

# ---- sequential write + SLC cache: temporary file, removed afterwards -------
if [ "${DISK_WRITE_GIB:-0}" -gt 0 ]; then
    D_FILE="$DISK_TMPDIR/bc250-disk-bench-${TIMESTAMP}.bin"
    DISK_CSV="$LOG_DIR/bc250-disk-${TIMESTAMP}.csv"
    AVAIL=$(df -B1 --output=avail "$DISK_TMPDIR" 2>/dev/null | tail -1 | tr -dc '0-9')
    if [ "${AVAIL:-0}" -lt $(( (DISK_WRITE_GIB + 5) * 1073741824 )) ]; then
        log_result "WARNING: Write test skipped: it needs ${DISK_WRITE_GIB} GiB plus 5 GiB spare in $DISK_TMPDIR, only $(( ${AVAIL:-0} / 1073741824 )) GiB is free."
        WARN_FOUND=true
    else
        : > "$D_FILE"
        # btrfs compresses by default on Bazzite; No_COW turns compression and checksums off for this
        # file, otherwise the zeros written below would shrink to nothing and the result would be fake.
        chattr +C "$D_FILE" 2>/dev/null
        if [ "$D_FSTYPE" = btrfs ] && ! lsattr "$D_FILE" 2>/dev/null | awk '{print $1}' | grep -q C; then
            log_result "WARNING: Write test skipped: could not disable btrfs compression on the test file (chattr +C)."
            WARN_FOUND=true
            rm -f "$D_FILE"
        else
            log_result "Writing ${DISK_WRITE_GIB} GiB to $D_FILE in 256 MiB chunks (direct I/O, flushed); telemetry in $DISK_CSV"
            trap 'rm -f "$D_FILE"; log_result "Disk test interrupted; removed $D_FILE."; exit 130' INT TERM
            echo "elapsed_s,written_gib,write_mbps,drive_temp_c" > "$DISK_CSV"
            CHUNKS=$(( DISK_WRITE_GIB * 4 )); STEP=4; [ "$CHUNKS" -gt 64 ] && STEP=16
            W_START=$(date +%s%N); W_STOP=""
            for ((i = 0; i < CHUNKS; i++)); do
                t0=$(date +%s%N)
                if ! dd if=/dev/zero of="$D_FILE" bs=4M count=64 seek=$((i * 64)) oflag=direct conv=notrunc,fdatasync status=none 2>>"$LOG_FILE"; then
                    W_STOP="the write failed (see the dd error above)"; break
                fi
                t1=$(date +%s%N)
                T=$(disk_temp)
                MBPS=$(awk -v ns=$((t1 - t0)) 'BEGIN { printf "%d", 268435456 / (ns / 1e9) / 1e6 }')
                awk -v e=$((t1 - W_START)) -v g=$((i + 1)) -v m="$MBPS" -v t="$T" 'BEGIN { printf "%.1f,%.2f,%d,%s\n", e / 1e9, g / 4, m, t }' >> "$DISK_CSV"
                (( (i + 1) % STEP == 0 )) && log_result "Written $(( (i + 1) / 4 )) GiB: ${MBPS} MB/s, drive ${T:-?} °C"
                if [ -n "$T" ] && [ "$T" -ge "$D_CRIT_T" ]; then
                    W_STOP="the drive reached ${T} °C (critical ${D_CRIT_T} °C)"; break
                fi
            done
            rm -f "$D_FILE"
            trap - INT TERM
            sync
            chmod 644 "$DISK_CSV" 2>/dev/null
            if [ -n "$W_STOP" ]; then
                log_result "WARNING: Write test stopped early: $W_STOP."
                WARN_FOUND=true
            fi
            # Burst = chunks 2..n/4 (the first includes file allocation); sustained = the last quarter.
            # The cache ends at the first chunk pair averaging below 60% of the burst speed.
            read -r W_BURST W_SUS W_AVG W_SLC W_DROP_T W_MAX_T < <(awk -F, 'NR > 1 { n++; m[n] = $3; g[n] = $2; t[n] = $4 }
                END {
                    if (n == 0) exit
                    w = int(n / 4); if (w < 1) w = 1
                    a = (n > 1) ? 2 : 1; s = 0; c = 0
                    for (i = a; i < a + w && i <= n; i++) { s += m[i]; c++ }
                    burst = s / c
                    s = 0; c = 0; for (i = n - w + 1; i <= n; i++) { s += m[i]; c++ }
                    sus = s / c
                    s = 0; for (i = 1; i <= n; i++) s += m[i]
                    maxt = ""; for (i = 1; i <= n; i++) if (t[i] != "" && (maxt == "" || t[i] + 0 > maxt)) maxt = t[i] + 0
                    slc = "-"; dt = "-"
                    for (i = 2; i < n; i++) if ((m[i] + m[i + 1]) / 2 < 0.6 * burst) { slc = g[i - 1]; dt = (t[i] == "" ? "-" : t[i]); break }
                    printf "%d %d %d %s %s %s\n", burst, sus, s / n, slc, dt, (maxt == "" ? "-" : maxt)
                }' "$DISK_CSV")
            if [ -n "$W_BURST" ]; then
                log_result "SUCCESS: Sequential write: ${W_BURST} MB/s at the start, ${W_SUS} MB/s at the end, ${W_AVG} MB/s average (peak drive temperature ${W_MAX_T/-/?} °C)."
                if [ "$W_SLC" != "-" ] && [ $(( W_SUS * 10 )) -lt $(( W_BURST * 6 )) ]; then
                    if [ "$W_DROP_T" != "-" ] && [ "$W_DROP_T" -ge "$D_WARN_T" ]; then
                        log_result "WARNING: Write speed fell after ~${W_SLC} GiB while the drive was at ${W_DROP_T} °C: that is thermal throttling, not the end of the SLC cache."
                        log_result "HINT: Fit an M.2 heatsink or add airflow over the drive, then run the test again."
                        WARN_FOUND=true
                    else
                        log_result "INFO: SLC cache: about ${W_SLC} GiB. Writes run at ~${W_BURST} MB/s until it is full and at ~${W_SUS} MB/s after that."
                        if [ "$W_SUS" -lt 500 ]; then
                            log_result "NOTE: ${W_SUS} MB/s after the cache is typical of QLC or DRAM-less TLC drives; game installs and updates larger than ~${W_SLC} GiB slow down to this speed."
                        fi
                    fi
                else
                    log_result "INFO: No slowdown within ${DISK_WRITE_GIB} GiB: the SLC cache is larger than that (or the drive writes at full speed without one). Use a larger ${DISK_SIZE_WORD} to find its end."
                fi
                if [ "$W_BURST" -lt 200 ]; then
                    log_result "WARNING: Write speed is very low from the start. Check the PCIe link in test 10, the drive temperature and free space."
                    WARN_FOUND=true
                fi
            fi
        fi
    fi
else
    log_howto "INFO: Write test not requested (--disk-write=GiB); nothing was written." \
              "INFO: Write test not requested ('also test writes' not ticked); nothing was written."
fi
echo
fi
fi
fi  # TEST 43
if want 44; then
log_result "[TEST 44] Internet Speed Test (download, upload, latency under load)"
if [ "$SPEEDTEST_MODE" != true ]; then
    log_howto "INFO: Skipped. Re-run with --speedtest to measure download and upload speed and latency" \
              "INFO: Skipped. Start test 44 (Network page) to measure download and upload speed and latency"
    log_result "INFO: (uses about 1 GB of data on a fast connection)."
    echo
else
ST_BIN=""
{ find_tool speedtest || find_tool speedtest-cli; } && ST_BIN=$TOOL
if [ -z "$ST_BIN" ]; then
    log_result "WARNING: No speed test tool found (Ookla speedtest or speedtest-cli)."
    log_result "HINT: Get Ookla's CLI from https://www.speedtest.net/apps/cli (Linux x86_64 .tgz) and put the speedtest binary in ~/.local/bin"
    WARN_FOUND=true
    echo
else
ST_JSON="$LOG_DIR/bc250-speedtest-${TIMESTAMP}.json"
ST_HISTORY="$LOG_DIR/bc250-speedtest-history.csv"
# Which interface carries the traffic: Wi-Fi and the port's link speed both cap the result.
ST_IFACE=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'dev \K\S+')
ST_LINK=""; ST_KIND="wired"
if [ -n "$ST_IFACE" ]; then
    [ -d "/sys/class/net/$ST_IFACE/wireless" ] && ST_KIND="Wi-Fi"
    ST_LINK=$(cat "/sys/class/net/$ST_IFACE/speed" 2>/dev/null)
    [ "${ST_LINK:-0}" -gt 0 ] 2>/dev/null || ST_LINK=""
    log_result "INFO: Traffic goes through $ST_IFACE ($ST_KIND${ST_LINK:+, link ${ST_LINK} Mbit/s})."
fi
# Run as the desktop user so the tool's config/license file lands in their home, not root's, and so
# a speedtest in the user's ~/.local/bin is never run as root.
st_run() {
    if [ -n "$GAME_USER" ] && [ "$GAME_USER" != root ]; then sudo -u "$GAME_USER" -H "$@"; else "$@"; fi
}
if st_run "$ST_BIN" --version 2>/dev/null | grep -qi ookla; then
    ST_KINDTOOL=ookla
    log_result "Running Ookla speedtest (about 30 s; by running it you accept Ookla's license and GDPR terms)"
    ST_OUT=$(st_run timeout 180 "$ST_BIN" --accept-license --accept-gdpr -f json 2>>"$LOG_FILE")
else
    ST_KINDTOOL=speedtest-cli
    log_result "Running speedtest-cli (about 30 s)"
    ST_OUT=$(st_run timeout 180 "$ST_BIN" --json --secure 2>>"$LOG_FILE")
fi
# Ookla may print progress lines before the JSON result; keep the last JSON object.
ST_OUT=$(grep '^{' <<<"$ST_OUT" | tail -1)
unset ST; declare -A ST=()
while IFS='=' read -r k v; do [ -n "$k" ] && ST[$k]=$v; done < <(python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
out = {}
if sys.argv[1] == "ookla":
    ping, dl, ul = d.get("ping", {}), d.get("download", {}), d.get("upload", {})
    srv = d.get("server", {})
    out = {
        "ping": ping.get("latency"), "jitter": ping.get("jitter"),
        "down": dl.get("bandwidth", 0) * 8 / 1e6, "up": ul.get("bandwidth", 0) * 8 / 1e6,
        "down_lat": dl.get("latency", {}).get("iqm"), "up_lat": ul.get("latency", {}).get("iqm"),
        "down_mb": dl.get("bytes", 0) / 1e6, "up_mb": ul.get("bytes", 0) / 1e6,
        "loss": d.get("packetLoss"), "isp": d.get("isp"),
        "server": " - ".join(x for x in (srv.get("name"), srv.get("location")) if x),
        "url": d.get("result", {}).get("url"), "vpn": d.get("interface", {}).get("isVpn"),
    }
else:
    srv = d.get("server", {})
    out = {
        "ping": d.get("ping"), "down": (d.get("download") or 0) / 1e6, "up": (d.get("upload") or 0) / 1e6,
        "down_mb": (d.get("bytes_received") or 0) / 1e6, "up_mb": (d.get("bytes_sent") or 0) / 1e6,
        "isp": d.get("client", {}).get("isp"),
        "server": " - ".join(x for x in (srv.get("sponsor"), srv.get("name")) if x), "url": d.get("share"),
    }
for k, v in out.items():
    if v is None or v == "":
        continue
    if isinstance(v, bool):
        v = "yes" if v else "no"
    elif isinstance(v, float):
        v = "%.2f" % v
    print("%s=%s" % (k, str(v).replace("\n", " ").replace(",", " ")))
' "$ST_KINDTOOL" <<<"$ST_OUT" 2>/dev/null)
if [ -z "${ST[down]:-}" ] || [ -z "${ST[up]:-}" ]; then
    log_result "ERROR: The speed test did not produce a result (no connection, or the servers are unreachable)."
    ERROR_FOUND=true
else
    printf '%s\n' "$ST_OUT" > "$ST_JSON"; chmod 644 "$ST_JSON" 2>/dev/null
    log_result "INFO: Server: ${ST[server]:-unknown}; ISP: ${ST[isp]:-unknown}"
    log_result "SUCCESS: Download: ${ST[down]} Mbps (${ST[down_mb]:-?} MB used)${ST[down_lat]:+, latency while downloading ${ST[down_lat]} ms}"
    log_result "SUCCESS: Upload: ${ST[up]} Mbps (${ST[up_mb]:-?} MB used)${ST[up_lat]:+, latency while uploading ${ST[up_lat]} ms}"
    log_result "INFO: Idle latency: ${ST[ping]:-?} ms${ST[jitter]:+ (jitter ${ST[jitter]} ms)}"
    [ "${ST[vpn]:-}" = yes ] && log_result "NOTE: The test ran through a VPN; the results reflect the VPN, not the line itself."
    # Latency under load vs. idle ("bufferbloat") is what makes online games lag while something downloads.
    BLOAT=$(awk -v i="${ST[ping]:-0}" -v d="${ST[down_lat]:-0}" -v u="${ST[up_lat]:-0}" 'BEGIN { m = (d > u ? d : u); if (i > 0 && m > 0) printf "%d", m - i }')
    if [ -n "$BLOAT" ]; then
        if [ "$BLOAT" -gt 100 ]; then
            log_result "WARNING: Latency rises by ${BLOAT} ms while the line is busy (bufferbloat). Online games lag whenever something else downloads or uploads."
            log_result "HINT: Enable SQM / Smart Queue Management (fq_codel or CAKE) in your router, set to ~90% of these speeds."
            WARN_FOUND=true
        elif [ "$BLOAT" -gt 30 ]; then
            log_result "INFO: Latency rises by ${BLOAT} ms under load (mild bufferbloat; SQM in the router would reduce it)."
        else
            log_result "SUCCESS: Latency stays low under load (+${BLOAT} ms)."
        fi
    fi
    if [ -n "${ST[loss]:-}" ]; then
        if awk -v l="${ST[loss]}" 'BEGIN { exit !(l > 1) }'; then
            log_result "WARNING: Packet loss: ${ST[loss]}%. Expect rubber-banding in online games; check the cable, Wi-Fi signal or router."
            WARN_FOUND=true
        else
            log_result "SUCCESS: Packet loss: ${ST[loss]}%"
        fi
    fi
    if [ -n "$ST_LINK" ] && awk -v d="${ST[down]}" -v l="$ST_LINK" 'BEGIN { exit !(d > 0.85 * l) }'; then
        log_result "NOTE: The download is close to the ${ST_LINK} Mbit/s link speed of $ST_IFACE; the port, not the internet connection, is the limit."
    elif [ "$ST_LINK" = 100 ] || [ "$ST_LINK" = 10 ]; then
        log_result "WARNING: $ST_IFACE is linked at only ${ST_LINK} Mbit/s. A damaged cable or a 2-pair cable limits gigabit ports to 100 Mbit/s."
        WARN_FOUND=true
    fi
    [ "$ST_KIND" = "Wi-Fi" ] && log_result "HINT: Wi-Fi adds latency and jitter; a cable gives more stable online gaming and faster Steam downloads."
    [ -n "${ST[url]:-}" ] && log_result "INFO: Result URL: ${ST[url]}"
    [ -f "$ST_HISTORY" ] || echo "date,iface,link_mbps,server,isp,ping_ms,jitter_ms,down_mbps,up_mbps,down_latency_ms,up_latency_ms,packet_loss_pct" > "$ST_HISTORY"
    echo "$(date '+%Y-%m-%d %H:%M:%S'),${ST_IFACE},${ST_LINK},${ST[server]:-},${ST[isp]:-},${ST[ping]:-},${ST[jitter]:-},${ST[down]},${ST[up]},${ST[down_lat]:-},${ST[up_lat]:-},${ST[loss]:-}" >> "$ST_HISTORY"
    chmod 644 "$ST_HISTORY" 2>/dev/null
    log_result "INFO: Result saved to $ST_JSON; all runs are listed in $ST_HISTORY."
fi
echo
fi
fi
fi  # TEST 44
if want 47; then
log_result "[TEST 47] Vulkan Futureproof Matrix Test"
log_result "Hard evidence of what this GPU can and cannot run: API level, ray tracing, mesh shaders, VRAM"
if command -v vulkaninfo >/dev/null 2>&1; then
    VK_FULL=$(vulkaninfo 2>/dev/null)
    # vulkaninfo lists llvmpipe as an extra device on every healthy system; carve out the first
    # hardware GPU's block so its API version and extensions are judged, not llvmpipe's.
    VK_HW=$(awk '/^GPU[0-9]+:/ {i++} i {blk[i] = blk[i] $0 "\n"}
        END {for (k = 1; k <= i; k++) if (blk[k] ~ /deviceName/ && blk[k] !~ /llvmpipe/) {printf "%s", blk[k]; exit}}' <<<"$VK_FULL")
    if [ -z "$VK_HW" ]; then
        log_result "WARNING: No hardware Vulkan device (llvmpipe only, or no output); the matrix below would"
        log_result "WARNING: describe the software fallback, not the GPU. Fix test 20 first."
        WARN_FOUND=true
    else
        VK_DEV_NAME=$(grep -oE "deviceName *= *.*" <<<"$VK_HW" | head -1 | cut -d= -f2- | sed 's/^ //')
        log_result "INFO: Judging the hardware device: ${VK_DEV_NAME:-unknown}"
        VK_API=$(grep -E "apiVersion" <<<"$VK_HW" | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | tail -1)
        log_result "INFO: Vulkan API version: ${VK_API:-unknown}"
        VK_MAJMIN=$(cut -d. -f1-2 <<<"${VK_API:-0.0}")
        if awk -v v="$VK_MAJMIN" 'BEGIN {exit !(v >= 1.3)}'; then
            log_result "SUCCESS: Vulkan ${VK_MAJMIN} meets what DXVK 2.x and vkd3d-proton (DX12) require; current"
            log_result "SUCCESS: Proton versions run on this driver."
        else
            log_result "WARNING: Vulkan ${VK_MAJMIN:-?} is below 1.3; recent DXVK/vkd3d-proton need 1.3. Update Mesa (Bazzite update)."
            WARN_FOUND=true
        fi
        vk_has() { grep -q "$1" <<<"$VK_HW"; }
        VK_MATRIX=""
        for ext in VK_KHR_acceleration_structure VK_KHR_ray_query VK_KHR_ray_tracing_pipeline \
                   VK_EXT_mesh_shader VK_KHR_fragment_shading_rate VK_EXT_graphics_pipeline_library; do
            if vk_has "$ext"; then VK_MATRIX+="yes  $ext"$'\n'; else VK_MATRIX+="no   $ext"$'\n'; fi
        done
        log_result "INFO: Feature matrix (yes = the driver exposes it on this GPU):"
        printf '%s' "$VK_MATRIX" | tee -a "$LOG_FILE"
        if vk_has VK_KHR_ray_query || vk_has VK_KHR_ray_tracing_pipeline; then
            log_result "SUCCESS: Hardware ray tracing is exposed. RT-required titles (Indiana Jones: The Great Circle,"
            log_result "SUCCESS: Doom: The Dark Ages) can start; whether they are playable is a performance question (test 48)."
        else
            log_result "NOTE: No ray tracing extensions. Games that REQUIRE hardware RT will refuse to run on this"
            log_result "NOTE: system no matter how it is tuned — that is a hard limit of the silicon/driver, examples:"
            log_result "NOTE: Indiana Jones: The Great Circle, Doom: The Dark Ages, and future idTech/UE5-Lumen-HW titles."
        fi
        if ! vk_has VK_EXT_mesh_shader; then
            log_result "NOTE: No mesh shaders. Current engines (UE5 Nanite, Alan Wake 2) carry a slower fallback path;"
            log_result "NOTE: titles that drop the fallback in the future will not run."
        fi
        if ! vk_has VK_EXT_graphics_pipeline_library; then
            log_result "NOTE: No VK_EXT_graphics_pipeline_library: DXVK falls back to full pipeline compilation, so"
            log_result "NOTE: expect more first-run shader-compilation stutter."
        fi
    fi
else
    log_result "WARNING: vulkaninfo is not installed; the feature matrix needs it."
    log_result "HINT: rpm-ostree install vulkan-tools   (then reboot)"
    WARN_FOUND=true
fi
VRAM_B=$(read_num_g "$GPU_DEV/mem_info_vram_total")
if [ "$VRAM_B" -gt 0 ]; then
    VRAM_G=$((VRAM_B / 1073741824))
    log_result "INFO: VRAM carveout: ${VRAM_G} GiB (plus GTT spill from shared memory)."
    if [ "$VRAM_G" -lt 8 ]; then
        log_result "NOTE: Modern AAA titles recommend 8 GiB+ of VRAM. On this unified-memory board the carveout is"
        log_result "NOTE: adjustable: see the manual section on bc250_memcfg (a larger split also fixes pin failures)."
    else
        log_result "SUCCESS: The ${VRAM_G} GiB carveout meets the common 8 GiB recommendation of current AAA titles."
    fi
fi
echo
fi  # TEST 47
if want 48; then
log_result "[TEST 48] Real-Game Frametime Analysis Test (MangoHud logs)"
log_result "Synthetic scores (test 42) rank compute; this reads real play sessions: FPS, 1%/0.1% lows, stutter"
mh_user() { if [ "$(id -u)" = 0 ] && [ -n "$GAME_USER" ] && [ "$GAME_USER" != root ]; then sudo -u "$GAME_USER" -H -- "$@"; else "$@"; fi; }
MH_DIRS=()
MH_CONF_DIR=$(mh_user cat -- "$GAME_HOME/.config/MangoHud/MangoHud.conf" 2>/dev/null \
    | awk -F= '/^[[:space:]]*output_folder[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}')
[ -n "$MH_CONF_DIR" ] && MH_DIRS+=("$MH_CONF_DIR")
MH_DIRS+=("$GAME_HOME/mangohud-logs" "$GAME_HOME/.local/share/MangoHud")
MH_FILES=$(mh_user find "${MH_DIRS[@]}" -maxdepth 1 -type f -name '*.csv' -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | head -5 | cut -d' ' -f2-)
if [ -z "$MH_FILES" ]; then
    log_result "INFO: No MangoHud logs found (looked in: ${MH_DIRS[*]})."
    log_result "INFO: To collect real-game evidence, enable logging once in ~/.config/MangoHud/MangoHud.conf:"
    log_result "INFO:   output_folder=$GAME_HOME/mangohud-logs"
    log_result "INFO:   autostart_log=1"
    log_result "INFO:   log_interval=0"
    log_result "INFO: start games with 'mangohud %command%', play, then rerun this test."
else
    MH_ANALYSED=0
    while IFS= read -r MH_F; do
        [ -n "$MH_F" ] || continue
        MH_RES=$(mh_user cat -- "$MH_F" 2>/dev/null | head -c 20000000 | awk -F, '
            !col {
                for (i = 1; i <= NF; i++) if (tolower($i) == "frametime") { col = i; next }
                if (NR > 10) exit
                next
            }
            NF >= col && $col + 0 > 0 { n++; ft[n] = $col + 0; sum += $col }
            END {
                if (n < 100) { print "SHORT", n; exit }
                asort(ft)
                med = ft[int(n / 2)]
                st = 0; for (i = 1; i <= n; i++) if (ft[i] > 2 * med) st++
                # 1% / 0.1% low = FPS from the average of the worst 1% / 0.1% frametimes.
                k1 = int(n / 100);  if (k1 < 1) k1 = 1
                k2 = int(n / 1000); if (k2 < 1) k2 = 1
                s1 = 0; for (i = n - k1 + 1; i <= n; i++) s1 += ft[i]
                s2 = 0; for (i = n - k2 + 1; i <= n; i++) s2 += ft[i]
                printf "OK %d %.0f %.1f %.1f %.1f %.2f\n", n, sum / 1000, 1000 * n / sum, \
                    1000 * k1 / s1, 1000 * k2 / s2, 100 * st / n
            }')
        case "$MH_RES" in
            OK*)
                read -r _ MH_N MH_SECS MH_AVG MH_P1 MH_P01 MH_STUT <<<"$MH_RES"
                MH_ANALYSED=$((MH_ANALYSED + 1))
                log_result "INFO: $(basename "$MH_F"): ${MH_SECS}s, $MH_N frames"
                log_result "INFO:   avg $MH_AVG FPS | 1% low $MH_P1 FPS | 0.1% low $MH_P01 FPS | ${MH_STUT}% frames over 2x median"
                # Judge smoothness, not speed: lows far under the average are stutter the average hides.
                MH_RATIO=$(awk -v a="$MH_AVG" -v l="$MH_P1" 'BEGIN {if (a > 0) printf "%.0f", 100 * l / a}')
                if [ -n "$MH_RATIO" ] && [ "$MH_RATIO" -lt 50 ]; then
                    log_result "WARNING:   The 1% low is only ${MH_RATIO}% of the average: noticeable stutter in this session."
                    log_result "HINT:   Common causes here: first-run shader compilation, the VRAM carveout filling up"
                    log_result "HINT:   (test 37), or hhd running (test 27). A second session of the same game that keeps"
                    log_result "HINT:   this ratio points at memory pressure rather than shader compilation."
                    WARN_FOUND=true
                elif [ -n "$MH_RATIO" ]; then
                    log_result "SUCCESS:   Frametimes are consistent (1% low is ${MH_RATIO}% of the average)."
                fi ;;
            SHORT*)
                log_result "INFO: $(basename "$MH_F"): too short to judge ($(cut -d' ' -f2 <<<"$MH_RES") frames); skipped." ;;
            *)
                log_result "INFO: $(basename "$MH_F"): no frametime column found; skipped." ;;
        esac
        [ "$MH_ANALYSED" -ge 3 ] && break
    done <<<"$MH_FILES"
    [ "$MH_ANALYSED" -gt 0 ] && log_result "INFO: Analyzed the $MH_ANALYSED most recent session(s). Delete old logs to focus the verdict."
fi
echo
fi  # TEST 48
if want 49; then
log_result "[TEST 49] CPU Memory Bandwidth Test"
log_result "The GDDR6 gives the GPU console-class bandwidth, but the CPU pays latency for it; this measures the CPU side"
if find_tool stress-ng; then
    STREAM_CMD=("${TOOL_CMD[@]}")
    MEMBW_TMP=$(mktemp -d)
    mem_rate() {   # mem_rate THREADS: stress-ng stream memory rate in MB/s (summed over instances)
        local out="$MEMBW_TMP/stream-$1.txt" v
        "${STREAM_CMD[@]}" --stream "$1" --timeout 8s --metrics -v >"$out" 2>&1
        v=$(grep -oE "memory rate: [0-9.]+" "$out" | grep -oE "[0-9.]+" | awk '{s += $1} END {if (s > 0) printf "%.0f", s}')
        # Older stress-ng has no "memory rate" line; fall back to the bogo-ops metric (relative only).
        [ -z "$v" ] && v=$(awk '{for (i = 1; i <= NF; i++) if ($i == "stream") {printf "%.0f", $(i+5); exit}}' "$out")
        echo "$v"
    }
    log_result "stress-ng STREAM-like bandwidth, 1 thread then $(nproc) threads (8s each)"
    MEMBW_1=$(mem_rate 1)
    MEMBW_N=$(mem_rate "$(nproc)")
    rm -rf "$MEMBW_TMP"
    if [ -n "$MEMBW_1" ] && [ -n "$MEMBW_N" ]; then
        MEMBW_1G=$(awk -v b="$MEMBW_1" 'BEGIN {printf "%.1f", b / 1000}')
        MEMBW_NG=$(awk -v b="$MEMBW_N" 'BEGIN {printf "%.1f", b / 1000}')
        log_result "INFO: CPU memory bandwidth: single-thread ${MEMBW_1G} GB/s | all threads ${MEMBW_NG} GB/s"
        log_result "NOTE: For context: a desktop with dual-channel DDR4-3200 reaches roughly 20-40 GB/s here."
        log_result "NOTE: A low single-thread figure next to a healthy all-thread figure is the GDDR6 latency at"
        log_result "NOTE: work: it explains why single-thread-bound games lose more on this board than compute"
        log_result "NOTE: benchmarks (test 42) suggest."
        if awk -v n="$MEMBW_N" -v s="$MEMBW_1" 'BEGIN {exit !(s > 0 && n < s * 1.5)}'; then
            log_result "WARNING: All-thread bandwidth barely scales over one thread; memory is the bottleneck under load."
            WARN_FOUND=true
        else
            log_result "SUCCESS: Bandwidth scales with threads ($(awk -v n="$MEMBW_N" -v s="$MEMBW_1" 'BEGIN {printf "%.1f", n / s}')x)."
        fi
    else
        log_result "WARNING: stress-ng ran but reported no bandwidth figure; no result."
        WARN_FOUND=true
    fi
else
    log_result "INFO: stress-ng is not installed; skipping the bandwidth measurement."
    log_result "HINT: rpm-ostree install stress-ng   (then reboot), or: brew install stress-ng"
fi
echo
fi  # TEST 49
if want 50; then
log_result "[TEST 50] Video Decode and Encode Matrix Test (VCN)"
log_result "What the media block accelerates: matters for streaming, recording (OBS) and video playback while gaming"
VCN_BOOT=$(journalctl -b -k --no-pager -q 2>/dev/null | grep -iE "\[drm\].*vcn|vcn.*(enabled|initialized|firmware)" | tail -3)
if [ -n "$VCN_BOOT" ]; then
    log_result "INFO: Kernel VCN messages:"
    echo "$VCN_BOOT" | tee -a "$LOG_FILE"
else
    log_result "NOTE: The kernel logged nothing about VCN this boot: amdgpu did not initialize a media block"
    log_result "NOTE: on this board. Then there is no hardware video decode or encode at all — a hardware fact,"
    log_result "NOTE: not a configuration problem. Video plays fine but decodes on the CPU."
fi
if command -v vainfo >/dev/null 2>&1; then
    VA_DEV=""
    for rd in /dev/dri/renderD*; do [ -e "$rd" ] && VA_DEV="$rd" && break; done
    # Keep stderr: libva reports the failure reason (missing driver, init error) there.
    VA_OUT=$(vainfo --display drm ${VA_DEV:+--device "$VA_DEV"} 2>&1)
    grep -q VAProfile <<<"$VA_OUT" || VA_OUT=$(vainfo 2>&1)
    if grep -q VAProfile <<<"$VA_OUT"; then
        log_result "INFO: VA-API driver: $(grep -oE "Driver version: .*" <<<"$VA_OUT" | head -1 | cut -d: -f2- | sed 's/^ //')"
        va_has() { grep -E "VAProfile$1.*$2" <<<"$VA_OUT" >/dev/null; }
        for codec in "H264:H.264/AVC" "HEVC:HEVC/H.265" "VP9:VP9" "AV1:AV1"; do
            C_KEY=${codec%%:*}; C_NAME=${codec#*:}
            DEC=no; ENC=no
            va_has "$C_KEY" "VLD" && DEC=yes
            va_has "$C_KEY" "EncSlice|EncSliceLP" && ENC=yes
            log_result "INFO: $C_NAME: decode $DEC | encode $ENC"
        done
        if ! va_has "AV1" "VLD"; then
            log_result "NOTE: No AV1 decode: AV1 streams (YouTube increasingly serves them) fall back to the CPU."
            log_result "NOTE: Playable, but it costs CPU headroom while gaming; forcing H.264/VP9 in the browser avoids it."
        fi
        if va_has "H264" "EncSlice|EncSliceLP" || va_has "HEVC" "EncSlice|EncSliceLP"; then
            log_result "SUCCESS: Hardware encoding is available: OBS/recording can use VA-API (H.264/HEVC) at near-zero CPU cost."
        else
            log_result "NOTE: No hardware encoder exposed: recording and streaming will encode on the CPU."
        fi
    elif [ -z "$VCN_BOOT" ]; then
        log_result "INFO: vainfo exposes no profiles, consistent with the kernel initializing no VCN block (above):"
        log_result "INFO: this board simply has no hardware video engine to talk to. Nothing to fix."
    else
        log_result "WARNING: The kernel initialized VCN, but vainfo exposes no profiles; the VA-API userspace is broken."
        log_result "INFO: vainfo said:"
        echo "$VA_OUT" | grep -vE "^$" | head -6 | tee -a "$LOG_FILE"
        VA_DRV_FOUND=$(ls /usr/lib64/dri/radeonsi_drv_video.so 2>/dev/null)
        if [ -z "$VA_DRV_FOUND" ]; then
            log_result "HINT: /usr/lib64/dri/radeonsi_drv_video.so is missing. Fedora strips H.264/HEVC from its Mesa"
            log_result "HINT: VA-API driver; install the freeworld build: rpm-ostree install mesa-va-drivers-freeworld"
        fi
        WARN_FOUND=true
    fi
else
    log_result "INFO: vainfo is not installed; the codec matrix needs it."
    log_result "HINT: rpm-ostree install libva-utils   (then reboot)"
fi
echo
fi  # TEST 50
if want 51; then
log_result "[TEST 51] HDMI-CEC Test"
log_result "Whether the board can control the TV over HDMI: on and off, its input and its remote (HDMI CEC Manager)"
CEC_DEVS=$(ls /dev/cec* 2>/dev/null)
if [ -z "$CEC_DEVS" ]; then
    log_result "INFO: No CEC adapter (/dev/cec*). On the BC-250 amdgpu adds one for a DisplayPort output only when the"
    log_result "INFO: DP-to-HDMI cable or adapter reports CEC tunnelling; this one does not, so the board cannot control"
    log_result "INFO: the TV. Not a fault: the picture and sound do not need CEC."
    log_result "HINT: A DP-to-HDMI adapter that passes CEC, or a USB CEC adapter (Pulse-Eight), adds it."
elif ! command -v cec-ctl >/dev/null 2>&1; then
    log_result "INFO: CEC adapter: $(echo $CEC_DEVS), but cec-ctl is not installed to read it."
    log_result "HINT: rpm-ostree install v4l-utils   (then reboot)"
else
    # cec-ctl -d DEV with no message only prints the adapter's state; the poll below is the one message sent.
    cec_field() { sed -n "s/^[[:space:]]*$1[[:space:]]*: //p" <<<"$CEC_INFO" | head -1; }
    for CEC_DEV in $CEC_DEVS; do
        CEC_INFO=$(cec-ctl -d "$CEC_DEV" 2>&1)
        CEC_PA=$(cec_field "Physical Address")
        CEC_LA=$(cec_field "Logical Address")
        log_result "INFO: $CEC_DEV: driver $(cec_field "Driver Name"), adapter $(cec_field "Adapter Name"), physical address ${CEC_PA:-unknown}"
        if [ -z "$CEC_PA" ] || [ "$CEC_PA" = "f.f.f.f" ]; then
            log_result "NOTE: The adapter sees no display: the TV is off or its EDID was not read. CEC needs both."
        elif [ -z "$CEC_LA" ]; then
            log_result "NOTE: Nothing has configured the adapter yet (no logical address), so the TV was not asked."
            log_result "HINT: HDMI CEC Manager configures it with its first message, Valve's CEC daemon when it starts."
        # cec-ctl exits 0 either way; a "Tx, ..." status line without "Tx, OK" means the transmit failed.
        elif CEC_POLL=$(cec-ctl -d "$CEC_DEV" -s --poll --to 0 2>&1) && grep -q 'Sequence:' <<<"$CEC_POLL" &&
             ! grep -qE '^[[:space:]]*Tx, ([^O]|O[^K])' <<<"$CEC_POLL"; then
            log_result "SUCCESS: The TV answers on $CEC_DEV ($CEC_LA): the board can turn it on and off and switch its input."
        else
            log_result "NOTE: The TV does not answer a poll on $CEC_DEV. Check that CEC is switched on in the TV's settings"
            log_result "NOTE: (Anynet+, SimpLink, Bravia Sync, HDMI control, ...) and that the TV is on. Some DP-to-HDMI"
            log_result "NOTE: converters report CEC tunnelling but do not connect the CEC wire; then no setting helps."
        fi
    done
    if [ -f /etc/default/cec-control ] || command -v cecd >/dev/null 2>&1; then
        CEC_USER_HOME=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
        if [ -n "$CEC_USER_HOME" ] && [ -e "$CEC_USER_HOME/.config/systemd/user/graphical-session.target.wants/cecd.service" ]; then
            CEC_MODE_NOW="native (Valve's CEC daemon)"
        elif systemctl is-enabled --quiet cec-onboot.service cec-onsleep.service cec-onpoweroff.service 2>/dev/null; then
            CEC_MODE_NOW="dGPU (cec-control services)"
        else
            CEC_MODE_NOW="disabled"
        fi
        log_result "INFO: Bazzite CEC mode: $CEC_MODE_NOW. The automatic part (TV on and off with the board, the"
        log_result "INFO: remote as a keyboard) is Valve's CEC daemon: ujust cec-mode native, or HDMI CEC Manager."
    fi
fi
echo
fi  # TEST 51
if want 52; then
log_result "[TEST 52] HDMI-CEC Services Test"
log_result "Whether the services behind the TV control run: Valve's CEC daemon and those of HDMI CEC Manager"
CEC_HOME=$(getent passwd "$GAME_USER" 2>/dev/null | cut -d: -f6)
CEC_ADAPTER=$(ls /dev/cec* 2>/dev/null | head -1)
# The user services' state comes from the desktop user's systemd; without a session the answer is empty.
cec_user_state() { run_as_user systemctl --user is-active "$1"; }
cec_no_session() {
    log_result "INFO: $1: state unknown, $GAME_USER has no desktop session to ask."
    log_result "HINT: Run the test again while $GAME_USER is logged in to the desktop."
}

# Valve's CEC daemon: Bazzite's native CEC mode, a user service.
if ! command -v cecd >/dev/null 2>&1; then
    log_result "INFO: Valve's CEC daemon (cecd) is not part of this image."
else
    CEC_STATE=$(cec_user_state cecd.service)
    if [ -n "$CEC_HOME" ] && [ -e "$CEC_HOME/.config/systemd/user/graphical-session.target.wants/cecd.service" ] ||
       [ "$(run_as_user systemctl --user is-enabled cecd.service)" = enabled ]; then
        CEC_ENABLED=true
    else
        CEC_ENABLED=false
    fi
    if [ "$CEC_STATE" = active ]; then
        log_result "SUCCESS: cecd.service runs for $GAME_USER: TV on and off with sleep and wake, and the remote as a keyboard, as its settings say."
    elif [ "$CEC_ENABLED" = false ]; then
        log_result "INFO: cecd.service is not enabled (Bazzite's CEC mode is not native): nothing turns the TV on and off with the board."
        log_result "HINT: ujust cec-mode native, or Use Valve's CEC daemon... in HDMI CEC Manager."
    elif [ -z "$CEC_STATE" ]; then
        cec_no_session cecd.service
    elif [ -z "$CEC_ADAPTER" ]; then
        log_result "NOTE: cecd.service is enabled but '$CEC_STATE': there is no CEC adapter (/dev/cec*) for it to use."
    else
        log_result "WARNING: cecd.service is enabled but '$CEC_STATE' for $GAME_USER: the TV does not follow the board and the remote does nothing."
        log_result "HINT: Read why with: journalctl --user -b -u cecd; start it again with: systemctl --user restart cecd"
        WARN_FOUND=true
    fi
fi

# HDMI CEC Manager's background service: only installed while "Restart the picture" or "Pause videos and music" is on.
CEC_WATCH="bc250-hdmi-cec-watch.service"
CEC_WATCH_FILE="$CEC_HOME/.config/systemd/user/$CEC_WATCH"
if [ -z "$CEC_HOME" ] || [ ! -f "$CEC_WATCH_FILE" ]; then
    log_result "INFO: $CEC_WATCH is not installed: HDMI CEC Manager adds it for Restart the picture or Pause videos and music."
else
    CEC_JOBS_TEXT=""
    grep -q -- '--restart-picture' "$CEC_WATCH_FILE" && CEC_JOBS_TEXT="restart the picture"
    grep -q -- '--pause-media' "$CEC_WATCH_FILE" && CEC_JOBS_TEXT="${CEC_JOBS_TEXT:+$CEC_JOBS_TEXT and }pause videos and music"
    CEC_JOBS_TEXT=${CEC_JOBS_TEXT:-do nothing}
    CEC_STATE=$(cec_user_state "$CEC_WATCH")
    if [ "$CEC_STATE" = active ]; then
        log_result "SUCCESS: $CEC_WATCH runs for $GAME_USER: when the TV turns off and on, it will $CEC_JOBS_TEXT."
    elif [ -z "$CEC_STATE" ]; then
        cec_no_session "$CEC_WATCH"
    else
        log_result "WARNING: $CEC_WATCH is installed but '$CEC_STATE': nothing happens when the TV turns off and on."
        log_result "HINT: Read why with: journalctl --user -b -u bc250-hdmi-cec-watch; start it again with: systemctl --user restart bc250-hdmi-cec-watch"
        WARN_FOUND=true
    fi
fi

# HDMI CEC Manager's boot service: a system service that udev starts once per boot when a CEC adapter appears.
CEC_BOOT="bc250-hdmi-cec-boot.service"
if [ ! -f "/etc/systemd/system/$CEC_BOOT" ]; then
    log_result "INFO: $CEC_BOOT is not installed: HDMI CEC Manager adds it for At boot (the board's name, and the TV on, before login)."
else
    CEC_STATE=$(systemctl is-active "$CEC_BOOT" 2>/dev/null)
    if [ ! -f /etc/udev/rules.d/99-bc250-hdmi-cec-boot.rules ]; then
        log_result "WARNING: $CEC_BOOT is installed without its udev rule (99-bc250-hdmi-cec-boot.rules), so nothing starts it."
        log_result "HINT: In HDMI CEC Manager, switch At boot off and on again (or press Update there)."
        WARN_FOUND=true
    elif [ "$CEC_STATE" = active ]; then
        log_result "SUCCESS: $CEC_BOOT ran at this boot. What it did: journalctl -b -u bc250-hdmi-cec-boot"
    elif [ "$CEC_STATE" = activating ]; then
        log_result "NOTE: $CEC_BOOT is still running: it waits until the adapter sees the TV."
    elif [ "$CEC_STATE" = failed ]; then
        log_result "WARNING: $CEC_BOOT failed at this boot: the TV did not get the board's name."
        log_result "HINT: Read why with: journalctl -b -u bc250-hdmi-cec-boot"
        WARN_FOUND=true
    elif [ -z "$CEC_ADAPTER" ]; then
        log_result "INFO: $CEC_BOOT has not run: it starts when a CEC adapter appears, and there is none (/dev/cec*)."
    else
        log_result "NOTE: $CEC_BOOT is '${CEC_STATE:-unknown}' although $CEC_ADAPTER is there. What happened: journalctl -b -u bc250-hdmi-cec-boot"
    fi
fi

# Bazzite's dGPU CEC mode: the cec-control services (boot, sleep, power-off), for USB adapters.
for CEC_UNIT in cec-onboot.service cec-onsleep.service cec-onpoweroff.service; do
    [ -n "$(systemctl list-unit-files --no-legend "$CEC_UNIT" 2>/dev/null)" ] || continue
    CEC_STATE=$(systemctl is-active "$CEC_UNIT" 2>/dev/null)
    if [ "$CEC_STATE" = failed ]; then
        log_result "WARNING: $CEC_UNIT (Bazzite's dGPU CEC mode) failed. Read why with: journalctl -b -u ${CEC_UNIT%.service}"
        WARN_FOUND=true
    elif systemctl is-enabled --quiet "$CEC_UNIT" 2>/dev/null; then
        log_result "INFO: $CEC_UNIT (Bazzite's dGPU CEC mode) is enabled / ${CEC_STATE:-unknown}."
    fi
done
echo
fi  # TEST 52
if want 53; then
log_result "[TEST 53] Wi-Fi Adapter Test"
log_result "Every Wi-Fi adapter, whether the running kernel has a driver and firmware for it, and its connection"
# bc250_core's wifi reader (bundled next to the script in a release, core/ in the suite checkout), with the system
# python in isolated mode and without bytecode, so nothing is written as root into the app's folders. It only reads.
if [ -d "$SCRIPT_DIR/bc250_core" ]; then WIFI_CORE="$SCRIPT_DIR"; else WIFI_CORE="$SCRIPT_DIR/../../core"; fi
if ! command -v python3 >/dev/null 2>&1; then
    log_result "INFO: python3 is not installed, so the Wi-Fi adapters cannot be read."
elif [ ! -f "$WIFI_CORE/bc250_core/wifi.py" ]; then
    log_result "INFO: The Wi-Fi reader (bc250_core) is not next to this script, so the Wi-Fi adapters cannot be read."
else
    while IFS= read -r WIFI_LINE; do
        [ -n "$WIFI_LINE" ] || continue
        log_result "$WIFI_LINE"
        [[ "$WIFI_LINE" == WARNING:* ]] && WARN_FOUND=true
    done < <(python3 -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from bc250_core import wifi; sys.exit(wifi.main())' \
        "$WIFI_CORE" 2>&1)
fi

# BC-250 USB Wi-Fi's driver (AIC8800D80 sticks): a system service that builds and loads it at every boot.
WIFI_UNIT="bc250-usb-wifi.service"
if [ -f "/etc/systemd/system/$WIFI_UNIT" ]; then
    WIFI_KERNEL=$(uname -r)
    wifi_json() { python3 -I -B -c 'import json, sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$1" "$2" 2>/dev/null; }
    WIFI_BRANCH=$(wifi_json /etc/bc250-usb-wifi/driver.json branch)
    WIFI_STATE=$(systemctl is-active "$WIFI_UNIT" 2>/dev/null)
    WIFI_ERROR=$(wifi_json /run/bc250-usb-wifi/state.json error)
    log_result "INFO: BC-250 USB Wi-Fi's driver is installed (branch ${WIFI_BRANCH:-unknown}), $WIFI_UNIT is ${WIFI_STATE:-unknown}."
    if ! systemctl is-enabled --quiet "$WIFI_UNIT" 2>/dev/null; then
        log_result "WARNING: $WIFI_UNIT is not enabled: the driver is not loaded at boot."
        log_result "HINT: In BC-250 USB Wi-Fi, press Update to install the service again."
        WARN_FOUND=true
    elif [ -n "$WIFI_ERROR" ]; then
        log_result "WARNING: The service's last run at this boot failed: $WIFI_ERROR"
        log_result "HINT: Read why with: journalctl -b -u bc250-usb-wifi; BC-250 USB Wi-Fi shows it too."
        WARN_FOUND=true
    elif [ ! -f "/var/lib/bc250-usb-wifi/modules/$WIFI_KERNEL/aic8800_fdrv.ko" ]; then
        log_result "NOTE: No driver built for kernel $WIFI_KERNEL yet: the service builds it at the next boot, or press Install in BC-250 USB Wi-Fi."
    elif lsmod | grep -q '^aic_load_fw ' && lsmod | grep -q '^aic8800_fdrv '; then
        log_result "SUCCESS: The driver is built for kernel $WIFI_KERNEL and loaded (aic_load_fw, aic8800_fdrv)."
    else
        log_result "WARNING: The driver is built for kernel $WIFI_KERNEL but not loaded."
        log_result "HINT: Read why with: journalctl -b -u bc250-usb-wifi"
        WARN_FOUND=true
    fi
fi
echo
fi  # TEST 53
log_result "All tests completed. Review results in $LOG_FILE."
echo

# Summary
log_result "[SUMMARY] Test Results"
if [ "$ERROR_FOUND" = true ]; then
    log_result "FAILURE: Errors were found. Please review $LOG_FILE for more details."
elif [ "$WARN_FOUND" = true ]; then
    log_result "WARNING: No hard errors, but warnings were raised. Review $LOG_FILE."
else
    log_result "SUCCESS: No errors detected during the tests."
fi
echo

# Copy the report to the desktop user's Desktop for easy sharing
copy_to_desktop() {
    local TARGET_USER="${SUDO_USER:-$USER}"
    local TARGET_HOME DESKTOP_DIR

    if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
        log_result "INFO: No desktop user detected, leaving the report in $LOG_FILE."
        return
    fi

    TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
    if [ -z "$TARGET_HOME" ] || [ ! -d "$TARGET_HOME" ]; then
        log_result "WARNING: Could not resolve the home directory for $TARGET_USER."
        return
    fi

    # Respect a localized/relocated Desktop when xdg-user-dir is available.
    DESKTOP_DIR=$(sudo -u "$TARGET_USER" xdg-user-dir DESKTOP 2>/dev/null)
    if [ -z "$DESKTOP_DIR" ] || [ "$DESKTOP_DIR" = "$TARGET_HOME" ]; then
        DESKTOP_DIR="$TARGET_HOME/Desktop"
    fi
    DESKTOP_DIR="$DESKTOP_DIR/bc250-bazzite-test"

    # Everything inside the user's home is done as that user, never as root: root following a
    # symlink planted there could otherwise overwrite or chown any file on the system. The report
    # files are read by this (root) shell and only written by the user's process.
    as_target() {
        if [ "$(id -u)" = 0 ]; then sudo -u "$TARGET_USER" -H -- "$@"; else "$@"; fi
    }
    if ! as_target mkdir -p -- "$DESKTOP_DIR"; then
        log_result "WARNING: Could not create $DESKTOP_DIR."
        return
    fi
    ship() {   # ship SRC: copy one file into DESKTOP_DIR as the user, readable by everyone
        as_target sh -c 'umask 022; cat > "$1"' sh "$DESKTOP_DIR/$(basename -- "$1")" < "$1"
    }

    if ship "$LOG_FILE"; then
        log_result "SUCCESS: Report copied to $DESKTOP_DIR/$(basename "$LOG_FILE")"
    else
        log_result "WARNING: Failed to copy the report to $DESKTOP_DIR."
    fi

    # The stress run writes a telemetry CSV and the GPU load tool's output, the benchmark its
    # result JSON, the history CSV and the vkpeak output, the disk test its write CSV; ship them alongside.
    local extra
    for extra in "${STRESS_CSV:-}" "${GPU_WORKER_LOG:-}" "${MEMTEST_LOG:-}" "${BENCH_JSON:-}" "${BENCH_HISTORY:-}" "${BENCH_VKPEAK_LOG:-}" "${DISK_CSV:-}" "${ST_JSON:-}" "${ST_HISTORY:-}"; do
        if [ -n "$extra" ] && [ -f "$extra" ] && ship "$extra"; then
            log_result "SUCCESS: Copied to $DESKTOP_DIR/$(basename "$extra")"
        fi
    done
}
[ "$NO_DESKTOP" = true ] || copy_to_desktop
echo
