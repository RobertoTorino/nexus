<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Nexus Releases

The release front end of Nexus: it writes the versions, CHANGELOG entries, pins and portal bump of a release of a
suite in the repository (a suite chooser when the checkout holds several), and runs the board checks of a portal
release. It edits the checkout it lives in, so it is not part of a portal's releases and has none of its own.
Committing, tagging and pushing stay with you.

How to use it: [The release front end in the BC250 Bazzite Suite's wiki](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#the-release-front-end).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
