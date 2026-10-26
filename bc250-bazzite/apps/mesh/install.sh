#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs BC-250 Mesh Shaders as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app and its build; the driver stays as it is
#   ./install.sh --uninstall --purge     # also remove its settings and test results
#
# Installing the app changes nothing on the board: the driver is built, installed and switched on from the app.
#
# Run it as your own user, not with sudo: only the copy to /opt asks for the sudo password.
#  * /opt/bc250-mesh-shaders-v<version>, root-owned (its script runs as root, so a normal user must not be able to
#    change it), with the bc250_core it was tested with (bundled in the release; taken from the suite checkout
#    when run from there); /opt/bc250-mesh-shaders points at it and older versions go.
#  * ~/.local/share/bc250-bazzite-suite/venv, the BC250 Bazzite Suite's shared venv with PyQt6 (the wheels bundle
#    Qt; nothing is layered). It is removed with the last suite app that uses it.
#  * ~/.local/bin/bc250-mesh-shaders to start it from a terminal, plus an app menu entry and a Desktop icon.
set -euo pipefail

APP_ID="bc250-mesh-shaders"
APP_NAME="BC-250 Mesh Shaders"
OPT_DIR="${BC250_OPT_DIR:-/opt}"            # override only for testing
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
LINK="$OPT_DIR/$APP_ID"
SUITE_DIR="$DATA_DIR/bc250-bazzite-suite"
VENV="$SUITE_DIR/venv"                       # shared by the suite's apps
VENV_USERS="$SUITE_DIR/venv-users"           # one file per app that uses it
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
DRIVER_DIR=/usr/local/lib/bc250-mesh-shaders

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to mesh_shaders in a release; in the suite checkout it lives in core/.
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

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the venv and the launcher belong in your home folder."

if $UNINSTALL; then
    info "Removing the launcher, the menu entry and the Desktop icon"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    info "Removing $LINK and the installed versions (sudo)"
    as_root rm -rf "$LINK" "$OPT_DIR/$APP_ID"-v*
    info "Removing the driver build"
    rm -rf "$HOME/.cache/$APP_ID"
    rm -f "$VENV_USERS/$APP_ID"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Keeping the suite venv: other suite apps still use it"
    else
        info "Removing the suite venv"
        rm -rf "$VENV"
    fi
    if $PURGE; then
        info "Removing the settings and the test results"
        rm -rf "${CONFIG_DIR:?}/$APP_ID" "$HOME/.local/state/$APP_ID"
    fi
    info "$APP_NAME is uninstalled."
    if [ -d "$DRIVER_DIR" ]; then
        info "The patched driver is still installed in $DRIVER_DIR. To remove it as well: install the app again"
        info "and use Remove in its window, or run: sudo bash $SRC/bc250-mesh-shaders.sh --remove-driver"
    fi
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in bc250-mesh-shaders.sh bc250-mesh-shaders-run mesa/build-in-container.sh \
         mesa/bc250-directmesh-mesa-26.2.1.patch mesa/bc250-suite-mesa-26.2.1.patch mesa/release-maintainers-keys.asc \
         meshtest/mesh-test.c meshtest/mesh-test.comp requirements.txt VERSION \
         mesh_shaders/__main__.py "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
[ -n "$VERSION" ] || die "Could not read the version from VERSION."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

TARGET="$OPT_DIR/$APP_ID-v$VERSION"
info "Installing $APP_NAME $VERSION"

# --- 1. Root-owned copy in /opt, with its bc250_core --------------------------------------------
if [ "$SRC" = "$(cd "$TARGET" 2>/dev/null && pwd -P)" ]; then
    info "Already running from $TARGET, no copy needed"
else
    info "Copying to $TARGET (sudo)"
    STAGE="$OPT_DIR/.$APP_ID-v$VERSION.new"
    as_root rm -rf "$STAGE"
    as_root mkdir -p "$STAGE"
    # Plain copy, no -a: the files get /opt's default SELinux label instead of the Downloads one.
    (cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='./tests' --exclude='__pycache__' -cf - .) |
        as_root tar -xf - -C "$STAGE" --no-same-owner
    if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then         # from the checkout: bundle core like a release
        as_root mkdir -p "$STAGE/bc250_core"
        (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | as_root tar -xf - -C "$STAGE/bc250_core" --no-same-owner
    fi
    as_root chown -R root:root "$STAGE"
    as_root find "$STAGE" -type d -exec chmod 755 {} +
    as_root find "$STAGE" -type f -exec chmod go-w,a+r {} +
    as_root chmod 755 "$STAGE/bc250-mesh-shaders.sh" "$STAGE/bc250-mesh-shaders-run" "$STAGE/install.sh" \
        "$STAGE/mesa/build-in-container.sh"
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
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$LINK/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' || die "PyQt6 does not load from the venv."

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the root-owned app folder, so python -m never picks up a
# mesh_shaders folder from the current directory, and imports the bc250_core bundled there.
cd "$LINK" || { echo "$APP_NAME is not installed in $LINK; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m mesh_shaders "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=BC-250 mesh shaders
Comment=Mesh shaders for games on the BC-250: RADV with DirectMesh beside the system Mesa, tested before use
Exec=$LAUNCHER
Icon=$LINK/images/$APP_ID-128.png
Terminal=false
Categories=System;Settings;
Keywords=BC-250;Bazzite;mesh;shaders;DirectMesh;RADV;Mesa;Vulkan;
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
info "Installing the app changed nothing on the board; build and install the driver from its window."
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
