#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The two portal checks of a release, as the release front end's buttons run them (Linux):
#
#   check-release.sh local             # before the push: install the portal from this checkout and start it
#                                      # with the apps from the pinned GitHub releases (--source release)
#   check-release.sh release [TAG]     # after release.yml built the portal: download the published portal
#                                      # release (default portal-v<portal/VERSION>), verify it, install it
#                                      # and start it, so this board runs the official release again
#   ... --no-start                     # install only, do not start the portal
#
# The release is downloaded into ~/.cache/bc250-release-check/, emptied first. Installing it replaces the portal
# installed from the checkout; run ./install.sh in the checkout to go back. BC250_RELEASE_URL overrides the
# download address (tests).
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO=$PWD
URL=${BC250_RELEASE_URL:-https://github.com/RobertoTorino/nexus/releases/download}
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-release-check"
PORTAL="$HOME/.local/bin/bc250-bazzite-suite"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

mode=${1:-}; [ $# -gt 0 ] && shift
tag="" start=1
for arg in "$@"; do
    case "$arg" in
        --no-start) start=0 ;;
        portal-v*)  tag=$arg ;;
        *) die "Unknown argument: $arg (see the top of $0)" ;;
    esac
done
[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo."

case "$mode" in
    local)
        info "Installing the portal from this checkout ($REPO)"
        ./install.sh
        [ $start -eq 1 ] || exit 0
        info "Starting it with the apps from the pinned GitHub releases. Close the portal to finish."
        exec "$PORTAL" --source release
        ;;
    release)
        tag=${tag:-portal-v$(tr -d '[:space:]' < portal/VERSION)}
        rm -rf "$CACHE"; mkdir -p "$CACHE"; cd "$CACHE"
        info "Downloading $tag"
        for file in "$tag.tar.gz" SHA256SUMS; do
            curl -fsSL -o "$file" "$URL/$tag/$file" ||
                die "$tag has no $file yet. Is the tag pushed, and has GitHub finished the release workflow?"
        done
        info "Verifying the checksum"
        sha256sum --check SHA256SUMS || die "$tag.tar.gz does not match its SHA256SUMS."
        tar -xzf "$tag.tar.gz"
        info "Installing $tag"
        (cd "$tag" && ./install.sh)
        [ $start -eq 1 ] || exit 0
        info "Starting the released portal. Close it to finish; ./install.sh in the checkout goes back to it."
        exec "$PORTAL"
        ;;
    *) die "Usage: check-release.sh local|release [portal-vX.Y.Z] [--no-start]" ;;
esac
