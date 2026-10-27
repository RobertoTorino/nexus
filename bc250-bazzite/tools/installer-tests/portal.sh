#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise portal/install.sh: from the checkout (through the root install.sh), from a release-shaped tree,
# uninstall and purge.
set -u
SUITE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NEXUS=$(cd "$SUITE/.." && pwd)      # the repository: the Nexus tools (stage_app.py) and core/
T=/tmp/bc250-portal-test
# shellcheck source=bc250-bazzite/tools/installer-tests/shims.sh
source "$(dirname "${BASH_SOURCE[0]}")/shims.sh" "$T"; set +e
fail=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }
D=$XDG_DATA_HOME
logs=()
V=$(cat "$SUITE/portal/VERSION")
NEXT="${V%.*}.$(( ${V##*.} + 1 ))"   # a later portal release, for the update in step 2
BT="check-v$(tr -d '[:space:]' < "$SUITE/apps/check/VERSION")"   # the bundled release

echo "== 1. install from the suite checkout, with the install.sh at its root"
bash "$SUITE/install.sh" > "$T/log1" 2>&1; rc=$?; logs+=("$T/log1")
check "exit 0" "[ $rc -eq 0 ]"
check "portal installs apps from the checkout" "[ \"\$(cat $T/opt/bc250-bazzite-suite/suite-checkout)\" = \"\$(cd $NEXUS && pwd -P)\" ]"
check "portal in /opt without the dependency checker catalog" "[ -f $T/opt/bc250-bazzite-suite/bc250_portal/__main__.py ] && [ -f $T/opt/bc250-bazzite-suite/apps.toml ] && [ ! -e $T/opt/bc250-bazzite-suite/dependencies.toml ]"
check "portal symlink" "[ \"\$(readlink $T/opt/bc250-bazzite-suite)\" = bc250-bazzite-suite-v$V ]"
check "core bundled with portal" "[ -f $T/opt/bc250-bazzite-suite/bc250_core/platform.py ]"
check "no tests in /opt" "[ ! -d $T/opt/bc250-bazzite-suite/tests ]"
check "the sounds are in /opt" "[ -s $T/opt/bc250-bazzite-suite/bc250_portal/sounds/swoosh.wav ] && [ -s $T/opt/bc250-bazzite-suite/bc250_portal/sounds/bigpicture.wav ]"
check "the controller reader is in the requirements" "grep -q '^pygame-ce' $T/opt/bc250-bazzite-suite/requirements.txt"
check "check installed too" "[ -f $T/opt/bc250-bazzite-test/test-bazzite.sh ] && [ -x $HOME/.local/bin/bc250-bazzite-test ]"
check "check has its manual" "cmp -s $SUITE/docs/apps/check.md $T/opt/bc250-bazzite-test/MANUAL.md"
check "both venv users" "[ -f $D/bc250-bazzite-suite/venv-users/bc250-bazzite-suite ] && [ -f $D/bc250-bazzite-suite/venv-users/bc250-bazzite-test ]"
check "portal launcher" "grep -qF 'm bc250_portal' $HOME/.local/bin/bc250-bazzite-suite"
check "desktop icons" "[ -x $HOME/Desktop/bc250-bazzite-suite.desktop ] && [ -x $HOME/Desktop/bc250-bazzite-test.desktop ]"
check "record says local" "grep -q '\"check\": \"local\"' $D/bc250-bazzite-suite/portal/installed.json"
check "portal imports its bundled core" "(cd $T/opt/bc250-bazzite-suite && /usr/bin/python3 -c 'import bc250_core, os, sys; sys.exit(0 if os.path.abspath(bc250_core.__file__).startswith(\"$T/opt/bc250-bazzite-suite\") else 1)')"
check "manifest parses on Linux python" "(cd $T/opt/bc250-bazzite-suite && /usr/bin/python3 -c 'import tomllib; d=tomllib.load(open(\"apps.toml\",\"rb\")); assert list(d[\"apps\"])[0]==\"check\"')"

echo "== 2. release-shaped tree: portal staged + bundled check, no desktop icons"
R="$T/release/portal-v$NEXT"; rm -rf "$T/release"; mkdir -p "$T/release"
/usr/bin/python3 "$NEXUS/tools/stage_app.py" portal "$R" > /dev/null
/usr/bin/python3 "$NEXUS/tools/stage_app.py" check "$R/bundled/$BT" > /dev/null
sed -i "s/^__version__ = \"$V\"\$/__version__ = \"$NEXT\"/" "$R/bc250_portal/__init__.py"
bash "$R/install.sh" --no-desktop-shortcut > "$T/log2" 2>&1; rc=$?; logs+=("$T/log2")
check "exit 0" "[ $rc -eq 0 ]"
check "new portal version, old removed" "[ \"\$(readlink $T/opt/bc250-bazzite-suite)\" = bc250-bazzite-suite-v$NEXT ] && [ ! -d $T/opt/bc250-bazzite-suite-v$V ]"
check "the release has the sounds" "[ -s $T/opt/bc250-bazzite-suite/bc250_portal/sounds/swoosh.wav ] && [ -s $T/opt/bc250-bazzite-suite/bc250_portal/sounds/bigpicture.wav ]"
check "bundled/ not copied to /opt" "[ ! -d $T/opt/bc250-bazzite-suite/bundled ]"
check "portal installs apps from releases" "[ ! -e $T/opt/bc250-bazzite-suite/suite-checkout ]"
check "record has the bundled tag" "grep -q '\"check\": \"$BT\"' $D/bc250-bazzite-suite/portal/installed.json"
check "desktop icons removed" "[ ! -e $HOME/Desktop/bc250-bazzite-suite.desktop ] && [ ! -e $HOME/Desktop/bc250-bazzite-test.desktop ]"

echo "== 3. uninstall keeps the venv for another suite app, drops the state of apps that are gone"
touch "$D/bc250-bazzite-suite/venv-users/bc250-governor-manager"
mkdir -p "$D/bc250-bazzite-suite/portal/releases/governor-v0.0.1" "$D/bc250-bazzite-suite/portal/releases/local-bios"
bash "$T/opt/bc250-bazzite-suite/install.sh" --uninstall > "$T/log3" 2>&1; rc=$?; logs+=("$T/log3")
check "exit 0" "[ $rc -eq 0 ]"
check "portal and check gone from /opt" "[ -z \"\$(ls $T/opt)\" ]"
check "launchers gone" "[ ! -e $HOME/.local/bin/bc250-bazzite-suite ] && [ ! -e $HOME/.local/bin/bc250-bazzite-test ]"
check "venv kept, only governor left" "[ -x $D/bc250-bazzite-suite/venv/bin/python ] && [ \"\$(ls $D/bc250-bazzite-suite/venv-users)\" = bc250-governor-manager ]"
check "mentions what is left" "grep -q 'Still installed: bc250-governor-manager' $T/log3"
check "no state left: no app it installed remains" "[ ! -e $D/bc250-bazzite-suite/portal ]"

echo "== 4. reinstall and purge as the last user"
rm "$D/bc250-bazzite-suite/venv-users/bc250-governor-manager"
mkdir -p "$T/log/bc250-bazzite-test" && touch "$T/log/bc250-bazzite-test/bc250-test-results-20260101-000000.log"
bash "$R/install.sh" > "$T/log4" 2>&1 && bash "$T/opt/bc250-bazzite-suite/install.sh" --uninstall --purge >> "$T/log4" 2>&1; rc=$?; logs+=("$T/log4")
check "exit 0" "[ $rc -eq 0 ]"
check "suite data dir gone" "[ ! -e $D/bc250-bazzite-suite ]"
check "check results gone" "[ ! -e $T/log/bc250-bazzite-test ]"
check "/opt empty" "[ -z \"\$(ls $T/opt)\" ]"

echo "== 5. uninstall asks about each other app: cancel, then skip one and uninstall the others"
# The others: overlay and bios as the portal installs them from the checkout, and ncgui, installed the same way.
# Then bios and ncgui are dropped from the installed portal's manifest, as a newer portal drops an app: bios keeps
# its record and release folder (the portal's), ncgui neither (found by its own installed copy under
# ~/.local/share). Installer Tests, installed from the checkout too, is not the portal's (no Development tab, owner
# 27-10-2026): the portal's uninstall leaves it.
bash "$SUITE/install.sh" > "$T/log5" 2>&1; logs+=("$T/log5")
for app in overlay bios ncgui; do
    /usr/bin/python3 "$NEXUS/tools/stage_app.py" "$app" "$D/bc250-bazzite-suite/portal/releases/local-$app" > /dev/null
    (cd "$D/bc250-bazzite-suite/portal/releases/local-$app" && bash install.sh) >> "$T/log5" 2>&1
done
bash "$SUITE/tools/installer-tests/gui/install.sh" --no-desktop-shortcut >> "$T/log5" 2>&1
rm -rf "$D/bc250-bazzite-suite/portal/releases/local-ncgui"
/usr/bin/python3 - "$D/bc250-bazzite-suite/portal/installed.json" "$T/opt/bc250-bazzite-suite/apps.toml" <<'PY'
import json, re, sys
from pathlib import Path
data = json.load(open(sys.argv[1]))
data.update({"overlay": "local", "bios": "local"})
json.dump(data, open(sys.argv[1], "w"))
manifest = Path(sys.argv[2])
text = manifest.read_text(encoding="utf-8")
for key in ("bios", "ncgui"):                     # dropped from this portal's manifest
    text = re.sub(rf"^\[apps\.{key}\]\n(?:(?!^\[).*\n)*", "", text, flags=re.M)
manifest.write_text(text, encoding="utf-8")
PY
installed() { [ -x "$HOME/.local/bin/$1" ]; }
check "the apps are installed" "installed bc250-system-overlay && installed bc250-bios-reader && installed bazzite-netcatgui && installed bc250-installer-test-gui"
check "two of them dropped from the installed manifest" "! grep -q 'apps.bios' $T/opt/bc250-bazzite-suite/apps.toml && ! grep -q 'apps.ncgui' $T/opt/bc250-bazzite-suite/apps.toml && grep -q 'apps.overlay' $T/opt/bc250-bazzite-suite/apps.toml"
mkdir -p "$D/bc250-bazzite-suite/portal/releases/overlay-v0.0.1"   # an older release it was updated from
printf 'y\nc\n' | BC250_INTERACTIVE=1 bash "$SUITE/install.sh" --uninstall >> "$T/log5" 2>&1; rc=$?
check "cancel: exit 1" "[ $rc -eq 1 ]"
check "cancel: nothing removed" "installed bc250-system-overlay && installed bc250-bios-reader && installed bazzite-netcatgui && installed bc250-installer-test-gui && installed bc250-bazzite-suite && installed bc250-bazzite-test"
check "cancel: says so" "grep -q 'Canceled: nothing was uninstalled.' $T/log5"
printf 'x\ns\ny\ny\n' | BC250_INTERACTIVE=1 bash "$SUITE/install.sh" --uninstall >> "$T/log5" 2>&1; rc=$?
check "exit 0" "[ $rc -eq 0 ]"
check "asked about overlay three times (the cancel run, an unknown answer), bios twice, ncgui once, Installer Tests never" "[ \$(grep -o 'Uninstall System Overlay?' $T/log5 | wc -l) -eq 3 ] && [ \$(grep -o 'Uninstall BC-250 BIOS Reader?' $T/log5 | wc -l) -eq 2 ] && [ \$(grep -o 'Uninstall Bazzite NetcatGUI?' $T/log5 | wc -l) -eq 1 ] && ! grep -q 'Uninstall BC-250 Installer Tests?' $T/log5"
check "skipped app stays" "installed bc250-system-overlay && [ -d $D/bc250-bazzite-suite/portal/releases/local-overlay ]"
check "chosen app gone" "! installed bc250-bios-reader && [ ! -e $D/bc250-bazzite-suite/portal/releases/local-bios ]"
check "Installer Tests stays: the checkout's, not the portal's" "installed bc250-installer-test-gui"
check "dropped app without a record gone" "! installed bazzite-netcatgui && [ ! -e $D/bazzite-netcatgui/app ]"
check "record drops the chosen app" "! grep -q bios $D/bc250-bazzite-suite/portal/installed.json && grep -q overlay $D/bc250-bazzite-suite/portal/installed.json"
check "record and folder of check gone" "! grep -q check $D/bc250-bazzite-suite/portal/installed.json && [ ! -e $D/bc250-bazzite-suite/portal/releases/local-check ]"
check "older release of the skipped app gone" "[ ! -e $D/bc250-bazzite-suite/portal/releases/overlay-v0.0.1 ]"
check "portal and check gone" "! installed bc250-bazzite-suite && ! installed bc250-bazzite-test"
check "mentions what is left" "grep -q 'Still installed: bc250-system-overlay' $T/log5"
(cd "$D/bc250-bazzite-suite/portal/releases/local-overlay" && bash install.sh --uninstall) >> "$T/log5" 2>&1
bash "$SUITE/tools/installer-tests/gui/install.sh" --uninstall >> "$T/log5" 2>&1

echo "== 6. after an uninstall that kept nothing, no suite folder is left"
bash "$SUITE/install.sh" > "$T/log6" 2>&1 && bash "$T/opt/bc250-bazzite-suite/install.sh" --uninstall >> "$T/log6" 2>&1
rc=$?; logs+=("$T/log6")
check "exit 0" "[ $rc -eq 0 ]"
check "suite data dir gone (settings stay in ~/.config)" "[ ! -e $D/bc250-bazzite-suite ]"

echo "== 7. --uninstall --all: one confirmation for the whole suite, no question per app"
bash "$SUITE/install.sh" > "$T/log7" 2>&1; logs+=("$T/log7")
for app in overlay bios; do
    rm -rf "$D/bc250-bazzite-suite/portal/releases/local-$app"
    /usr/bin/python3 "$NEXUS/tools/stage_app.py" "$app" "$D/bc250-bazzite-suite/portal/releases/local-$app" > /dev/null
    (cd "$D/bc250-bazzite-suite/portal/releases/local-$app" && bash install.sh) >> "$T/log7" 2>&1
done
mkdir -p "$XDG_CONFIG_HOME/bc250-system-overlay" && echo x > "$XDG_CONFIG_HOME/bc250-system-overlay/settings.ini"
check "both apps installed, overlay has settings" "installed bc250-system-overlay && installed bc250-bios-reader && [ -f $XDG_CONFIG_HOME/bc250-system-overlay/settings.ini ]"
bash "$SUITE/install.sh" --all > "$T/log7a" 2>&1; rc=$?
check "--all without --uninstall refused" "[ $rc -ne 0 ] && grep -q 'only goes with --uninstall' $T/log7a"
bash "$SUITE/install.sh" --uninstall --all < /dev/null >> "$T/log7" 2>&1; rc=$?
check "without a terminal: refused, nothing removed" "[ $rc -ne 0 ] && grep -q 'needs a terminal' $T/log7 && installed bc250-system-overlay && installed bc250-bazzite-suite"
printf 'n\n' | BC250_INTERACTIVE=1 bash "$SUITE/install.sh" --uninstall --all >> "$T/log7" 2>&1; rc=$?
check "no: canceled, nothing removed" "[ $rc -eq 1 ] && grep -q 'Canceled: nothing was uninstalled.' $T/log7 && installed bc250-system-overlay && installed bc250-bios-reader && installed bc250-bazzite-suite"
check "the warning names every app" "grep -q 'WARNING: --all removes the whole suite from this computer: System Overlay, BC-250 BIOS Reader, with the portal and Bazzite Test.' $T/log7"
check "asks once, not per app" "grep -q 'Are you sure you want to delete everything permanently?' $T/log7 && ! grep -q 'Uninstall System Overlay?' $T/log7"
printf 'y\n' | BC250_INTERACTIVE=1 bash "$SUITE/install.sh" --uninstall --all --purge >> "$T/log7" 2>&1; rc=$?
check "yes: exit 0" "[ $rc -eq 0 ]"
check "the warning says the settings go too" "grep -q 'WARNING: --purge removes their settings' $T/log7"
check "everything gone, the apps' settings too" "! installed bc250-system-overlay && ! installed bc250-bios-reader && ! installed bc250-bazzite-suite && ! installed bc250-bazzite-test && [ ! -e $XDG_CONFIG_HOME/bc250-system-overlay ] && [ ! -e $D/bc250-bazzite-suite ]"
check "nothing left to mention" "! grep -q 'Still installed' $T/log7"

[ $fail -eq 0 ] && echo "ALL OK" || for l in "${logs[@]}"; do echo "--- $l"; cat "$l"; done
exit $fail
