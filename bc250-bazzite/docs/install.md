<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<span class="page-icon">:material-tray-arrow-down:</span>

# Install

Install the portal, not the apps one by one: it installs, updates and removes the apps for you. Download
`portal-v<version>.tar.gz` and `SHA256SUMS` from the
[latest portal release](https://github.com/RobertoTorino/nexus/releases/latest), then:

```bash
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf portal-v*.tar.gz && cd portal-v*/ && ./install.sh
```

This installs the portal and BC-250 Bazzite Test. Install the other apps from the portal. The other releases on
the Releases page (`gpu-v…`, `upscaler-v…` and so on) are the app downloads the portal uses; you do not need
them. What goes where and how
to uninstall: [Portal](portal.md).

To test from a clone of the repository instead, run `./install.sh` in its root. The portal then installs every app
from the clone, so keep it where it is. `./install.sh --uninstall` removes it again, and asks about each other
installed app.

What each app does: [The apps](apps/index.md).
