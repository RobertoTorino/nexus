<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Dependency Checker](../assets/package/bc250-dependency-checker.webp){ .app-logo }

# Dependency Checker

Dependency Checker lists the Python packages and external tools of the BC250 Bazzite Suite's apps, and which
apps and features use them. On top, it shows whether a Bazzite update waits for you, and it reminds you of one every
week.

**Bazzite**, the first card, shows the Bazzite image the board runs (its version and build date), whether a newer
one is installed and waits for a reboot, and when Bazzite's updater last ran. That updater, `uupd`, runs every night
by itself and updates the image, Flatpaks, Homebrew and distroboxes; a new image takes effect at the next boot, so
an update can wait unnoticed for days. The card turns to **Reboot to update** then: restart the board to use it.
It also warns when the updater failed on its last run or has not run for over a week. The checker only reads this
(from `rpm-ostree status` and `systemctl`, without root or the network); installing updates stays Bazzite's.

**The weekly reminder:** every Monday at about 10:00 (or at the next login, when the board was off then) a desktop
notification says so when an update waits for a reboot, or when the updater failed or stopped running. When all is
well it says nothing. It is a systemd user timer, `bc250-bazzite-update-reminder.timer`, that the installer adds and
`--uninstall` removes; to switch it off yourself, run `systemctl --user disable --now
bc250-bazzite-update-reminder.timer`. `bc250-portal-dependency-checker --bazzite-reminder` does the same check once,
from a terminal.

**Python packages** are checked where each app runs: the checker finds every installed app by its launcher and
reads the package versions in that app's Python environment (the suite's shared one, or the app's own). A card
shows the version in each environment, whether it meets the app's requirement, and the latest version on PyPI.
A package that no installed app uses is shown as **Not needed**.

Each installed version is also looked up in [OSV.dev](https://osv.dev), the open vulnerability database that
collects the GitHub, PyPA and NVD advisories. A green **✓ CVE** means no known vulnerability; a red **✗ CVE** lists
each one by its CVE ID, linked to [Snyk's vulnerability database](https://security.snyk.io/), with the release that
fixes it. **CVE ?** means the check could not run (no network) or no installed app has the package. The external
tools are not looked up: they come with Bazzite and its updates, or from their makers, and OSV.dev has no
reliable record of those builds. Keeping Bazzite's own packages up to date is Bazzite's job, done by the updates
the Bazzite card shows; the checker lists a system tool only because one of the suite's apps uses it.

**External tools** are checked for availability only, on your PATH and in `~/.local/bin` and Homebrew, where the
apps also look. Each app says whether it needs the tool (required) or uses it when it is there (optional); the
links open the app's manual, which says how to install it. Tools that do their work only as root are marked
**Needs root.**; the apps run them through sudo or pkexec, which ask for your password. Where a tool has two
forms, one is enough: Bazzite Test's internet speed test runs Ookla's `speedtest` or `speedtest-cli`. A library
that an app brings itself is listed too: Console Link carries FFmpeg inside its native core, so the checker
asks the installed core which FFmpeg version it holds and shows it on the card. When the core does not load (the
system's libva missing, for example), the card says so.

Under a missing package or tool, or one that needs an update, an **Advice** line says what to install and which
features of the installed apps need it.

Click the information button beside a name for what the package or tool is and what each app uses it for. The
line at the bottom names the tools that are not there, those an installed app needs apart from the optional ones.

The checker is read-only. It does not install or update packages or tools. It sends the names and versions of the
Python packages to PyPI and OSV.dev, nothing else.

## What the statuses mean

Each card has one status, the most urgent that applies. The boxes at the top count them.

| Status | For | Meaning |
|---|---|---|
| **Up to date** | package | Installed where the apps need it, at PyPI's latest version, no known vulnerability. |
| **Update available** | package | PyPI has a newer version. Nothing is wrong: the installed one meets the apps' requirements and has no known vulnerability. Newer versions come with an app release, after they are tested. |
| **Needs update** | package | It must be updated: an installed app needs a newer version than the one installed, or a newer release fixes a known vulnerability of it. The status's tooltip and the Advice line say which, and to which version. |
| **Vulnerable** | package | An installed version has a known vulnerability that no release fixes yet. |
| **Wrong version** | package | An installed version does not meet an app's requirement in a way an update does not fix (newer than the app allows). Install that app again from the portal. |
| **Missing** | package | Not in the Python environment of an installed app that uses it. Install that app again from the portal. |
| **Missing** | tool | Not found, and an installed app needs it. |
| **Not installed** | tool | Not found, but the installed apps only use it when it is there: they work without it. It stays so until you install the tool; the app's manual, linked on the card, says how. |
| **Available** | tool | Found; the card shows where (and the version, where the check can read one, as for FFmpeg). |
| **Unsupported build** | tool | Found, but in a form the app cannot use, for example a flashrom without the internal programmer, or a Console Link native core built without its video decoder. |
| **Not needed** | both | No installed app uses it. |
| **Check failed** | package | PyPI could not be reached (no network). |

## Install

In the [portal](../portal.md), open the **Utilities** tab and click the Install button beside its icon. Or by hand:
from the suite's [Releases](https://github.com/RobertoTorino/nexus/releases) page, download the
`package-v<version>.tar.gz` release and extract it. Run `install.sh` as your own user:

```shell
./install.sh
```

It adds an app-menu entry, a Desktop icon and the weekly Bazzite update reminder (in `~/.config/systemd/user`). To
omit the Desktop icon, use `./install.sh --no-desktop-shortcut`. To remove the app and the reminder, run
`./install.sh --uninstall`; add `--purge` to remove its settings too. The app shares the
suite's PyQt6 environment and removes that environment only when no other suite app uses it.

## Run from a checkout

```shell
cd bc250-bazzite/apps/package
PYTHONPATH=../../core ../../.venv-linux/bin/python -m package_checker
```
