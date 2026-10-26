#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the BC-250 GPU OC toolset (script + GUI) as a desktop app, from a clone or the
# extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps results, settings and logs
#   ./install.sh --uninstall --purge     # also remove results, settings and logs
#
# Run it as your own user, not with sudo: only the copy to /opt asks for the sudo password.
set -euo pipefail

APP_ID="bc250-gpu-oc-bisect"
APP_NAME="BC-250 GPU OC Bisect"
OPT_DIR="${BC250_OPT_DIR:-/opt}"            # override only for testing
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
VENV="$DATA_DIR/$APP_ID-app/venv"
STATE_DIR="$DATA_DIR/$APP_ID"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
LINK="$OPT_DIR/$APP_ID"

LAUNCHER="$BIN_DIR/$APP_ID-gui"
DESKTOP_FILE="$APP_ID-gui.desktop"
ICON_FILE="images/$APP_ID-128.png"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

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
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."

refresh_menu() {
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$DATA_DIR/applications" || true
}

remove_menu_entries() {
    rm -f "$LAUNCHER" \
          "$DATA_DIR/applications/$DESKTOP_FILE" \
          "$DESKTOP_DIR/$DESKTOP_FILE"
    refresh_menu
}

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the venv and launcher belong in your home folder."

if $UNINSTALL; then
    info "Removing launcher and menu entry"
    remove_menu_entries
    info "Removing $LINK and installed versions (sudo)"
    as_root rm -rf "$LINK" "$OPT_DIR/$APP_ID"-v*
    info "Removing venv"
    rm -rf "$DATA_DIR/$APP_ID-app"
    if $PURGE; then
        info "Removing results, logs and settings"
        rm -rf "${STATE_DIR:?}" "${CONFIG_DIR:?}/$APP_ID"
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in bc250-gpu-oc-bisect.sh requirements.txt VERSION oc_bisect/__main__.py \
         "images/$APP_ID.webp" "$ICON_FILE"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
[ -n "$VERSION" ] || die "Could not read the version from VERSION."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

TARGET="$OPT_DIR/$APP_ID-v$VERSION"
info "Installing $APP_NAME $VERSION"

# --- 1. Root-owned copy in /opt ----------------------------------------------------------------
if [ "$SRC" = "$(cd "$TARGET" 2>/dev/null && pwd -P)" ]; then
    info "Already running from $TARGET, no copy needed"
else
    info "Copying to $TARGET (sudo)"
    STAGE="$OPT_DIR/.$APP_ID-v$VERSION.new"
    as_root rm -rf "$STAGE"
    as_root mkdir -p "$STAGE"
    (cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='__pycache__' -cf - .) |
        as_root tar -xf - -C "$STAGE" --no-same-owner
    as_root chown -R root:root "$STAGE"
    as_root find "$STAGE" -type d -exec chmod 755 {} +
    as_root find "$STAGE" -type f -exec chmod go-w,a+r {} +
    as_root chmod 755 "$STAGE/bc250-gpu-oc-bisect.sh" "$STAGE/install.sh"
    as_root rm -rf "$TARGET"
    as_root mv "$STAGE" "$TARGET"
    command -v restorecon >/dev/null 2>&1 && as_root restorecon -R "$TARGET" 2>/dev/null || true
fi
as_root ln -sfn "$(basename "$TARGET")" "$LINK"
for old in "$OPT_DIR/$APP_ID"-v*; do
    [ -d "$old" ] && [ "$old" != "$TARGET" ] || continue
    info "Removing previous version $(basename "$old")"
    as_root rm -rf "$old"
done

# --- 2. venv with PyQt6 ------------------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating venv in $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
info "Installing PyQt6 into the venv"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$LINK/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' ||
    die "PyQt6 does not load from the venv; see the error above."

# --- 3. Launcher + menu entry (+ optional Desktop icon) ---------------------------------------
mkdir -p "$BIN_DIR"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
cd "$LINK" || { echo "$APP_NAME is not installed in $LINK; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m oc_bisect --script "$LINK/bc250-gpu-oc-bisect.sh" "\$@"
EOF
chmod 755 "$LAUNCHER"

entry="[Desktop Entry]
Type=Application
Version=1.0
Name=BC-250 GPU OC Bisect
GenericName=BC-250 GPU tool
Comment=Set up and start a BC-250 GPU OC/UV bisect run
Exec=$LAUNCHER
Icon=$LINK/$ICON_FILE
Terminal=false
Categories=System;Settings;
Keywords=BC-250;Bazzite;GPU;overclock;undervolt;bisect;
StartupNotify=true
StartupWMClass=$APP_ID-gui"

mkdir -p "$DATA_DIR/applications"
printf '%s\n' "$entry" >"$DATA_DIR/applications/$DESKTOP_FILE"
chmod 644 "$DATA_DIR/applications/$DESKTOP_FILE"

if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    printf '%s\n' "$entry" >"$DESKTOP_DIR/$DESKTOP_FILE"
    chmod 755 "$DESKTOP_DIR/$DESKTOP_FILE"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_DIR/$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
else
    rm -f "$DESKTOP_DIR/$DESKTOP_FILE"
fi
refresh_menu

info "Done. Start from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run:"
info "  $APP_ID-gui   (or $LINK/bc250-gpu-oc-bisect.sh in a terminal)"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) info "Note: $BIN_DIR is not on your PATH, so the command needs the full path." ;; esac
