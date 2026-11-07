<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Bazzite DatStation](../assets/datstation/ps5-datstation.webp){ .app-logo }

# Bazzite DatStation

Bazzite DatStation is a PlayStation reference app. Its home page opens a timed quiz, console histories, system
software versions, region-code explanations, user manuals, and PlayStation news. Quiz scores and trophies are kept
in the app.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/datstation/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/datstation/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/datstation/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-datstation`; the app runs on the suite's shared Python environment.

## Use it

Choose a tile on the home page to open a section. The quiz records your results in the app; the manuals and news
open their referenced web pages.
