#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Starts the release front end, Nexus Releases (dev/releases), with the dev venv of this OS.
# It only edits files; committing, tagging and pushing stay with you.
#
#   tools/release.sh                              # open it (dev/releases/run.sh)
#   tools/release.sh --list                       # the apps, their tags and what needs a release
#   tools/release.sh --install                    # app menu entry and Desktop icon (dev/releases/install.sh)
#   tools/release.sh --install --no-desktop-shortcut
#   tools/release.sh --uninstall [--purge]        # remove them again (--purge: and the settings)
# On Windows (Git Bash), --install and --uninstall run dev/releases/install.ps1: a Start-menu entry and a shortcut.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
APP="$ROOT/dev/releases"
install() {
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$APP/install.ps1")" "$@" ;;
        *) exec bash "$APP/install.sh" "$@" ;;
    esac
}
case "${1:-}" in
    --install) shift; install "$@" ;;
    --uninstall) install "$@" ;;                            # --uninstall [--purge]
    -h|--help) sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) exec bash "$APP/run.sh" "$@" ;;
esac
