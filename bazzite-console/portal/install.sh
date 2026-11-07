#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the portal and its required app for the logged-in user.
set -euo pipefail

APP_ID="bazzite-console-suite"
APP_NAME="Bazzite Console Suite"
APP_KEY="bazzite"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
SUITE_DIR="$DATA_DIR/$APP_ID"
VENV="$SUITE_DIR/venv"
VENV_USERS="$SUITE_DIR/venv-users"
PORTAL_DIR="$SUITE_DIR/portal"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
if [ -d "$SRC/bundled" ]; then
    APP_SRC=$(find "$SRC/bundled" -mindepth 2 -maxdepth 2 -type f -path '*/install.sh' -print -quit |
        sed 's|/install.sh$||')
    [ -n "$APP_SRC" ] || { echo "The required Bazzite Test app is missing from this portal release." >&2; exit 1; }
else
    APP_SRC="$SRC/../apps/$APP_KEY"
fi

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
usage() {
    cat <<'EOF'
Usage: ./install.sh [--no-desktop-shortcut] [--uninstall [--purge]]
Install or update the Bazzite Console Suite portal and Bazzite Test.
EOF
}

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
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

if $UNINSTALL; then
    info "Removing the portal launcher and menu entry"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    rm -rf "${PORTAL_DIR:?}"
    rm -f "$VENV_USERS/$APP_ID-portal"
    if $PURGE; then
        rm -rf "${CONFIG_DIR:?}/$APP_ID"
    fi
    info "Bazzite Test stays installed; remove it with its own installer."
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "This suite runs on Linux (Bazzite) only."
for file in "$SRC/apps.toml" "$SRC/requirements.txt" "$APP_SRC/install.sh"; do
    [ -f "$file" ] || die "Required file is missing: $file"
done
if [ -d "$SRC/bc250_core" ]; then CORE_SRC="$SRC/bc250_core"; else CORE_SRC="$SRC/../../core/bc250_core"; fi
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing."
[ -f "$APP_SRC/VERSION" ] || die "Bazzite Test is missing its VERSION file."

info "Installing the required Bazzite Test app"
bash "$APP_SRC/install.sh" --no-desktop-shortcut
info "Copying the portal to $PORTAL_DIR"
rm -rf "${PORTAL_DIR:?}"
mkdir -p "$PORTAL_DIR"
(cd "$SRC" && tar --exclude='./tests' --exclude='__pycache__' --exclude='./.git' -cf - .) |
    tar -xf - -C "$PORTAL_DIR"
if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then
    mkdir -p "$PORTAL_DIR/bc250_core"
    (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$PORTAL_DIR/bc250_core"
fi
if [ ! -x "$VENV/bin/python" ]; then
    mkdir -p "$SUITE_DIR"
    python3 -m venv "$VENV"
fi
mkdir -p "$VENV_USERS"
touch "$VENV_USERS/$APP_ID-portal"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$PORTAL_DIR/requirements.txt"

mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
cd "$PORTAL_DIR"
exec "$VENV/bin/python" -m bazzite_console_portal "\$@"
EOF
chmod 755 "$LAUNCHER"
mkdir -p "$(dirname "$MENU_ENTRY")"
cat >"$MENU_ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=$LAUNCHER
Icon=$PORTAL_DIR/images/$APP_ID-128.png
Terminal=false
Categories=System;
EOF
chmod 644 "$MENU_ENTRY"
if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    cp "$MENU_ENTRY" "$DESKTOP_ICON"
    chmod 755 "$DESKTOP_ICON"
elif ! $DESKTOP_SHORTCUT; then
    rm -f "$DESKTOP_ICON"
fi
info "Installed. Start $APP_NAME from the app menu or run $LAUNCHER."
