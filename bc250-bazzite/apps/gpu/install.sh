#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Installs BC-250 GPU Governor Manager for the current user: a private venv with PyQt6, the app
# in ~/.local/share, a launcher in ~/.local/bin and a desktop entry with icon, so it shows up in
# the application menu like any other app. Nothing is layered with rpm-ostree, no root needed.
#
#   ./install.sh                         install or update
#   ./install.sh --no-desktop-shortcut   app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             remove everything it installed; keeps its settings and profiles
#   ./install.sh --uninstall --purge     also remove its settings, profiles and the start-at-login entry
#   ./install.sh --run                   install and start the app
#
# Run it as your own user, not with sudo. The governor's own config.toml and its backups are never touched.

set -euo pipefail

APP_ID="bc250-governor-manager"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/$APP_ID"
VENV_DIR="$APP_DIR/venv"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/128x128/apps"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"

say()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

uninstall() {
    say "Removing $APP_ID"
    rm -rf "$APP_DIR"
    rm -f "$BIN_DIR/$APP_ID" "$APPS_DIR/$APP_ID.desktop" "$ICON_DIR/$APP_ID.png" "$DESKTOP_DIR/$APP_ID.desktop" \
          "$DATA_HOME/icons/hicolor/512x512/apps/$APP_ID.png"
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS_DIR" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
    if $PURGE; then
        say "Removing the settings, profiles and the start-at-login entry"
        rm -rf "${CONFIG_DIR:?}/$APP_ID"
        rm -f "$CONFIG_DIR/autostart/$APP_ID.desktop"
    fi
    say "Done. The governor's config.toml and backups were left untouched."
}

RUN=false
DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
for arg in "$@"; do
    case "$arg" in
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        --run) RUN=true ;;
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        -h|--help) sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "unknown option: $arg (try --help)" ;;
    esac
done
$PURGE && ! $UNINSTALL && fail "--purge only goes with --uninstall"
[[ "$(id -u)" -ne 0 ]] || fail "run this as your own user, not with sudo: the app, venv and launcher belong in your home folder"
if $UNINSTALL; then uninstall; exit 0; fi

[[ -f "$SRC_DIR/gpu_governor/__main__.py" ]] || fail "run this script from the unpacked release directory"
command -v python3 >/dev/null || fail "python3 is required"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail "Python 3.11 or newer is required"
python3 -c 'import venv, ensurepip' 2>/dev/null || fail "python3 venv/ensurepip modules are missing"

say "Installing the app to $APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
rm -rf "$APP_DIR/gpu_governor" "$APP_DIR/bc250_governor" "$APP_DIR/images"   # and the package before its rename
cp -R "$SRC_DIR/gpu_governor" "$SRC_DIR/images" "$APP_DIR/"
cp "$SRC_DIR/requirements.txt" "$SRC_DIR/LICENSE" "$SRC_DIR/README.md" "$APP_DIR/" 2>/dev/null || true
find "$APP_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    say "Creating the virtual environment"
    python3 -m venv "$VENV_DIR"
fi
say "Installing PyQt6 into the virtual environment (this takes a moment the first time)"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade -r "$SRC_DIR/requirements.txt"

say "Installing the launcher, desktop entry and icon"
cat > "$BIN_DIR/$APP_ID" <<EOF
#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$APP_DIR" && exec "$VENV_DIR/bin/python" -m gpu_governor "\$@"
EOF
chmod 755 "$BIN_DIR/$APP_ID"

# The desktop entry points at the launcher by absolute path, so it works even when ~/.local/bin
# is not on PATH of the session that spawns menu entries.
sed "s|^Exec=.*|Exec=$BIN_DIR/$APP_ID|" "$SRC_DIR/$APP_ID.desktop" > "$APPS_DIR/$APP_ID.desktop"
chmod 644 "$APPS_DIR/$APP_ID.desktop"
if $DESKTOP_SHORTCUT && [[ -d "$DESKTOP_DIR" ]]; then
    cp "$APPS_DIR/$APP_ID.desktop" "$DESKTOP_DIR/$APP_ID.desktop"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_DIR/$APP_ID.desktop"
    command -v gio >/dev/null && gio set "$DESKTOP_DIR/$APP_ID.desktop" metadata::trusted true 2>/dev/null || true
else
    rm -f "$DESKTOP_DIR/$APP_ID.desktop"
fi
cp "$SRC_DIR/images/$APP_ID-128.png" "$ICON_DIR/$APP_ID.png"
rm -f "$DATA_HOME/icons/hicolor/512x512/apps/$APP_ID.png"   # the 512 px icon of before
command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true

say "Installed. Find \"BC-250 GPU Governor Manager\" in the application menu$($DESKTOP_SHORTCUT && echo ' or on the Desktop'), or run: $BIN_DIR/$APP_ID"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "    (note: $BIN_DIR is not on your PATH in this shell)" ;;
esac

if $RUN; then
    exec "$BIN_DIR/$APP_ID"
fi
