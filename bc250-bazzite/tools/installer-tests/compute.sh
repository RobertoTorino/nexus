#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/compute's two GUI installers as the portal runs them (packaging/bazzite/install-bisect-gui.sh, then
# install-gui.sh): from the checkout, without the Desktop icons, from a staged release, an unknown option, and the
# two uninstallers, which keep the bisect results; then the app's install.sh, which runs them, with its options. Runs with the shims from shims.sh (CI, or WSL on Windows).
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-cu-bisect-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
B=$D/bc250-bisect-gui
U=$D/bc250-unlock-cu-gui
printf '#!/bin/sh\necho "sudo called: $*" >&2\nexit 1\n' > "$T/shims/sudo"
install_both() {   # $1 folder, then options
    local dir=$1; shift
    bash "$dir/packaging/bazzite/install-bisect-gui.sh" "$@" && bash "$dir/packaging/bazzite/install-gui.sh" "$@"
}

echo "== 1. install both GUIs from the suite checkout"
install_both "$SUITE/apps/compute" > "$T/log1" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "no sudo used" "! grep -q 'sudo called' $T/log1"
check "bisect app copied" "[ -f $B/app/cu_bisect/__main__.py ] && [ -x $B/app/bc250-cu-bisect.sh ] && [ -f $B/app/images/bc250-cu-bisect.webp ]"
check "unlock app copied" "[ -f $U/app/cu_unlock/__main__.py ] && [ -x $U/app/bc250-cu-unlock.sh ] && [ -f $U/app/images/bc250-cu-bisect-unlock.webp ]"
check "no caches copied" "! find $B $U -name __pycache__ | grep -q ."
check "two venvs" "[ -x $B/venv/bin/python ] && [ -x $U/venv/bin/python ]"
check "bisect launcher" "grep -qF 'cd \"$B/app\" && exec \"$B/venv/bin/python\" -m cu_bisect --script \"$B/app/bc250-cu-bisect.sh\"' $HOME/.local/bin/bc250-bisect-gui"
check "unlock launcher" "grep -qF 'cd \"$U/app\" && exec \"$U/venv/bin/python\" -m cu_unlock --script \"$U/app/bc250-cu-unlock.sh\"' $HOME/.local/bin/bc250-unlock-cu-gui"
check "launchers executable" "[ -x $HOME/.local/bin/bc250-bisect-gui ] && [ -x $HOME/.local/bin/bc250-unlock-cu-gui ]"
check "menu entries" "grep -qx 'Exec=$HOME/.local/bin/bc250-bisect-gui' $D/applications/bc250-cu-bisect.desktop && grep -qx 'Exec=$HOME/.local/bin/bc250-unlock-cu-gui' $D/applications/bc250-cu-unlock.desktop"
check "icons by path" "grep -qx 'Icon=$D/icons/hicolor/128x128/apps/bc250-cu-bisect.png' $D/applications/bc250-cu-bisect.desktop && [ -f $D/icons/hicolor/128x128/apps/bc250-cu-bisect-unlock.png ]"
check "desktop icons, executable" "[ -x $HOME/Desktop/bc250-cu-bisect.desktop ] && [ -x $HOME/Desktop/bc250-cu-unlock.desktop ]"

echo "== 2. reinstall without the Desktop icons"
install_both "$SUITE/apps/compute" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "desktop icons removed" "[ ! -e $HOME/Desktop/bc250-cu-bisect.desktop ] && [ ! -e $HOME/Desktop/bc250-cu-unlock.desktop ]"
check "menu entries kept" "[ -f $D/applications/bc250-cu-bisect.desktop ] && [ -f $D/applications/bc250-cu-unlock.desktop ]"

echo "== 3. install a staged release over it"
mkdir -p "$B/app/bc250_bisect_gui" "$U/app/bc250_unlock_gui"   # a copy installed before the packages' rename
rm -rf "$T/stage"; /usr/bin/python3 "$NEXUS/tools/stage_app.py" compute "$T/stage" > /dev/null
check "manual bundled" "[ -f $T/stage/MANUAL.md ]"
echo "# release marker" >> "$T/stage/bc250-cu-bisect.sh"
install_both "$T/stage" > "$T/log3" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "the release's files used" "grep -q 'release marker' $B/app/bc250-cu-bisect.sh"
check "the packages before the rename removed" "[ ! -e $B/app/bc250_bisect_gui ] && [ ! -e $U/app/bc250_unlock_gui ]"

echo "== 4. unknown option refused"
bash "$T/stage/packaging/bazzite/install-bisect-gui.sh" --bogus > "$T/log4" 2>&1; rc=$?
check "exit non-zero" "[ $rc -ne 0 ]"
check "says why" "grep -q 'unknown option: --bogus' $T/log4"

echo "== 5. uninstall both, keeping the results"
mkdir -p "$D/bc250-cu-bisect" && touch "$D/bc250-cu-bisect/state"
bash "$T/stage/packaging/bazzite/uninstall-bisect-gui.sh" > "$T/log5" 2>&1 &&
    bash "$T/stage/packaging/bazzite/uninstall-gui.sh" >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "apps and venvs gone" "[ ! -e $B ] && [ ! -e $U ]"
check "launchers, menu entries, icons gone" "! ls $HOME/.local/bin/bc250-bisect-gui $HOME/.local/bin/bc250-unlock-cu-gui $D/applications/bc250-cu-*.desktop $D/icons/hicolor/*/apps/bc250-cu-* $HOME/Desktop/bc250-cu-*.desktop 2>/dev/null | grep -q ."
check "bisect results kept" "[ -f $D/bc250-cu-bisect/state ]"

echo "== 6. the app's install.sh: both GUIs, one of them, refusals, --purge"
bash "$T/stage/install.sh" > "$T/log6" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "both GUIs installed" "[ -x $HOME/.local/bin/bc250-bisect-gui ] && [ -x $HOME/.local/bin/bc250-unlock-cu-gui ] && [ -x $HOME/Desktop/bc250-cu-bisect.desktop ]"
bash "$T/stage/install.sh" --unlock-only --no-desktop-shortcut > "$T/log6b" 2>&1; rc=$?
check "--unlock-only removes the bisect GUI" "[ $rc -eq 0 ] && [ ! -e $B ] && [ ! -e $HOME/.local/bin/bc250-bisect-gui ] && [ -x $HOME/.local/bin/bc250-unlock-cu-gui ]"
check "--no-desktop-shortcut passed on" "[ ! -e $HOME/Desktop/bc250-cu-unlock.desktop ] && [ -f $D/applications/bc250-cu-unlock.desktop ]"
bash "$T/stage/install.sh" --bisect-only --unlock-only > "$T/log6c" 2>&1; rc=$?
check "--bisect-only with --unlock-only refused" "[ $rc -ne 0 ] && grep -q 'cannot be combined' $T/log6c"
bash "$T/stage/install.sh" --purge > "$T/log6c" 2>&1; rc=$?
check "--purge alone refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log6c"
fakeroot -- bash "$T/stage/install.sh" > "$T/log6c" 2>&1; rc=$?
check "root refused" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log6c"
fakeroot -- bash "$T/stage/packaging/bazzite/install-gui.sh" > "$T/log6c" 2>&1; rc=$?
check "root refused by the GUI installer too" "[ $rc -ne 0 ] && grep -q 'not with sudo' $T/log6c"
bash "$T/stage/install.sh" > "$T/log6" 2>&1
mkdir -p "$XDG_CONFIG_HOME/bc250-cu-bisect" "$XDG_CONFIG_HOME/autostart"
touch "$XDG_CONFIG_HOME/bc250-cu-bisect/bc250-bisect-gui.conf" "$XDG_CONFIG_HOME/autostart/bc250-cu-bisect-watch.desktop"
bash "$T/stage/install.sh" --uninstall > "$T/log6d" 2>&1; rc=$?
check "uninstall keeps results and settings" "[ $rc -eq 0 ] && [ ! -e $B ] && [ ! -e $U ] && [ -f $D/bc250-cu-bisect/state ] && [ -d $XDG_CONFIG_HOME/bc250-cu-bisect ]"
bash "$T/stage/install.sh" --uninstall --purge > "$T/log6d" 2>&1; rc=$?
check "--purge removes results, settings and the autostart entry" "[ $rc -eq 0 ] && [ ! -e $D/bc250-cu-bisect ] && [ ! -e $XDG_CONFIG_HOME/bc250-cu-bisect ] && [ ! -e $XDG_CONFIG_HOME/autostart/bc250-cu-bisect-watch.desktop ]"

[ $fail -eq 0 ] && echo "ALL OK" || for n in 1 2 3 4 5 6 6b 6c 6d; do echo "--- log$n"; cat "$T/log$n"; done
exit $fail
