#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the BC-250 Cores toolset (bisect GUI + unlock GUI) as desktop apps, from a clone or the
# extracted release tarball:
#
#   ./install.sh                         # install or update both GUIs
#   ./install.sh --bisect-only           # only the bisect GUI
#   ./install.sh --unlock-only           # only the unlock GUI
#   ./install.sh --no-desktop-shortcut   # app menu entries only, no icons on the Desktop
#   ./install.sh --uninstall             # remove the apps; keeps results, settings and logs
#   ./install.sh --uninstall --purge     # also remove results, settings, logs and the autostart unit
#
# Run it as your own user, not with sudo: only the copy to /opt asks for the sudo password.
#  * /opt/bc250-cores-bisect-v<version>, root-owned (so the scripts that run under sudo cannot be
#    changed by a normal user), with /opt/bc250-cores-bisect pointing at it; older versions go.
#  * ~/.local/share/bc250-cores-bisect-app/venv with PyQt6 (the wheels bundle Qt; nothing is layered).
#  * ~/.local/bin/bc250-cores-bisect-gui and ~/.local/bin/bc250-cores-unlock-gui to start them from
#    a terminal, plus app menu entries and Desktop icons.
set -euo pipefail

APP_ID="bc250-cores-bisect"
APP_NAME="BC-250 Cores"
OPT_DIR="${BC250_OPT_DIR:-/opt}"            # override only for testing
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
# Not $DATA_DIR/$APP_ID: that folder is the bisect script's own state (runs, logs, config).
VENV="$DATA_DIR/$APP_ID-app/venv"
STATE_DIR="$DATA_DIR/$APP_ID"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
LINK="$OPT_DIR/$APP_ID"
AUTO_UNIT="$CONFIG_DIR/systemd/user/bc250-cores-bisect-auto.service"

BISECT_LAUNCHER="$BIN_DIR/bc250-cores-bisect-gui"
UNLOCK_LAUNCHER="$BIN_DIR/bc250-cores-unlock-gui"
BISECT_DESKTOP="bc250-cores-bisect-gui.desktop"
UNLOCK_DESKTOP="bc250-cores-unlock.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

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

refresh_menu() {
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database -q "$DATA_DIR/applications" || true
}

# The pre-install.sh packaging/bazzite scripts kept a private copy of the app, its own launcher and
# differently named .desktop files; clear those out so there is only one menu entry per GUI.
remove_legacy_install() {
    rm -rf "$DATA_DIR/bc250-cores-bisect-gui" "$DATA_DIR/bc250-cores-unlock-gui"
    rm -f "$DATA_DIR/applications/bc250-cores-bisect.desktop" \
          "$DATA_DIR/icons/hicolor/512x512/apps/bc250-cores-bisect.png" \
          "$DATA_DIR/icons/hicolor/512x512/apps/bc250-cores-unlock.png" \
          "$DATA_DIR/icons/hicolor/128x128/apps/bc250-cores-bisect.png" \
          "$DATA_DIR/icons/hicolor/128x128/apps/bc250-cores-unlock.png"
}

remove_menu_entries() {
    rm -f "$BISECT_LAUNCHER" "$UNLOCK_LAUNCHER" \
          "$DATA_DIR/applications/$BISECT_DESKTOP" "$DATA_DIR/applications/$UNLOCK_DESKTOP" \
          "$DESKTOP_DIR/$BISECT_DESKTOP" "$DESKTOP_DIR/$UNLOCK_DESKTOP"
    refresh_menu
}

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the venv and the launchers belong in your home folder."

if $UNINSTALL; then
    info "Removing the launchers and the menu entries"
    remove_menu_entries
    remove_legacy_install
    info "Removing $LINK and the installed versions (sudo)"
    as_root rm -rf "$LINK" "$OPT_DIR/$APP_ID"-v*
    info "Removing the venv"
    rm -rf "$DATA_DIR/$APP_ID-app"
    if $PURGE; then
        info "Removing the autostart unit, results, logs and settings"
        if [ -f "$AUTO_UNIT" ]; then
            systemctl --user disable --now bc250-cores-bisect-auto.service 2>/dev/null || true
            rm -f "$AUTO_UNIT"
            systemctl --user daemon-reload 2>/dev/null || true
        fi
        rm -rf "${STATE_DIR:?}" "${CONFIG_DIR:?}/$APP_ID"
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "These apps run on Linux (Bazzite) only."
for f in bc250-cores-bisect.sh bc250-cores-unlock.sh requirements.txt VERSION \
         cores_bisect/__main__.py cores_unlock/__main__.py "images/$APP_ID.webp" \
         "images/$APP_ID-128.png" images/bc250-cores-unlock.webp images/bc250-cores-unlock-128.png; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
[ -n "$VERSION" ] || die "Could not read the version from VERSION."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

TARGET="$OPT_DIR/$APP_ID-v$VERSION"
info "Installing $APP_NAME $VERSION"

# --- 1. Root-owned copy in /opt -----------------------------------------------------------------
if [ "$SRC" = "$(cd "$TARGET" 2>/dev/null && pwd -P)" ]; then
    info "Already running from $TARGET, no copy needed"
else
    info "Copying to $TARGET (sudo)"
    STAGE="$OPT_DIR/.$APP_ID-v$VERSION.new"
    as_root rm -rf "$STAGE"
    as_root mkdir -p "$STAGE"
    # Plain copy, no -a: the files get /opt's default SELinux label instead of the Downloads one.
    (cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='__pycache__' -cf - .) |
        as_root tar -xf - -C "$STAGE" --no-same-owner
    as_root chown -R root:root "$STAGE"
    as_root find "$STAGE" -type d -exec chmod 755 {} +
    as_root find "$STAGE" -type f -exec chmod go-w,a+r {} +
    as_root chmod 755 "$STAGE/bc250-cores-bisect.sh" "$STAGE/bc250-cores-unlock.sh"
    as_root rm -rf "$TARGET"
    as_root mv "$STAGE" "$TARGET"
    command -v restorecon >/dev/null 2>&1 && as_root restorecon -R "$TARGET" 2>/dev/null || true
fi
as_root ln -sfn "$(basename "$TARGET")" "$LINK"
for old in "$OPT_DIR/$APP_ID"-v*; do
    [ -d "$old" ] && [ "$old" != "$TARGET" ] || continue
    info "Removing the previous version $(basename "$old")"
    as_root rm -rf "$old"
done

# --- 2. venv with PyQt6 -------------------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the venv in $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
info "Installing PyQt6 into the venv (downloads ~100 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$LINK/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' ||
    die "PyQt6 does not load from the venv - see the error above; this is usually a missing system Qt/X11 library (e.g. libxcb-cursor0, libEGL)."

# --- 3. Launchers, menu entries, Desktop icons --------------------------------------------------
remove_legacy_install

write_launcher() {
    # $1 launcher path, $2 python package
    mkdir -p "$(dirname "$1")"
    cat >"$1" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the root-owned app folder, so python -m
# never picks up a $2 folder from the current directory.
cd "$LINK" || { echo "$APP_NAME is not installed in $LINK; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m $2 "\$@"
EOF
    chmod 755 "$1"
}

write_entry() {
    # $1 .desktop file name, $2 StartupWMClass/desktop id, $3 Name, $4 Comment, $5 launcher path, $6 icon in images/
    local content="[Desktop Entry]
Type=Application
Version=1.0
Name=$3
GenericName=BC-250 core tools
Comment=$4
Exec=$5
Icon=$LINK/images/$6-128.png
Terminal=false
Categories=System;Settings;
Keywords=BC-250;Bazzite;cores;bisect;unlock;CPU;
StartupNotify=true
StartupWMClass=$2"

    mkdir -p "$DATA_DIR/applications"
    printf '%s\n' "$content" >"$DATA_DIR/applications/$1"
    chmod 644 "$DATA_DIR/applications/$1"

    if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
        printf '%s\n' "$content" >"$DESKTOP_DIR/$1"
        # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
        chmod 755 "$DESKTOP_DIR/$1"
        command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_DIR/$1" metadata::trusted true 2>/dev/null || true
    else
        rm -f "$DESKTOP_DIR/$1"
    fi
}

if $WANT_BISECT; then
    info "Creating the launcher $BISECT_LAUNCHER and its menu entry"
    write_launcher "$BISECT_LAUNCHER" cores_bisect
    write_entry "$BISECT_DESKTOP" bc250-cores-bisect-gui "BC-250 Cores Bisect" \
        "Set up and start a BC-250 CPU core bisect run" "$BISECT_LAUNCHER" "$APP_ID"
else
    rm -f "$BISECT_LAUNCHER" "$DATA_DIR/applications/$BISECT_DESKTOP" "$DESKTOP_DIR/$BISECT_DESKTOP"
fi

if $WANT_UNLOCK; then
    info "Creating the launcher $UNLOCK_LAUNCHER and its menu entry"
    write_launcher "$UNLOCK_LAUNCHER" cores_unlock
    write_entry "$UNLOCK_DESKTOP" bc250-cores-unlock "BC-250 Cores Unlock" \
        "Persist a validated BC-250 8C/16T core unlock across reboots" "$UNLOCK_LAUNCHER" bc250-cores-unlock
else
    rm -f "$UNLOCK_LAUNCHER" "$DATA_DIR/applications/$UNLOCK_DESKTOP" "$DESKTOP_DIR/$UNLOCK_DESKTOP"
fi
refresh_menu

info "Done. Start the apps from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run:"
$WANT_BISECT && info "  bc250-cores-bisect-gui   (or $LINK/bc250-cores-bisect.sh in a terminal)"
$WANT_UNLOCK && info "  bc250-cores-unlock-gui   (or $LINK/bc250-cores-unlock.sh in a terminal)"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) info "Note: $BIN_DIR is not on your PATH, so the terminal commands need the full path." ;; esac
