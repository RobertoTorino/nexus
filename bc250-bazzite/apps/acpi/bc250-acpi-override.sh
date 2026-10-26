#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# bc250-acpi-override — persistent ACPI fix for the AMD BC-250.
#
# Installs the SSDT overrides from e-tho/bc250-acpi-fix as a GRUB early
# initrd. Survives kernel and rpm-ostree/image updates: the blscfg GRUB
# module prepends GRUB_EARLY_INITRD_LINUX_CUSTOM to every BLS boot entry,
# including kernels installed later.
#
# Usage:
#   sudo ./bc250-acpi-override.sh --install          # install, then reboot
#   sudo ./bc250-acpi-override.sh --install --yes    # also answer "yes" to the warnings
#   sudo ./bc250-acpi-override.sh --uninstall        # fully reverses --install, then reboot
#   ./bc250-acpi-override.sh --status                # with sudo it also reads the kernel log
#
# Without a terminal (from the app), a warning that would ask "Continue anyway?" stops the
# install with exit code 3 instead; the app shows the warning and runs again with --yes.
set -euo pipefail

# BC250_ACPI_ROOT is for testing only: a folder that stands in for / (boot, etc and sys).
ROOT_DIR="${BC250_ACPI_ROOT:-}"
CPIO_SRC="$(cd "$(dirname "$0")" && pwd)/tables/acpi_override.cpio"
CPIO_DST="$ROOT_DIR/boot/acpi_override.cpio"
GRUB_DEFAULT="$ROOT_DIR/etc/default/grub"
GRUB_LINE='GRUB_EARLY_INITRD_LINUX_CUSTOM="../../acpi_override.cpio"'
CPU0="$ROOT_DIR/sys/devices/system/cpu/cpu0"
NEEDS_CONFIRMATION=3

info()  { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '10,14p' "$0" | sed 's/^# \{0,1\}//'; }

YES=false

# After a warning: ask on a terminal, stop with NEEDS_CONFIRMATION without one.
confirm() {
    $YES && return 0
    if [ -t 0 ]; then
        read -rp "Continue anyway? [y/N] " a; [[ ${a,,} == y ]] || exit 1
    else
        warn "Not installed: confirm the warning above to continue (--yes)."
        exit "$NEEDS_CONFIRMATION"
    fi
}

regenerate_grub() {
    if command -v ujust >/dev/null 2>&1; then
        info "Regenerating GRUB config (ujust regenerate-grub)..."
        ujust regenerate-grub
    elif command -v grub2-mkconfig >/dev/null 2>&1; then
        info "Regenerating GRUB config (grub2-mkconfig)..."
        grub2-mkconfig -o /boot/grub2/grub.cfg
    else
        error "Neither ujust nor grub2-mkconfig found; regenerate your GRUB config manually."
    fi
}

do_install() {
    [ "$(id -u)" -eq 0 ] || error "Run as root: sudo $0 --install"
    [ -f "$CPIO_SRC" ] || error "tables/acpi_override.cpio not found next to this script."

    # Sanity: BC-250 uses the 'cyan skillfish' GPU (1002:13fe).
    if command -v lspci >/dev/null 2>&1 && ! lspci -nd 1002:13fe | grep -q .; then
        warn "No BC-250 GPU (1002:13fe) detected. This fix is only meant for the AMD BC-250."
        confirm
    fi

    # Modded BIOSes may ship their own ACPI fixes; duplicate tables fail to load.
    bios_ver=$(cat "$ROOT_DIR/sys/class/dmi/id/bios_version" 2>/dev/null || true)
    if printf '%s' "$bios_ver" | grep -qiE 'mei|dxe|mod|unlock'; then
        warn "BIOS version '$bios_ver' looks modded. If it already injects ACPI fixes, do NOT install this override."
        confirm
    fi

    # Kernel must support the ACPI table upgrade mechanism.
    for cfg in "$ROOT_DIR/boot/config-$(uname -r)" "$ROOT_DIR/usr/lib/modules/$(uname -r)/config"; do
        if [ -r "$cfg" ]; then
            grep -q '^CONFIG_ACPI_TABLE_UPGRADE=y' "$cfg" \
                || error "Kernel lacks CONFIG_ACPI_TABLE_UPGRADE; the override cannot load."
            break
        fi
    done

    # Already loaded from a previous install or another method?
    if journalctl -b -k --no-pager -q 2>/dev/null | grep -qiE 'ACPI: Table Upgrade'; then
        info "An ACPI table override is already active this boot; reinstalling the files anyway."
    fi

    install -m 0644 "$CPIO_SRC" "$CPIO_DST"
    info "Installed $CPIO_DST"

    if grep -q '^GRUB_EARLY_INITRD_LINUX_CUSTOM=' "$GRUB_DEFAULT" 2>/dev/null; then
        sed -i "s|^GRUB_EARLY_INITRD_LINUX_CUSTOM=.*|$GRUB_LINE|" "$GRUB_DEFAULT"
        info "Updated existing GRUB_EARLY_INITRD_LINUX_CUSTOM in $GRUB_DEFAULT"
    else
        printf '%s\n' "$GRUB_LINE" >> "$GRUB_DEFAULT"
        info "Appended early-initrd line to $GRUB_DEFAULT"
    fi

    regenerate_grub

    info "Done. Reboot, then verify with:"
    info "  sudo dmesg | grep -iE 'ACPI.*(SSDT|Table Upgrade)'"
    info "  cpupower frequency-info   # 8 steps, 800 MHz - 3.2 GHz"
    info "  cpupower idle-info        # POLL, C1, C2"
}

do_uninstall() {
    [ "$(id -u)" -eq 0 ] || error "Run as root: sudo $0 --uninstall"

    rm -f "$CPIO_DST"
    info "Removed $CPIO_DST"

    sed -i '/^GRUB_EARLY_INITRD_LINUX_CUSTOM=/d' "$GRUB_DEFAULT"
    info "Removed early-initrd line from $GRUB_DEFAULT"

    regenerate_grub

    info "Done. Reboot to return to the BIOS-provided ACPI tables."
}

# One "Name: value" line each; the app reads the Override line.
do_status() {
    local files=0 steps idle freqs min max
    [ -f "$CPIO_DST" ] && files=$((files + 1))
    grep -qF "$GRUB_LINE" "$GRUB_DEFAULT" 2>/dev/null && files=$((files + 1))
    case $files in
        2) echo "Override: installed ($CPIO_DST and the GRUB line)" ;;
        0) echo "Override: not installed" ;;
        *) echo "Override: incomplete ($([ -f "$CPIO_DST" ] && echo "GRUB line missing" || echo "$CPIO_DST missing")); install again or uninstall" ;;
    esac

    freqs=$(cat "$CPU0/cpufreq/scaling_available_frequencies" 2>/dev/null || true)
    if [ -n "$freqs" ]; then
        steps=$(wc -w <<<"$freqs")
        min=$(tr ' ' '\n' <<<"$freqs" | grep . | sort -n | head -1)
        max=$(tr ' ' '\n' <<<"$freqs" | grep . | sort -n | tail -1)
        echo "Frequency steps: $steps ($((min / 1000))-$((max / 1000)) MHz; the override gives 8, 800-3200 MHz)"
    else
        echo "Frequency steps: none listed (the BIOS tables give none; the override gives 8)"
    fi
    idle=$(cat "$CPU0"/cpuidle/state*/name 2>/dev/null | paste -sd, - || true)
    echo "Idle states: ${idle:-none listed} (the override gives POLL,C1,C2)"

    if [ "$(id -u)" -eq 0 ]; then
        if journalctl -b -k --no-pager -q 2>/dev/null | grep -qiE 'ACPI: Table Upgrade'; then
            echo "Kernel log: override tables loaded this boot"
        else
            echo "Kernel log: no override tables loaded this boot"
        fi
    else
        echo "Kernel log: run with sudo to also check this."
    fi
}

ACTION=""
for arg in "$@"; do
    case "$arg" in
        --install|--uninstall|--status) [ -z "$ACTION" ] || error "Give one of --install, --uninstall or --status."; ACTION=$arg ;;
        --yes) YES=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; error "Unknown option: $arg" ;;
    esac
done

case "$ACTION" in
    --install) do_install ;;
    --uninstall) do_uninstall ;;
    --status) do_status ;;
    *) usage >&2; exit 2 ;;
esac
