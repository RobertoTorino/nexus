#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs the jobs of ci-nexus.yml (Nexus's CI) here, as GitHub runs them (Python 3.12,
# each job with only its own requirements), in a container: tools/ci_local.py inside
# tools/ci-local/Containerfile. Before a push or a release, so "passes here, fails in CI" shows up here first.
#
#   tools/ci-local.sh                                      # the workflows this push starts on GitHub (--all: every one)
#   tools/ci-local.sh nexus-shell nexus-pytest/tools
#                                                         # jobs by workflow-prefixed name
#   tools/ci-local.sh --list                    # the jobs
#
# Needs podman (Bazzite has it) or docker. The image is built the first time and when the Containerfile changes;
# venvs, pip's downloads and the logs stay in ~/.cache/bc250-ci-local. Linux only.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }

ENGINE=$(command -v podman || command -v docker || true)
[ -n "$ENGINE" ] || die "Needs podman or docker."
CONTAINERFILE="$ROOT/tools/ci-local/Containerfile"
IMAGE="localhost/bc250-ci-local:$(sha256sum "$CONTAINERFILE" | cut -c1-12)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-ci-local"
mkdir -p "$CACHE"

if ! "$ENGINE" image inspect "$IMAGE" >/dev/null 2>&1; then
    info "Building the CI image (once; a few minutes)"
    "$ENGINE" build -q -t "$IMAGE" -f "$CONTAINERFILE" "$ROOT/tools/ci-local" >/dev/null 2>"$CACHE/image-build.log" ||
        die "Building the image failed: $CACHE/image-build.log"
    # earlier versions of the image: the Containerfile changed since
    "$ENGINE" images --format '{{.Repository}}:{{.Tag}}' | grep '^localhost/bc250-ci-local:' | grep -vx "$IMAGE" |
        xargs -r "$ENGINE" rmi -f >/dev/null 2>&1 || true
fi

# The jobs run as you, as on GitHub.
if [ "${ENGINE##*/}" = podman ]; then as_user=(--userns=keep-id); else as_user=(--user "$(id -u):$(id -g)"); fi
exec "$ENGINE" run --rm --init "${as_user[@]}" \
    --tmpfs "$HOME:rw,mode=1777" -e HOME="$HOME" \
    -v "$ROOT:/src:ro,z" -v "$CACHE:/cache:z" \
    -e CI_LOCAL_HOST_LOGS="$CACHE/logs" \
    "$IMAGE" python3 /src/tools/ci_local.py "$@"
