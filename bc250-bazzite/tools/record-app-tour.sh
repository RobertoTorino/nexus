#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Records the video tour of one app from this checkout (tools/app_tour.py): the same for every app, only the name
# changes. Nothing is shown on screen and nothing outside the output file is touched; the app reads the board as it
# does when it starts, so watch the video before publishing it.
#
#   bc250-bazzite/tools/record-app-tour.sh APP [OUT.mp4] [--package PACKAGE] [--seconds 40] [--music FILE | --no-music]
#
# APP: its key in portal/apps.toml (fan, cec, ...). compute and cores have two programs: --package says which.
# Music: bc250-bazzite/tools/sounds/the_quiet_engine.mp3 (made with generative AI tools), faded out over the last two seconds.
# Default output: ~/Videos/bc250-<app>-tour-v<its version>.mp4 (an earlier file of that name is replaced).
# Interpreter: $PYTHON if set, else the venv for this OS, as test.sh. Needs ffmpeg with libx264.
set -euo pipefail
SUITE=$(cd "$(dirname "$0")/.." && pwd -P)       # the suite: bc250-bazzite/
cd "$SUITE/.."                                   # the repository: the venvs and tools/app_tour.py

if [[ $# -lt 1 || "$1" == -* ]]; then
    echo "Usage: bc250-bazzite/tools/record-app-tour.sh APP [OUT.mp4] [--package P] [--seconds S] [--music F | --no-music]" >&2
    exit 2
fi
PY=${PYTHON:-}
if [[ -z "$PY" ]]; then
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) candidates=(.venv-windows/Scripts/python.exe .venv/Scripts/python.exe) ;;
        *)                    candidates=(.venv-linux/bin/python .venv/bin/python) ;;
    esac
    for candidate in "${candidates[@]}"; do
        [[ -x "$candidate" ]] && PY="$PWD/$candidate" && break
    done
fi
if [[ -z "$PY" ]]; then
    echo "No venv for this OS. Create one, e.g. on Linux:" >&2
    echo "  python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt" >&2
    exit 1
fi
if ! command -v ffmpeg >/dev/null; then
    echo "ffmpeg is needed (on Bazzite: brew install ffmpeg)." >&2
    exit 1
fi

echo "Recording the tour of $1..."
# Qt's notes about the offscreen platform (no raise, no keyboard grab) are left out.
"$PY" tools/app_tour.py --suite "$(basename "$SUITE")" "$@" 2> >(grep -v -e "does not support" -e "propagateSizeHints" >&2)
