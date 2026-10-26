#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Builds the local Bazzite test image from the Containerfile in this directory.
#
# Usage:
#   ./build.sh            # build, tagged with a timestamp and :latest
#   ./build.sh --no-cache # full rebuild
#   ./build.sh --test     # also run a post-build sanity check (rpm-ostree status)
#
# Test the image on a Bazzite board afterwards (undo with: rpm-ostree rollback):
#   sudo rpm-ostree rebase ostree-unverified-image:containers-storage:localhost/bazzite-custom:latest
set -euo pipefail

cd "$(dirname "$0")"
IMAGE_NAME="${IMAGE_NAME:-bazzite-custom}"
CONTAINERFILE="${CONTAINERFILE:-Containerfile}"
TAG="$(date +%Y%m%d-%H%M%S)"
NO_CACHE=""
RUN_TEST=false
for arg in "$@"; do
    case "$arg" in
        --no-cache) NO_CACHE="--no-cache" ;;
        --test)     RUN_TEST=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

command -v podman >/dev/null 2>&1 || { echo -e "${RED}Error: 'podman' is required but not installed.${NC}" >&2; exit 1; }
[ -f "$CONTAINERFILE" ] || { echo -e "${RED}Error: Containerfile not found at '$CONTAINERFILE'.${NC}" >&2; exit 1; }

echo -e "${GREEN}==> Building Bazzite image: ${IMAGE_NAME}:${TAG}${NC}"
podman build \
    $NO_CACHE \
    -f "$CONTAINERFILE" \
    -t "${IMAGE_NAME}:${TAG}" \
    -t "${IMAGE_NAME}:latest" \
    .
echo -e "${GREEN}[SUCCESS] Built '${IMAGE_NAME}:${TAG}' and '${IMAGE_NAME}:latest'${NC}"

if $RUN_TEST; then
    echo -e "${GREEN}==> Sanity check: rpm-ostree status inside the image${NC}"
    if podman run --rm "${IMAGE_NAME}:${TAG}" rpm-ostree status; then
        echo -e "${GREEN}[SUCCESS] Image sanity check passed.${NC}"
    else
        echo -e "${RED}[WARNING] Sanity check failed.${NC}" >&2
    fi
fi
