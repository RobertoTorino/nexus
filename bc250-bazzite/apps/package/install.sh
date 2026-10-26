#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Dependency Checker as a desktop app, from a clone or the extracted release tarball:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
#   ./install.sh --uninstall             # remove the app; keeps its settings
#   ./install.sh --uninstall --purge     # also remove its settings
#
# Run it as your own user; it checks dependencies but does not install or update them.
#  * ~/.local/share/bc250-portal-dependency-checker/app: the app, with the bc250_core it was tested with.
#  * ~/.local/share/bc250-bazzite-suite/venv, the suite's shared venv with PyQt6.
#  * ~/.local/bin/bc250-portal-dependency-checker, plus an app menu entry and a Desktop icon.
#  * ~/.config/systemd/user/bc250-bazzite-update-reminder.service and .timer: every Monday the checker reads
#    Bazzite's update state and shows a desktop notification when an update waits for a reboot (or Bazzite's
#    updater failed or stopped running). It only reads; updating stays Bazzite's.
set -euo pipefail

APP_ID="bc250-portal-dependency-checker"
APP_NAME="Dependency Checker"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_DIR="$DATA_DIR/$APP_ID/app"
SUITE_DIR="$DATA_DIR/bc250-bazzite-suite"
VENV="$SUITE_DIR/venv"
VENV_USERS="$SUITE_DIR/venv-users"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
REMINDER="bc250-bazzite-update-reminder"
UNIT_DIR="$CONFIG_DIR/systemd/user"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
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
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the app, venv and launcher belong in your home folder."

if $UNINSTALL; then
    if [ -e "$UNIT_DIR/$REMINDER.timer" ]; then
        info "Removing the weekly Bazzite update reminder"
        systemctl --user disable --now "$REMINDER.timer" >/dev/null 2>&1 || true
        rm -f "$UNIT_DIR/$REMINDER.timer" "$UNIT_DIR/$REMINDER.service" "$UNIT_DIR/timers.target.wants/$REMINDER.timer"
        systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi
    info "Removing the launcher, menu entry and app"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    rm -rf "${DATA_DIR:?}/$APP_ID"
    rm -f "$VENV_USERS/$APP_ID"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Keeping the suite venv: other suite apps still use it"
    else
        info "Removing the suite venv"
        rm -rf "$VENV"
    fi
    if $PURGE; then
        info "Removing the settings"
        rm -rf "${CONFIG_DIR:?}/$APP_ID"
    fi
    info "$APP_NAME is uninstalled."
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
[ -f "$SRC/requirements.txt" ] || die "requirements.txt is missing: run install.sh from a clone or the extracted release folder."
[ -f "$SRC/VERSION" ] || die "VERSION is missing: run install.sh from a clone or the extracted release folder."
for f in package_checker/__main__.py package_checker/dependencies.toml \
         images/bc250-dependency-checker.webp images/bc250-dependency-checker-128.png; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from a clone or the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from a clone or the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
VERSION=$(tr -d '[:space:]' <"$SRC/VERSION")
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "Python 3.11 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

info "Installing $APP_NAME $VERSION"
info "Copying the app to $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
(cd "$SRC" && tar --exclude='./.git' --exclude='./.idea' --exclude='./tests' --exclude='./.pytest_cache' \
    --exclude='__pycache__' -cf - .) | tar -xf - -C "$APP_DIR"
if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then         # from the checkout: bundle core like a release
    mkdir -p "$APP_DIR/bc250_core"
    (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) | tar -xf - -C "$APP_DIR/bc250_core"
fi

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
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' || die "PyQt6 does not load from the venv."

info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh.
cd "$APP_DIR" || { echo "$APP_NAME is not installed in $APP_DIR; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m package_checker "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=BC-250 dependency checker
Comment=Check suite Python package updates and external tool availability
Exec=$LAUNCHER
Icon=$APP_DIR/images/bc250-dependency-checker-128.png
Terminal=false
Categories=System;Utility;
Keywords=BC-250;Bazzite;dependencies;updates;PyPI;
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
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
elif ! $DESKTOP_SHORTCUT; then
    rm -f "$DESKTOP_ICON"
fi

info "Adding the weekly Bazzite update reminder ($REMINDER.timer, Mondays)"
mkdir -p "$UNIT_DIR"
cat >"$UNIT_DIR/$REMINDER.service" <<EOF
# Written by the $APP_NAME's install.sh: a desktop notification when a Bazzite update waits for a reboot.
[Unit]
Description=$APP_NAME: is a Bazzite update waiting?

[Service]
Type=oneshot
ExecStart=$LAUNCHER --bazzite-reminder
EOF
cat >"$UNIT_DIR/$REMINDER.timer" <<EOF
# Written by the $APP_NAME's install.sh; --uninstall removes it.
[Unit]
Description=$APP_NAME: weekly look at Bazzite's update state

[Timer]
OnCalendar=Mon *-*-* 10:00
Persistent=true
RandomizedDelaySec=15min

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload >/dev/null 2>&1 || true
if ! systemctl --user enable --now "$REMINDER.timer" >/dev/null 2>&1; then
    # No user session to ask (an install over ssh, say): enable it as systemctl would, for the next login.
    mkdir -p "$UNIT_DIR/timers.target.wants"
    ln -sfn "../$REMINDER.timer" "$UNIT_DIR/timers.target.wants/$REMINDER.timer"
    info "Note: the reminder starts with your next login."
fi

info "Done. Start \"$APP_NAME\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so use $LAUNCHER" ;; esac
