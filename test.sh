#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs every test suite in the repo (core, tools, the Nexus apps in dev/, and each suite's portal, tools and apps with
# a tests/ folder), offscreen.
# Extra arguments go to pytest, e.g. ./test.sh -k profile  or  ./test.sh -x -vv
#
# System: a suite is tested on the system it is made for (<suite>/SYSTEM): on Windows the windows suites, elsewhere
# the bazzite ones. Core, tools and dev/ run on both. NEXUS_SYSTEM=bazzite or windows picks the suites by hand.
#
# Interpreter: $PYTHON if set, else the venv for this OS. A venv only runs on the OS that made it, so a checkout
# used from both Linux and Windows keeps one per OS: .venv-linux/ and .venv-windows/ (a plain .venv/ works too).
set -euo pipefail
cd "$(dirname "$0")"

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
    echo "or on Windows (Git Bash):" >&2
    echo "  py -m venv .venv-windows && .venv-windows/Scripts/python.exe -m pip install -r requirements-dev.txt" >&2
    exit 1
fi

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) system=${NEXUS_SYSTEM:-windows} ;;
    *)                    system=${NEXUS_SYSTEM:-bazzite} ;;
esac

export QT_QPA_PLATFORM=offscreen
export PYTHONDONTWRITEBYTECODE=1
rc=0
dirs=(core tools dev/*)
for suite in */SYSTEM; do                           # each suite: bc250-bazzite/, windows-portable/
    suite=${suite%/SYSTEM}
    suite_system=$(tr -d '[:space:]' < "$suite/SYSTEM" 2>/dev/null || true)
    if [[ "$suite_system" != "$system" ]]; then
        echo "== $suite: made for ${suite_system:-no system}, left out on $system (NEXUS_SYSTEM=${suite_system:-...} ./test.sh runs it)"
        continue
    fi
    dirs+=("$suite/portal" "$suite/tools" "$suite/tools/installer-tests/gui" "$suite"/apps/*)
done
for dir in "${dirs[@]}"; do
    [[ -d "$dir/tests" ]] || continue
    echo "== $dir"
    (cd "$dir" && "$PY" -m pytest -q -p no:cacheprovider tests "$@") || rc=1
done
exit $rc
