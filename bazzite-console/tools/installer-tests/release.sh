#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the required app and portal releases, then install the portal tarball with its bundled app.
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)
T=/tmp/bazzite-console-release-test
# shellcheck source=bazzite-console/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
APP="ps5-bazzite-v$(tr -d '[:space:]' < "$SUITE/apps/bazzite/VERSION")"
PORTAL="ps5-portal-v$(tr -d '[:space:]' < "$SUITE/portal/VERSION")"
export SOURCE_DATE_EPOCH=1790000000

mkdir -p "$T/suite" "$T/build-app"
(cd "$NEXUS" && git ls-files -z --cached --others --exclude-standard |
    while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done | tar --null -T - -cf -) |
    tar -xf - -C "$T/suite"
S=$T/suite

echo "== 1. build the app and portal releases"
/usr/bin/python3 "$S/tools/build_release.py" "$APP" "$T/build-app" > "$T/build-app.log" 2>&1 || {
    cat "$T/build-app.log"; exit 1;
}
/usr/bin/python3 - "$S" "$APP" "$(cut -d' ' -f1 "$T/build-app/SHA256SUMS")" <<'PY'
import importlib.util, sys
from pathlib import Path
suite, tag, digest = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("suite_release", suite / "bazzite-console/tools/suite_release.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
path = suite / "bazzite-console/portal/apps.toml"
path.write_text(module.pin(path.read_text(encoding="utf-8"), tag, digest), encoding="utf-8")
PY
/usr/bin/python3 "$S/bazzite-console/tools/check_manifest.py" > "$T/manifest.log" 2>&1 || {
    cat "$T/manifest.log"; exit 1;
}
mkdir -p "$T/bundle"
cp "$T/build-app/$APP.tar.gz" "$T/build-app/SHA256SUMS" "$T/bundle/"
/usr/bin/python3 "$S/tools/build_release.py" "$PORTAL" "$T/build-portal" --bundle "$T/bundle" \
    > "$T/build-portal.log" 2>&1 || { cat "$T/build-portal.log"; exit 1; }
check "app and portal tarballs built with valid checksums" \
    "[ -f $T/build-app/$APP.tar.gz ] && [ -f $T/build-portal/$PORTAL.tar.gz ] && \
     (cd $T/build-app && sha256sum --check --quiet SHA256SUMS) && \
     (cd $T/build-portal && sha256sum --check --quiet SHA256SUMS)"

echo "== 2. install the portal tarball with its bundled app"
mkdir -p "$T/unpacked"
tar -xzf "$T/build-portal/$PORTAL.tar.gz" -C "$T/unpacked"
check "portal and bundled app installers are executable" \
    "[ -x $T/unpacked/$PORTAL/install.sh ] && [ -x $T/unpacked/$PORTAL/bundled/$APP/install.sh ]"
(cd /tmp && "$T/unpacked/$PORTAL/install.sh" > "$T/install.log" 2>&1); rc=$?
check "portal install succeeds" "[ $rc -eq 0 ]"
check "required app was installed" "[ -f $D/bazzite-test/app/bazzite_test/main_window.py ]"
check "portal launcher was installed" "[ -x $HOME/.local/bin/bazzite-console-suite ]"

[ $fail -eq 0 ] && echo "ALL OK" || { cat "$T/install.log"; exit 1; }
exit "$fail"
