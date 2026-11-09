#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Nexus Deps for the current user: a launcher, an app menu entry, a Desktop icon and the hourly reminder,
# all starting run.sh in this checkout (Linux). Nothing is copied: the app runs from the checkout it lives in, so it
# always runs the checkout's own code. It is not part of a portal's releases. Moving the checkout needs install.sh
# again.
#
#   ./install.sh                         # launcher, app menu entry, Desktop icon and the hourly reminder
#   ./install.sh --no-desktop-shortcut   # the same without the Desktop icon
#   ./install.sh --uninstall             # remove them; the checkout and the settings stay
#   ./install.sh --uninstall --purge     # also remove the settings; the checkout stays
#
#  * ~/.config/systemd/user/nexus-deps-reminder.service and .timer: every hour Nexus Deps checks the suite's
#    dependencies, Bazzite's update state and the machine's updates (Flatpaks, Homebrew, Rust, the dev venv), and
#    shows a desktop notification when something needs you, with buttons to open it or to fix what is missing or
#    newer (it asks before it changes anything).
set -euo pipefail
APP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd "$APP/../.." && pwd -P)          # the repository: the venvs

APP_ID="nexus-deps"
APP_NAME="Nexus Deps"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
ICON="$APP/images/$APP_ID-128.png"
REMINDER="nexus-deps-reminder"
UNIT_DIR="$CONFIG_DIR/systemd/user"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

shortcut=true
uninstall=false
purge=false
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) shortcut=false ;;
        --uninstall) uninstall=true ;;
        --purge) purge=true ;;
        -h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $arg (use --help)." ;;
    esac
done
$purge && ! $uninstall && die "--purge only goes with --uninstall."
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

# remove_timer NAME: a systemd user timer and its service, stopped and gone
remove_timer() {
    [ -e "$UNIT_DIR/$1.timer" ] || [ -e "$UNIT_DIR/$1.service" ] || return 0
    systemctl --user disable --now "$1.timer" >/dev/null 2>&1 || true
    rm -f "$UNIT_DIR/$1.timer" "$UNIT_DIR/$1.service" "$UNIT_DIR/timers.target.wants/$1.timer"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
}

if $uninstall; then
    info "Removing the hourly reminder"
    remove_timer "$REMINDER"
    info "Removing the launcher, the menu entry and the Desktop icon"
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
    if $purge; then
        info "Removing the settings"
        rm -rf "${CONFIG_DIR:?}/$APP_ID"
        info "$APP_NAME is uninstalled; the checkout stays."
    else
        info "$APP_NAME is uninstalled; the checkout and its settings stay."
    fi
    exit 0
fi

[ "$(uname -s)" = Linux ] || die "install.sh makes a Linux app menu entry and a systemd timer; the app runs on Linux."
[ -x "$REPO/.venv-linux/bin/python" ] || [ -x "$REPO/.venv/bin/python" ] || [ -n "${PYTHON:-}" ] ||
    info "Note: no .venv-linux yet; create it (see CLAUDE.md) before you start the app."

# The app was the BC250 Bazzite Suite's Dependency Checker until 07-11-2026: installed by the portal with a copy of
# its own under ~/.local/share/bc250-portal-dependency-checker, a launcher, a menu entry, a Desktop icon and a weekly
# timer of its own. They go when this app is installed, and the checker's use of the suite's shared venv with them
# (the portal's own uninstall removes that venv once no app uses it).
OLD_ID="bc250-portal-dependency-checker"
for old in "$HOME/.local/bin/$OLD_ID" "$DATA_DIR/applications/$OLD_ID.desktop" "$DESKTOP_DIR/$OLD_ID.desktop" \
           "$DATA_DIR/$OLD_ID" "$DATA_DIR/bc250-bazzite-suite/venv-users/$OLD_ID"; do
    [ -e "$old" ] || continue
    info "Removing $old (the app's earlier name)"
    rm -rf -- "$old"
done
if [ -e "$UNIT_DIR/bc250-bazzite-update-reminder.timer" ]; then
    info "Removing the Dependency Checker's weekly timer (bc250-bazzite-update-reminder): this app's takes its place"
    remove_timer bc250-bazzite-update-reminder
fi
# The development machine's hourly look for newer versions (tools/dev-updates.sh, until 09-11-2026): this app shows
# every update of the machine now, and its reminder says so.
if [ -e "$UNIT_DIR/nexus-dev-updates.timer" ]; then
    info "Removing the hourly nexus-dev-updates timer: this app's reminder takes its place"
    remove_timer nexus-dev-updates
fi

info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
# $APP_NAME launcher, written by dev/deps/install.sh. Runs the app of this checkout.
[ -x "$APP/run.sh" ] || { echo "No checkout in $REPO any more; run dev/deps/install.sh again." >&2; exit 1; }
exec "$APP/run.sh" "\$@"
LAUNCH
chmod 755 "$LAUNCHER"

entry="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Nexus dependencies
Comment=Check and fix a suite's Python packages and tools on this machine ($REPO)
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Development;System;
Keywords=Nexus;dependencies;updates;PyPI;Bazzite;
StartupNotify=true
StartupWMClass=$APP_ID"
info "Adding the app menu entry"
mkdir -p "$(dirname "$MENU_ENTRY")"
printf '%s\n' "$entry" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
if $shortcut && [ -d "$DESKTOP_DIR" ]; then
    info "Adding the Desktop icon"
    printf '%s\n' "$entry" >"$DESKTOP_ICON"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
elif ! $shortcut; then
    rm -f "$DESKTOP_ICON"
fi

info "Adding the hourly reminder ($REMINDER.timer)"
mkdir -p "$UNIT_DIR"
cat >"$UNIT_DIR/$REMINDER.service" <<EOF
# Written by $APP_NAME's install.sh: a desktop notification when a dependency or an update of the machine needs you.
[Unit]
Description=$APP_NAME: is something missing, outdated or waiting?

[Service]
Type=oneshot
ExecStart=$LAUNCHER --remind
EOF
cat >"$UNIT_DIR/$REMINDER.timer" <<EOF
# Written by $APP_NAME's install.sh; --uninstall removes it.
[Unit]
Description=$APP_NAME: hourly look at the suite's dependencies and the machine's updates

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=5min

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
info "Done. Start \"$APP_NAME\" from the app menu$($shortcut && echo ' or the Desktop'), or run: $APP_ID"
