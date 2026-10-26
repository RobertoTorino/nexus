#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Media Tool for the current user, from a clone or the extracted release tarball:
#
#   ./install.sh                         install or update
#   ./install.sh --no-desktop-shortcut   app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             remove the app
#   ./install.sh --uninstall --purge     the same: the app keeps no settings
#
# Run it as your own user, not with sudo. Recordings in ~/MediaToolRecordings are never removed.
set -euo pipefail

APP_ID="media-tool"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_DIR/$APP_ID"
RECORDINGS_DIR="$HOME/MediaToolRecordings"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# The tool before its rename (Simple Demo Tool): its launcher, menu entry, Desktop icon and folder (no settings).
OLD_ID="simple-demo-tool"

# Install and uninstall both remove a copy installed under the old name; its recordings folder stays.
remove_old() {
    rm -f "$HOME/.local/bin/$OLD_ID" "$DATA_DIR/applications/$OLD_ID.desktop" "$DESKTOP_DIR/$OLD_ID.desktop"
    rm -rf -- "${DATA_DIR:?}/$OLD_ID"
}
info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

usage() { sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'; }

DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg (use --help)." ;;
    esac
done
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

if $UNINSTALL; then
    info "Removing Media Tool"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    rm -rf -- "$APP_DIR"
    remove_old
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$DATA_DIR/applications" || true
    info "Media Tool is uninstalled. The recordings in $RECORDINGS_DIR are kept."
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "Media Tool runs on Linux (Bazzite) only."
[ -f "$SRC/VERSION" ] && [ -f "$SRC/requirements.txt" ] &&
    [ -f "$SRC/media_tool/__main__.py" ] &&
    [ -f "$SRC/images/media-tool.webp" ] &&
    [ -f "$SRC/images/media-tool-128.png" ] ||
    die "Run install.sh from the complete Media Tool folder."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' ||
    die "Python 3.11 or newer is required."

info "Installing app files in $APP_DIR"
mkdir -p "$APP_DIR" "$RECORDINGS_DIR" "$HOME/.local/bin" "$DATA_DIR/applications"
remove_old
rm -rf -- "$APP_DIR/media_tool"
cp -R "$SRC/media_tool" "$APP_DIR/media_tool"
rm -rf -- "$APP_DIR/images"
cp -R "$SRC/images" "$APP_DIR/images"
cp "$SRC/requirements.txt" "$APP_DIR/requirements.txt"

VENV="$APP_DIR/venv"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV" || die "Could not create the app's Python venv."
fi
info "Installing PyQt6, the OBS WebSocket client and Pillow in the app's own venv"
"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets, PyQt6.QtMultimedia, PyQt6.QtMultimediaWidgets, obsws_python, dbus_next, PIL' ||
    die "The app dependencies did not import successfully."

cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR" || exit 1
exec "$VENV/bin/python" -m media_tool "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=Media Tool
GenericName=Screen recording helper
Comment=Prepare and record a portal installation demo
Exec=$LAUNCHER
Icon=$APP_DIR/images/media-tool-128.png
Terminal=false
Categories=Utility;AudioVideo;
Keywords=OBS;recording;Bazzite;demo;
StartupNotify=true"
printf '%s\n' "$DESKTOP_CONTENT" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    printf '%s\n' "$DESKTOP_CONTENT" >"$DESKTOP_ICON"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
else
    rm -f "$DESKTOP_ICON"
fi
command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database -q "$DATA_DIR/applications" || true
info "Media Tool is installed. Start it from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop')."
