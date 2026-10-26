#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

GUI_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SUITE=$(cd "$GUI_DIR/../../.." && pwd)     # the suite: bc250-bazzite/
NEXUS=$(cd "$SUITE/.." && pwd)              # the repository, with the dev venv
PY=${PYTHON:-}

if [[ -z "$PY" ]]; then
    for candidate in \
        "$NEXUS/.venv-linux/bin/python" \
        "$NEXUS/.venv/bin/python" \
        "${HOME:-}/.local/share/bc250-bazzite-suite/venv/bin/python"; do
        if [[ -x "$candidate" ]]; then
            PY=$candidate
            break
        fi
    done
fi

PY=${PY:-python3}
cd "$GUI_DIR"
exec "$PY" -m installer_test_gui
