#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Bazzite SFTP Tools as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps its profiles, settings and log
#   ./install.sh --uninstall --purge     # also remove its profiles, settings and log
#
# Run it as your own user; installing needs no root. The app is a client: the Bazzite host you connect to only
# needs a reachable sshd. Trusted hosts in ~/.ssh/known_hosts are never touched.
#  * ~/.local/share/bc250-bazzite-sftp-tools/app: the app, with the bc250_core it was tested with (bundled in the
#    release; taken from the suite checkout when run from there).
#  * ~/.local/share/bc250-bazzite-sftp-tools/venv: the app's own Python venv with PyQt6 and paramiko (the suite's
#    shared venv has no paramiko).
#  * ~/.config/bc250-bazzite-sftp-tools: settings and connection profiles, once you save them in the app.
#  * ~/.local/share/bc250-bazzite-sftp-tools/bc250-bazzite-sftp-tools.log: the app's log.
#  * ~/.local/bin/bc250-bazzite-sftp-tools to start it from a terminal, plus an app menu entry and a Desktop icon.
set -euo pipefail

APP_ID="bc250-bazzite-sftp-tools"
APP_NAME="Bazzite SFTP Tools"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_HOME="$DATA_DIR/$APP_ID"
APP_DIR="$APP_HOME/app"
VENV="$APP_HOME/venv"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to sftp_tools in a release; in the suite checkout it lives in core/.
if [ -d "$SRC/bc250_core" ]; then CORE_SRC="$SRC/bc250_core"; else CORE_SRC="$SRC/../../../core/bc250_core"; fi

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

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
    info "Removing the launcher, the menu entry, the Desktop icon, the app and its venv"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "${APP_HOME:?}/app" "${APP_HOME:?}/venv"
    if $PURGE; then
        info "Removing the profiles, the settings and the log"
        rm -rf "${CONFIG_DIR:?}/$APP_ID" "${APP_HOME:?}"
    else
        info "Keeping your profiles and settings in $CONFIG_DIR/$APP_ID and the log in $APP_HOME"
        rmdir "$APP_HOME" 2>/dev/null || true
    fi
    info "$APP_NAME is uninstalled. Trusted hosts in ~/.ssh/known_hosts were left untouched."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This installer runs on Linux (Bazzite) only."
for f in requirements.txt VERSION sftp_tools/__main__.py "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
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

# --- 2. The app's own venv with PyQt6 and paramiko ----------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the app's venv in $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV" || die "Could not create the app's Python venv."
fi
info "Installing PyQt6 and paramiko into the venv (downloads ~100 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets, paramiko' || die "PyQt6 or paramiko does not load from the venv."

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the app folder, so python -m never picks up a
# sftp_tools folder from the current directory, and imports the bc250_core bundled there.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m sftp_tools "\$@"
LAUNCHER_EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=SFTP client and server manager
Comment=Transfer files over SFTP and manage the SSH server of a Bazzite host
Exec=$LAUNCHER
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=System;FileTransfer;
Keywords=BC-250;Bazzite;SFTP;SSH;file transfer;
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

info "Done. Start \"$APP_NAME\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
