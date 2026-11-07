#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/portal/install.sh" "$@"
