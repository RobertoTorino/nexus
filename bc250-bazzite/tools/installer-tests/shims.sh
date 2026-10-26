#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Shims for running the suite installers without root or network (CI, WSL). Usage: source shims.sh <root>
# sudo becomes fakeroot (chown root:root is faked); python3 -m venv makes a stub venv whose pip (python -m pip
# or bin/pip) does nothing.
# Needs fakeroot. Everything happens under <root>: HOME, XDG folders and the /opt and /var/log replacements.
set -e
ROOT=$1
rm -rf "$ROOT"; mkdir -p "$ROOT/shims" "$ROOT/home/Desktop" "$ROOT/opt"
cat > "$ROOT/shims/sudo" <<'X'
#!/bin/sh
# Pretend root: chown root:root is faked, files stay the test user's.
exec fakeroot -- "$@"
X
cat > "$ROOT/shims/python3" <<'X'
#!/bin/sh
# Real python3, except: venv/ensurepip check passes, and "-m venv DIR" makes a stub venv.
case "$*" in
  *"import venv, ensurepip"*) exit 0 ;;
  "-m venv "*) d=$3; mkdir -p "$d/bin"; cat > "$d/bin/python" <<'Y'
#!/bin/sh
# stub venv python: pip installs and import checks succeed without doing anything, as long as every
# requirements file given with -r is there (pip itself would stop on a missing one).
if [ "$1 $2" = "-m pip" ]; then
    prev=
    for a in "$@"; do
        if [ "$prev" = -r ] && [ ! -f "$a" ]; then echo "ERROR: Could not open requirements file: $a" >&2; exit 1; fi
        prev=$a
    done
fi
case "$1" in -m|-c) exit 0 ;; esac
exec /usr/bin/python3 "$@"
Y
     chmod +x "$d/bin/python"
     # pip called directly (the compute installers): the same as "python -m pip".
     printf '#!/bin/sh\nexec "$(dirname "$0")/python" -m pip "$@"\n' > "$d/bin/pip"
     chmod +x "$d/bin/pip"; exit 0 ;;
esac
exec /usr/bin/python3 "$@"
X
chmod +x "$ROOT/shims/"*
export PATH="$ROOT/shims:$PATH" HOME="$ROOT/home" XDG_DATA_HOME="$ROOT/home/.local/share" \
       XDG_CONFIG_HOME="$ROOT/home/.config" BC250_OPT_DIR="$ROOT/opt" BC250_LOG_DIR="$ROOT/log"
