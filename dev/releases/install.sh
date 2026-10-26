#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs Nexus Releases for the current user: a launcher, an app menu entry and a Desktop icon that start
# run.sh in this checkout (Linux). Nothing is copied: the app edits the checkout it lives in, so it always runs the
# checkout's own code. It is not part of a portal's releases. Moving the checkout needs install.sh again.
#
#   ./install.sh                         # launcher, app menu entry and Desktop icon
#   ./install.sh --no-desktop-shortcut   # launcher and app menu entry only
#   ./install.sh --uninstall             # remove them; the checkout and the settings stay
#   ./install.sh --uninstall --purge     # also remove the settings; the checkout stays
set -euo pipefail
APP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd "$APP/../.." && pwd -P)          # the repository: the venvs

APP_ID="nexus-releases"
APP_NAME="Nexus Releases"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
ICON="$APP/images/$APP_ID-128.png"

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
        -h|--help) sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $arg (use --help)." ;;
    esac
done
$purge && ! $uninstall && die "--purge only goes with --uninstall."
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

if $uninstall; then
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

[ "$(uname -s)" = Linux ] || die "install.sh makes a Linux app menu entry; on Windows run dev/releases/run.sh."
[ -x "$REPO/.venv-linux/bin/python" ] || [ -x "$REPO/.venv/bin/python" ] || [ -n "${PYTHON:-}" ] ||
    info "Note: no .venv-linux yet; create it (see CLAUDE.md) before you start the app."

# The launcher, menu entry and Desktop icon of BC250 Suite Releases (bc250-release, until 26-10-2026) pointed at a
# folder that is gone: they go when this app is installed.
OLD_ID="bc250-release"
for old in "$HOME/.local/bin/$OLD_ID" "$DATA_DIR/applications/$OLD_ID.desktop" "$DESKTOP_DIR/$OLD_ID.desktop"; do
    [ -e "$old" ] || continue
    info "Removing $old (BC250 Suite Releases, the app's earlier name)"
    rm -f "$old"
done

info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
# $APP_NAME launcher, written by dev/releases/install.sh. Runs the app of this checkout.
[ -x "$APP/run.sh" ] || { echo "No checkout in $REPO any more; run dev/releases/install.sh again." >&2; exit 1; }
exec "$APP/run.sh" "\$@"
LAUNCH
chmod 755 "$LAUNCHER"

entry="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Nexus release tool
Comment=Versions, CHANGELOG entries, pins and portal bumps of a suite release ($REPO)
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Development;
Keywords=Nexus;BC-250;release;version;portal;
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
info "Done. Start \"$APP_NAME\" from the app menu$($shortcut && echo ' or the Desktop'), or run: $APP_ID"
