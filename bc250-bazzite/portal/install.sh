#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the BC250 Bazzite Suite portal and BC-250 Bazzite Test, from the extracted portal release:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entries only, no icons on the Desktop
#   ./install.sh --uninstall             # remove the portal, Bazzite Test and (asked per app) the other apps;
#                                        # keeps settings and results
#   ./install.sh --uninstall --purge     # also remove settings, history and results
#   ./install.sh --uninstall --all       # the whole suite: every other app too, without a question per app,
#                                        # after one confirmation; with --purge their settings go as well
#
# Run it as your own user, not with sudo: only the copies to /opt ask for the sudo password.
#  * /opt/bc250-bazzite-suite-v<version>, root-owned, with /opt/bc250-bazzite-suite pointing at it: the portal,
#    its apps.toml and the bc250_core it was tested with. Older versions are removed.
#  * ~/.local/share/bc250-bazzite-suite/venv: the suite's shared venv with PyQt6 and pygame-ce (the controller of
#    Suite Big Picture Mode), removed with the last suite app that uses it.
#  * ~/.local/bin/bc250-bazzite-suite, an app menu entry and a Desktop icon.
#  * BC-250 Bazzite Test, which the suite always includes, through its own installer (bundled in the release).
# The other apps are installed from the portal, each with its own installer.
set -euo pipefail

APP_ID="bc250-bazzite-suite"
APP_NAME="BC250 Bazzite Suite"
OPT_DIR="${BC250_OPT_DIR:-/opt}"            # override only for testing
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
SUITE_DIR="$DATA_DIR/$APP_ID"
VENV="$SUITE_DIR/venv"
VENV_USERS="$SUITE_DIR/venv-users"
STATE_DIR="$SUITE_DIR/portal"
LAUNCHER="$HOME/.local/bin/$APP_ID"
MENU_ENTRY="$DATA_DIR/applications/$APP_ID.desktop"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
DESKTOP_ICON="$DESKTOP_DIR/$APP_ID.desktop"
LINK="$OPT_DIR/$APP_ID"
BT_ID="bc250-bazzite-test"

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# A release bundles bc250_core and the pinned Bazzite Test; in the suite checkout they live in core/ and apps/.
if [ -d "$SRC/bc250_core" ]; then CORE_SRC="$SRC/bc250_core"; else CORE_SRC="$SRC/../../core/bc250_core"; fi
BT_SRC=""
if [ -d "$SRC/bundled" ]; then
    BT_SRC=$(find "$SRC/bundled" -mindepth 1 -maxdepth 1 -type d -name 'check-v*' | sort -V | tail -1)
fi
BT_TAG=$(basename "${BT_SRC:-local}")
[ -n "$BT_SRC" ] || BT_SRC="$SRC/../apps/check"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

usage() { sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'; }

DESKTOP_SHORTCUT=true
UNINSTALL=false
PURGE=false
ALL=false
for arg in "$@"; do
    case "$arg" in
        --no-desktop-shortcut) DESKTOP_SHORTCUT=false ;;
        --uninstall) UNINSTALL=true ;;
        --purge) PURGE=true ;;
        --all) ALL=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Unknown option: $arg" ;;
    esac
done
$PURGE && ! $UNINSTALL && die "--purge only goes with --uninstall."
$ALL && ! $UNINSTALL && die "--all only goes with --uninstall."

[ "$(id -u)" -ne 0 ] || die "Run this as your own user, not with sudo: the venv and the launcher belong in your home folder."

remove_menu_entries() {
    rm -f "$LAUNCHER" "$MENU_ENTRY" "$DESKTOP_ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true
}

release_venv() {
    rm -f "$VENV_USERS/$APP_ID"
    rmdir "$VENV_USERS" 2>/dev/null || true
    if [ -d "$VENV_USERS" ]; then
        info "Keeping the suite venv: other suite apps still use it ($(ls "$VENV_USERS" | tr '\n' ' '))"
    else
        info "Removing the suite venv"
        rm -rf "$VENV"
    fi
}

# The other suite apps that are installed, one per line: key, name, the folder its uninstaller runs in (empty when
# there is none) and its uninstall commands, tab-separated. Read from the installed portal's apps.toml, the one
# that installed them; the folder is the release the portal kept, or the app staged afresh from the checkout. The
# checkout-only apps ([checkout.<key>]) run their uninstaller in their folder of the checkout. An app this portal no
# longer lists (dropped from the manifest, installed by an earlier portal) is found by the record and release folder
# the portal kept for it, else by its own installed copy (~/.local/share/<app-id>/app or /opt/<app-id>, an install.sh
# with the suite installers' options), and uninstalled with that installer.
installed_apps() {
    local manifest="$SRC/apps.toml" checkout=""
    [ -f "$LINK/apps.toml" ] && manifest="$LINK/apps.toml"
    if [ -f "$LINK/suite-checkout" ]; then checkout=$(cat "$LINK/suite-checkout")
    elif [ -f "$SRC/../../tools/stage_app.py" ]; then checkout=$(cd "$SRC/../.." && pwd -P); fi   # <checkout>/bc250-bazzite/portal
    python3 - "$manifest" "$STATE_DIR" "$checkout" "$1" "$DATA_DIR" "$OPT_DIR" "$APP_ID" "$BT_ID" <<'PY'
import json, os, re, subprocess, sys, tomllib
from pathlib import Path
manifest, state, checkout, staging = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
data_dir, opt_dir, own_ids = Path(sys.argv[5]), Path(sys.argv[6]), set(sys.argv[7:9])    # the portal, Bazzite Test
tables = tomllib.loads(manifest.read_text(encoding="utf-8"))
apps, checkout_apps = tables.get("apps", {}), tables.get("checkout", {})
suite = Path(checkout) / "bc250-bazzite" if checkout else None     # the suite's folder in the checkout
try:
    records = json.loads((state / "installed.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    records = {}
records = records if isinstance(records, dict) else {}


def present(paths):
    return any(Path(os.path.expandvars(os.path.expanduser(p))).exists() for p in paths)


def installer_value(folder, name):
    """APP_ID or APP_NAME as the install.sh in *folder* sets it; "" when it does not."""
    try:
        text = (folder / "install.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    found = re.search(rf'^{name}="([^"]*)"', text, re.M)
    return found[1] if found else ""


def row(key, name, folder, commands):
    print("\t".join((key, name, str(folder) if folder else "", commands)))


def suite_installer(folder):
    """Whether *folder* holds a suite app's install.sh: one with the options every suite installer has."""
    try:
        text = (folder / "install.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "--no-desktop-shortcut)" in text and "--uninstall)" in text and "not with sudo" in text


app_ids = set()                         # the ids of the apps this portal lists: their launchers' names
for key, app in apps.items():
    app_ids |= {Path(p).name for p in app.get("detect", [])}
    if app.get("required") or not present(app.get("detect", [])):
        continue
    # The portal keeps releases/<tag> (from a release) or releases/local-<key> (from the checkout).
    kept = [state / "releases" / name for name in (records.get(key, ""), "local-" + key, app.get("tag", ""))
            if name and name != "local"]
    folder = next((f for f in kept if f.is_dir()), None)
    if folder is None and suite and (suite / "apps" / key).is_dir():
        dest = staging / key
        if subprocess.run([sys.executable, str(Path(checkout) / "tools" / "stage_app.py"), key, str(dest)],
                          capture_output=True).returncode == 0:
            folder = dest
    row(key, app.get("name", key), folder, " && ".join(app.get("uninstall", [])))

# The checkout-only apps: their folder in the suite's folder of the checkout, when there is one.
for key, app in checkout_apps.items():
    app_ids |= {Path(p).name for p in app.get("detect", [])}
    if not present(app.get("detect", [])):
        continue
    folder = suite / app.get("folder", f"apps/{key}") if suite else None
    row(key, app.get("name", key), folder if folder and folder.is_dir() else None,
        " && ".join(app.get("uninstall", ["bash install.sh --uninstall"])))

# Apps this portal no longer lists: first by the record and release folder kept for them ...
found_ids = set()
releases = state / "releases"
candidates = {key: tag for key, tag in records.items() if key not in apps and key not in checkout_apps}
if releases.is_dir():
    for path in releases.iterdir():
        match = re.match(r"^(.+)-v\d+\.\d+\.\d+$", path.name)
        key = match[1] if match else path.name.removeprefix("local-")
        if key not in apps and key not in checkout_apps and key not in candidates:
            candidates[key] = path.name
for key, tag in sorted(candidates.items()):
    folder = releases / (f"local-{key}" if tag == "local" else tag)
    app_id = installer_value(folder, "APP_ID")
    if (not app_id or app_id in own_ids or app_id in app_ids or not folder.is_dir()
            or not present([str(data_dir / app_id / "app"), str(opt_dir / app_id), f"~/.local/bin/{app_id}"])):
        continue
    found_ids.add(app_id)
    row(key, installer_value(folder, "APP_NAME") or key, folder, "bash install.sh --uninstall")
# ... else by their own installed copy: the places the suite's installers copy an app to.
copies = [p / "app" for p in data_dir.iterdir() if p.is_dir()] if data_dir.is_dir() else []
copies += [p for p in opt_dir.iterdir() if p.is_dir()] if opt_dir.is_dir() else []
for folder in sorted(copies):
    app_id = installer_value(folder, "APP_ID")
    if not app_id or app_id in own_ids or app_id in app_ids or app_id in found_ids or not suite_installer(folder):
        continue
    found_ids.add(app_id)
    row(app_id, installer_value(folder, "APP_NAME") or app_id, folder, "bash install.sh --uninstall")
PY
}

# Asks about every other installed suite app before anything is removed: uninstall it, skip it, or cancel the
# whole uninstall. Without a terminal nothing is asked and the apps stay, as they are named at the end. With --all,
# one confirmation instead, then every app goes (with --purge, their settings too); it needs a terminal.
uninstall_other_apps() {
    local staging list key name folder commands answer names
    local -a chosen=() failed=()
    staging=$(mktemp -d)
    list=$(installed_apps "$staging") || die "Could not read the list of installed apps."
    if $ALL && [ -n "$list" ]; then
        { [ -t 0 ] || [ -n "${BC250_INTERACTIVE:-}" ]; } || die "--all needs a terminal to confirm; nothing was uninstalled."
        names=$(cut -f2 <<<"$list" | paste -sd, - | sed 's/,/, /g')
        info "WARNING: --all removes the whole suite from this computer: $names, with the portal and Bazzite Test."
        $PURGE && info "WARNING: --purge removes their settings, history and results as well."
        printf "Are you sure you want to delete everything permanently? [y/N] "
        read -r answer || answer=n
        case "${answer,,}" in
            y|yes) ;;
            *) rm -rf "$staging"; info "Canceled: nothing was uninstalled."; exit 1 ;;
        esac
        mapfile -t chosen < <(cut -f1 <<<"$list")
    elif [ -n "$list" ] && { [ -t 0 ] || [ -n "${BC250_INTERACTIVE:-}" ]; }; then   # BC250_INTERACTIVE: tests only
        info "Other suite apps are installed. For each: y = uninstall it, s = skip it (keep it), c = cancel."
        while IFS=$'\t' read -r key name folder commands <&3; do
            while true; do
                printf "Uninstall %s? [y/s/c] " "$name"
                read -r answer || answer=c
                case "${answer,,}" in
                    y|yes) chosen+=("$key"); break ;;
                    s|skip) break ;;
                    c|cancel) rm -rf "$staging"; info "Canceled: nothing was uninstalled."; exit 1 ;;
                esac
            done
        done 3<<<"$list"
    fi
    while IFS=$'\t' read -r key name folder commands; do
        [ -n "$key" ] && [[ " ${chosen[*]} " == *" $key "* ]] || continue
        if [ -z "$folder" ]; then
            info "No uninstaller found for $name: remove it with its own install.sh --uninstall."
            failed+=("$name")
            continue
        fi
        info "Uninstalling $name"
        # --all --purge: the apps' own --purge too (the commands that are an install.sh --uninstall take it).
        $ALL && $PURGE && commands=$(sed 's/ --uninstall\( \|$\)/ --uninstall --purge\1/g' <<<"$commands")
        if (cd "$folder" && bash -c "$commands"); then
            forget_app "$key" "$folder"
        else
            info "The uninstall of $name failed; see above."
            failed+=("$name")
        fi
    done <<<"$list"
    rm -rf "$staging"
    [ ${#failed[@]} -eq 0 ] || info "Not uninstalled: ${failed[*]}"
    if $PURGE && [ ${#chosen[@]} -gt 0 ] && ! $ALL; then
        info "Their own settings are kept: --purge applies to the portal and Bazzite Test (with --all, to every app)."
    fi
}

# Like the portal after an uninstall: drop the app from installed.json and the release folder it kept.
forget_app() {
    case "$2" in "$STATE_DIR"/releases/*) rm -rf "$2" ;; esac
    [ -f "$STATE_DIR/installed.json" ] || return 0
    python3 - "$STATE_DIR/installed.json" "$1" <<'PY'
import json, sys
from pathlib import Path
path, key = Path(sys.argv[1]), sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)
if isinstance(data, dict) and data.pop(key, None) is not None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
PY
}

# After the uninstall without --purge: keep only what an app that is still installed needs (its record and the
# release folder its uninstaller runs from); records and folders of apps that are gone, and Bazzite Test's, go.
# With nothing left, the portal's state folder goes too.
prune_state() {
    local manifest="$SRC/apps.toml"
    [ -f "$LINK/apps.toml" ] && manifest="$LINK/apps.toml"
    [ -d "$STATE_DIR" ] || return 0
    python3 - "$manifest" "$STATE_DIR" <<'PY'
import json, os, re, shutil, sys, tomllib
from pathlib import Path
manifest, state = Path(sys.argv[1]), Path(sys.argv[2])
apps = tomllib.loads(manifest.read_text(encoding="utf-8")).get("apps", {})
try:
    records = json.loads((state / "installed.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    records = {}
records = records if isinstance(records, dict) else {}
def installed(key):
    app = apps.get(key)
    if app is None:
        return True                     # not in this portal's list: unknown, so kept
    return not app.get("required") and any(Path(os.path.expandvars(os.path.expanduser(p))).exists()
                                           for p in app.get("detect", []))
records = {k: v for k, v in records.items() if installed(k)}
keep = {f"local-{k}" if v == "local" else v for k, v in records.items()}
releases = state / "releases"
if releases.is_dir():
    for path in releases.iterdir():
        match = re.match(r"^(.+)-v\d+\.\d+\.\d+$", path.name)
        key = match[1] if match else path.name.removeprefix("local-")
        if path.name not in keep and (key in apps or key not in records):
            shutil.rmtree(path, ignore_errors=True)
if records:
    tmp = state / "installed.tmp"
    tmp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(state / "installed.json")
else:
    shutil.rmtree(state, ignore_errors=True)
PY
}

if $UNINSTALL; then
    uninstall_other_apps
    if [ -f "$OPT_DIR/$BT_ID/install.sh" ]; then
        info "Uninstalling BC-250 Bazzite Test"
        bt_args=(--uninstall)
        $PURGE && bt_args+=(--purge)
        bash "$OPT_DIR/$BT_ID/install.sh" "${bt_args[@]}"
    fi
    $PURGE || prune_state
    info "Removing the portal's launcher and menu entry"
    remove_menu_entries
    info "Removing $LINK and the installed versions (sudo)"
    as_root rm -rf "$LINK" "$OPT_DIR/$APP_ID"-v*
    release_venv
    if $PURGE; then
        info "Removing the portal's settings and state"
        rm -rf "${STATE_DIR:?}" "${CONFIG_DIR:?}/$APP_ID"
    fi
    rmdir "$SUITE_DIR" 2>/dev/null || true             # nothing of the suite left in it
    others=""
    if [ -d "$VENV_USERS" ]; then others=$(ls "$VENV_USERS" | tr '\n' ' '); fi
    [ -z "$others" ] || info "Still installed: $others- remove them with their own uninstallers (or reinstall the portal)."
    info "$APP_NAME is uninstalled."
    exit 0
fi

# --- Checks ------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "This app runs on Linux (Bazzite) only."
for f in apps.toml requirements.txt bc250_portal/__init__.py bc250_portal/__main__.py; do
    [ -f "$SRC/$f" ] || die "$f is missing: run install.sh from the extracted release folder."
done
[ -f "$CORE_SRC/__init__.py" ] || die "bc250_core is missing: run install.sh from the extracted release folder."
CORE_SRC=$(cd "$CORE_SRC" && pwd -P)
[ -f "$BT_SRC/install.sh" ] || die "BC-250 Bazzite Test is missing: run install.sh from the extracted release folder."
VERSION=$(sed -n 's/^__version__ = "\([0-9.]*\)"$/\1/p' "$SRC/bc250_portal/__init__.py")
[ -n "$VERSION" ] || die "Could not read the version from bc250_portal/__init__.py."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "Python 3.11 or newer is needed."
python3 -c 'import venv, ensurepip' 2>/dev/null || die "python3 has no venv/ensurepip module."

TARGET="$OPT_DIR/$APP_ID-v$VERSION"
info "Installing $APP_NAME $VERSION"

# --- 1. Root-owned copy in /opt -----------------------------------------------------------------
if [ "$SRC" = "$(cd "$TARGET" 2>/dev/null && pwd -P)" ]; then
    info "Already running from $TARGET, no copy needed"
else
    info "Copying to $TARGET (sudo)"
    STAGE="$OPT_DIR/.$APP_ID-v$VERSION.new"
    as_root rm -rf "$STAGE"
    as_root mkdir -p "$STAGE"
    # Plain copy, no -a: the files get /opt's default SELinux label instead of the Downloads one. The bundled
    # Bazzite Test is installed by its own installer below, so it is not part of the portal's copy.
    (cd "$SRC" && tar --exclude='./bundled' --exclude='./tests' --exclude='./.git' --exclude='__pycache__' \
        --exclude='./requirements-dev.txt' -cf - .) | as_root tar -xf - -C "$STAGE" --no-same-owner
    if [ "$CORE_SRC" != "$SRC/bc250_core" ]; then         # from the checkout: bundle core like a release
        as_root mkdir -p "$STAGE/bc250_core"
        (cd "$CORE_SRC" && tar --exclude='__pycache__' -cf - .) |
            as_root tar -xf - -C "$STAGE/bc250_core" --no-same-owner
        # The installed portal installs the other apps from this checkout too, as when it runs from here: the
        # repository, two levels up from <checkout>/bc250-bazzite/portal.
        (cd "$SRC/../.." && pwd -P) | as_root tee "$STAGE/suite-checkout" >/dev/null
    fi
    as_root chown -R root:root "$STAGE"
    as_root find "$STAGE" -type d -exec chmod 755 {} +
    as_root find "$STAGE" -type f -exec chmod go-w,a+r {} +
    as_root rm -rf "$TARGET"
    as_root mv "$STAGE" "$TARGET"
    command -v restorecon >/dev/null 2>&1 && as_root restorecon -R "$TARGET" 2>/dev/null || true
fi
as_root ln -sfn "$(basename "$TARGET")" "$LINK"
for old in "$OPT_DIR/$APP_ID"-v*; do
    [ -d "$old" ] && [ "$old" != "$TARGET" ] || continue
    info "Removing the previous version $(basename "$old")"
    as_root rm -rf "$old"
done

# --- 2. Shared suite venv with PyQt6 and pygame-ce ------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    info "Creating the suite venv in $VENV"
    rm -rf "$VENV"
    mkdir -p "$SUITE_DIR"
    python3 -m venv "$VENV"
fi
mkdir -p "$VENV_USERS"
touch "$VENV_USERS/$APP_ID"
info "Installing PyQt6 and pygame-ce into the venv (downloads ~110 MB the first time)"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$LINK/requirements.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets' || die "PyQt6 does not load from the venv."

# --- 3. Launcher, menu entry, Desktop icon ------------------------------------------------------
info "Creating the launcher $LAUNCHER"
mkdir -p "$(dirname "$LAUNCHER")"
cat >"$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $APP_NAME launcher, written by install.sh. Starts from the root-owned portal folder, so Python imports the
# portal and the bc250_core bundled there, never a copy from the current directory.
cd "$LINK" || { echo "$APP_NAME is not installed in $LINK; run install.sh again." >&2; exit 1; }
exec "$VENV/bin/python" -m bc250_portal "\$@"
EOF
chmod 755 "$LAUNCHER"

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=BC-250 tools
Comment=Install and start the BC-250 tools for Bazzite
Exec=$LAUNCHER
Icon=$LINK/images/$APP_ID-128.png
Terminal=false
Categories=System;Settings;
Keywords=BC-250;Bazzite;suite;portal;
StartupNotify=true
StartupWMClass=$APP_ID"

info "Adding the app menu entry"
mkdir -p "$(dirname "$MENU_ENTRY")"
printf '%s\n' "$DESKTOP_FILE_CONTENT" >"$MENU_ENTRY"
chmod 644 "$MENU_ENTRY"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$DATA_DIR/applications" || true

if $DESKTOP_SHORTCUT && [ -d "$DESKTOP_DIR" ]; then
    info "Adding the Desktop icon"
    printf '%s\n' "$DESKTOP_FILE_CONTENT" >"$DESKTOP_ICON"
    # KDE and GNOME only start Desktop launchers that are executable (GNOME also wants them trusted).
    chmod 755 "$DESKTOP_ICON"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_ICON" metadata::trusted true 2>/dev/null || true
elif ! $DESKTOP_SHORTCUT; then
    rm -f "$DESKTOP_ICON"
fi

# --- 4. BC-250 Bazzite Test, always part of the suite -------------------------------------------
info "Installing BC-250 Bazzite Test ($BT_TAG)"
bt_args=()
$DESKTOP_SHORTCUT || bt_args+=(--no-desktop-shortcut)
bash "$BT_SRC/install.sh" "${bt_args[@]}"
# Tell the portal which Bazzite Test it installed ("local" from a checkout), as it does for apps it installs.
mkdir -p "$STATE_DIR"
python3 - "$STATE_DIR/installed.json" "check" "$BT_TAG" <<'PY'
import json, sys
from pathlib import Path
path, key, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = data if isinstance(data, dict) else {}
except (OSError, ValueError):
    data = {}
data[key] = tag
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(path)
PY

info "Done. Start \"$APP_NAME\" from the app menu$($DESKTOP_SHORTCUT && echo ' or the Desktop'), or run: $APP_ID"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) info "Note: ~/.local/bin is not on your PATH, so the terminal command needs the full path: $LAUNCHER" ;; esac
# A portal window that is still open keeps running the old version, and starting the portal again only brings that
# window to the front: say so.
if command -v pgrep >/dev/null 2>&1 && pgrep -u "$(id -u)" -f -- '-m bc250_portal' >/dev/null 2>&1; then
    info "A $APP_NAME window is still open with the version from before: close it, then start it again."
fi
