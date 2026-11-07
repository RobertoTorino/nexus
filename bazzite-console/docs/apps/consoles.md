<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Console Link](../assets/consoles/ps5-console-link.webp){ .app-logo }

# Console Link

Console Link finds PS4 and PS5 consoles on the local network, can wake a console from rest mode, and registers the
client for Remote Play. Registration uses the PSN account ID and the temporary PIN shown by the console. Use the
connection and stream checks before starting a session; network quality and console firmware affect the result.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/consoles/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/consoles/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/consoles/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-console-link`; the app runs on the suite's shared Python environment.

## Use it

Sign in to PSN to fill in the account ID, select a discovered console, and follow its on-screen steps to register.
After registration, select the console and start a session or stream. The registration keys are stored in
`~/.config/ps5-console-link/consoles.json` with owner-only permissions. Remove a console in the app to delete its
local keys; removing the app with `--purge` also deletes them, but does not unlink the client from the console.

Console Link is an independent Remote Play client, not a Sony-certified app. Actual console registration and stream
compatibility depend on the console, firmware, and network.
