#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# git's settings for this checkout, once per checkout (and again after a clone): tools/hooks as the hooks folder, so
# every git push runs tools/pre-push.sh first, and tools/merge_changelog.py as the merge driver of the CHANGELOGs
# (.gitattributes: CHANGELOG merge=changelog), so an entry written here and one pushed from the other machine merge
# without a conflict in a pull. Prints what it changed; nothing when it was set already. Nexus Release Tool's
# git pull runs it first.
#
#   tools/git-setup.sh
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"

python=""
for candidate in .venv-linux/bin/python .venv-windows/Scripts/python.exe python3 py; do
    # one that runs: Windows has a python3 on PATH that only points at the Microsoft Store
    if "$candidate" -c '' >/dev/null 2>&1; then python=$candidate; break; fi
done
[ -n "$python" ] || { echo "git-setup: no Python found for the CHANGELOG merge driver" >&2; exit 1; }

set_config() {   # key value: set it when it differs, and say so
    local key=$1 value=$2
    if [ "$(git config --local --get "$key" || true)" != "$value" ]; then
        git config --local "$key" "$value"
        echo "git-setup: $key = $value"
    fi
}
set_config core.hooksPath tools/hooks
set_config merge.changelog.name "the CHANGELOGs, merged by entry (tools/merge_changelog.py)"
set_config merge.changelog.driver "$python tools/merge_changelog.py %O %A %B"
