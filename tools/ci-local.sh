#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs the jobs of .github/workflows/ci.yml (the BC250 Bazzite Suite's CI) and ci-nexus.yml (Nexus's) here, as
# GitHub runs them (Python 3.12, each job with only its own requirements), in a container: tools/ci_local.py inside
# tools/ci-local/Containerfile. Before a push or a release, so "passes here, fails in CI" shows up here first.
#
#   tools/ci-local.sh                           # every job of both workflows
#   tools/ci-local.sh shell nexus-pytest/tools  # these jobs (a matrix job by its value: pytest/bc250-bazzite/apps/gpu;
#                                               # ci-nexus.yml's jobs with nexus- before the name)
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
# Console Link's FFmpeg, built in the container like CI's (the host's links its newer libva): its own cache folder.
FFMPEG="$CACHE/console-link-ffmpeg"
mkdir -p "$CACHE" "$FFMPEG"

if ! "$ENGINE" image inspect "$IMAGE" >/dev/null 2>&1; then
    info "Building the CI image (once; a few minutes)"
    "$ENGINE" build -q -t "$IMAGE" -f "$CONTAINERFILE" "$ROOT/tools/ci-local" >/dev/null 2>"$CACHE/image-build.log" ||
        die "Building the image failed: $CACHE/image-build.log"
    # earlier versions of the image: the Containerfile changed since
    "$ENGINE" images --format '{{.Repository}}:{{.Tag}}' | grep '^localhost/bc250-ci-local:' | grep -vx "$IMAGE" |
        xargs -r "$ENGINE" rmi -f >/dev/null 2>&1 || true
fi

# The jobs run as you, as on GitHub (the installers refuse root). FFmpeg's build names its own folder in its pkg-config
# files, so it is always mounted at the same place: ~/.cache/bc250-console-link in the container's home.
if [ "${ENGINE##*/}" = podman ]; then as_user=(--userns=keep-id); else as_user=(--user "$(id -u):$(id -g)"); fi
exec "$ENGINE" run --rm --init "${as_user[@]}" \
    --tmpfs "$HOME:rw,mode=1777" -e HOME="$HOME" \
    -v "$ROOT:/src:ro,z" -v "$CACHE:/cache:z" -v "$FFMPEG:$HOME/.cache/bc250-console-link:z" \
    -e CI_LOCAL_HOST_LOGS="$CACHE/logs" -e CARGO_HOME=/cache/cargo \
    "$IMAGE" python3 /src/tools/ci_local.py "$@"
