#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# Removes everything packaging/bazzite/install-bisect-gui.sh set up for the current user. Does not
# touch any bisect results in ~/.local/share/bc250-cu-bisect or the --auto systemd unit - disable
# that yourself with: systemctl --user disable --now bc250-cu-bisect-auto.service
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$DATA_HOME/bc250-bisect-gui"
LAUNCHER="$BIN_HOME/bc250-bisect-gui"
DESKTOP_FILE="$DATA_HOME/applications/bc250-cu-bisect.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
ICON_FILE="$DATA_HOME/icons/hicolor/128x128/apps/bc250-cu-bisect.png"
OLD_ICON="$DATA_HOME/icons/hicolor/512x512/apps/bc250-cu-bisect.png"   # the 512 px icon of before

rm -rf "$APP_DIR"
rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE" "$OLD_ICON" "$DESKTOP_DIR/bc250-cu-bisect.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

echo "Removed BC-250 CU Bisect launcher GUI (app, venv, launcher, menu entry, icon, Desktop icon)."
