<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Nexus Releases

The release front end of Nexus: it writes the versions, CHANGELOG entries, pins and portal bump of a release of a
suite in the repository (a suite chooser when the checkout holds several), and runs the board checks of a portal
release. It edits the checkout it lives in, so it is not part of a portal's releases and has none of its own.
Committing, tagging and pushing stay with you.

## Start it

From the repository's root, with the checkout's venv for the system (see the root CLAUDE.md):

| | Linux | Windows (PowerShell) |
|---|---|---|
| Open it | `tools/release.sh` | `dev\releases\run.ps1` |
| The overview in the terminal | `tools/release.sh --list` | `dev\releases\run.ps1 --list` |
| Menu entry and Desktop icon | `dev/releases/install.sh` | `powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1` |

Both installers take `--no-desktop-shortcut`, `--uninstall` and `--uninstall --purge` (the settings too). Nothing is
copied: the entry starts the app of the checkout you installed it from.

How to use it: [The release front end in the BC250 Bazzite Suite's wiki](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#the-release-front-end).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
