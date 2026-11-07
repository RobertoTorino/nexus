#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Check the portal installer options without installing or changing the host.
set -euo pipefail
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
T=/tmp/bazzite-console-portal-test
mkdir -p "$T/home"
export HOME="$T/home" XDG_DATA_HOME="$T/home/.local/share" XDG_CONFIG_HOME="$T/home/.config"
if [ "$(id -u)" -eq 0 ]; then
    if bash "$SUITE/portal/install.sh" --help >/dev/null 2>&1; then
        echo "The installer accepted root." >&2
        exit 1
    fi
else
    bash "$SUITE/portal/install.sh" --help >/dev/null
fi
if bash "$SUITE/portal/install.sh" --purge >/dev/null 2>&1; then
    echo "The installer accepted --purge without --uninstall." >&2
    exit 1
fi
echo "Portal installer options passed."
