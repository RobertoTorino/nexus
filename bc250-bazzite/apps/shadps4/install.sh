#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs shadPS4 Manager as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app and the shadPS4 it installed; keeps its settings and log
#   ./install.sh --uninstall --purge     # also remove its settings, covers and logs
#
# Run it as your own user; installing needs no root. shadPS4 itself is downloaded by the app (Install), not here.
#  * ~/.local/share/bc250-shadps4-manager/app: the app, with the bc250_core it was tested with (bundled in the
#    release; taken from the suite checkout when run from there).
#  * ~/.local/share/bc250-shadps4-manager/emulator: the shadPS4 the app installs.
#  * ~/.local/share/bc250-shadps4-manager/venv: the app's own Python venv with PyQt6 and cryptography (the wheels
#    bundle Qt and OpenSSL; nothing is layered). An install from before it used the suite's shared venv: it leaves
#    that, which goes with the last suite app that uses it.
#  * ~/.local/share/bc250-shadps4-manager/pkgxtractor.log, .state, .progress: the log, the crash marker and the
#    progress checkpoint of Extract PKG.
#  * ~/.local/bin/bc250-shadps4-manager to start it from a terminal (with a .pkg: in Extract PKG), plus an app menu
#    entry and a Desktop icon; ~/.local/bin/bc250-shadps4-pkg-cli, the terminal package extractor.
#  * ~/.local/bin/bc250-shadps4-run, which starts shadPS4: the Steam shortcuts run it.
#  * ~/.local/share/bc250-shadps4-manager/bc250-shadps4-manager.log: the app's log.
# shadPS4's own folder, ~/.local/share/shadPS4 (saves, settings, system modules), is never removed, nor are the
# games; the Steam shortcuts stay in Steam (take them out in the app first).
# Installing also removes the standalone Bazzite pkgxtractor, absorbed into this app (Extract PKG…); its settings
# folder stays, and the app adopts the last used folders from it.
set -euo pipefail

APP_ID="bc250-shadps4-manager"
APP_NAME="shadPS4 Manager"
RUN_NAME="bc250-shadps4-run"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_HOME="$DATA_DIR/$APP_ID"
APP_DIR="$APP_HOME/app"
EMULATOR_DIR="$APP_HOME/emulator"
VENV="$APP_HOME/venv"                        # the app's own: cryptography is not in the suite's shared venv
SUITE_DIR="$DATA_DIR/bc250-bazzite-suite"
SHARED_VENV="$SUITE_DIR/venv"                # what an install from before the own venv used
VENV_USERS="$SUITE_DIR/venv-users"           # one file per app that uses the shared venv
PACKAGE="shadps4_manager"
LAUNCHER="$HOME/.local/bin/$APP_ID"
CLI_LAUNCHER="$HOME/.local/bin/bc250-shadps4-pkg-cli"
RUN="$HOME/.local/bin/$RUN_NAME"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# bc250_core: bundled next to shadps4_manager in a release; in the suite checkout it lives in core/.
if [ -d "$SRC/bc250_core" ]; then CORE_SRC="$SRC/bc250_core"; else CORE_SRC="$SRC/../../../core/bc250_core"; fi

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

usage() { sed -n '3,8p' "$0" | sed 's/^# \{0,1\}//'; }

# Off the suite's shared venv (an install from before the own venv): it goes when no other suite app uses it.
leave_shared_venv() {
    [ -e "$VENV_USERS/$APP_ID" ] || return 0
    rm -f "$VENV_USERS/$APP_ID"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Leaving the suite venv: other suite apps still use it"
    else
        info "Removing the suite venv: no other suite app uses it"
        rm -rf "$SHARED_VENV"
    fi
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

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the app, the venv and the launcher belong in your home folder."

if $UNINSTALL; then
    info "Removing the launchers, the menu entry, the app, its venv and the shadPS4 it installed"
    rm -f "$LAUNCHER" "$CLI_LAUNCHER" "$RUN" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "$APP_DIR" "$EMULATOR_DIR" "$VENV"
    leave_shared_venv
    if $PURGE; then
        info "Removing the settings and the logs"
        rm -rf "${CONFIG_DIR:?}/$APP_ID" "${APP_HOME:?}"
    fi
    rmdir "$APP_HOME" 2>/dev/null || true
    info "$APP_NAME is uninstalled. shadPS4's own folder ($DATA_DIR/shadPS4) and your games were left as they are."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in requirements.txt VERSION "$PACKAGE/__main__.py" "$PACKAGE/pkgxtractor/cli.py" "$RUN_NAME" \
         "images/$APP_ID.webp" "images/$APP_ID-128.png"; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

info "Installing $APP_NAME $VERSION"

# --- 0. The standalone Bazzite pkgxtractor, absorbed into this app (Extract PKG…) ----------------
# Its settings folder stays: the app adopts the last used folders from it.
OLD_APP="bazzite-pkgxtractor"
if [ -e "$DATA_DIR/$OLD_APP" ] || [ -e "$HOME/.local/bin/$OLD_APP" ]; then
    info "Removing the standalone Bazzite pkgxtractor: extracting lives in this app now (Extract PKG…)"
    rm -f "$HOME/.local/bin/$OLD_APP" "$HOME/.local/bin/$OLD_APP-cli" "$DATA_DIR/applications/$OLD_APP.desktop" \
        "$DESKTOP_DIR/$OLD_APP.desktop"
    rm -rf "${DATA_DIR:?}/$OLD_APP"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
fi

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

# --- 2. The app's own venv with PyQt6 and cryptography ------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the venv in $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
info "Installing PyQt6 and cryptography into the venv (downloads ~100 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets, cryptography' || die "PyQt6 or cryptography does not load from the venv."
leave_shared_venv

# --- 3. Launchers, menu entry, Desktop icon -----------------------------------------------------
# The launchers run python in the folder they are started from, so a relative path on the command line means what
# it says. python -m would put that folder first on sys.path; this puts the app folder there instead, so $PACKAGE
# and the bc250_core bundled with it always come from the app.
RUN_MODULE='import runpy, sys; sys.path[0] = sys.argv.pop(1); runpy.run_module(sys.argv.pop(1), run_name="__main__", alter_sys=True)'
info "Creating the launchers $LAUNCHER, $CLI_LAUNCHER and $RUN"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh: python runs $PACKAGE from the app folder, with the
# bc250_core bundled there, in the folder this is started from.
#   $APP_ID [file.pkg]
[ -d "$APP_DIR" ] || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -c '$RUN_MODULE' "$APP_DIR" $PACKAGE "\$@"
EOF
chmod 755 "$LAUNCHER"
cat >"$CLI_LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME terminal package extractor, written by install.sh:
#   $(basename "$CLI_LAUNCHER") <file.pkg> [output folder] [--salvage] [--preview-only] [--no-subfolder]
[ -d "$APP_DIR" ] || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -c '$RUN_MODULE' "$APP_DIR" $PACKAGE.pkgxtractor.cli "\$@"
EOF
chmod 755 "$CLI_LAUNCHER"
install -m 755 "$SRC/$RUN_NAME" "$RUN"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=PS4 emulator manager
Comment=Install shadPS4, find your PS4 games and add them to Steam
Exec=$LAUNCHER %f
Icon=$APP_DIR/images/$APP_ID-128.png
Terminal=false
Categories=Game;Emulator;
Keywords=BC-250;Bazzite;shadPS4;PS4;emulator;Steam;pkg;extract;
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
