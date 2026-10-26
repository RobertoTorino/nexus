#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs inside a Fedora container (bc250-mesh-shaders.sh --build starts it): checks the Mesa source against its
# signature and the DirectMesh patch against its checksum, patches Mesa with it and then with the suite's own patch,
# builds RADV alone and the mesh test, and installs them into /work/stage.
#
#   /app   this app (read-only): mesa/ and meshtest/
#   /src   mesa-$MESA_VER.tar.xz and its .sig (read-only)
#   /work  build tree, logs and the stage
#
# PREFIX must be the folder the driver is installed in: Mesa writes it into the ICD file and its drirc paths.
set -euo pipefail

: "${MESA_VER:?}" "${PREFIX:?}" "${DIRECTMESH:?}" "${PATCH_SHA256:?}"
TARBALL=/src/mesa-$MESA_VER.tar.xz
PATCH=/app/mesa/bc250-directmesh-mesa-$MESA_VER.patch
SUITE_PATCH=/app/mesa/bc250-suite-mesa-$MESA_VER.patch
STAGE=/work/stage
LOGS=/work/logs

say() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
# Runs a build step with its output in a log; on failure the end of the log is shown.
step() {
    local log=$LOGS/$1.log; shift
    "$@" >"$log" 2>&1 || { tail -40 "$log"; die "$(basename "$log") failed; the whole log is in the build folder."; }
}

mkdir -p "$LOGS"
say "Installing the build tools in the container"
step dnf dnf -y install meson ninja-build gcc gcc-c++ python3-mako python3-packaging python3-pyyaml \
    libdrm-devel wayland-devel wayland-protocols-devel libX11-devel libxcb-devel xcb-util-keysyms-devel \
    libXrandr-devel libxshmfence-devel zlib-devel expat-devel libzstd-devel bison flex glslang glslc spirv-tools \
    vulkan-headers vulkan-loader-devel gnupg2 patch xz

say "Checking the signature of mesa-$MESA_VER.tar.xz"
gpg --dearmor <"/app/mesa/release-maintainers-keys.asc" >/work/mesa-keys.gpg
gpgv --keyring /work/mesa-keys.gpg "$TARBALL.sig" "$TARBALL" 2>"$LOGS/gpgv.log" ||
    { cat "$LOGS/gpgv.log"; die "The Mesa source is not signed by a Mesa release maintainer."; }
grep -h 'Good signature' "$LOGS/gpgv.log" || true

say "Checking the DirectMesh $DIRECTMESH patch"
[ -f "$PATCH" ] || die "$(basename "$PATCH") is missing from the app."
[ "$(sha256sum "$PATCH" | cut -d' ' -f1)" = "$PATCH_SHA256" ] ||
    die "$(basename "$PATCH") is not the one DirectMesh $DIRECTMESH published (its SHA-256 differs)."

say "Unpacking and patching Mesa $MESA_VER"
rm -rf /work/mesa /work/build "$STAGE"
mkdir -p /work/mesa
tar -xf "$TARBALL" -C /work/mesa --strip-components=1
(cd /work/mesa && patch -p1 --dry-run <"$PATCH" >/dev/null) ||
    die "The DirectMesh patch does not apply to Mesa $MESA_VER."
(cd /work/mesa && patch -p1 -s <"$PATCH")
say "Applying the suite's patch on top of it"
[ -f "$SUITE_PATCH" ] || die "$(basename "$SUITE_PATCH") is missing from the app."
(cd /work/mesa && patch -p1 --dry-run <"$SUITE_PATCH" >/dev/null) ||
    die "The suite's patch does not apply on top of DirectMesh $DIRECTMESH."
(cd /work/mesa && patch -p1 -s <"$SUITE_PATCH")

say "Building RADV with DirectMesh (this takes a while)"
# RADV alone, without LLVM (it compiles shaders with ACO), for X11 and Wayland.
step meson-setup meson setup /work/build /work/mesa --prefix="$PREFIX" --buildtype=release \
    -Dvulkan-drivers=amd -Dgallium-drivers= -Dplatforms=wayland,x11 -Dglx=disabled -Degl=disabled \
    -Dgbm=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dllvm=disabled -Dvideo-codecs= \
    -Dvulkan-layers= -Dtools=
step ninja ninja -C /work/build
step install env DESTDIR="$STAGE" ninja -C /work/build install

say "Building the mesh test"
mkdir -p "$STAGE$PREFIX/libexec"
glsl() { glslc -O --target-env=vulkan1.3 -mfmt=c "$@"; }
glsl -o /work/mesh-test.task.spv.inc /app/meshtest/mesh-test.task
glsl -DTASK -DROWS=1u -o /work/mesh-test-task.mesh.spv.inc /app/meshtest/mesh-test.mesh
glsl -DROWS=4u -o /work/mesh-test-alone.mesh.spv.inc /app/meshtest/mesh-test.mesh
glsl -o /work/mesh-test.frag.spv.inc /app/meshtest/mesh-test.frag
glsl -o /work/mesh-test.comp.spv.inc /app/meshtest/mesh-test.comp
gcc -O2 -Wall -Werror -I/work -o "$STAGE$PREFIX/libexec/bc250-mesh-test" /app/meshtest/mesh-test.c -lvulkan

{
    echo "directmesh=$DIRECTMESH"
    echo "mesa=$MESA_VER"
    echo "patch=$PATCH_SHA256"
    echo "suite_patch=$(sha256sum "$SUITE_PATCH" | cut -c1-8)"
    echo "fedora=$(. /etc/os-release && echo "$VERSION_ID")"
    echo "built=$(date -u '+%Y-%m-%d %H:%M UTC')"
} >"$STAGE$PREFIX/BUILD-INFO"
rm -rf /work/mesa /work/build              # the stage is all that is needed; the tree is ~1 GB
say "Built: $(tr '\n' ' ' <"$STAGE$PREFIX/BUILD-INFO")"
