#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs a launcher, app menu entry and Desktop icon for this checkout. Moving the checkout needs reinstalling.
#
#   ./install.sh                         launcher, app menu entry and Desktop icon
#   ./install.sh --no-desktop-shortcut   launcher and app menu entry only
#   ./install.sh --uninstall             remove them; the checkout stays
#   ./install.sh --uninstall --purge     the same: the app keeps no settings
set -euo pipefail

APP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
APP_ID="bc250-installer-test-gui"
APP_NAME="BC-250 Installer Tests"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ENTRY="$DESKTOP_DIR/$APP_ID.desktop"
ICON="$APP/images/$APP_ID-128.png"
shortcut=true
uninstall=false
purge=false

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) shortcut=false ;;
        --uninstall) uninstall=true ;;
        --purge) purge=true ;;
        -h|--help) sed -n '3,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $arg (use --help)." ;;
    esac
done
$purge && ! $uninstall && die "--purge only goes with --uninstall."
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

if $uninstall; then
    info "Removing the launcher, app menu entry and Desktop icon"
    rm -f -- "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ENTRY"
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$DATA_DIR/applications" || true
    info "$APP_NAME is uninstalled; the checkout is unchanged."
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "This installer creates Linux desktop entries."
[ -f "$APP/run.sh" ] && [ -f "$APP/images/$APP_ID.webp" ] && [ -f "$ICON" ] &&
    [ -f "$APP/installer_test_gui/__main__.py" ] ||
    die "Run install.sh from the complete installer test GUI folder."

info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
[ -x "$APP/run.sh" ] || { echo "Checkout not found; run $APP/install.sh again." >&2; exit 1; }
exec "$APP/run.sh" "\$@"
LAUNCH
chmod 755 "$LAUNCHER"

entry="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Installer test runner
Comment=Run the BC-250 suite installer checks
Exec=\"$LAUNCHER\"
Icon=$ICON
Terminal=false
Categories=Development;System;
Keywords=BC-250;installer;test;
StartupNotify=true
StartupWMClass=$APP_ID"

info "Adding the app menu entry"
mkdir -p "$(dirname "$MENU_ENTRY")"
printf '%s\n' "$entry" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database -q "$DATA_DIR/applications" || true

if $shortcut && [ -d "$DESKTOP_DIR" ]; then
    info "Adding the Desktop icon"
    printf '%s\n' "$entry" >"$DESKTOP_ENTRY"
    chmod 755 "$DESKTOP_ENTRY"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ENTRY" metadata::trusted true 2>/dev/null || true
elif ! $shortcut; then
    rm -f -- "$DESKTOP_ENTRY"
fi

info "Done. Start \"$APP_NAME\" from the app menu$($shortcut && [ -d "$DESKTOP_DIR" ] && echo ' or the Desktop'), or run: $APP_ID"
