#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the BC-250 CU toolset (bisect GUI + unlock GUI) as desktop apps, from a clone or the extracted release
# tarball:
#
#   ./install.sh                         # install or update both GUIs
#   ./install.sh --bisect-only           # only the bisect GUI
#   ./install.sh --unlock-only           # only the unlock GUI
#   ./install.sh --no-desktop-shortcut   # app menu entries only, no icons on the Desktop
#   ./install.sh --uninstall             # remove the apps; keeps results, settings and logs
#   ./install.sh --uninstall --purge     # also remove results, settings, logs and the autostart entries
#
# Run it as your own user, not with sudo; nothing here needs root. Each GUI gets its own venv with PyQt6 under
# ~/.local/share (bc250-bisect-gui, bc250-unlock-cu-gui), a launcher in ~/.local/bin, an app menu entry and a
# Desktop icon. The work is done by packaging/bazzite/install-bisect-gui.sh and install-gui.sh (and their
# uninstallers), which can also be run on their own.
set -euo pipefail

APP_NAME="BC-250 CU Bisect"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_DIR="$DATA_DIR/bc250-cu-bisect"                # the bisect script's runs, logs and results
SETTINGS_DIR="$CONFIG_DIR/bc250-cu-bisect"            # both GUIs' settings (QSettings organization)
AUTO_UNIT="$CONFIG_DIR/systemd/user/bc250-cu-bisect-auto.service"
WATCH_ENTRY="$CONFIG_DIR/autostart/bc250-cu-bisect-watch.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
PACKAGING="$SRC/packaging/bazzite"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
usage() { sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'; }

DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
WANT_BISECT=true
WANT_UNLOCK=true
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        --bisect-only) WANT_UNLOCK=false ;;
        --unlock-only) WANT_BISECT=false ;;
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done
$WANT_BISECT || $WANT_UNLOCK || die "--bisect-only and --unlock-only cannot be combined."
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the venvs and the launchers belong in your home folder."
for f in install-bisect-gui.sh install-gui.sh uninstall-bisect-gui.sh uninstall-gui.sh; do
    [ -f "$PACKAGING/$f" ] || die "packaging/bazzite/$f is missing: run install.sh from a clone or the extracted release folder."
done

if $UNINSTALL; then
    info "Removing the bisect GUI"
    bash "$PACKAGING/uninstall-bisect-gui.sh"
    info "Removing the unlock GUI"
    bash "$PACKAGING/uninstall-gui.sh"
    if $PURGE; then
        info "Removing the autostart entries, results, logs and settings"
        if [ -f "$AUTO_UNIT" ]; then
            systemctl --user disable --now bc250-cu-bisect-auto.service 2>/dev/null || true
            rm -f "$AUTO_UNIT"
            systemctl --user daemon-reload 2>/dev/null || true
        fi
        rm -f "$WATCH_ENTRY"
        rm -rf "${STATE_DIR:?}" "${SETTINGS_DIR:?}"
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "These apps run on Linux (Bazzite) only."
OPTIONS=()
$DESKTOP_SHORTCUT || OPTIONS+=(--no-desktop-shortcut)
if $WANT_BISECT; then
    info "Installing the bisect GUI"
    bash "$PACKAGING/install-bisect-gui.sh" "${OPTIONS[@]}"
else
    bash "$PACKAGING/uninstall-bisect-gui.sh" >/dev/null
fi
if $WANT_UNLOCK; then
    info "Installing the unlock GUI"
    bash "$PACKAGING/install-gui.sh" "${OPTIONS[@]}"
else
    bash "$PACKAGING/uninstall-gui.sh" >/dev/null
fi
info "$APP_NAME is installed."
