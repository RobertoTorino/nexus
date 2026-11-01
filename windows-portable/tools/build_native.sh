#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Builds an app's native core on Windows (Remote Play's, windows-portable/apps/rplay/native) and installs its wheel in
# the Python on PATH, so that the app's tests and build_release.py find it: FFmpeg from the app's native/ffmpeg/build.sh
# when it is not built yet, then the Rust module with maturin. From Git Bash at the repository's root, as CI and the
# release workflow run it:
#
#   bash windows-portable/tools/build_native.sh <app> [--setup]
#
# --setup first installs what it needs (the CI runners have MSYS2 in C:\msys64 and rustup): MSYS2's MINGW64 GCC, make,
# pkg-config and nasm, and Rust's stable-x86_64-pc-windows-gnu toolchain, whose C runtime (msvcrt) is MINGW64's. The
# app's README says which. The wheel is left in native/dist/.
set -euo pipefail

die() { printf 'build_native.sh: %s\n' "$*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: build_native.sh <app> [--setup]"
app=$1
native="windows-portable/apps/$app/native"
[ -f "$native/Cargo.toml" ] || die "$native has no Cargo.toml: the app has no native core"
msys=${MSYS2_ROOT:-/c/msys64}
toolchain=stable-x86_64-pc-windows-gnu

if [ "${2:-}" = "--setup" ]; then
    "$msys/usr/bin/bash.exe" -lc "pacman -S --noconfirm --needed make diffutils tar xz mingw-w64-x86_64-gcc \
        mingw-w64-x86_64-pkgconf mingw-w64-x86_64-nasm mingw-w64-x86_64-binutils"
    rustup toolchain install "$toolchain" --profile minimal -c clippy
fi
export PATH="$msys/mingw64/bin:$HOME/.cargo/bin:$PATH"     # MINGW64's gcc, pkg-config and dlltool first

version=$(sed -n 's/^FFMPEG_VERSION=//p' "$native/ffmpeg/build.sh")
ffmpeg=$(cygpath -u "${RPLAY_FFMPEG_DIR:-$LOCALAPPDATA/windows-portable-suite/build/ffmpeg-$version}")
# The folder is named to build.sh and build.rs: MSYS2's login shell does not pass LOCALAPPDATA on (GitHub's runner)
if [ ! -f "$ffmpeg/lib/pkgconfig/libavcodec.pc" ]; then
    MSYSTEM=MINGW64 CHERE_INVOKING=1 "$msys/usr/bin/bash.exe" -lc \
        "bash '$(cygpath -u "$PWD")/$native/ffmpeg/build.sh' '$(cygpath -m "$ffmpeg")'"
fi

rm -rf "$native/dist"
(cd "$native" && RPLAY_FFMPEG_DIR=$(cygpath -w "$ffmpeg") RUSTUP_TOOLCHAIN=$toolchain \
    python -m maturin build --release --locked --features python,pyo3/extension-module,decoder \
    -i "$(command -v python)" -o dist)
python -m pip install -q --force-reinstall --no-deps "$native"/dist/*.whl
module=$(sed -n 's/^name = "\(.*_core\)"$/\1/p' "$native/Cargo.toml")
python -c "import importlib; m = importlib.import_module('$module'); \
print(m.__name__, m.__version__, 'with FFmpeg', m.FFMPEG_VERSION)"
