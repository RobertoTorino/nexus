#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# bc250-mesh-shaders — mesh shaders for games on the AMD BC-250: RADV with DirectMesh, built on the board and
# installed beside the system Mesa, used by the games you choose after its test passed on the running kernel.
#
# Usage:
#   ./bc250-mesh-shaders.sh --status                # one "Name: value" line each (the app reads them)
#   ./bc250-mesh-shaders.sh --build                 # build the driver in a podman container (your user)
#   sudo ./bc250-mesh-shaders.sh --install-driver   # install that build
#   ./bc250-mesh-shaders.sh --test [--rounds N]     # run the mesh test on the installed driver
#   sudo ./bc250-mesh-shaders.sh --remove-driver    # remove the driver
#   ./bc250-mesh-shaders.sh --launch-options        # the Steam launch options for one game
#
# The system Mesa is never changed. The driver goes to /usr/local/lib/bc250-mesh-shaders (on Bazzite /usr/local is
# /var/usrlocal: writable, and kept across image updates). Your build is in ~/.cache/bc250-mesh-shaders and your
# test results in ~/.local/state/bc250-mesh-shaders; under sudo or pkexec these are the calling user's.
set -euo pipefail

VERSION="0.14.0"
# The DirectMesh release this version of the app builds: its patch (in mesa/), the stock Mesa release it is made
# for, and the patch's SHA-256 from the release's SHA256SUMS.
DIRECTMESH=v1.3.1
MESA_VER=26.2.1
PATCH_SHA256=6669d4644d9a00ad8da022dd2716c59e4d235a2c6f0eb4f272c9c8d9fbcc9b77

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# The suite's own patch, applied on top of DirectMesh's; a build names it by the start of its SHA-256.
SUITE_PATCH="$HERE/mesa/bc250-suite-mesa-$MESA_VER.patch"
PREFIX=/usr/local/lib/bc250-mesh-shaders        # built into the driver: its ICD file and drirc paths
# BC250_MESH_ROOT is for testing only: a folder that stands in for / (usr/local and sys).
ROOT_DIR="${BC250_MESH_ROOT:-}"
DRIVER_DIR="$ROOT_DIR$PREFIX"
DRIVER_LIB="$DRIVER_DIR/lib64/libvulkan_radeon.so"
ICD="$PREFIX/share/vulkan/icd.d/radeon_icd.x86_64.json"
MESH_TEST="$DRIVER_DIR/libexec/bc250-mesh-test"
RUNNER_NAME=bc250-mesh-shaders-run
RUNNER="$ROOT_DIR/usr/local/bin/$RUNNER_NAME"
MESA_URL=https://archive.mesa3d.org
BUILD_CONTAINER=bc250-mesh-shaders-build
FAULTS='amdgpu.*(ring .*timeout|GPU reset|gpu reset)'
BOARD_IDS="13fe 143f"                           # the BC-250's GPU, as the DirectMesh driver knows it

info()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '6,12p' "$0" | sed 's/^# \{0,1\}//'; }

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
CACHE="$USER_HOME/.cache/bc250-mesh-shaders"
STATE="$USER_HOME/.local/state/bc250-mesh-shaders"
STAGE_DRIVER="$CACHE/stage$PREFIX"
TESTED="$STATE/tested"                          # the kernel and driver the test last passed with
TEST_FAILED="$STATE/test-failed"

kernel() { uname -r; }
driver_sum() { sha256sum "$DRIVER_LIB" 2>/dev/null | cut -d' ' -f1 || true; }
field() { sed -n "s/^$1=//p" "$2" 2>/dev/null | head -1 || true; }
system_mesa() { rpm -q --qf '%{VERSION}\n' mesa-vulkan-drivers.x86_64 2>/dev/null | head -1 || true; }

# The BC-250's PCI device id (13fe or 143f), or nothing.
board_id() {
    local dev id
    for dev in "$ROOT_DIR"/sys/bus/pci/devices/*; do
        [ "$(cat "$dev/vendor" 2>/dev/null)" = 0x1002 ] || continue
        id=$(cat "$dev/device" 2>/dev/null) || continue
        case " $BOARD_IDS " in *" ${id#0x} "*) printf '%s' "${id#0x}"; return 0 ;; esac
    done
    return 1
}

# "DirectMesh v1.3.1, Mesa 26.2.1, suite patch 1a2b3c4d, 2026-10-13 19:42 UTC" from a BUILD-INFO file (a build
# from before the suite's patch has no suite patch).
build_info() {
    local suite
    suite=$(field suite_patch "$1")
    printf 'DirectMesh %s, Mesa %s, %s%s' "$(field directmesh "$1" | grep . || echo '?')" \
        "$(field mesa "$1" | grep . || echo '?')" "${suite:+suite patch $suite, }" \
        "$(field built "$1" | grep . || echo '?')"
}

suite_patch_id() { sha256sum "$SUITE_PATCH" 2>/dev/null | cut -c1-8; }

# True when the test passed with the running kernel and the installed driver.
tested_now() {
    local sum
    sum=$(driver_sum)
    [ -n "$sum" ] && [ "$(field kernel "$TESTED")" = "$(kernel)" ] && [ "$(field driver "$TESTED")" = "$sum" ]
}

# --- status --------------------------------------------------------------------------------------------------

do_status() {
    local id
    if id=$(board_id); then echo "Board: BC-250 (1002:$id)"; else echo "Board: no BC-250 found (1002:13fe or 1002:143f)"; fi
    echo "Kernel: $(kernel)"
    echo "System Mesa: $(system_mesa | grep . || echo unknown)"
    echo "DirectMesh: $DIRECTMESH, Mesa $MESA_VER, suite patch $(suite_patch_id | grep . || echo '?')"
    if [ -f "$STAGE_DRIVER/BUILD-INFO" ]; then
        echo "Build: $(build_info "$STAGE_DRIVER/BUILD-INFO")"
    else
        echo "Build: none"
    fi
    if [ ! -f "$DRIVER_LIB" ]; then
        echo "Driver: not installed"
        echo "Test: none"
    else
        echo "Driver: installed, $(build_info "$DRIVER_DIR/BUILD-INFO")"
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
    local fedora
    command -v podman >/dev/null 2>&1 || error "podman is not installed (Bazzite ships it)."
    command -v curl >/dev/null 2>&1 || error "curl is not installed."
    fedora=$(. /etc/os-release && echo "${VERSION_ID:-}")
    [ -n "$fedora" ] || error "Could not read the Fedora version from /etc/os-release."

    info "Building RADV with DirectMesh $DIRECTMESH (Mesa $MESA_VER) in a Fedora $fedora container"
    mkdir -p "$CACHE/src" "$CACHE/work"
    find "$CACHE/src" -name 'mesa-*' ! -name "mesa-$MESA_VER.tar.xz*" -delete      # older sources
    download "$MESA_URL/mesa-$MESA_VER.tar.xz" "$CACHE/src/mesa-$MESA_VER.tar.xz"
    download "$MESA_URL/mesa-$MESA_VER.tar.xz.sig" "$CACHE/src/mesa-$MESA_VER.tar.xz.sig"
    # In the background with a trap, so stopping this script (the app's window closing) stops the container too.
    # label=disable: the folders are mounted as they are, instead of relabelled (the app's are root's).
    trap 'podman rm -f "$BUILD_CONTAINER" >/dev/null 2>&1; exit 143' TERM INT HUP
    podman run --rm --replace --name "$BUILD_CONTAINER" --security-opt label=disable --pull=newer \
        -v "$HERE:/app:ro" -v "$CACHE/src:/src:ro" -v "$CACHE/work:/work" \
        -e MESA_VER="$MESA_VER" -e PREFIX="$PREFIX" -e DIRECTMESH="$DIRECTMESH" -e PATCH_SHA256="$PATCH_SHA256" \
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
    for f in lib64/libvulkan_radeon.so share/vulkan/icd.d/radeon_icd.x86_64.json libexec/bc250-mesh-test BUILD-INFO; do
        [ -f "$STAGE_DRIVER/$f" ] || error "No complete build in $STAGE_DRIVER ($f is missing): build it first."
    done
    grep -qF "\"$PREFIX/lib64/libvulkan_radeon.so\"" "$STAGE_DRIVER/share/vulkan/icd.d/radeon_icd.x86_64.json" ||
        error "The build was made for another folder than $PREFIX: build it again."
    missing=$(ldd "$STAGE_DRIVER/lib64/libvulkan_radeon.so" 2>/dev/null | awk '/not found/ {print $1}' || true)
    [ -z "$missing" ] || error "The driver needs libraries this system does not have: $(echo "$missing" | tr '\n' ' ')"

    info "Installing the driver in $DRIVER_DIR ($(build_info "$STAGE_DRIVER/BUILD-INFO"))"
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
    install -D -m 755 "$HERE/$RUNNER_NAME" "$RUNNER"
    command -v restorecon >/dev/null 2>&1 && [ -z "$ROOT_DIR" ] && restorecon -R "$DRIVER_DIR" "$RUNNER" 2>/dev/null
    info "Installed. Nothing uses it yet: run the test next ($0 --test)."
}

do_remove_driver() {
    need_root --remove-driver
    rm -rf "$DRIVER_DIR" "$DRIVER_DIR.new"
    rm -f "$RUNNER"
    info "The driver is removed."
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
    [ -f "$DRIVER_LIB" ] && [ -x "$MESH_TEST" ] || error "The driver is not installed."
    board_id >/dev/null || warn "No BC-250 found: the test runs, but its result says nothing about a BC-250."
    sum=$(driver_sum)
    mkdir -p "$STATE"
    rm -f "$TESTED" "$TEST_FAILED"
    info "Testing $(build_info "$DRIVER_DIR/BUILD-INFO") on kernel $(kernel)"
    before=$(fault_count)
    set +e
    env -u VK_ICD_FILENAMES VK_DRIVER_FILES="$ICD" timeout 600 "$MESH_TEST" --rounds "$rounds" 2>&1 |
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

# --- arguments -----------------------------------------------------------------------------------------------

ACTION=""
ROUNDS=10
while [ $# -gt 0 ]; do
    case "$1" in
        --status|--build|--install-driver|--test|--remove-driver|--launch-options)
            [ -z "$ACTION" ] || error "Give one action at a time."; ACTION=$1 ;;
        --rounds) ROUNDS=${2:-}; shift || true; [[ $ROUNDS =~ ^[1-9][0-9]*$ ]] || error "--rounds takes a number." ;;
        --version) echo "bc250-mesh-shaders $VERSION (DirectMesh $DIRECTMESH, Mesa $MESA_VER)"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; error "Unknown option: $1" ;;
    esac
    shift
done

case "$ACTION" in
    --status) do_status ;;
    --build) do_build ;;
    --install-driver) do_install_driver ;;
    --test) do_test "$ROUNDS" ;;
    --remove-driver) do_remove_driver ;;
    --launch-options) launch_options; echo ;;
    *) usage >&2; exit 2 ;;
esac
