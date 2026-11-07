<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Install

The portal is the installer and launcher for the Bazzite Console Suite. It installs the required Bazzite Test app
with it.

## Install from a checkout

From the repository root on the target Bazzite system, run:

```bash
bash bazzite-console/install.sh
```

The installer is for the logged-in user; do not run it with `sudo`.

## Install a release

Download the Bazzite Console Suite portal release and its `SHA256SUMS` from the Nexus repository's Releases page.
Check the archive against the checksum file, extract it, and run `./install.sh` from the extracted folder.
