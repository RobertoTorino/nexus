#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Starts Nexus Deps with the dev venv of this OS, as ./test.sh picks it, on the checkout it lives in.
#
#   dev/deps/run.sh            # open the window; --fix offers Fix at once, --remind is the hourly check
#   dev/deps/run.sh --sync-upstreams   # nexus_deps/catalogs/upstreams.json in line with the apps' pins again
#   dev/deps/install.sh        # app menu entry, Desktop icon and the hourly reminder for this checkout
set -euo pipefail
APP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$(cd "$APP/../.." && pwd -P)          # the repository: the venvs and core/

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

case "${1:-}" in
    -h|--help) sed -n '3,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

PY=${PYTHON:-}
if [[ -z "$PY" ]]; then
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) candidates=(.venv-windows/Scripts/python.exe .venv/Scripts/python.exe) ;;
        *)                    candidates=(.venv-linux/bin/python .venv/bin/python) ;;
    esac
    for candidate in "${candidates[@]}"; do
        [[ -x "$REPO/$candidate" ]] && PY="$REPO/$candidate" && break
    done
fi
[[ -n "$PY" ]] || die "No venv for this OS in $REPO: see CLAUDE.md or ./test.sh for how to create one."
cd "$APP"
PYTHONPATH="$REPO/core${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m nexus_deps "$@"
