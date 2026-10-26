#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/mesh/install.sh: install from the checkout (root-owned /opt copy with core bundled, shared
# venv), a staged release replacing it, uninstall with another venv user (build removed, test results kept),
# --purge, the note about a driver that stays, and the refusal to run as root.
# Runs with the shims from shims.sh (CI, or WSL on Windows). The script itself is tested in apps/mesh/tests.
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-mesh-shaders-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
V=$(tr -d '[:space:]' < "$SUITE/apps/mesh/VERSION")
APP=bc250-mesh-shaders
O=$T/opt/$APP

echo "== 1. install from the suite checkout"
bash "$SUITE/apps/mesh/install.sh" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "versioned /opt copy" "[ -f $T/opt/$APP-v$V/bc250-mesh-shaders.sh ]"
check "symlink" "[ \"\$(readlink $O)\" = $APP-v$V ]"
check "scripts executable" "[ -x $O/bc250-mesh-shaders.sh ] && [ -x $O/bc250-mesh-shaders-run ] && [ -x $O/mesa/build-in-container.sh ]"
check "build files copied" "[ -f $O/mesa/bc250-directmesh-mesa-26.2.1.patch ] && [ -f $O/mesa/bc250-suite-mesa-26.2.1.patch ] && [ -f $O/mesa/release-maintainers-keys.asc ] && [ -f $O/meshtest/mesh-test.mesh ] && [ -f $O/meshtest/mesh-test.comp ]"
check "core bundled from checkout" "[ -f $O/bc250_core/theme.py ]"
check "no tests or caches copied" "[ ! -d $O/tests ] && ! find $O/ -name __pycache__ | grep -q ."
check "shared venv" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ -f $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher uses shared venv" "grep -qF 'bc250-bazzite-suite/venv/bin/python\" -m mesh_shaders' $HOME/.local/bin/$APP"
check "launcher cds into /opt link" "grep -qF 'cd \"$O\"' $HOME/.local/bin/$APP"
check "menu entry" "grep -qx 'Exec=$HOME/.local/bin/$APP' $D/applications/$APP.desktop"
check "desktop icon, executable" "[ -x $HOME/Desktop/$APP.desktop ]"
check "board untouched message" "grep -q 'changed nothing on the board' $T/log1"
check "core imports from the app copy" "(cd $O && /usr/bin/python3 -c 'import importlib.util as u, sys; s=u.find_spec(\"bc250_core\"); sys.exit(0 if s and s.origin.startswith(\"$O\") else 1)')"

echo "== 2. install a staged release with a new version, without the Desktop icon"
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" mesh "$T/stage" > /dev/null
echo 9.9.9 > "$T/stage/VERSION"
echo "# release marker" >> "$T/stage/bc250_core/__init__.py"
bash "$T/stage/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "new version linked" "[ \"\$(readlink $O)\" = $APP-v9.9.9 ]"
check "old version removed" "[ ! -d $T/opt/$APP-v$V ]"
check "the release's own core used" "grep -q 'release marker' $O/bc250_core/__init__.py"
check "desktop icon removed" "[ ! -e $HOME/Desktop/$APP.desktop ]"

echo "== 3. refuses to run as root"
fakeroot -- bash "$T/stage/install.sh" > "$T/log3" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log3"

echo "== 4. uninstall while another suite app still uses the venv"
touch "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$HOME/.cache/$APP/stage" "$HOME/.local/state/$APP" && touch "$HOME/.local/state/$APP/tested"
bash "$T/stage/install.sh" --uninstall > "$T/log4" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "/opt copy gone" "[ ! -e $O ] && ! ls -d $T/opt/$APP-v* >/dev/null 2>&1"
check "build gone, test results kept" "[ ! -e $HOME/.cache/$APP ] && [ -f $HOME/.local/state/$APP/tested ]"
check "venv kept, own marker gone" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ ! -e $D/bc250-bazzite-suite/venv-users/$APP ]"
check "launcher and menu entry gone" "[ ! -e $HOME/.local/bin/$APP ] && [ ! -e $D/applications/$APP.desktop ]"

echo "== 5. reinstall, then uninstall --purge as the last venv user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-bazzite-test"
mkdir -p "$XDG_CONFIG_HOME/$APP" && touch "$XDG_CONFIG_HOME/$APP/$APP.ini"
bash "$T/stage/install.sh" > "$T/log5" 2>&1 && bash "$T/stage/install.sh" --uninstall --purge >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "venv removed" "[ ! -e $D/bc250-bazzite-suite/venv ] && [ ! -e $D/bc250-bazzite-suite/venv-users ]"
check "settings and test results removed" "[ ! -e $XDG_CONFIG_HOME/$APP ] && [ ! -e $HOME/.local/state/$APP ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
