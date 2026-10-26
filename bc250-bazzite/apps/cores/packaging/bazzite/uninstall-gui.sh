#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# Removes everything packaging/bazzite/install-gui.sh set up for the current user. Does not touch
# the unlock service - use the GUI's Uninstall button or "sudo ./bc250-cores-unlock.sh --uninstall"
# first if you also want the persistent unlock removed.
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$DATA_HOME/bc250-cores-unlock-gui"
LAUNCHER="$BIN_HOME/bc250-cores-unlock-gui"
DESKTOP_FILE="$DATA_HOME/applications/bc250-cores-unlock.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/128x128/apps/bc250-cores-unlock.png"
OLD_ICON="$DATA_HOME/icons/hicolor/512x512/apps/bc250-cores-unlock.png"   # the 512 px icon of before

rm -rf "$APP_DIR"
rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE" "$OLD_ICON"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true

echo "Removed BC-250 Cores Unlock GUI (app, venv, launcher, menu entry, icon)."
