#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Builds the FFmpeg that the native core's video decoder links statically (cargo feature "decoder"): FFmpeg's own
# sources, pinned and checked, configured as small as the stream needs: the H.264 and HEVC decoders with VA-API,
# and the Opus decoder for the sound (which needs libswresample).
# LGPL only (no --enable-gpl, no external codec libraries). libva stays the system's, linked dynamically, so the
# board's own drivers decode.
#
#   native/ffmpeg/build.sh [PREFIX]
#
# PREFIX defaults to ~/.cache/bc250-console-link/ffmpeg-<version>; build.rs finds it there, or in BC250_FFMPEG_DIR.
# Needs a C compiler, make and pkg-config; nasm for FFmpeg's assembly (without it, slower software decoding). The
# libva headers come from the system (libva-devel) or, without them, from libva's pinned sources, linked against
# the system's libva.so.2: Bazzite has the libraries but no headers.
set -euo pipefail

FFMPEG_VERSION=7.1.2
FFMPEG_SHA256=089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304     # signature checked 13-10-2026
LIBVA_VERSION=2.22.0
LIBVA_API=1.22.0
LIBVA_SHA256=467c418c2640a178c6baad5be2e00d569842123763b80507721ab87eb7af8735

PREFIX=${1:-${XDG_CACHE_HOME:-$HOME/.cache}/bc250-console-link/ffmpeg-$FFMPEG_VERSION}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

info() { printf '%s\n' "$*"; }
die() { printf 'build.sh: %s\n' "$*" >&2; exit 1; }

fetch() {   # url file sha256
    curl -sSfL --retry 3 -o "$WORK/$2" "$1" || die "could not download $1"
    echo "$3  $WORK/$2" | sha256sum -c --quiet - || die "$2 does not match its checksum"
}

for tool in curl make pkg-config cc; do
    command -v "$tool" >/dev/null || die "$tool is missing"
done

# libva: the system's when it has the headers, else the headers from libva's sources and the system's libraries.
VA_PKG=""
if ! pkg-config --exists libva libva-drm; then
    VA="$PREFIX/libva"
    rm -rf "$VA"
    mkdir -p "$VA/include" "$VA/lib/pkgconfig"
    fetch "https://github.com/intel/libva/archive/refs/tags/$LIBVA_VERSION.tar.gz" libva.tar.gz "$LIBVA_SHA256"
    tar -xzf "$WORK/libva.tar.gz" -C "$WORK"
    mkdir -p "$VA/include/va"
    cp "$WORK/libva-$LIBVA_VERSION"/va/*.h "$VA/include/va/"
    cp "$WORK/libva-$LIBVA_VERSION"/va/drm/*.h "$VA/include/va/"
    IFS=. read -r major minor micro <<< "$LIBVA_API"
    sed -e "s/@VA_API_MAJOR_VERSION@/$major/; s/@VA_API_MINOR_VERSION@/$minor/" \
        -e "s/@VA_API_MICRO_VERSION@/$micro/; s/@VA_API_VERSION@/$LIBVA_API/g" \
        "$WORK/libva-$LIBVA_VERSION/va/va_version.h.in" > "$VA/include/va/va_version.h"
    for lib in libva libva-drm; do
        so=$(ldconfig -p | awk -v name="$lib.so.2" '$1 == name && /x86-64/ && !found { found = $NF } END { print found }')
        [ -n "$so" ] || die "the system has no $lib.so.2 (libva)"
        ln -sf "$so" "$VA/lib/$lib.so"
    done
    cat > "$VA/lib/pkgconfig/libva.pc" <<EOF
Name: libva
Description: VA-API headers from libva $LIBVA_VERSION, the system's library
Version: $LIBVA_API
Cflags: -I$VA/include
Libs: -L$VA/lib -lva
EOF
    cat > "$VA/lib/pkgconfig/libva-drm.pc" <<EOF
Name: libva-drm
Description: VA-API DRM headers from libva $LIBVA_VERSION, the system's library
Version: $LIBVA_API
Requires: libva
Libs: -L$VA/lib -lva-drm
EOF
    VA_PKG="$VA/lib/pkgconfig"
    info "libva: headers from libva $LIBVA_VERSION, the system's libraries"
fi
export PKG_CONFIG_PATH="${VA_PKG:+$VA_PKG:}${PKG_CONFIG_PATH:-}"

fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" ffmpeg.tar.xz "$FFMPEG_SHA256"
tar -xJf "$WORK/ffmpeg.tar.xz" -C "$WORK"

asm=()
if ! command -v nasm >/dev/null; then
    asm=(--disable-x86asm)
    info "Note: nasm is not installed, so FFmpeg is built without its assembly (software decoding is slower)."
fi

cd "$WORK/ffmpeg-$FFMPEG_VERSION"
./configure --prefix="$PREFIX" --enable-static --disable-shared --enable-pic \
    --disable-programs --disable-doc --disable-network --disable-autodetect --disable-everything \
    --disable-avdevice --disable-avformat --disable-avfilter --disable-swscale \
    --enable-decoder=h264,hevc,opus --enable-parser=h264,hevc \
    --enable-vaapi --enable-hwaccel=h264_vaapi,hevc_vaapi \
    "${asm[@]}" > "$WORK/configure.log" || { tail -30 "$WORK/configure.log" ffbuild/config.log >&2; die "configure failed"; }
grep -q '^CONFIG_VAAPI=yes' ffbuild/config.mak || die "configure did not enable VA-API"
for decoder in H264 HEVC OPUS; do                   # configure drops a decoder whose dependencies are off
    grep -q "^CONFIG_${decoder}_DECODER=yes" ffbuild/config.mak || die "configure did not enable the $decoder decoder"
done
make -j"$(nproc)" > "$WORK/make.log" 2>&1 || { tail -30 "$WORK/make.log" >&2; die "make failed"; }
make install > /dev/null
[ -n "$VA_PKG" ] && cp "$VA_PKG"/*.pc "$PREFIX/lib/pkgconfig/"
echo "$FFMPEG_VERSION" > "$PREFIX/VERSION"
info "FFmpeg $FFMPEG_VERSION is in $PREFIX"
