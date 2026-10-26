#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Records the portal's video tour again from this checkout (bc250-bazzite/tools/portal_tour.py), e.g. after a change to the
# portal's window. Takes about a minute; nothing is shown on screen and nothing outside the output file is touched.
#
#   bc250-bazzite/tools/record-tour.sh [OUT.mp4] [--music FILE | --no-music] [--wiki]
#
# --wiki also writes the copy on the wiki's Portal Tour page (docs/videos/portal-tour.mp4 and its poster).
#
# Music: bc250-bazzite/tools/sounds/the_quiet_engine_remix_3min.mp3 (made with generative AI tools), faded out over the last two
# seconds.
# Default output: ~/Videos/bc250-portal-tour-v<portal version>.mp4 (an earlier file of that name is replaced).
# Interpreter: $PYTHON if set, else the venv for this OS, as test.sh. Needs ffmpeg with libx264.
set -euo pipefail
SUITE=$(cd "$(dirname "$0")/.." && pwd -P)       # the suite: bc250-bazzite/
cd "$SUITE/.."                                   # the repository: the venvs

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

out=$HOME/Videos/bc250-portal-tour-v$(tr -d '[:space:]' < "$SUITE/portal/VERSION").mp4
if [[ $# -gt 0 && "$1" != -* ]]; then
    out=$1
    shift
fi
mkdir -p "$(dirname "$out")"
echo "Recording the portal tour into $out (about a minute)..."
# Qt's notes about the offscreen platform (no raise, no keyboard grab) are left out.
"$PY" "$SUITE/tools/portal_tour.py" "$out" "$@" 2> >(grep -v -e "does not support" -e "propagateSizeHints" >&2)
echo "Done: $out"
