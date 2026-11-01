#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Builds the FFmpeg that the native core's video decoder links statically (cargo feature "decoder"), on Windows:
# FFmpeg's own sources, pinned and checked (Console Link's version and checksum), configured as small as the stream
# needs: the H.264 and HEVC decoders with Direct3D 11 (D3D11VA: the d3d11va2 hwaccels work from a device context,
# as decoder.c opens it, and the decoders offer their pixel format only with the older d3d11va ones enabled too;
# DXVA2 for older drivers) in place of Linux's VA-API, and the Opus decoder for the sound (which needs
# libswresample). LGPL only (no --enable-gpl, no external codec libraries); Direct3D and DXVA are Windows' own,
# nothing to bundle.
#
# Run it in MSYS2's MINGW64 shell (the GCC whose C runtime, msvcrt, Rust's x86_64-pc-windows-gnu links), with
#   pacman -S make diffutils tar xz mingw-w64-x86_64-gcc mingw-w64-x86_64-pkgconf mingw-w64-x86_64-nasm
#
#   native/ffmpeg/build.sh [PREFIX]
#
# PREFIX defaults to %LOCALAPPDATA%\windows-portable-suite\build\ffmpeg-<version>; build.rs finds it there, or in
# RPLAY_FFMPEG_DIR. It is written as C:/... so that its pkg-config files serve cargo, which is not an MSYS2 program.
set -euo pipefail

FFMPEG_VERSION=7.1.2
FFMPEG_SHA256=089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304     # as Console Link's build.sh

die() { printf 'build.sh: %s\n' "$*" >&2; exit 1; }

[ "${MSYSTEM:-}" = MINGW64 ] || die "run this in MSYS2's MINGW64 shell (MSYSTEM=MINGW64), not ${MSYSTEM:-outside MSYS2}"
[ -n "${LOCALAPPDATA:-}" ] || [ $# -gt 0 ] || die "LOCALAPPDATA is not set: give the PREFIX"
PREFIX=$(cygpath -m "${1:-$LOCALAPPDATA/windows-portable-suite/build/ffmpeg-$FFMPEG_VERSION}")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for tool in curl make pkg-config gcc nasm; do
    command -v "$tool" >/dev/null || die "$tool is missing (see the pacman line at the top)"
done

# The download is kept beside the builds (downloads/) and used again while it matches its checksum.
TARBALL=$(cygpath -u "$(dirname "$PREFIX")/downloads/ffmpeg-$FFMPEG_VERSION.tar.xz")    # tar reads C: as a host
mkdir -p "$(dirname "$TARBALL")"
if ! echo "$FFMPEG_SHA256  $TARBALL" | sha256sum -c --quiet - 2>/dev/null; then
    curl -sSfL --retry 3 -o "$TARBALL" "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" \
        || die "could not download FFmpeg $FFMPEG_VERSION"
    echo "$FFMPEG_SHA256  $TARBALL" | sha256sum -c --quiet - || { rm -f "$TARBALL"; die "the download does not match its checksum"; }
fi
tar -xJf "$TARBALL" -C "$WORK"

cd "$WORK/ffmpeg-$FFMPEG_VERSION"
./configure --prefix="$PREFIX" --enable-static --disable-shared \
    --disable-programs --disable-doc --disable-network --disable-autodetect --disable-everything \
    --disable-avdevice --disable-avformat --disable-avfilter --disable-swscale \
    --enable-w32threads \
    --enable-decoder=h264,hevc,opus --enable-parser=h264,hevc \
    --enable-d3d11va --enable-dxva2 \
    --enable-hwaccel=h264_d3d11va,h264_d3d11va2,hevc_d3d11va,hevc_d3d11va2,h264_dxva2,hevc_dxva2 \
    > "$WORK/configure.log" || { tail -30 "$WORK/configure.log" ffbuild/config.log >&2; die "configure failed"; }
for config in D3D11VA W32THREADS H264_DECODER HEVC_DECODER OPUS_DECODER H264_D3D11VA_HWACCEL H264_D3D11VA2_HWACCEL \
        HEVC_D3D11VA_HWACCEL HEVC_D3D11VA2_HWACCEL; do
    # configure quietly drops what its dependencies do not allow
    grep -q "^CONFIG_${config}=yes\|^HAVE_${config}=yes" ffbuild/config.mak || die "configure did not enable $config"
done
make -j"$(nproc)" > "$WORK/make.log" 2>&1 || { tail -30 "$WORK/make.log" >&2; die "make failed"; }
make install > /dev/null
echo "$FFMPEG_VERSION" > "$PREFIX/VERSION"
printf 'FFmpeg %s is in %s\n' "$FFMPEG_VERSION" "$PREFIX"
