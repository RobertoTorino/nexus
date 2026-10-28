<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-8b4fd8)
[![CI](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

# PCSX2 Manager

Plays PS2 games on the **AMD BC-250** on **Bazzite** with [PCSX2](https://pcsx2.net): installs the PCSX2 release it
was tried with and sets it up, takes your PS2 BIOS, finds your games and adds them to Steam, so a game starts
straight away, on the desktop or from Steam's Big Picture Mode. Everything about PCSX2 is done in the app, without
PCSX2's own window: its settings, each game's screen, and the memory cards (import, export, copy, delete, new
cards, format, check and the slot each is in). A log keeps what the app did.

How to install and use it: [PCSX2 Manager in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/pcsx2/).

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite
/ Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other programs the
apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3,
PS2, PSP, PS Vita, PSN, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud Gaming, Game Pass and
Windows are Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's consoles, of the
emulators (shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their
owners. The suites use them only to say what their apps work with.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). PCSX2 is a separate program (GPL-3.0), downloaded from its own release.
The memory card code in `pcsx2_manager/mymc` is from [mymc++](https://github.com/Adubbz/mymcplusplus)
(GPL-3.0-or-later) by Adubbz, based on mymc+ by Florian Märkl and mymc by Ross Ridge.
