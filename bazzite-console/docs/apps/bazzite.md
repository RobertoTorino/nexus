<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Bazzite Test](../assets/bazzite/bazzite-test.webp){ .app-logo }

# Bazzite Test

Read-only system details for PlayStation 5 hardware running Bazzite.

## Install

Install it from the portal (the **Sustainable** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/bazzite/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/bazzite/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/bazzite/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/bazzite-test`; the app runs on the suite's shared Python environment.

## The window

The header shows the app's state beside its name and a status box under it; **Refresh** reads again.
