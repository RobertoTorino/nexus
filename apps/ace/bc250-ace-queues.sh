#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# bc250-ace-queues — the dedicated compute (ACE) queues of the AMD BC-250 for games: a patched RADV, built on the
# board and installed beside the system Mesa, used by the games you choose (or by every app, after a passed test).
#
# Usage:
#   ./bc250-ace-queues.sh --status                  # one "Name: value" line each (the app reads them)
#   ./bc250-ace-queues.sh --build [--mesa X.Y.Z]    # build the patched RADV in a podman container (your user)
#   sudo ./bc250-ace-queues.sh --install-driver     # install that build
#   ./bc250-ace-queues.sh --test [--rounds N]       # run the ACE queue test on the installed driver
#   sudo ./bc250-ace-queues.sh --all-apps on|off    # every app uses the driver (on: only after a passed test)
#   sudo ./bc250-ace-queues.sh --remove-driver      # all apps off, then remove the driver
#   ./bc250-ace-queues.sh --launch-options          # the Steam launch options for one game
#
# The system Mesa is never changed. The driver goes to /usr/local/lib/bc250-ace-queues (on Bazzite /usr/local is
# /var/usrlocal: writable, and kept across image updates). Your build is in ~/.cache/bc250-ace-queues and your
# test results in ~/.local/state/bc250-ace-queues; under sudo or pkexec these are the calling user's.
set -euo pipefail

VERSION="0.11.1"
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
PREFIX=/usr/local/lib/bc250-ace-queues          # built into the driver: its ICD file and drirc paths
# BC250_ACE_ROOT is for testing only: a folder that stands in for / (usr/local, etc and sys).
ROOT_DIR="${BC250_ACE_ROOT:-}"
DRIVER_DIR="$ROOT_DIR$PREFIX"
DRIVER_LIB="$DRIVER_DIR/lib64/libvulkan_radeon.so"
ICD="$PREFIX/share/vulkan/icd.d/radeon_icd.x86_64.json"
TEST_BIN="$DRIVER_DIR/libexec/bc250-ace-test"
RUNNER_NAME=bc250-ace-queues-run
RUNNER="$ROOT_DIR/usr/local/bin/$RUNNER_NAME"
ENV_CONF="$ROOT_DIR/etc/environment.d/90-bc250-ace-queues.conf"
PROFILE_CONF="$ROOT_DIR/etc/profile.d/90-bc250-ace-queues.sh"
GUARD_NAME=bc250-ace-queues-guard.service
GUARD_UNIT="$ROOT_DIR/etc/systemd/system/$GUARD_NAME"
BOOT_CHECK="$DRIVER_DIR/boot-check"
ALL_APPS_RECORD="$DRIVER_DIR/all-apps"          # the kernel and driver the switch was turned on with
ALL_APPS_OFF="$DRIVER_DIR/all-apps-off"         # why the boot check turned it off
MESA_URL=https://archive.mesa3d.org
BUILD_CONTAINER=bc250-ace-queues-build
FAULTS='amdgpu.*(ring .*timeout|GPU reset|gpu reset)'

info()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '6,13p' "$0" | sed 's/^# \{0,1\}//'; }

is_root() { [ "$(id -u)" -eq 0 ]; }
need_root() { is_root || error "Run as root: sudo $0 $1"; }
need_user() { ! is_root || error "Run this as your own user, not as root: $0 $1"; }

# The home of the user who started this, also under sudo or pkexec.
user_home() {
    local uid=${PKEXEC_UID:-${SUDO_UID:-}} home=""
    [ -n "$uid" ] && home=$(getent passwd "$uid" | cut -d: -f6)
    printf '%s' "${home:-$HOME}"
}
USER_HOME=$(user_home)
CACHE="$USER_HOME/.cache/bc250-ace-queues"
STATE="$USER_HOME/.local/state/bc250-ace-queues"
STAGE_DRIVER="$CACHE/stage$PREFIX"
TESTED="$STATE/tested"                          # the kernel and driver the test last passed with
TEST_FAILED="$STATE/test-failed"

kernel() { uname -r; }
driver_sum() { sha256sum "$DRIVER_LIB" 2>/dev/null | cut -d' ' -f1 || true; }
field() { sed -n "s/^$1=//p" "$2" 2>/dev/null | head -1 || true; }
system_mesa() { rpm -q --qf '%{VERSION}\n' mesa-vulkan-drivers.x86_64 2>/dev/null | head -1 || true; }

is_bc250() {
    local dev
    for dev in "$ROOT_DIR"/sys/bus/pci/devices/*; do
        [ "$(cat "$dev/vendor" 2>/dev/null)" = 0x1002 ] && [ "$(cat "$dev/device" 2>/dev/null)" = 0x13fe ] && return 0
    done
    return 1
}

# VK_DRIVER_FILES: the patched 64-bit driver, the stock 32-bit one (no 32-bit game uses async compute, and Proton's
# 32-bit helpers need one) and lavapipe (VK_DRIVER_FILES replaces the loader's search, so without it there would
# be no Vulkan at all if amdgpu ever failed to load).
driver_files() {
    local files=$ICD f
    for f in /usr/share/vulkan/icd.d/radeon_icd.i686.json /usr/share/vulkan/icd.d/lvp_icd.x86_64.json; do
        [ -f "$ROOT_DIR$f" ] && files="$files:$f"
    done
    printf '%s' "$files"
}

# True when the test passed with the running kernel and the installed driver.
tested_now() {
    local sum
    sum=$(driver_sum)
    [ -n "$sum" ] && [ "$(field kernel "$TESTED")" = "$(kernel)" ] && [ "$(field driver "$TESTED")" = "$sum" ]
}

all_apps_on() { [ -f "$ENV_CONF" ]; }

# --- status --------------------------------------------------------------------------------------------------

do_status() {
    if is_bc250; then echo "Board: BC-250 (1002:13fe)"; else echo "Board: no BC-250 found (1002:13fe)"; fi
    echo "Kernel: $(kernel)"
    echo "System Mesa: $(system_mesa | grep . || echo unknown)"
    if [ -f "$STAGE_DRIVER/BUILD-INFO" ]; then
        echo "Build: Mesa $(field mesa "$STAGE_DRIVER/BUILD-INFO"), $(field built "$STAGE_DRIVER/BUILD-INFO")"
    else
        echo "Build: none"
    fi
    if [ ! -f "$DRIVER_LIB" ]; then
        echo "Driver: not installed"
        echo "Test: none"
    else
        echo "Driver: installed, Mesa $(field mesa "$DRIVER_DIR/BUILD-INFO" | grep . || echo '?')"
        local sum
        sum=$(driver_sum)
        if tested_now; then
            echo "Test: passed on this kernel ($(field date "$TESTED"))"
        elif [ "$(field driver "$TEST_FAILED")" = "$sum" ] && [ "$(field kernel "$TEST_FAILED")" = "$(kernel)" ]; then
            echo "Test: failed ($(field date "$TEST_FAILED")); see the test log"
        elif [ "$(field driver "$TESTED")" = "$sum" ]; then
            echo "Test: passed on kernel $(field kernel "$TESTED"); test again on this one"
        else
            echo "Test: not run with this driver"
        fi
    fi
    if all_apps_on; then
        echo "All apps: on"
    elif [ -f "$ALL_APPS_OFF" ]; then
        echo "All apps: off (switched off at boot: $(cat "$ALL_APPS_OFF"))"
    else
        echo "All apps: off"
    fi
    echo "Launch options: $(launch_options)"
}

launch_options() { printf '%s %%command%%' "${RUNNER#"$ROOT_DIR"}"; }

# --- build ---------------------------------------------------------------------------------------------------

download() {
    local url=$1 dest=$2
    [ -s "$dest" ] && return 0
    curl -fL --retry 3 -o "$dest.part" "$url" || error "Could not download $url"
    mv "$dest.part" "$dest"
}

do_build() {
    need_user --build
    local mesa=$1 fedora
    command -v podman >/dev/null 2>&1 || error "podman is not installed (Bazzite ships it)."
    command -v curl >/dev/null 2>&1 || error "curl is not installed."
    [ -n "$mesa" ] || mesa=$(system_mesa)
    [[ $mesa =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || error "Could not tell the system's Mesa version; give it: --mesa X.Y.Z"
    fedora=$(. /etc/os-release && echo "${VERSION_ID:-}")
    [ -n "$fedora" ] || error "Could not read the Fedora version from /etc/os-release."

    info "Building the patched RADV for Mesa $mesa in a Fedora $fedora container"
    mkdir -p "$CACHE/src" "$CACHE/work"
    find "$CACHE/src" -name 'mesa-*' ! -name "mesa-$mesa.tar.xz*" -delete     # older sources
    download "$MESA_URL/mesa-$mesa.tar.xz" "$CACHE/src/mesa-$mesa.tar.xz"
    download "$MESA_URL/mesa-$mesa.tar.xz.sig" "$CACHE/src/mesa-$mesa.tar.xz.sig"
    # In the background with a trap, so stopping this script (the app's window closing) stops the container too.
    # label=disable: the folders are mounted as they are, instead of relabelled (the app's are root's).
    trap 'podman rm -f "$BUILD_CONTAINER" >/dev/null 2>&1; exit 143' TERM INT HUP
    podman run --rm --replace --name "$BUILD_CONTAINER" --security-opt label=disable --pull=newer \
        -v "$HERE:/app:ro" -v "$CACHE/src:/src:ro" -v "$CACHE/work:/work" \
        -e MESA_VER="$mesa" -e PREFIX="$PREFIX" \
        "registry.fedoraproject.org/fedora:$fedora" bash /app/mesa/build-in-container.sh &
    wait $! || error "The build failed; see above. Its logs are in $CACHE/work/logs."
    trap - TERM INT HUP
    rm -rf "$CACHE/stage"
    mv "$CACHE/work/stage" "$CACHE/stage"
    info "Built. Next: install the driver (sudo $0 --install-driver)."
}

# --- install and remove --------------------------------------------------------------------------------------

do_install_driver() {
    need_root --install-driver
    local f missing
    for f in lib64/libvulkan_radeon.so share/vulkan/icd.d/radeon_icd.x86_64.json libexec/bc250-ace-test BUILD-INFO; do
        [ -f "$STAGE_DRIVER/$f" ] || error "No complete build in $STAGE_DRIVER ($f is missing): build it first."
    done
    grep -qF "\"$PREFIX/lib64/libvulkan_radeon.so\"" "$STAGE_DRIVER/share/vulkan/icd.d/radeon_icd.x86_64.json" ||
        error "The build was made for another folder than $PREFIX: build it again."
    missing=$(ldd "$STAGE_DRIVER/lib64/libvulkan_radeon.so" 2>/dev/null | awk '/not found/ {print $1}' || true)
    [ -z "$missing" ] || error "The driver needs libraries this system does not have: $(echo "$missing" | tr '\n' ' ')"

    if all_apps_on; then
        warn "Switching \"all apps\" off: the new driver has not been tested yet."
        all_apps_off
    fi
    info "Installing the driver in $DRIVER_DIR (Mesa $(field mesa "$STAGE_DRIVER/BUILD-INFO"))"
    rm -rf "$DRIVER_DIR.new"
    mkdir -p "$DRIVER_DIR.new"
    # Plain copy, no -a: the files get root's ownership and the folder's SELinux label, not the cache's.
    (cd "$STAGE_DRIVER" && tar --exclude='./share/drirc.d' --exclude='./etc' -cf - .) |
        tar -xf - -C "$DRIVER_DIR.new" --no-same-owner
    # Mesa reads game profiles from $PREFIX/share/drirc.d and your own from $PREFIX/etc/drirc: point both at the
    # system's, so the profiles stay those of the system Mesa.
    mkdir -p "$DRIVER_DIR.new/share" "$DRIVER_DIR.new/etc"
    if [ -d "$ROOT_DIR/usr/share/drirc.d" ]; then
        ln -sfn /usr/share/drirc.d "$DRIVER_DIR.new/share/drirc.d"
    elif [ -d "$STAGE_DRIVER/share/drirc.d" ]; then
        cp -r "$STAGE_DRIVER/share/drirc.d" "$DRIVER_DIR.new/share/"
    fi
    ln -sfn /etc/drirc "$DRIVER_DIR.new/etc/drirc"
    chmod -R go-w,a+rX "$DRIVER_DIR.new"
    rm -rf "$DRIVER_DIR"
    mv "$DRIVER_DIR.new" "$DRIVER_DIR"
    rm -f "$ALL_APPS_OFF"
    install -D -m 755 "$HERE/$RUNNER_NAME" "$RUNNER"
    command -v restorecon >/dev/null 2>&1 && [ -z "$ROOT_DIR" ] && restorecon -R "$DRIVER_DIR" "$RUNNER" 2>/dev/null
    info "Installed. Nothing uses it yet: run the test next ($0 --test)."
}

do_remove_driver() {
    need_root --remove-driver
    all_apps_on && all_apps_off
    rm -rf "$DRIVER_DIR" "$DRIVER_DIR.new"
    rm -f "$RUNNER"
    info "The driver is removed; every app uses the system Mesa again."
    info "Remove \"$(launch_options)\" from the launch options of your games: without the driver they do not start."
}

# --- test ----------------------------------------------------------------------------------------------------

# Number of amdgpu ring timeouts and GPU resets in this boot's kernel log, or "?" when it cannot be read.
fault_count() {
    local log
    log=$(journalctl -k -b -q --no-pager 2>/dev/null) || { echo "?"; return; }
    [ -n "$log" ] || { echo "?"; return; }
    grep -ciE "$FAULTS" <<<"$log" || true
}

do_test() {
    need_user --test
    local rounds=$1 rc before after sum
    [ -f "$DRIVER_LIB" ] && [ -x "$TEST_BIN" ] || error "The driver is not installed."
    is_bc250 || warn "No BC-250 found: the test runs, but its result says nothing about a BC-250."
    sum=$(driver_sum)
    mkdir -p "$STATE"
    rm -f "$TESTED" "$TEST_FAILED"
    info "Testing the ACE queues on kernel $(kernel) (Mesa $(field mesa "$DRIVER_DIR/BUILD-INFO"))"
    before=$(fault_count)
    set +e
    env -u VK_ICD_FILENAMES VK_DRIVER_FILES="$ICD" timeout 600 "$TEST_BIN" --rounds "$rounds" 2>&1 |
        tee "$STATE/test.log"
    rc=${PIPESTATUS[0]}
    set -e
    after=$(fault_count)
    if [ "$rc" -eq 0 ] && [ "$before" != "?" ] && [ "$after" != "?" ] && [ "$after" -gt "$before" ]; then
        echo "FAIL: the kernel log shows a GPU ring timeout or reset during the test" | tee -a "$STATE/test.log"
        rc=5
    fi
    [ "$before" = "?" ] && warn "The kernel log could not be read, so it was not checked for GPU resets."
    {
        echo "kernel=$(kernel)"
        echo "driver=$sum"
        echo "date=$(date '+%Y-%m-%d %H:%M')"
        echo "exit=$rc"
    } >"$STATE/result.new"
    if [ "$rc" -eq 0 ]; then
        mv "$STATE/result.new" "$TESTED"
        info "Passed on kernel $(kernel). Games can use the driver: $(launch_options)"
    else
        mv "$STATE/result.new" "$TEST_FAILED"
        [ "$rc" -eq 124 ] && echo "FAIL: the test did not finish in 10 minutes" | tee -a "$STATE/test.log"
        error "The test failed (exit code $rc). Don't use the driver on this kernel; the log is $STATE/test.log."
    fi
}

# --- all apps ------------------------------------------------------------------------------------------------

write_boot_check() {
    cat >"$BOOT_CHECK" <<EOF
#!/usr/bin/env bash
# Written by bc250-ace-queues.sh --all-apps on; run at boot by $GUARD_NAME, before anyone logs in.
# Switches "all apps" off when the kernel or the driver is no longer the one the ACE queue test passed with.
[ -f "$ENV_CONF" ] || exit 0
kernel=\$(sed -n 's/^kernel=//p' "$ALL_APPS_RECORD" 2>/dev/null)
driver=\$(sed -n 's/^driver=//p' "$ALL_APPS_RECORD" 2>/dev/null)
now=\$(uname -r)
sum=\$(sha256sum "$DRIVER_LIB" 2>/dev/null | cut -d' ' -f1)
[ "\$now" = "\$kernel" ] && [ -n "\$sum" ] && [ "\$sum" = "\$driver" ] && exit 0
if [ "\$now" != "\$kernel" ]; then why="kernel \$now, tested on \$kernel"; else why="the driver changed"; fi
rm -f "$ENV_CONF" "$PROFILE_CONF" "$ALL_APPS_RECORD"
echo "\$(date '+%Y-%m-%d %H:%M'), \$why" >"$ALL_APPS_OFF"
echo "bc250-ace-queues: all apps switched off: \$why"
EOF
    chmod 755 "$BOOT_CHECK"
}

all_apps_on_cmd() {
    need_root "--all-apps on"
    [ -f "$DRIVER_LIB" ] || error "The driver is not installed."
    tested_now || error "The ACE queue test has not passed with this driver on kernel $(kernel): run it first."
    local files
    files=$(driver_files)
    {
        echo "kernel=$(kernel)"
        echo "driver=$(driver_sum)"
    } >"$ALL_APPS_RECORD"
    mkdir -p "$(dirname "$ENV_CONF")" "$(dirname "$PROFILE_CONF")" "$(dirname "$GUARD_UNIT")"
    {
        echo "# BC-250 ACE Queues: every app uses the patched RADV. Remove this file to go back to the system Mesa."
        echo "VK_DRIVER_FILES=$files"
        echo "VK_ICD_FILENAMES=$files"
    } >"$ENV_CONF"
    # environment.d reaches the desktop session; login shells (a text console, ssh) read profile.d.
    {
        echo "# BC-250 ACE Queues: see $ENV_CONF"
        echo "export VK_DRIVER_FILES=$files"
        echo "export VK_ICD_FILENAMES=$files"
    } >"$PROFILE_CONF"
    chmod 644 "$ENV_CONF" "$PROFILE_CONF" "$ALL_APPS_RECORD"
    write_boot_check
    cat >"$GUARD_UNIT" <<EOF
[Unit]
Description=BC-250 ACE Queues: all apps off when the kernel or the driver changed since the test
Before=display-manager.service systemd-user-sessions.service
ConditionPathExists=${BOOT_CHECK#"$ROOT_DIR"}

[Service]
Type=oneshot
ExecStart=/usr/bin/bash ${BOOT_CHECK#"$ROOT_DIR"}

[Install]
WantedBy=multi-user.target
EOF
    chmod 644 "$GUARD_UNIT"
    rm -f "$ALL_APPS_OFF"
    if [ -z "$ROOT_DIR" ]; then
        command -v restorecon >/dev/null 2>&1 && restorecon "$ENV_CONF" "$PROFILE_CONF" "$GUARD_UNIT" 2>/dev/null
        systemctl daemon-reload
        systemctl enable "$GUARD_NAME" >/dev/null 2>&1 || warn "Could not enable $GUARD_NAME."
    fi
    info "Every app uses the patched driver after you log out and back in (Flatpak apps keep their own)."
    info "If the desktop does not come back: Ctrl+Alt+F3, log in, run: sudo rm $ENV_CONF, and reboot."
}

all_apps_off() {
    rm -f "$ENV_CONF" "$PROFILE_CONF" "$ALL_APPS_RECORD" "$BOOT_CHECK"
    if [ -f "$GUARD_UNIT" ]; then
        [ -z "$ROOT_DIR" ] && systemctl disable "$GUARD_NAME" >/dev/null 2>&1 || true
        rm -f "$GUARD_UNIT"
        [ -z "$ROOT_DIR" ] && systemctl daemon-reload || true
    fi
    info "Apps use the system Mesa again after you log out and back in; games with the launch options still use the patched driver."
}

all_apps_off_cmd() {
    need_root "--all-apps off"
    all_apps_off
    rm -f "$ALL_APPS_OFF"
}

# --- arguments -----------------------------------------------------------------------------------------------

ACTION=""
MESA=""
ROUNDS=10
SWITCH=""
while [ $# -gt 0 ]; do
    case "$1" in
        --status|--build|--install-driver|--test|--remove-driver|--launch-options)
            [ -z "$ACTION" ] || error "Give one action at a time."; ACTION=$1 ;;
        --all-apps)
            [ -z "$ACTION" ] || error "Give one action at a time."; ACTION=$1
            SWITCH=${2:-}; shift || true
            [ "$SWITCH" = on ] || [ "$SWITCH" = off ] || error "--all-apps takes on or off." ;;
        --mesa) MESA=${2:-}; shift || true ;;
        --rounds) ROUNDS=${2:-}; shift || true; [[ $ROUNDS =~ ^[1-9][0-9]*$ ]] || error "--rounds takes a number." ;;
        --version) echo "bc250-ace-queues $VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; error "Unknown option: $1" ;;
    esac
    shift
done

case "$ACTION" in
    --status) do_status ;;
    --build) do_build "$MESA" ;;
    --install-driver) do_install_driver ;;
    --test) do_test "$ROUNDS" ;;
    --all-apps) if [ "$SWITCH" = on ]; then all_apps_on_cmd; else all_apps_off_cmd; fi ;;
    --remove-driver) do_remove_driver ;;
    --launch-options) launch_options; echo ;;
    *) usage >&2; exit 2 ;;
esac
