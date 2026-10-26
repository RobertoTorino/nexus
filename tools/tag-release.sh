#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tags release commits and pushes the tags, but only when they can be built: HEAD must hold each tag's version
# (the bump is committed), have no uncommitted changes in that folder, be pushed to origin/main, and have passed CI
# on GitHub (tools/ci_state.py; it waits while CI still runs, up to an hour). A portal tag also needs every app
# release HEAD's apps.toml pins: tagged on origin and pinned with its sha256 (step 2). A plain `git tag` tags
# whatever HEAD is, also a commit from before the bump or one CI failed, which release.yml then refuses.
#
#   tools/tag-release.sh portal-v0.9.5
#   tools/tag-release.sh governor-v0.1.1 upscaler-v0.2.1
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }

[ $# -gt 0 ] || die "Usage: $0 <name>-v<x.y.z> [...], for example $0 portal-v0.9.5"
suite=$(python3 tools/suites.py --default) || die "Which suite? (tools/suites.py)"      # bc250-bazzite
[ "$suite" = . ] && suite="" || suite="$suite/"                                        # a prefix for its paths

for tag in "$@"; do
    [[ $tag =~ ^([a-z0-9-]+)-v([0-9]+\.[0-9]+\.[0-9]+)$ ]] || die "$tag is not <name>-v<x.y.z>."
    name=${BASH_REMATCH[1]} version=${BASH_REMATCH[2]}
    if [ "$name" = portal ]; then dir=${suite}portal; else dir=${suite}apps/$name; fi
    [ -f "$dir/VERSION" ] || die "$tag: there is no $dir/VERSION."
    committed=$(git show "HEAD:$dir/VERSION" 2>/dev/null | tr -d '[:space:]')
    if [ "$committed" != "$version" ]; then
        if [ "$(tr -d '[:space:]' <"$dir/VERSION")" = "$version" ]; then
            die "$tag: the bump to $version is not committed yet (HEAD has $dir/VERSION $committed). Commit it, push, then run this again."
        fi
        die "$tag: HEAD has $dir/VERSION $committed, not $version."
    fi
    git diff --quiet HEAD -- "$dir" ||
        die "$tag: $dir has changes that are not committed (git status $dir). Commit them first: the tag gets only what is committed."
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null &&
        die "$tag exists already. To move it: git tag -d $tag && git push origin :refs/tags/$tag (with the release-tag ruleset set to Disabled for a moment: it restricts deletions)"
    if [ "$name" = portal ] && git cat-file -e "HEAD:${suite}portal/apps.toml" 2>/dev/null; then
        # release.yml builds a portal only on app releases that exist, pinned with their checksum (step 2).
        pins=$(git show "HEAD:${suite}portal/apps.toml" 2>/dev/null | python3 -c '
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

git fetch -q origin main || die "Could not reach origin to check that HEAD is pushed."
git merge-base --is-ancestor HEAD origin/main ||
    die "HEAD ($(git rev-parse --short HEAD)) is not on origin/main yet: git push first, then run this again."

info "Checking that CI passed on $(git rev-parse --short HEAD) (waits while it runs, up to an hour)"
python3 tools/ci_state.py --wait 60 "$(git rev-parse HEAD)" ||
    die "CI has not passed on HEAD ($(git rev-parse --short HEAD)), so it gets no tag: fix what failed, commit and push, then run this again."

for tag in "$@"; do
    git tag "$tag"
    git push -q origin "$tag"
    info "Tagged $(git rev-parse --short HEAD) as $tag and pushed it: release.yml builds it now."
done
