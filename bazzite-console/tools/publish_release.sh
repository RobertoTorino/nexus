#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish one Bazzite Console Suite release from build_release.py's output folder.
set -euo pipefail
[ $# -ge 3 ] || { echo "Usage: $0 TAG COMMIT DIR [--draft]" >&2; exit 2; }
tag=$1 commit=$2 dir=$3 draft=false
[ "${4:-}" = --draft ] && draft=true
title=$(cat "$dir/title.txt")
assets=("$dir/$tag.tar.gz" "$dir/SHA256SUMS")

state() {
    local is_draft
    if is_draft=$(gh release view "$tag" --json isDraft --jq .isDraft 2>/dev/null); then
        [ "$is_draft" = true ] && echo draft || echo published
    else
        echo none
    fi
}

create() {
    local args=(--title "$title" --notes-file "$dir/notes.md" --target "$commit" --latest=false)
    $draft && args+=(--draft)
    gh release create "$tag" "${assets[@]}" "${args[@]}"
}

publish() {
    case "$(state)" in
        published)
            if $draft; then
                echo "$tag is out already: left as it is"
                return 0
            fi
            gh release upload "$tag" "${assets[@]}" --clobber ;;
        draft)
            gh release delete "$tag" --yes
            create ;;
        none)
            create ;;
    esac
}

for attempt in 1 2 3 4 5; do
    publish && exit 0
    [ "$attempt" = 5 ] && break
    echo "Publishing failed (try $attempt of 5); again in $((attempt * 30)) s" >&2
    sleep $((attempt * 30))
done
echo "Publishing $tag failed five times." >&2
exit 1
