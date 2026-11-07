<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Console LinkB](../assets/clb/ps5-console-linkb.webp){ .app-logo }

# Console LinkB

Console LinkB connects to Xbox consoles for Remote Play and to Xbox Cloud Gaming. It supports account sign-in,
console discovery and wake-up, then starts a stream in the app. Xbox service availability, subscriptions, and
network conditions are determined by Microsoft.

## Install

Install it from the portal (the **Gaming** tab), or from a checkout of the repository:

```bash
bazzite-console/apps/clb/install.sh                         # the app, its launcher, a menu entry and a Desktop icon
bazzite-console/apps/clb/install.sh --no-desktop-shortcut   # without the Desktop icon
bazzite-console/apps/clb/install.sh --uninstall             # remove it; --purge removes its settings too
```

The launcher is `~/.local/bin/ps5-console-linkb`; the app runs on the suite's shared Python environment.

## Use it

Sign in with your Microsoft account, choose an Xbox console or the cloud service, and follow the prompts to connect.
For console Remote Play, the Xbox must be configured for remote features and reachable on your network. Streaming
quality depends on the connection and the Xbox service; it is not guaranteed on every network or region.
