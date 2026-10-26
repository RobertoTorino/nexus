#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Installs Console Link as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps its settings and the registered consoles
#   ./install.sh --uninstall --purge     # also remove its settings and the registered consoles' keys
#
# Run it as your own user; installing needs no root. The app talks to PS4 and PS5 consoles on the local network.
#  * ~/.local/share/bc250-console-link/app: the app, with the bc250_core it was tested with (bundled in the
#    release; taken from the suite checkout when run from there).
#  * ~/.local/share/bc250-console-link/venv: the app's own venv with PyQt6 and cryptography (the wheels bundle Qt
#    and OpenSSL; nothing is layered), and the native core for the stream: from a release, its wheel (native/wheel,
#    built by CI with FFmpeg for the video inside); from a clone, built from native/ when Rust (cargo, from rustup)
#    is installed, with the video decoder when native/ffmpeg/build.sh has built FFmpeg.
#  * ~/.config/bc250-console-link: its settings and consoles.json, the keys of the registered consoles (mode 0600).
#  * ~/.local/bin/bc250-console-link to start it from a terminal, plus an app menu entry and a Desktop icon.
set -euo pipefail

APP_ID="bc250-console-link"
APP_NAME="Console Link"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_DIR="$DATA_DIR/$APP_ID/app"
VENV="$DATA_DIR/$APP_ID/venv"                # the app's own: cryptography is not in the suite's shared venv
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
OLD_ID="bc250-remote-play"                    # the app's name until 13-10-2026: BC250 Remote Play

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to consoles_link in a release; in the suite checkout it lives in core/.
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
    info "Removing the launcher, the menu entry, the app and its venv"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "${DATA_DIR:?}/$APP_ID/app" "${DATA_DIR:?}/$APP_ID/venv"
    rmdir "${DATA_DIR:?}/$APP_ID" 2>/dev/null || true
    if $PURGE; then
        info "Removing the settings and the registered consoles"
        rm -rf "${CONFIG_DIR:?}/$APP_ID"
        info "$APP_NAME is uninstalled. A PS5 still lists the board under Link Device; remove it there too."
    else
        info "$APP_NAME is uninstalled. Its settings and registered consoles are kept in $CONFIG_DIR/$APP_ID."
    fi
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in requirements.txt VERSION consoles_link/__main__.py "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

info "Installing $APP_NAME $VERSION"

# --- 0. BC250 Remote Play, this app's former name -----------------------------------------------
# Its program files go; its settings and registered consoles move to this app's folder (the app does the same at
# its first start), so the consoles need no new registration.
if [ -e "$DATA_DIR/$OLD_ID" ] || [ -e "$HOME/.local/bin/$OLD_ID" ]; then
    info "Removing BC250 Remote Play, this app's former name (its registered consoles move over)"
    rm -rf "${DATA_DIR:?}/$OLD_ID" "$HOME/.local/bin/$OLD_ID" "$DATA_DIR/applications/$OLD_ID.desktop" \
        "$DESKTOP_DIR/$OLD_ID.desktop"
fi
if [ -d "$CONFIG_DIR/$OLD_ID" ] && [ ! -e "$CONFIG_DIR/$APP_ID" ]; then
    mv "$CONFIG_DIR/$OLD_ID" "$CONFIG_DIR/$APP_ID"
    [ ! -e "$CONFIG_DIR/$APP_ID/$OLD_ID.ini" ] || mv "$CONFIG_DIR/$APP_ID/$OLD_ID.ini" "$CONFIG_DIR/$APP_ID/$APP_ID.ini"
fi

# --- 1. The app and its bc250_core --------------------------------------------------------------
info "Copying the app to $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
(cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='./tests' --exclude='__pycache__' \
    --exclude='./native/target' --exclude='./native/dist' -cf - .) |
    tar -xf - -C "$APP_DIR"
if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then         # from the checkout: bundle core like a release
    mkdir -p "$APP_DIR/bc250_core"
    (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$APP_DIR/bc250_core"
fi

# --- 2. The app's own venv with PyQt6 and cryptography ------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the app's venv in $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
info "Installing PyQt6 and cryptography into the venv (downloads ~110 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets, cryptography' || die "PyQt6 or cryptography does not load from the venv."

# The native core (Rust): the stream needs it, everything else works without. A release brings it as a wheel; from
# a clone it is built in a temporary folder, so the app folder gets no build output (pip fetches maturin for it).
WHEEL=""
[ ! -d "$APP_DIR/native/wheel" ] || WHEEL=$(find "$APP_DIR/native/wheel" -name '*.whl' | sort | tail -n 1)
CARGO=$(command -v cargo || echo "$HOME/.cargo/bin/cargo")
FFMPEG_VERSION=$(sed -n 's/^FFMPEG_VERSION=//p' "$APP_DIR/native/ffmpeg/build.sh")
FFMPEG_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/$APP_ID/ffmpeg-$FFMPEG_VERSION"
if [ -n "$WHEEL" ]; then
    info "Installing the native core for the stream from the release ($(basename "$WHEEL"))"
    "$VENV/bin/python" -m pip install -q --disable-pip-version-check --force-reinstall --no-deps "$WHEEL" ||
        info "Note: the native core did not install; the app works, but Test stream will say it is missing."
elif [ -x "$CARGO" ]; then
    features=python,pyo3/extension-module
    if [ -f "$FFMPEG_DIR/lib/pkgconfig/libavcodec.pc" ]; then
        features+=,decoder
        info "Building the native core for the stream with Rust, with the video decoder (FFmpeg $FFMPEG_VERSION)"
    else
        info "Building the native core for the stream with Rust (takes a minute or two the first time); without"
        info "the video decoder, which needs FFmpeg from native/ffmpeg/build.sh first"
    fi
    BUILD_DIR=$(mktemp -d)
    if PATH="$(dirname "$CARGO"):$PATH" CARGO_TARGET_DIR="$BUILD_DIR" MATURIN_PEP517_ARGS="--features $features" \
        "$VENV/bin/python" -m pip install -q --disable-pip-version-check "$APP_DIR/native"; then
        info "Native core installed"
    else
        info "Note: the native core did not build; the app works, but Test stream will say it is missing."
    fi
    rm -rf "$BUILD_DIR"
else
    info "Note: Rust is not installed, so the native core for the stream is not built. The app works, but Test"
    info "stream will say it is missing. Install Rust (rustup) and run install.sh again to add it."
fi

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the app folder, so python -m never picks up a
# consoles_link folder from the current directory, and imports the bc250_core bundled there.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m consoles_link "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Console Link
Comment=Find, wake and register PS4 and PS5 consoles for Remote Play on the BC-250
Exec=$LAUNCHER
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=Game;Network;
Keywords=BC-250;Bazzite;Remote Play;PS4;PS5;stream;
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
