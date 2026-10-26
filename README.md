<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# Nexus

One home for the suites: one repository holding every suite, the code they share, and the tools that test and
release them. A suite is the apps for one operating system on one kind of device; its portal installs, opens, updates
and removes them, and each suite has its own wiki. The name, the structure and how the suites relate:
**[the Nexus page](https://robertotorino.github.io/nexus/)**.

## The suites

- **[BC250 Bazzite Suite](bc250-bazzite/)**: tools for the AMD BC-250 running Bazzite, in `bc250-bazzite/`. Its
  [README](bc250-bazzite/README.md) says how to install the portal and lists the apps;
  [its wiki](https://robertotorino.github.io/nexus/bc250-bazzite-suite/) is the manual.

## The structure

Every suite sits in a folder of its own, with its `apps/`, its `portal/` (the manifest of pinned releases and the
installer), its wiki in `docs/`, its icons and its own tools. The root holds what they share: `core/`, the Python
code bundled into every app at release time, `tools/`, the release and CI tools, `dev/`, the development apps of
Nexus itself (Nexus Releases, the release front end, on every suite's portal), `test.sh`, which runs every test
suite, and `nexus/`, the Nexus page. Each suite's rules are in its folder's `CLAUDE.md`; the repository's are in the
root's.

## License

GPL-3.0-or-later ([LICENSE](LICENSE)) for every suite. The exceptions are a suite's own (an app ported from another
project under its license) and are listed in that suite's README; each app keeps its own `LICENSE`.

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite /
Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other programs the
apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3,
PS2, PSP, PS Vita, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud Gaming and Windows are
Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's consoles, of the emulators
(shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their owners. The
suites use them only to say what their apps work with.
