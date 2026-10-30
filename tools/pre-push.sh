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
# does. The checks read the commit that is pushed, as CI does, in a checkout of it of their own (git worktree, a second
# or two): what is not committed never makes a push pass (owner, 30-10-2026: the lost CHANGELOG entry, put back but not
# committed, let the push through, and CI failed on it).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"

ZERO=0000000000000000000000000000000000000000
fail() { printf '\033[1;31mpre-push:\033[0m %s\n' "$1" >&2; failed=1; }
info() { printf '\033[1;35mpre-push:\033[0m %s\n' "$1"; }

[ "${BC250_PRE_PUSH:-}" = off ] && exit 0

python=""
for candidate in "$ROOT/.venv-linux/bin/python" "$ROOT/.venv-windows/Scripts/python.exe" python3 py; do
    # one that runs: Windows has a python3 on PATH that only points at the Microsoft Store
    if "$candidate" -c '' >/dev/null 2>&1; then python=$candidate; break; fi
done
[ -n "$python" ] || { echo "pre-push: no Python found, the checks did not run" >&2; exit 1; }

# The branch commits being pushed, each with what the remote has ("" for a new branch: CI then has no base either).
# git hands them over on stdin; by hand, HEAD against BASE.
pushes=()
if [ $# -ge 2 ] && [ ! -t 0 ]; then
    while read -r local_ref local_sha _ remote_sha; do
        remote_sha=${remote_sha%$'\r'}                               # a CRLF line (Windows' text-mode pipes)
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
checkout=""
done_with_checkout() {
    if [ -n "$checkout" ]; then
        git -C "$ROOT" worktree remove --force "$checkout/tree" >/dev/null 2>&1 || true
        rm -rf "$checkout"
        git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
        checkout=""
    fi
}
trap done_with_checkout EXIT
for push in "${pushes[@]}"; do
    read -r sha base <<<"$push"
    cd "$ROOT"
    # The remote has commits this checkout lacks (pushed from the other machine): git would refuse the push anyway,
    # and the checks below cannot compare with a commit that is not here. Say so, rather than a CHANGELOG error.
    if [ -n "$base" ] && ! git merge-base --is-ancestor "$base" "$sha" 2>/dev/null; then
        fail "the remote has commits this checkout does not (pushed from another machine?): git pull --rebase, then push again"
        continue
    fi
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        info "uncommitted changes stay here: the checks read the commit that is pushed (${sha:0:7})"
    fi
    done_with_checkout
    checkout=$(mktemp -d)
    if ! git worktree add -q --detach "$checkout/tree" "$sha" >/dev/null 2>&1; then
        fail "${sha:0:7} could not be checked out to check it (git worktree add)"
        continue
    fi
    cd "$checkout/tree"
    # A suite's checks run when this push changes that suite (its folder; the root's copy of apps.toml, portal/, is
    # the suite's without a tag prefix): one suite's checks never hold another suite's push, as its CI and its tags
    # stand apart (owner, 28-10-2026). Core and dev/ are checked always; a new branch (no base) or a suite at the
    # root (".") checks every suite.
    changed=""
    [ -z "$base" ] || changed=$(git diff --name-only "$base" "$sha")
    touched=()
    for suite in $("$python" tools/suites.py | tr -d '\r'); do   # Windows' Python ends lines with CRLF
        if [ -z "$base" ] || [ "$suite" = . ] || grep -q "^$suite/" <<<"$changed" ||
            { [ ! -f "$suite/TAG_PREFIX" ] && grep -q '^portal/' <<<"$changed"; }; then
            touched+=("$suite")
        fi
    done
    versions() {
        "$python" tools/check_versions.py "$@" >/dev/null ||
            fail "versions differ from their VERSION file (python3 tools/check_versions.py $* shows which)"
    }
    if [ -z "$base" ] || [[ " ${touched[*]-} " == *" . "* ]]; then
        versions                                                  # every suite
    elif [ ${#touched[@]} -eq 0 ]; then
        versions --nexus                                          # no suite changed: core and dev/
    else
        for suite in "${touched[@]}"; do versions --suite "$suite"; done
    fi
    for suite in ${touched[@]+"${touched[@]}"}; do               # each suite's manifest with its portal bump
        if [ -n "$base" ] && ! out=$("$python" "./$suite/tools/check_manifest.py" --base "$base" 2>&1); then
            printf '%s\n' "$out" >&2
            fail "$suite/portal/apps.toml: bump portal/VERSION in this push (Nexus Releases, step 2: Bump portal)"
        fi
    done
    if [ -n "$base" ] && ! out=$("$python" tools/check_changelogs.py --base "$base" 2>&1); then
        printf '%s\n' "$out" >&2
        fail "a CHANGELOG lost entries the remote has: put them back below the new ones"
    fi
    cd "$ROOT"
    missing=$(git ls-tree -r "$sha" | awk '($4 ~ /\.sh$/ || $4 ~ /^tools\/hooks\//) && $1 != "100755" { print $4 }')
    [ -z "$missing" ] || fail "not executable in git (tools/fix-modes.sh, then amend the commit): $(echo "$missing" | tr '\n' ' ')"
    crlf=$(git ls-files --eol | awk '$1 ~ /^i\/(crlf|mixed)/ { print $NF }')
    [ -z "$crlf" ] || fail "CRLF in the index: $(echo "$crlf" | tr '\n' ' ')"
done
done_with_checkout

if [ "$failed" = 0 ] && [ "${BC250_PRE_PUSH:-}" = full ]; then
    tools/ci-local.sh || fail "tools/ci-local.sh: a CI job failed (above)"
fi
if [ "$failed" != 0 ]; then
    echo "pre-push: not pushed. CI would fail on the same: fix it, commit, and push again." >&2
    exit 1
fi
info "versions, apps.toml, CHANGELOGs, exec bits and line endings are fine"
