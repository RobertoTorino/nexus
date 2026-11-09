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

## After a Bazzite update to a new Python

The apps run in Python venvs in your home folder. When a Bazzite update brings a new version of Python, a venv made
by the old one no longer finds its packages, and the portal and the apps stop starting. Install the portal again as
above (`bash bazzite-console/install.sh` from the checkout, or `./install.sh` from the release folder): it makes the
venv again. Then reinstall from the portal any app that still does not start (Reinstall in its tile's menu).
