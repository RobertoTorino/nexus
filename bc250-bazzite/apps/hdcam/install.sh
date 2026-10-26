#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs USB HD Cam as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps its settings and firmware
#   ./install.sh --uninstall --purge     # also remove its settings and firmware
#
# Run it as your own user; installing needs no root. The app itself asks for your password once, through pkexec, to
# give your user the camera's boot loader (a udev rule); --uninstall removes that rule again with sudo.
#  * ~/.local/share/bc250-usb-hdcam/app: the app, with the bc250_core it was tested with (bundled in the
#    release; taken from the suite checkout when run from there).
#  * ~/.local/share/bc250-bazzite-suite/venv, the BC250 Bazzite Suite's shared venv with PyQt6 (the wheels bundle
#    Qt; nothing is layered). It is removed with the last suite app that uses it.
#  * ~/.local/bin/bc250-usb-hdcam to start it from a terminal, plus an app menu entry and a Desktop icon.
#  * ~/.config/systemd/user/bc250-usb-hdcam-load.service, enabled for your login: it sends the firmware when the
#    camera is plugged in (started by the app's udev rule) and at login (a camera plugged in before).
#  * Made by the app, removed here on --uninstall: /etc/udev/rules.d/70-bc250-usb-hdcam.rules (Allow access).
#    With --purge also the firmware the app downloaded or was given, ~/.local/share/bc250-usb-hdcam/firmware.
set -euo pipefail

APP_ID="bc250-usb-hdcam"
APP_NAME="USB HD Cam"
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
UNIT_DIR="$CONFIG_DIR/systemd/user"
SERVICE="$APP_ID-load.service"
SYSTEM_ROOT="${BC250_SYSTEM_ROOT:-}"         # override only for testing
UDEV_RULE="$SYSTEM_ROOT/etc/udev/rules.d/70-$APP_ID.rules"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to usb_hdcam in a release; in the suite checkout it lives in core/.
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
    if [ -e "$UDEV_RULE" ]; then
        info "Removing the udev rule for the camera's boot loader (sudo)"
        as_root rm -f "$UDEV_RULE"
        as_root udevadm control --reload >/dev/null 2>&1 || true
    fi
    info "Removing the load service, the launcher, the menu entry and the app"
    rm -f "$UNIT_DIR/default.target.wants/$SERVICE" "$UNIT_DIR/$SERVICE"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
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
        info "Removing the settings and the firmware"
        rm -rf "${CONFIG_DIR:?}/$APP_ID" "${DATA_DIR:?}/$APP_ID"
    else
        rmdir "$DATA_DIR/$APP_ID" 2>/dev/null || true
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in requirements.txt VERSION usb_hdcam/__main__.py "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

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
# usb_hdcam folder from the current directory, and imports the bc250_core bundled there.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m usb_hdcam "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Camera firmware loader
Comment=The PS5 HD Camera (CFI-ZEY1) as a webcam: loads its firmware and shows its picture
Exec=$LAUNCHER
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=AudioVideo;Video;Utility;
Keywords=BC-250;Bazzite;PlayStation;PS5;PS4;HD Camera;CFI-ZEY1;CUH-ZEY2;camera;webcam;OV580;firmware;
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

# --- 4. The load service ------------------------------------------------------------------------
info "Adding the load service $SERVICE"
mkdir -p "$UNIT_DIR/default.target.wants"
cat >"$UNIT_DIR/$SERVICE" <<EOF
# $APP_NAME, written by install.sh: sends the PS5 HD Camera's firmware when the camera is plugged in (the
# app's udev rule starts this service) and at login (a camera that was plugged in before). It does nothing when
# Load it by itself is off in the app, or when no camera waits for its firmware.
[Unit]
Description=$APP_NAME: load the PS5 HD Camera's firmware

[Service]
Type=oneshot
ExecStart="$LAUNCHER" --load --auto

[Install]
WantedBy=default.target
EOF
chmod 644 "$UNIT_DIR/$SERVICE"
ln -sfn "../$SERVICE" "$UNIT_DIR/default.target.wants/$SERVICE"
systemctl --user daemon-reload >/dev/null 2>&1 || true

[ -e "$UDEV_RULE" ] || info "The first time, the app asks for your password once to give your user the camera's boot loader (Allow access)."
info "Done. Start \"$APP_NAME\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
