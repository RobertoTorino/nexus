#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tags release commits and pushes the tags, but only when they can be built: HEAD must hold each tag's version
# (the bump is committed), have no uncommitted changes in that folder, be pushed to origin/main, and have passed CI
# on GitHub (tools/ci_state.py; it waits while CI still runs, up to an hour): the CI of the tag's suite, its
# .github/workflows/ci-<suite>.yml when it has one (ci-windows-portable.yml), else ci.yml (the BC250 Bazzite
# Suite's), so one suite's CI never holds another suite's tags (owner, 27-10-2026), and Nexus's ci-nexus.yml (core,
# which every app bundles, the release tools and the repository's rules). A portal tag also needs every app
# release HEAD's apps.toml pins: tagged on origin and pinned with its sha256 (step 2). A plain `git tag` tags
# whatever HEAD is, also a commit from before the bump or one CI failed, which release.yml then refuses.
#
#   tools/tag-release.sh portal-v0.9.5
#   tools/tag-release.sh governor-v0.1.1 upscaler-v0.2.1
#   tools/tag-release.sh wp-portal-v0.1.0             # a suite with a tag prefix (tools/suites.py)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }

[ $# -gt 0 ] || die "Usage: $0 <name>-v<x.y.z> [...], for example $0 portal-v0.9.5"
python=""
for candidate in python3 py; do      # one that runs: Windows has a python3 that only points at the Microsoft Store
    if "$candidate" -c '' >/dev/null 2>&1; then python=$candidate; break; fi
done
[ -n "$python" ] || die "No Python found (python3, or py on Windows)."

workflows=()                         # the CI each tag waits for, once each, then Nexus's
for tag in "$@"; do
    # the tag's suite, by its prefix (tools/suites.py): bc250-bazzite's tags have none, windows-portable's wp-
    read -r suite name version < <("$python" tools/suites.py --tag "$tag" | tr -d '\r') ||
        die "$tag is not <name>-v<x.y.z> of a suite (tools/suites.py --tag)."
    workflow=ci.yml
    [ "$suite" != . ] && [ -f ".github/workflows/ci-$suite.yml" ] && workflow=ci-$suite.yml
    [[ " ${workflows[*]} " == *" $workflow "* ]] || workflows+=("$workflow")
    [ "$suite" = . ] && suite="" || suite="$suite/"                                    # a prefix for its paths
    if [ "$name" = portal ]; then dir=${suite}portal; else dir=${suite}apps/$name; fi
    [ -f "$dir/VERSION" ] || die "$tag: there is no $dir/VERSION."
    # A new app is not in HEAD yet: git show fails, which pipefail would turn into a silent exit 128.
    committed=$(git show "HEAD:$dir/VERSION" 2>/dev/null | tr -d '[:space:]') || committed=""
    if [ "$committed" != "$version" ]; then
        if [ "$(tr -d '[:space:]' <"$dir/VERSION")" = "$version" ]; then
            die "$tag: the bump to $version is not committed yet (HEAD has $dir/VERSION ${committed:-not at all}). Commit it, push, then run this again."
        fi
        die "$tag: HEAD has $dir/VERSION ${committed:-not at all}, not $version."
    fi
    git diff --quiet HEAD -- "$dir" ||
        die "$tag: $dir has changes that are not committed (git status $dir). Commit them first: the tag gets only what is committed."
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null &&
        die "$tag exists already. To move it: git tag -d $tag && git push origin :refs/tags/$tag (with the release-tag ruleset set to Disabled for a moment: it restricts deletions)"
    if [ "$name" = portal ] && git cat-file -e "HEAD:${suite}portal/apps.toml" 2>/dev/null; then
        # release.yml builds a portal only on app releases that exist, pinned with their checksum (step 2).
        pins=$(git show "HEAD:${suite}portal/apps.toml" 2>/dev/null | "$python" -c '
import sys, tomllib
for key, app in tomllib.loads(sys.stdin.read()).get("apps", {}).items():
    print(app.get("tag", ""), app.get("sha256", "") or "-")') ||
            die "$tag: could not read ${suite}portal/apps.toml at HEAD."
        remote=$(git ls-remote --tags origin) || die "Could not reach origin to check the pinned app releases."
        while read -r pin sha; do
            [ -n "$pin" ] || continue
            awk -v ref="refs/tags/$pin" '$2 == ref { found = 1 } END { exit !found }' <<<"$remote" ||
                die "$tag: apps.toml pins $pin, which is not tagged yet. Tag the apps first ($0 $pin), then pin their releases (step 2) and commit, push and tag the portal."
            [ "$sha" != - ] ||
                die "$tag: apps.toml pins $pin without its sha256. Pin it when GitHub has built it (step 2: Pin), commit, push, then tag the portal."
        done <<<"$pins"
    fi
done
workflows+=(ci-nexus.yml)

git fetch -q origin main || die "Could not reach origin to check that HEAD is pushed."
git merge-base --is-ancestor HEAD origin/main ||
    die "HEAD ($(git rev-parse --short HEAD)) is not on origin/main yet: git push first, then run this again."

for workflow in "${workflows[@]}"; do
    info "Checking that CI ($workflow) passed on $(git rev-parse --short HEAD) (waits while it runs, up to an hour)"
    "$python" tools/ci_state.py --wait 60 --workflow "$workflow" "$(git rev-parse HEAD)" ||
        die "CI has not passed on HEAD ($(git rev-parse --short HEAD), $workflow), so it gets no tag: fix what failed, commit and push, then run this again."
done

for tag in "$@"; do
    git tag "$tag"
    git push -q origin "$tag"
    info "Tagged $(git rev-parse --short HEAD) as $tag and pushed it: its suite's release workflow builds it now."
done
