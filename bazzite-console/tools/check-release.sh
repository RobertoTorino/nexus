#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install and start this suite's portal from the checkout, a published release or a draft release.
set -euo pipefail
export PATH="$PATH:${HOMEBREW_PREFIX:-/home/linuxbrew/.linuxbrew}/bin"
cd "$(dirname "$0")/.."
REPO=$PWD
URL=${PS5_RELEASE_URL:-https://github.com/RobertoTorino/nexus/releases/download}
GH_REPO_NAME=RobertoTorino/nexus
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/bazzite-console-release-check"
PORTAL="$HOME/.local/bin/bazzite-console-suite"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

mode=${1:-}; [ $# -gt 0 ] && shift
tag="" start=1
for arg in "$@"; do
    case "$arg" in
        --no-start) start=0 ;;
        ps5-portal-v*) tag=$arg ;;
        *) die "Unknown argument: $arg (see the top of $0)" ;;
    esac
done
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

case "$mode" in
    local)
        info "Installing the portal from this checkout ($REPO)"
        ./install.sh
        [ "$start" -eq 1 ] || exit 0
        info "Starting the portal. Close it to finish."
        exec "$PORTAL"
        ;;
    release|draft)
        tag=${tag:-ps5-portal-v$(tr -d '[:space:]' < portal/VERSION)}
        rm -rf "$CACHE"
        mkdir -p "$CACHE"
        cd "$CACHE"
        if [ "$mode" = draft ]; then
            info "Downloading the draft of $tag"
            gh release download "$tag" --pattern "$tag.tar.gz" --pattern SHA256SUMS --dir . --repo "$GH_REPO_NAME" ||
                die "No draft of $tag to download. Has the release workflow built it, and is gh signed in?"
        else
            info "Downloading $tag"
            for file in "$tag.tar.gz" SHA256SUMS; do
                curl -fsSL -o "$file" "$URL/$tag/$file" ||
                    die "$tag has no $file yet. Is the tag pushed, and has GitHub finished the release workflow?"
            done
        fi
        info "Verifying the checksum"
        sha256sum --check SHA256SUMS || die "$tag.tar.gz does not match its SHA256SUMS."
        tar -xzf "$tag.tar.gz"
        info "Installing $tag"
        (cd "$tag" && ./install.sh)
        [ "$start" -eq 1 ] || exit 0
        info "Starting the installed portal. Close it to finish."
        exec "$PORTAL"
        ;;
    *) die "Usage: check-release.sh local|release|draft [ps5-portal-vX.Y.Z] [--no-start]" ;;
esac
