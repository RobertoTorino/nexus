#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Installs BC-250 Upscaler Manager for the current user: a private venv with PyQt6, the app
# in ~/.local/share, a launcher in ~/.local/bin and a desktop entry with icon, so it shows up in
# the application menu like any other app. Nothing is layered with rpm-ostree, no root needed.
# The imported HelixSR release lives in ~/.local/share/bc250-upscaler/payload and is
# kept across updates and uninstalls (it is never shipped with this app).
#
#   ./install.sh                         install or update
#   ./install.sh --no-desktop-shortcut   app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             remove everything it installed; keeps the payload and settings
#   ./install.sh --uninstall --purge     also remove the imported payload and the settings
#   ./install.sh --run                   install and start the app
#
# Run it as your own user, not with sudo. Deployed games and the list of them (deployments.json) are never
# touched, so a reinstalled app can still restore those games.

set -euo pipefail

APP_ID="bc250-upscaler"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# bc250_core: bundled next to upscaler in a release; in the suite checkout it lives in core/.
if [[ -d "$SRC_DIR/bc250_core" ]]; then CORE_SRC="$SRC_DIR/bc250_core"; else CORE_SRC="$SRC_DIR/../../../core/bc250_core"; fi

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$DATA_HOME/$APP_ID"
VENV_DIR="$APP_DIR/venv"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/128x128/apps"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
# The app before its rename (HelixSR Manager, until 21-10-2026): its payload, settings and list of deployed games move
# to the new name, its launcher, menu entry, icons and the rest of its folder go.
OLD_ID="bc250-bazzite-helixsr-gui"

say()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Install and uninstall both take over a copy installed under the old name.
move_old() {
    if [[ -d "$DATA_HOME/$OLD_ID/payload" && ! -e "$APP_DIR/payload" ]]; then
        say "Moving the imported HelixSR payload to $APP_DIR/payload"
        mkdir -p "$APP_DIR"
        mv "$DATA_HOME/$OLD_ID/payload" "$APP_DIR/payload"
    fi
    if [[ -d "$CONFIG_DIR/$OLD_ID" && ! -e "$CONFIG_DIR/$APP_ID" ]]; then
        mv "$CONFIG_DIR/$OLD_ID" "$CONFIG_DIR/$APP_ID"
        [[ ! -e "$CONFIG_DIR/$APP_ID/$OLD_ID.conf" ]] || mv "$CONFIG_DIR/$APP_ID/$OLD_ID.conf" "$CONFIG_DIR/$APP_ID/$APP_ID.conf"
    fi
    rm -rf -- "${DATA_HOME:?}/$OLD_ID"
    rm -f "$BIN_DIR/$OLD_ID" "$APPS_DIR/$OLD_ID.desktop" "$ICON_DIR/$OLD_ID.png" "$DESKTOP_DIR/$OLD_ID.desktop" \
          "$DATA_HOME/icons/hicolor/512x512/apps/$OLD_ID.png"
}

uninstall() {
    move_old
    say "Removing $APP_ID"
    rm -rf "$APP_DIR/venv" "$APP_DIR/upscaler" "$APP_DIR/bc250_core" "$APP_DIR/images"
    rm -f "$APP_DIR/requirements.txt" "$APP_DIR/LICENSE" "$APP_DIR/README.md"
    if $PURGE; then
        say "Removing the imported payload and the settings"
        rm -rf "$APP_DIR/payload"
        rm -f "$CONFIG_DIR/$APP_ID/$APP_ID.conf"
        rmdir "$CONFIG_DIR/$APP_ID" 2>/dev/null || true
    fi
    rmdir "$APP_DIR" 2>/dev/null || true
    rm -f "$BIN_DIR/$APP_ID" "$APPS_DIR/$APP_ID.desktop" "$ICON_DIR/$APP_ID.png" "$DESKTOP_DIR/$APP_ID.desktop" \
          "$DATA_HOME/icons/hicolor/512x512/apps/$APP_ID.png"
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS_DIR" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
    if [[ -d "$APP_DIR/payload" ]]; then
        say "Done. The imported HelixSR payload in $APP_DIR/payload and any deployed games were left untouched."
    else
        say "Done. Deployed games were left untouched."
    fi
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
        -h|--help) sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "unknown option: $arg (try --help)" ;;
    esac
done
$PURGE && ! $UNINSTALL && fail "--purge only goes with --uninstall"
[[ "$(id -u)" -ne 0 ]] || fail "run this as your own user, not with sudo: the app, venv and launcher belong in your home folder"
if $UNINSTALL; then uninstall; exit 0; fi

[[ -f "$SRC_DIR/upscaler/__main__.py" ]] || fail "run this script from the unpacked release directory"
[[ -f "$CORE_SRC/__init__.py" ]] || fail "bc250_core is missing: run install.sh from a clone or the unpacked release directory"
command -v python3 >/dev/null || fail "python3 is required"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail "Python 3.11 or newer is required"
python3 -c 'import venv, ensurepip' 2>/dev/null || fail "python3 venv/ensurepip modules are missing"

say "Installing the app to $APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$APPS_DIR" "$ICON_DIR"
move_old
rm -rf "$APP_DIR/upscaler" "$APP_DIR/bc250_core" "$APP_DIR/images"
cp -R "$SRC_DIR/upscaler" "$SRC_DIR/images" "$APP_DIR/"
cp -R "$CORE_SRC" "$APP_DIR/bc250_core"     # the core it was tested with (from the checkout: bundled like a release)
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
cd "$APP_DIR" && exec "$VENV_DIR/bin/python" -m upscaler "\$@"
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

say "Installed. Find \"BC-250 Upscaler Manager\" in the application menu$($DESKTOP_SHORTCUT && echo ' or on the Desktop'), or run: $BIN_DIR/$APP_ID"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "    (note: $BIN_DIR is not on your PATH in this shell)" ;;
esac

if $RUN; then
    exec "$BIN_DIR/$APP_ID"
fi
