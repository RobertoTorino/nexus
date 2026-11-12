#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# git's settings for this checkout, once per checkout (and again after a clone): tools/hooks as the hooks folder, so
# every git push runs tools/pre-push.sh first.
#
#   tools/git-setup.sh
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"

set_config() {   # key value: set it when it differs, and say so
    local key=$1 value=$2
    if [ "$(git config --local --get "$key" || true)" != "$value" ]; then
        git config --local "$key" "$value"
        echo "git-setup: $key = $value"
    fi
}
set_config core.hooksPath tools/hooks
