#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The system libraries Qt needs on a GitHub runner, for the CI workflows' tests and ci.yml's picture of the portal. The runner image
# usually has them, so Ubuntu's mirror is asked only when one is missing: apt-get update, run in every job, hung a CI
# job for 20 minutes on 23-10-2026. Libraries are looked up by file (ldconfig), not by package: Ubuntu 24.04 renamed
# some packages (libglib2.0-0t64).
#
#   tools/ci-qt-libs.sh           # Qt's libraries
#   tools/ci-qt-libs.sh --pulse   # and libpulse0, for Qt Multimedia in the apps' tests
set -euo pipefail

libs=(libEGL.so.1 libGL.so.1 libxkbcommon.so.0 libdbus-1.so.3 libfontconfig.so.1 libglib-2.0.so.0)
packages=(libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libglib2.0-0)
if [ "${1:-}" = --pulse ]; then
    libs+=(libpulse.so.0)
    packages+=(libpulse0)
fi

known=$(ldconfig -p)
missing=()
for lib in "${libs[@]}"; do
    grep -qF -- "$lib (" <<<"$known" || missing+=("$lib")
done
if [ ${#missing[@]} -eq 0 ]; then
    echo "All on the runner already: ${libs[*]}"
    exit 0
fi

echo "Missing: ${missing[*]}; installing them from Ubuntu's mirror"
apt_options=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)
sudo apt-get "${apt_options[@]}" update -q
sudo apt-get "${apt_options[@]}" install -y -q "${packages[@]}"
