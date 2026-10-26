#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Starts the release front end, BC250 Suite Releases (bc250-bazzite/apps/suite), with the dev venv of this OS.
# It only edits files; committing, tagging and pushing stay with you.
#
#   tools/release.sh                              # open it (apps/suite/run.sh)
#   tools/release.sh --list                       # the apps, their tags and what needs a release
#   tools/release.sh --install                    # app menu entry and Desktop icon (apps/suite/install.sh)
#   tools/release.sh --install --no-desktop-shortcut
#   tools/release.sh --uninstall [--purge]        # remove them again (--purge: and the settings)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
APP="$ROOT/$(python3 "$ROOT/tools/suites.py" --default)/apps/suite"
case "${1:-}" in
    --install) shift; exec bash "$APP/install.sh" "$@" ;;
    --uninstall) exec bash "$APP/install.sh" "$@" ;;      # --uninstall [--purge]
    -h|--help) sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) exec bash "$APP/run.sh" "$@" ;;
esac
