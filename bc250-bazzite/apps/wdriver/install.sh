#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs BC-250 USB Wi-Fi as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app and the driver's service; keeps its settings and builds
#   ./install.sh --uninstall --purge     # also remove its settings and the builds in your home folder
#
# Run it as your own user; installing needs no root. The app reads the stick and builds the driver without root; it
# installs the driver, its service and the stick's rule, and removes them, only when you ask, through a password
# prompt (pkexec) and the system python3.
#  * ~/.local/share/bc250-usb-wifi/app: the app, with the bc250_core it was tested with (bundled in the release;
#    taken from the suite checkout when run from there); src/ and build/ beside it hold the driver sources and
#    builds the app makes.
#  * ~/.local/share/bc250-bazzite-suite/venv, the BC250 Bazzite Suite's shared venv with PyQt6 (the wheels bundle
#    Qt; nothing is layered). It is removed with the last suite app that uses it.
#  * /etc/bc250-usb-wifi (driver.py, driver.json), /etc/systemd/system/bc250-usb-wifi.service,
#    /etc/udev/rules.d/90-bc250-usb-wifi.rules and /var/lib/bc250-usb-wifi (the sources and the built modules):
#    the driver, only while it is installed in the app. Uninstalling removes it (sudo); an update says when the
#    installed copy is from another version.
#  * ~/.local/bin/bc250-usb-wifi to start it from a terminal, plus an app menu entry and a Desktop icon.
set -euo pipefail

APP_ID="bc250-usb-wifi"
APP_NAME="BC-250 USB Wi-Fi"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_DIR="$DATA_DIR/$APP_ID/app"
SUITE_DIR="$DATA_DIR/bc250-bazzite-suite"
VENV="$SUITE_DIR/venv"                       # shared by the suite's apps
VENV_USERS="$SUITE_DIR/venv-users"           # one file per app that uses it
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"

SYSTEM_ROOT="${BC250_SYSTEM_ROOT:-}"         # override only for testing
DRIVER_UNIT="bc250-usb-wifi.service"
DRIVER_DIR="$SYSTEM_ROOT/etc/$APP_ID"
DRIVER_FILES=("$SYSTEM_ROOT/etc/systemd/system/$DRIVER_UNIT" "$SYSTEM_ROOT/etc/udev/rules.d/90-$APP_ID.rules"
              "$DRIVER_DIR" "$SYSTEM_ROOT/var/lib/$APP_ID")

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to usb_wifidriver in a release; in the suite checkout it lives in core/.
if [ -d "$SRC/bc250_core" ]; then CORE_SRC="$SRC/bc250_core"; else CORE_SRC="$SRC/../../../core/bc250_core"; fi

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

usage() { sed -n '3,8p' "$0" | sed 's/^# \{0,1\}//'; }

DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the app, the venv and the launcher belong in your home folder."

if $UNINSTALL; then
    if [ -e "${DRIVER_FILES[0]}" ] || [ -e "$DRIVER_DIR" ]; then
        # Stopping the service unloads the driver; the stick is without one until the app installs it again.
        info "Stopping and removing the driver's service $DRIVER_UNIT (sudo)"
        as_root systemctl disable --now "$DRIVER_UNIT" >/dev/null 2>&1 || true
        as_root rm -rf "${DRIVER_FILES[@]}"
        as_root systemctl daemon-reload >/dev/null 2>&1 || true
        as_root udevadm control --reload >/dev/null 2>&1 || true
    fi
    info "Removing the launcher, the menu entry and the app"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "${DATA_DIR:?}/$APP_ID/app"
    rm -f "$VENV_USERS/$APP_ID"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Keeping the suite venv: other suite apps still use it"
    else
        info "Removing the suite venv"
        rm -rf "$VENV"
    fi
    if $PURGE; then
        info "Removing the settings and the builds"
        rm -rf "${CONFIG_DIR:?}/$APP_ID" "${DATA_DIR:?}/$APP_ID"
    fi
    rmdir "${DATA_DIR:?}/$APP_ID" 2>/dev/null || true
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in requirements.txt VERSION usb_wifidriver/__main__.py usb_wifidriver/driver.py \
         "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."
command -v pkexec >/dev/null 2>&1 || info "Note: pkexec is not installed; installing and removing the driver needs it."
for tool in gcc make git; do
    command -v "$tool" >/dev/null 2>&1 || info "Note: $tool is not installed; building the driver needs it."
done

info "Installing $APP_NAME $VERSION"

# --- 1. The app and its bc250_core --------------------------------------------------------------
info "Copying the app to $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
(cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='./tests' --exclude='__pycache__' -cf - .) |
    tar -xf - -C "$APP_DIR"
if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then         # from the checkout: bundle core like a release
    mkdir -p "$APP_DIR/bc250_core"
    (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$APP_DIR/bc250_core"
fi

# --- 2. Shared suite venv with PyQt6 ------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the suite venv in $VENV"
    rm -rf "$VENV"
    mkdir -p "$SUITE_DIR"
    python3 -m venv "$VENV"
fi
mkdir -p "$VENV_USERS"
touch "$VENV_USERS/$APP_ID"
info "Installing PyQt6 into the venv (downloads ~100 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' || die "PyQt6 does not load from the venv."

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the app folder, so python -m never picks up a
# usb_wifidriver folder from the current directory, and imports the bc250_core bundled there.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m usb_wifidriver "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=BC-250 USB Wi-Fi driver
Comment=The driver for AIC8800D80 USB Wi-Fi sticks, built for the running kernel and loaded at boot
Exec=$LAUNCHER
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=System;Network;
Keywords=BC-250;Bazzite;Wi-Fi;WiFi;USB;AIC8800;driver;
StartupNotify=true
StartupWMClass=$APP_ID"

info "Adding the app menu entry"
mkdir -p "$(dirname "$MENU_ENTRY")"
printf '%s\n' "$DESKTOP_FILE_CONTENT" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true

if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    info "Adding the Desktop icon"
    printf '%s\n' "$DESKTOP_FILE_CONTENT" >"$DESKTOP_ICON"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
elif ! $DESKTOP_SHORTCUT; then
    rm -f "$DESKTOP_ICON"
fi

if [ -f "$DRIVER_DIR/driver.py" ] && ! cmp -s "$DRIVER_DIR/driver.py" "$APP_DIR/usb_wifidriver/driver.py"; then
    info "The driver's service is from another version: press Update in the app (it asks for your password)"
fi

info "Done. Start \"$APP_NAME\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
