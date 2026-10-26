#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the BC250 Bazzite Suite from this checkout, for testing: the portal and BC-250 Bazzite Test, as
# portal/install.sh does. The installed portal then installs the other apps from this checkout as well, so keep
# the checkout where it is. Same options as portal/install.sh:
#
#   ./install.sh                         # install or update
#   ./install.sh --no-desktop-shortcut   # app menu entries only, no icons on the Desktop
#   ./install.sh --uninstall             # remove the portal, Bazzite Test and (asked per app) the other apps;
#                                        # keeps settings and results
#   ./install.sh --uninstall --purge     # also remove settings, history and results
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/portal/install.sh" "$@"
