#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# What has a newer version on this development machine: Bazzite's image, the Flatpaks, Homebrew's packages
# (gh, shellcheck, fakeroot, node, ffmpeg, ...), the Rust toolchain and the Python packages of the development
# venv (.venv-linux). It only looks; nothing is installed. Bazzite's own updater (uupd, daily at 04:00) installs the
# image, the Flatpaks and Homebrew's packages; the venv is pip's and the toolchain rustup's, as the output says.
#
#   tools/dev-updates.sh              # list what is outdated, per source
#   tools/dev-updates.sh --notify     # the same, plus a desktop notification when something is
#   tools/dev-updates.sh --install    # a user timer that runs --notify every hour (nexus-dev-updates.timer)
#   tools/dev-updates.sh --uninstall  # removes the timer
#
# Exit code: 0 when everything is current, 10 when something has a newer version, 1 when a source could not be
# checked. Linux only; on Windows, `winget upgrade` lists the programs and the venv's pip the packages.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
UNIT="nexus-dev-updates"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
usage() { sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'; }

NOTIFY=false
case "${1:-}" in
    "") ;;
    --notify) NOTIFY=true ;;
    --install)
        command -v systemctl >/dev/null || die "systemd is needed for the timer."
        mkdir -p "$UNIT_DIR"
        cat >"$UNIT_DIR/$UNIT.service" <<EOF
# Written by tools/dev-updates.sh --install; --uninstall removes it.
[Unit]
Description=Nexus development: what has a newer version on this machine
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$ROOT/tools/dev-updates.sh --notify
SuccessExitStatus=10
EOF
        cat >"$UNIT_DIR/$UNIT.timer" <<EOF
# Written by tools/dev-updates.sh --install; --uninstall removes it.
[Unit]
Description=Nexus development: hourly look for newer versions

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable --now "$UNIT.timer" >/dev/null
        info "$UNIT.timer runs every hour and notifies when something has a newer version."
        info "Now: systemctl --user start $UNIT.service; the timer: systemctl --user list-timers $UNIT.timer"
        exit 0 ;;
    --uninstall)
        systemctl --user disable --now "$UNIT.timer" >/dev/null 2>&1 || true
        rm -f "$UNIT_DIR/$UNIT.timer" "$UNIT_DIR/$UNIT.service" "$UNIT_DIR/timers.target.wants/$UNIT.timer"
        systemctl --user daemon-reload >/dev/null 2>&1 || true
        info "$UNIT.timer is removed."
        exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

# Each source adds a line to SUMMARY ("Homebrew: gh, node") and its details to DETAILS; FAILED names the sources
# that could not be checked (offline, a tool missing).
SUMMARY=()
DETAILS=""
FAILED=()

report() {   # <source> <how to install> <lines of outdated items, one per line; empty when current>
    local source=$1 how=$2 items=$3 names
    if [ -z "$items" ]; then
        printf '%-14s current\n' "$source:"
        return
    fi
    names=$(printf '%s\n' "$items" | awk '{print $1}' | paste -sd ' ' | sed 's/ /, /g')
    printf '%-14s %s\n%s\n' "$source:" "$how" "$(printf '%s\n' "$items" | sed 's/^/    /')"
    SUMMARY+=("$source: $names")
    DETAILS+="$source ($how): $names"$'\n'
}

failed() {   # <source> <why>
    printf '%-14s could not check (%s)\n' "$1:" "$2"
    FAILED+=("$1")
}

# Bazzite's image: rpm-ostree says what the next deployment would be. Exit 77 is "nothing new".
if command -v rpm-ostree >/dev/null; then
    out=$(timeout 120 rpm-ostree upgrade --check 2>&1); rc=$?
    if [ $rc -eq 77 ] || { [ $rc -eq 0 ] && ! grep -q AvailableUpdate <<<"$out"; }; then
        report "Bazzite" "" ""
    elif [ $rc -eq 0 ]; then
        version=$(grep -m1 -E '^\s*Version:' <<<"$out" | sed 's/^ *Version: *//')
        report "Bazzite" "uupd installs it at 04:00, or: ujust update" "image ${version:-(new deployment)}"
    else
        failed "Bazzite" "$(tail -n1 <<<"$out")"
    fi
fi

# Flatpaks, from every remote the user and the system have.
if command -v flatpak >/dev/null; then
    if out=$(timeout 120 flatpak remote-ls --updates --columns=application,version 2>&1); then
        report "Flatpak" "uupd installs them at 04:00, or: flatpak update" "$out"
    else
        failed "Flatpak" "$(tail -n1 <<<"$out")"
    fi
fi

# Homebrew: fetch the formulae first, else `outdated` only knows what the last fetch knew.
if command -v brew >/dev/null; then
    if timeout 300 brew update --quiet >/dev/null 2>&1 && out=$(brew outdated --verbose 2>&1); then
        report "Homebrew" "uupd installs them at 04:00, or: brew upgrade" "$out"
    else
        failed "Homebrew" "brew update or brew outdated failed"
    fi
fi

# The Rust toolchain (Console Link's native core), when rustup is installed. Exit 100 is "updates available".
if command -v rustup >/dev/null; then
    out=$(timeout 120 rustup check 2>&1); rc=$?
    if [ $rc -eq 0 ] || [ $rc -eq 100 ]; then
        report "Rust" "rustup update" "$(grep -i 'update available' <<<"$out" || true)"
    else
        failed "Rust" "$(tail -n1 <<<"$out")"
    fi
fi

# The development venv: every package requirements-dev.txt pulled in, against PyPI.
if [ -x "$ROOT/.venv-linux/bin/python" ]; then
    if out=$(timeout 300 "$ROOT/.venv-linux/bin/python" -m pip list --outdated --disable-pip-version-check 2>&1); then
        # pip prints a table (Package Version Latest Type) or nothing: keep the rows as "name current -> latest"
        rows=$(awk 'NR > 2 {print $1, $2, "->", $3}' <<<"$out")
        report "Python venv" ".venv-linux/bin/python -m pip install -U <package>" "$rows"
    else
        failed "Python venv" "$(tail -n1 <<<"$out")"
    fi
fi

if $NOTIFY && [ ${#SUMMARY[@]} -gt 0 ] && command -v notify-send >/dev/null; then
    notify-send --app-name="Nexus development" --icon=software-update-available \
        "Newer versions: ${#SUMMARY[@]} source(s)" "$(printf '%s' "$DETAILS")" || true
fi

[ ${#FAILED[@]} -eq 0 ] || exit 1
[ ${#SUMMARY[@]} -eq 0 ] || exit 10
exit 0
