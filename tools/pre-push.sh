#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The quick checks of CI's versions and shell jobs, before a push leaves this machine: the versions match each
# VERSION, apps.toml with its portal bump against what the remote has (the check a release push failed on), the
# CHANGELOGs keeping every entry the remote has, the scripts' exec bits and the line endings. A few seconds; tools/ci-local.sh runs every job (a minute or two).
#
# As git's pre-push hook, once per checkout:   git config core.hooksPath tools/hooks
# By hand:                                     tools/pre-push.sh [BASE]        (BASE: default origin/main)
#
# BC250_PRE_PUSH=full also runs tools/ci-local.sh (Linux); BC250_PRE_PUSH=off skips the hook, as git push --no-verify
# does. The checks read the working tree, as CI reads the commit: commit everything before the push.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"

ZERO=0000000000000000000000000000000000000000
fail() { printf '\033[1;31mpre-push:\033[0m %s\n' "$1" >&2; failed=1; }
info() { printf '\033[1;35mpre-push:\033[0m %s\n' "$1"; }

[ "${BC250_PRE_PUSH:-}" = off ] && exit 0

python=""
for candidate in .venv-linux/bin/python .venv-windows/Scripts/python.exe python3 py; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then python=$candidate; break; fi
done
[ -n "$python" ] || { echo "pre-push: no Python found, the checks did not run" >&2; exit 1; }

# The branch commits being pushed, each with what the remote has ("" for a new branch: CI then has no base either).
# git hands them over on stdin; by hand, HEAD against BASE.
pushes=()
if [ $# -ge 2 ] && [ ! -t 0 ]; then
    while read -r local_ref local_sha _ remote_sha; do
        case $local_ref in refs/heads/*) ;; *) continue ;; esac     # tags: tag-release.sh checks those
        [ "$local_sha" = "$ZERO" ] && continue                       # a deleted branch
        [ "$remote_sha" = "$ZERO" ] && remote_sha=""
        pushes+=("$local_sha ${remote_sha}")
    done
else
    pushes+=("$(git rev-parse HEAD) $(git rev-parse -q --verify "${1:-origin/main}" || true)")
fi
[ ${#pushes[@]} -gt 0 ] || exit 0

failed=0
for push in "${pushes[@]}"; do
    read -r sha base <<<"$push"
    if [ "$sha" != "$(git rev-parse HEAD)" ]; then
        info "${sha:0:7} is not HEAD: the checks read the working tree, so they are skipped for it"
        continue
    fi
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        info "uncommitted changes: the checks see them, the push does not"
    fi
    "$python" tools/check_versions.py >/dev/null ||
        fail "versions differ from their VERSION file (python3 tools/check_versions.py shows which)"
    for suite in $("$python" tools/suites.py); do        # each suite's manifest with its portal bump
        if [ -n "$base" ] && ! out=$("$python" "./$suite/tools/check_manifest.py" --base "$base" 2>&1); then
            printf '%s\n' "$out" >&2
            fail "$suite/portal/apps.toml: bump portal/VERSION in this push (Suite Releases, step 2: Bump portal)"
        fi
    done
    if [ -n "$base" ] && ! out=$("$python" tools/check_changelogs.py --base "$base" 2>&1); then
        printf '%s\n' "$out" >&2
        fail "a CHANGELOG lost entries the remote has: put them back below the new ones"
    fi
    missing=$(git ls-tree -r "$sha" | awk '($4 ~ /\.sh$/ || $4 ~ /^tools\/hooks\//) && $1 != "100755" { print $4 }')
    [ -z "$missing" ] || fail "not executable in git (tools/fix-modes.sh, then amend the commit): $(echo "$missing" | tr '\n' ' ')"
    crlf=$(git ls-files --eol | awk '$1 ~ /^i\/(crlf|mixed)/ { print $NF }')
    [ -z "$crlf" ] || fail "CRLF in the index: $(echo "$crlf" | tr '\n' ' ')"
done

if [ "$failed" = 0 ] && [ "${BC250_PRE_PUSH:-}" = full ]; then
    tools/ci-local.sh || fail "tools/ci-local.sh: a CI job failed (above)"
fi
if [ "$failed" != 0 ]; then
    echo "pre-push: not pushed. CI would fail on the same; fix it, or push anyway with git push --no-verify." >&2
    exit 1
fi
info "versions, apps.toml, CHANGELOGs, exec bits and line endings are fine"
